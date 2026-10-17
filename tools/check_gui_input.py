r"""GUI 输入校验冒烟检查: 确认数字输入框拒绝中文/字母/超长输入, 且错误提示是中文。

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
    """模拟键盘输入: 逐个字符 insert, Tk 的 validatecommand 会逐次拦截。"""
    entry.focus_set()
    for char in text:
        entry.insert('end', char)
    app.update()
    return entry.get()


# 1) 中文/字母/空格/全角数字/负号都被拒绝
for entry, name in ((app.entry_wss_port, 'wss 端口'), (app.entry_ws_port, 'ws 端口'),
                    (app.entry_cert_days, '有效期'), (app.entry_heartbeat, '心跳'),
                    (app.entry_timeout, '超时'), (app.entry_max_payload, '单帧上限')):
    original = entry.get()
    typed = type_into(entry, '端口abc １２３')
    if typed != original:
        failures.append('%s 接受了非法字符: %r -> %r' % (name, original, typed))

# 2) 正常数字可以输入
app.entry_wss_port.delete('0', 'end')
typed = type_into(app.entry_wss_port, '8443')
if typed != '8443':
    failures.append('wss 端口 无法输入正常数字: %r' % typed)

# 3) 最多 5 位: 第 6 位字符输入不进去
typed = type_into(app.entry_wss_port, '99')
if len(typed) != 5 or typed != '84439':
    failures.append('wss 端口 的位数限制不对: %r' % typed)

# 4) 超范围时 _collect_form 抛中文提示
app.entry_wss_port.delete('0', 'end')
type_into(app.entry_wss_port, '99999')
try:
    app._collect_form()
    failures.append('99999 没有被范围校验拦下')
except ValueError as exc:
    print('超范围提示: %s' % exc)

# 5) 清空端口后收集配置必须有明确提示
app.entry_wss_port.delete('0', 'end')
app.update()
try:
    app._collect_form()
    failures.append('空端口没有被拦下')
except ValueError as exc:
    print('空值提示: %s' % exc)

# 6) 超时字段: 只允许一个小数点, 第二个小数点被拒绝
app.entry_timeout.delete('0', 'end')
typed = type_into(app.entry_timeout, '10.5.5')
if typed != '10.55':
    failures.append('超时字段的小数点处理不对: %r' % typed)

app.destroy()
if failures:
    print('FAILED')
    for item in failures:
        print(' - %s' % item)
    sys.exit(1)
print('INPUT_VALIDATION_OK')
