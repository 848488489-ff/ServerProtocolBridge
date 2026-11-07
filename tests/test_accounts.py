"""Tests for account management: the on-disk store, the Yggdrasil flow, the
Microsoft wrappers around mcauth3 and session joins.

The network layer and the mcauth3 client are patched out
(``accounts_auth._request_json`` / ``accounts_auth.MCMSA`` -- the auth
backends live in ``proxy.accounts_auth``, which is where the code reads
those names); the store tests point ``SPB_DATA_DIR`` at a temporary
directory so nothing ever touches the real user data folder.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proxy import accounts, accounts_auth  # noqa: E402
from proxy.i18n import tr  # noqa: E402

PROFILE_ID = '0f0e0d0c0b0a09080706050403020100'


class TempDataMixin:
    """Point the standard data directory at a scratch folder for one test."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env_patch = unittest.mock.patch.dict(
            os.environ, {'SPB_DATA_DIR': self.temp.name})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.temp.cleanup()


class StoreTests(TempDataMixin, unittest.TestCase):
    def test_store_roundtrip_and_selection(self):
        first = accounts.add_account(
            accounts.Account(kind=accounts.KIND_OFFLINE, username='Steve'))
        self.assertTrue(first.id)
        second = accounts.add_account(accounts.Account(
            kind=accounts.KIND_MICROSOFT, username='Alex', uuid=PROFILE_ID,
            refresh_token='refresh-token'))
        accounts.set_active(second.id)

        store = accounts.load_store()
        self.assertEqual([item.username for item in store.accounts], ['Steve', 'Alex'])
        self.assertEqual(store.active, second.id)
        self.assertEqual(accounts.active_account().username, 'Alex')
        self.assertEqual(accounts.find_account('alex').id, second.id)
        self.assertEqual(accounts.find_account(second.id).id, second.id)

        # accounts.json sits in the data directory, not next to the program
        self.assertEqual(accounts.store_path().parent, Path(self.temp.name))
        payload = json.loads(accounts.store_path().read_text(encoding='utf-8'))
        self.assertEqual(payload['active'], second.id)
        self.assertEqual(payload['accounts'][1]['kind'], 'microsoft')

        self.assertTrue(accounts.remove_account(second.id))
        self.assertEqual(accounts.load_store().active, '')
        self.assertFalse(accounts.remove_account('nope'))

    def test_set_active_ignores_unknown_ids(self):
        accounts.add_account(accounts.Account(kind=accounts.KIND_OFFLINE, username='Steve'))
        accounts.set_active('missing')
        self.assertEqual(accounts.load_store().active, '')

    def test_broken_store_reads_as_empty(self):
        accounts.store_path().write_text('{not json', encoding='utf-8')
        store = accounts.load_store()
        self.assertEqual(store.accounts, [])
        self.assertIsNone(accounts.active_account())

    def test_uuid_parsing(self):
        account = accounts.Account(uuid='0F0E0D0C-0B0A-0908-0706-050403020100')
        self.assertEqual(account.uuid_bytes, bytes.fromhex(PROFILE_ID))
        self.assertIsNone(accounts.Account(uuid='').uuid_bytes)
        self.assertIsNone(accounts.Account(uuid='zz').uuid_bytes)

    def test_account_json_roundtrip(self):
        account = accounts.Account(kind=accounts.KIND_THIRDPARTY, id='x1',
                                   username='Steve', uuid=PROFILE_ID,
                                   authserver='https://a.invalid', password='pw',
                                   access_token='tok', client_token='ct',
                                   refresh_token='rt', token_expires=123.5)
        restored = accounts.Account.from_json(json.loads(json.dumps(account.to_json())))
        self.assertEqual(restored, account)
        fallback = accounts.Account.from_json({'kind': 'martian'})
        self.assertEqual(fallback.kind, accounts.KIND_OFFLINE)


class ThirdPartyTests(TempDataMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.calls = []

    def route_json(self, responses):
        def call(url, payload=None, headers=None, timeout=None):
            self.calls.append((url, payload))
            for key, value in responses.items():
                if url.endswith(key):
                    if isinstance(value, Exception):
                        raise value
                    return value
            raise AssertionError('unexpected URL %s' % url)
        return call

    def test_authenticate_builds_an_account(self):
        responses = {
            '/authserver/authenticate': {
                'accessToken': 'access-1', 'clientToken': 'client-1',
                'selectedProfile': {'name': 'Steve', 'id': PROFILE_ID}},
        }
        with unittest.mock.patch.object(accounts_auth, '_request_json',
                                        self.route_json(responses)):
            account = accounts.thirdparty_authenticate(
                'https://auth.example.com/api/yggdrasil', 'steve@example.com', 'hunter2')
        self.assertEqual(account.kind, accounts.KIND_THIRDPARTY)
        self.assertEqual(account.username, 'Steve')
        self.assertEqual(account.uuid, PROFILE_ID)
        self.assertEqual(account.access_token, 'access-1')
        self.assertEqual(account.password, 'hunter2')
        url, payload = self.calls[0]
        self.assertEqual(url,
                         'https://auth.example.com/api/yggdrasil/authserver/authenticate')
        self.assertEqual(payload['agent'], {'name': 'Minecraft', 'version': 1})
        self.assertTrue(payload['clientToken'])

    def test_bad_url_and_missing_profile_are_reported(self):
        with self.assertRaises(accounts.AccountError):
            accounts.thirdparty_authenticate('auth.example.com', 'a', 'b')
        responses = {'/authserver/authenticate': {'accessToken': 'x'}}
        with unittest.mock.patch.object(accounts_auth, '_request_json',
                                        self.route_json(responses)):
            with self.assertRaises(accounts.AccountError):
                accounts.thirdparty_authenticate('https://x.invalid', 'a', 'b')

    def test_ensure_token_falls_back_to_the_password(self):
        account = accounts.Account(kind=accounts.KIND_THIRDPARTY, username='Steve',
                                   uuid=PROFILE_ID, authserver='https://x.invalid',
                                   access_token='old', client_token='c1', password='pw')
        responses = {
            '/authserver/validate': accounts.AccountError('invalid'),
            '/authserver/refresh': accounts.AccountError('invalid'),
            '/authserver/authenticate': {
                'accessToken': 'new', 'clientToken': 'c2',
                'selectedProfile': {'name': 'Steve', 'id': PROFILE_ID}},
        }
        with unittest.mock.patch.object(accounts_auth, '_request_json',
                                        self.route_json(responses)):
            accounts.thirdparty_ensure_token(account)
        self.assertEqual(account.access_token, 'new')
        self.assertEqual(account.client_token, 'c2')

    def test_ensure_token_without_password_needs_a_new_login(self):
        account = accounts.Account(kind=accounts.KIND_THIRDPARTY, username='Steve',
                                   uuid=PROFILE_ID, authserver='https://x.invalid',
                                   access_token='old', client_token='c1')
        responses = {
            '/authserver/validate': accounts.AccountError('invalid'),
            '/authserver/refresh': accounts.AccountError('invalid'),
        }
        with unittest.mock.patch.object(accounts_auth, '_request_json',
                                        self.route_json(responses)):
            with self.assertRaises(accounts.AccountError) as ctx:
                accounts.thirdparty_ensure_token(account)
        self.assertEqual(str(ctx.exception), tr('accounts.error.need_login'))

    def test_join_posts_to_the_session_endpoint(self):
        account = accounts.Account(kind=accounts.KIND_THIRDPARTY, username='Steve',
                                   uuid=PROFILE_ID, authserver='https://x.invalid',
                                   access_token='tok', client_token='c')
        posts = []

        def call(url, payload=None, headers=None, timeout=None):
            posts.append((url, payload))
            if url.endswith('/authserver/validate') or url.endswith('/join'):
                return {}
            raise AssertionError('unexpected URL %s' % url)

        with unittest.mock.patch.object(accounts_auth, '_request_json', call), \
                unittest.mock.patch.object(accounts, '_request_json', call):
            accounts.join_session(account, 'f' * 40)
        self.assertEqual(posts[-1][0],
                         'https://x.invalid/sessionserver/session/minecraft/join')
        self.assertEqual(posts[-1][1], {
            'accessToken': 'tok', 'selectedProfile': PROFILE_ID, 'serverId': 'f' * 40})

    def test_join_hash_matches_the_formula(self):
        secret = bytes(range(16))
        key_der = b'\x30\x82fake'
        expected = hashlib.sha1(b'' + secret + key_der).hexdigest()
        self.assertEqual(accounts.join_hash('', secret, key_der), expected)
        expected = hashlib.sha1('mc.example.com'.encode('utf-8') + secret + key_der).hexdigest()
        self.assertEqual(accounts.join_hash('mc.example.com', secret, key_der), expected)


class FakeMCAuthError(Exception):
    """Stand-in for mcauth3.MCAuthError in the tests."""


class FakeOAuthError(FakeMCAuthError):
    """Stand-in for mcauth3.OAuthError in the tests."""


class FakeMCMSA:
    """Stand-in for mcauth3.MCMSA: hands back canned answers."""

    start = None
    finish = None
    refresh = None
    refresh_error = None

    def start_auth(self):
        return type(self).start

    def finish_auth(self, info):
        return type(self).finish

    def refresh_auth(self, token):
        error = type(self).refresh_error
        if error is not None:
            raise error
        return type(self).refresh


class MicrosoftTests(TempDataMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        FakeMCMSA.start = None
        FakeMCMSA.finish = None
        FakeMCMSA.refresh = None
        FakeMCMSA.refresh_error = None

    def test_device_start_returns_the_library_answer(self):
        info = {'device_code': 'dev-1', 'user_code': 'ABCD-EFGH',
                'verification_uri': 'https://microsoft.com/link'}
        FakeMCMSA.start = info
        with unittest.mock.patch.object(accounts_auth, 'MCMSA', FakeMCMSA):
            self.assertEqual(accounts.microsoft_device_start(), info)

    def test_device_poll_builds_the_account(self):
        FakeMCMSA.finish = {
            'tokens': {'minecraft_access_token': 'mc-token',
                       'microsoft_refresh_token': 'refresh-token',
                       'expires_in': 86400},
            'profile': {'id': PROFILE_ID, 'name': 'Steve'}}
        with unittest.mock.patch.object(accounts_auth, 'MCMSA', FakeMCMSA):
            account = accounts.microsoft_device_poll({'device_code': 'dev-1'})
        self.assertEqual(account.kind, accounts.KIND_MICROSOFT)
        self.assertEqual(account.username, 'Steve')
        self.assertEqual(account.uuid, PROFILE_ID)
        self.assertEqual(account.access_token, 'mc-token')
        self.assertEqual(account.refresh_token, 'refresh-token')
        self.assertGreater(account.token_expires, time.time())

    def test_missing_library_is_reported(self):
        with unittest.mock.patch.object(accounts_auth, 'MCMSA', None), \
                unittest.mock.patch.object(accounts_auth, '_mcauth_attempted', True):
            with self.assertRaises(accounts.AccountError) as ctx:
                accounts.microsoft_device_start()
        self.assertEqual(str(ctx.exception),
                         tr('accounts.ms.library_missing'))

    def test_reused_device_code_gets_a_friendly_error(self):
        error = FakeOAuthError(
            'AADSTS70000: The provided value for the input parameter '
            "'device_code' has already been used.")
        with unittest.mock.patch.object(accounts_auth, 'MCAuthError', FakeMCAuthError):
            failure = accounts._mcauth_failure(error)
        self.assertEqual(failure.code, 'code_used')
        self.assertEqual(str(failure), tr('accounts.ms.code_used'))

    def test_refresh_uses_the_stored_token(self):
        FakeMCMSA.refresh = {
            'tokens': {'minecraft_access_token': 'mc-2',
                       'microsoft_refresh_token': 'new',
                       'expires_in': 86400},
            'profile': {'id': PROFILE_ID, 'name': 'Alex'}}
        account = accounts.Account(kind=accounts.KIND_MICROSOFT, username='Steve',
                                   uuid=PROFILE_ID, refresh_token='old')
        with unittest.mock.patch.object(accounts_auth, 'MCMSA', FakeMCMSA):
            accounts.microsoft_refresh(account)
        self.assertEqual(account.refresh_token, 'new')
        self.assertEqual(account.username, 'Alex')
        self.assertEqual(account.access_token, 'mc-2')

    def test_refresh_recognises_a_dead_refresh_token(self):
        account = accounts.Account(kind=accounts.KIND_MICROSOFT, username='Steve',
                                   uuid=PROFILE_ID, refresh_token='old')
        FakeMCMSA.refresh_error = FakeOAuthError(
            'invalid_grant: the refresh token is not valid')
        with unittest.mock.patch.object(accounts_auth, 'MCMSA', FakeMCMSA), \
                unittest.mock.patch.object(accounts_auth, 'MCAuthError', FakeMCAuthError), \
                unittest.mock.patch.object(accounts_auth, 'OAuthError', FakeOAuthError):
            with self.assertRaises(accounts.AccountError) as ctx:
                accounts.microsoft_refresh(account)
        self.assertEqual(str(ctx.exception),
                         tr('accounts.ms.refresh_failed',
                            error=tr('accounts.error.need_login')))

    def test_join_refreshes_before_the_first_request(self):
        account = accounts.Account(kind=accounts.KIND_MICROSOFT, username='Steve',
                                   uuid=PROFILE_ID, access_token='stale',
                                   token_expires=time.time() + 3600,
                                   refresh_token='refresh-token')
        joins = []
        refreshes = []

        def call(url, payload=None, headers=None, timeout=None):
            if url.endswith('/session/minecraft/join'):
                joins.append(payload['accessToken'])
                if len(joins) == 1:
                    raise accounts.AccountError('Forbidden',
                                                code='ForbiddenOperationException')
                return {}
            raise AssertionError('unexpected URL %s' % url)

        def refresh(account, log=None):
            refreshes.append(account.access_token)
            account.access_token = 'fresh'
            account.token_expires = time.time() + 3600

        with unittest.mock.patch.object(accounts, '_request_json', call), \
                unittest.mock.patch.object(accounts, 'microsoft_refresh', refresh):
            accounts.join_session(account, 'a' * 40)
        self.assertEqual(refreshes, ['stale', 'fresh'])
        self.assertEqual(joins, ['fresh', 'fresh'])

    def test_offline_accounts_do_not_join(self):
        account = accounts.Account(kind=accounts.KIND_OFFLINE, username='Steve')
        accounts.join_session(account, 'a' * 40)      # no session service involved


if __name__ == '__main__':
    unittest.main()
