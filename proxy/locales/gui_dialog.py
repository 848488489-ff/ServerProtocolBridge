"""Auto-split locale fragment: gui_dialog.  Merged by the parent module."""

EN = {
    'gui.error.title': 'Invalid Configuration',
    'gui.error.empty': '"%(label)s" cannot be empty',
    'gui.error.not_number': '"%(label)s" must be a number, got: %(value)s',
    'gui.error.invalid_number': '"%(label)s" is not a valid number: %(value)s',
    'gui.error.port_range': '"%(label)s" must be between 0 and 65535, got: %(value)s',
    'gui.dialog.switch_failed': 'Language Switch Failed',
    'gui.dialog.need_stop.title': 'Stop the Service First',
    'gui.dialog.need_stop.text': 'The service must be stopped before the certificate '
                                 'can be regenerated.',
    'gui.dialog.regen.title': 'Regenerate Certificate',
    'gui.dialog.regen.confirm': 'The current certificate will be deleted and a new one '
                                'issued. Continue?',
    'gui.dialog.delete_failed': 'Delete Failed',
    'gui.dialog.generate_failed': 'Generation Failed',
    'gui.dialog.regen.done_title': 'Done',
    'gui.dialog.regen.done': 'The certificate has been regenerated.',
    'gui.dialog.regen.done_deleted': 'The certificate has been regenerated; '
                                     'the old one was deleted.',
    'gui.dialog.cert_missing.title': 'No Certificate Yet',
    'gui.dialog.cert_missing.ask': 'There is no certificate file yet. Generate and install it now?',
    'gui.dialog.install_ok.title': 'Installed',
    'gui.dialog.install_ok.text': 'The certificate was added to the current user\'s "Trusted Root Certification '
        'Authorities".\n\n'
        'Please restart the browser (Chrome / Edge take effect immediately; Firefox\n'
        'needs a separate import under Settings -> Privacy & Security ->\n'
        'Certificates -> View Certificates).',
    'gui.dialog.install_failed': 'Installation Failed',
    'gui.dialog.unknown_error': 'Unknown error',
    'gui.dialog.no_endpoint.title': 'No Usable Address',
    'gui.dialog.no_endpoint.text': 'Set a wss port first',
    'gui.dialog.not_running.title': 'Not Running',
    'gui.dialog.not_running.text': 'Start the service first.',
    'gui.dialog.save_failed': 'Save Failed',
    'gui.dialog.reset.title': 'Restore Defaults',
    'gui.dialog.reset.ask': 'The settings in the window will be reset to their defaults '
                            '(the saved configuration file is not overwritten). Continue?',
    'gui.dialog.open_failed': 'Open Failed',
    'gui.error.password_mismatch': 'The two passwords do not match.',
    'gui.error.password_required': 'Enter a password before enabling access control.',
    'gui.error.password_short': 'The password must contain at least 4 characters.',
    'gui.confirm.title': 'Clear Access Password',
    'gui.confirm.web_password_off': 'This clears the stored Web UI password permanently. Continue?',
}

ZH = {
    'gui.error.title': '配置有误',
    'gui.error.empty': '「%(label)s」不能为空',
    'gui.error.not_number': '「%(label)s」只能是数字, 当前值是: %(value)s',
    'gui.error.invalid_number': '「%(label)s」不是有效的数字: %(value)s',
    'gui.error.port_range': '「%(label)s」必须在 0~65535 之间, 当前值是: %(value)s',
    'gui.dialog.switch_failed': '切换语言失败',
    'gui.dialog.need_stop.title': '请先停止服务',
    'gui.dialog.need_stop.text': '重新生成证书需要先停止服务。',
    'gui.dialog.regen.title': '重新生成证书',
    'gui.dialog.regen.confirm': '将删除现有证书并重新签发一张, 需要继续吗?',
    'gui.dialog.delete_failed': '删除失败',
    'gui.dialog.generate_failed': '生成失败',
    'gui.dialog.regen.done_title': '完成',
    'gui.dialog.regen.done': '证书已重新生成。',
    'gui.dialog.regen.done_deleted': '证书已重新生成。已删除旧证书。',
    'gui.dialog.cert_missing.title': '尚未生成证书',
    'gui.dialog.cert_missing.ask': '还没有证书文件, 是否现在生成并导入?',
    'gui.dialog.install_ok.title': '导入成功',
    'gui.dialog.install_ok.text': '证书已加入当前用户的"受信任的根证书颁发机构"。\n\n'
        '请重启浏览器(Chrome / Edge 立即生效, Firefox 需要在\n'
        '设置 → 隐私与安全 → 证书 → 查看证书 中再单独导入一次)。',
    'gui.dialog.install_failed': '导入失败',
    'gui.dialog.unknown_error': '未知错误',
    'gui.dialog.no_endpoint.title': '没有可用地址',
    'gui.dialog.no_endpoint.text': '请先设置 wss 端口',
    'gui.dialog.not_running.title': '未运行',
    'gui.dialog.not_running.text': '请先启动服务。',
    'gui.dialog.save_failed': '保存失败',
    'gui.dialog.reset.title': '恢复默认配置',
    'gui.dialog.reset.ask': '将把界面上的设置恢复为默认值(不覆盖已保存的配置文件), 继续吗?',
    'gui.dialog.open_failed': '打开失败',
    'gui.error.password_mismatch': '两次输入的密码不一致。',
    'gui.error.password_required': '启用访问控制前请先设置密码。',
    'gui.error.password_short': '密码至少需要 4 个字符。',
    'gui.confirm.title': '清空访问密码',
    'gui.confirm.web_password_off': '这将永久清空已保存的 Web UI 密码，且无法恢复。要继续吗？',
}
