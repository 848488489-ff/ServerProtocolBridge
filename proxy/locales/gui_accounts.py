"""Auto-split locale fragment: gui_accounts.  Merged by the parent module."""

EN = {
    'gui.accounts.col.name': 'Account',
    'gui.accounts.col.kind': 'Type',
    'gui.accounts.col.uuid': 'UUID',
    'gui.accounts.col.state': 'In use',
    'gui.accounts.button.add': 'Add account',
    'gui.accounts.add.offline': 'Add offline account',
    'gui.accounts.add.thirdparty': 'Third-party account',
    'gui.accounts.add.microsoft': 'Microsoft account',
    'gui.accounts.button.active': 'Use this account',
    'gui.accounts.button.clear': 'Use none',
    'gui.accounts.button.remove': 'Remove',
    'gui.accounts.button.open_dir': 'Open folder',
    'gui.accounts.hint': 'The selected account is used to sign in to the target server: its '
                         'exact name and UUID are sent upstream, and third-party / Microsoft '
                         'accounts also register the session join, so servers that require '
                         'an authenticated session let browser clients through.  Microsoft '
                         'credentials are refreshed automatically before every join; if that '
                         'fails, the connection closes and the reason appears in chat.  '
                         '"Use none" keeps the old behaviour: the name the client sends.',
    'gui.accounts.data_dir': 'Account file: %(path)s',
    'gui.accounts.need_selection': 'Select an account in the list first.',
    'gui.accounts.selected': 'Now using account %(name)s',
    'gui.accounts.cleared': 'No account selected; clients use their own names again',
    'gui.accounts.removed': 'Removed account %(name)s',
    'gui.accounts.remove.title': 'Remove account',
    'gui.accounts.remove.ask': 'Remove account %(name)s?',
    'gui.accounts.offline.prompt': 'Player name',
    'gui.accounts.offline.bad_name': 'That name cannot be used: it is empty, or contains '
                                     'only control characters. Length and the allowed '
                                     'characters are up to the target server.',
    'gui.accounts.offline.warn_name': 'The name "%(name)s" is outside the usual server rules '
                                      '(3-16 letters, digits or underscores); some servers '
                                      'may reject it and you may be unable to join. '
                                      'Add it anyway?',
    'gui.accounts.offline.submit': 'Add',
    'gui.accounts.thirdparty.title': 'Add third-party account',
    'gui.accounts.thirdparty.server': 'Account service address',
    'gui.accounts.thirdparty.username': 'User name / e-mail',
    'gui.accounts.thirdparty.password': 'Password',
    'gui.accounts.thirdparty.note': 'Use the API root provided by your third-party account '
                                    'service.',
    'gui.accounts.thirdparty.submit': 'Sign in and add',
    'gui.accounts.thirdparty.busy': 'Signing in...',
    'gui.accounts.thirdparty.added': 'Added third-party account %(name)s',
    'gui.accounts.thirdparty.missing': 'Please fill in the address, the user name and the password.',
    'gui.accounts.ms.title': 'Add Microsoft account',
    'gui.accounts.ms.intro': 'A browser window opens at microsoft.com/link: type the '
                             'code below there and sign in to your Microsoft account.  '
                             'If no browser opened, use the buttons below.  This window '
                             'carries on by itself once the browser is done.',
    'gui.accounts.ms.code_label': 'Code:',
    'gui.accounts.ms.starting': 'Requesting a sign-in code from Microsoft...',
    'gui.accounts.ms.waiting': 'Waiting for the sign-in in the browser...',
    'gui.accounts.ms.code_copied': 'Sign-in code copied to the clipboard',
    'gui.accounts.ms.copy': 'Copy code',
    'gui.accounts.ms.open': 'Open in browser',
    'gui.accounts.ms.open_failed': 'Could not open a browser; use the "Open in browser" '
                                   'button or paste the sign-in link into a browser '
                                   'window instead',
    'gui.accounts.ms.added': 'Added Microsoft account %(name)s',
    'gui.accounts.ms.ssl_title': 'Certificate check failed',
    'gui.accounts.ms.ssl_ask': 'The secure connection to Microsoft could not be '
                               'verified:\n\n%(detail)s\n\n'
                               'Click Yes to ignore the SSL certificate error and '
                               'continue; click No to stop.\n\n'
                               'If you ignore it, data on this connection could be '
                               'read by others on the network.',
    'gui.accounts.ms.renewing': 'Microsoft rejected this sign-in code; '
                                'requesting a new one...',
    'gui.accounts.ms.retrying_ssl': 'Certificate check skipped; requesting a new '
                                    'sign-in code...',
    'gui.accounts.legal': 'By adding an offline or third-party account, you confirm that you '
                          'own Minecraft with a Microsoft account.',
    'gui.accounts.none': 'No account yet. Add one above.',
    'gui.accounts.added_offline': 'Offline account added: %(name)s',
}

