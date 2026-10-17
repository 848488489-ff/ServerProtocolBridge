r"""GUI input-validation smoke check: numeric entries must reject Chinese characters, letters,
spaces, full-width digits and signs, enforce the 5-digit cap, and raise a clear ValueError for
out-of-range or empty values.

    py -3.14 -X utf8 tools\check_gui_input.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, '.')

from mcjs_proxy.gui import BridgeApp  # noqa: E402

app = BridgeApp()
app.update()
failures = []


def type_into(entry, text: str) -> str:
    """Simulate typing: insert one character at a time so Tk's validatecommand fires per keypress."""
    entry.focus_set()
    for char in text:
        entry.insert('end', char)
    app.update()
    return entry.get()


# 1) Chinese characters / letters / spaces / full-width digits / minus sign are all rejected
for entry, name in ((app.entry_wss_port, 'wss port'), (app.entry_ws_port, 'ws port'),
                    (app.entry_cert_days, 'cert valid days'), (app.entry_heartbeat, 'heartbeat'),
                    (app.entry_timeout, 'timeout'), (app.entry_max_payload, 'max frame payload')):
    original = entry.get()
    typed = type_into(entry, '端口abc １２３')
    if typed != original:
        failures.append('%s accepted invalid characters: %r -> %r' % (name, original, typed))

# 2) a normal number can be typed
app.entry_wss_port.delete('0', 'end')
typed = type_into(app.entry_wss_port, '8443')
if typed != '8443':
    failures.append('wss port rejected a valid number: %r' % typed)

# 3) at most 5 digits: the 6th character must not go in
typed = type_into(app.entry_wss_port, '99')
if len(typed) != 5 or typed != '84439':
    failures.append('wss port length cap is wrong: %r' % typed)

# 4) out of range: _collect_form must raise
app.entry_wss_port.delete('0', 'end')
type_into(app.entry_wss_port, '99999')
try:
    app._collect_form()
    failures.append('99999 was not caught by the range check')
except ValueError as exc:
    print('range error message: %s' % exc)

# 5) cleared port: collecting the config must report a clear error
app.entry_wss_port.delete('0', 'end')
app.update()
try:
    app._collect_form()
    failures.append('an empty port was not caught')
except ValueError as exc:
    print('empty value message: %s' % exc)

# 6) timeout field: only one decimal point, the second one must be rejected
app.entry_timeout.delete('0', 'end')
typed = type_into(app.entry_timeout, '10.5.5')
if typed != '10.55':
    failures.append('timeout field mishandles decimal points: %r' % typed)

app.destroy()
if failures:
    print('FAILED')
    for item in failures:
        print(' - %s' % item)
    sys.exit(1)
print('INPUT_VALIDATION_OK')
