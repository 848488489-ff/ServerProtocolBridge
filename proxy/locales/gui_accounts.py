"""Auto-split locale fragment: gui_accounts.  Merged by the parent module."""

EN = {
    'gui.accounts.col.name': 'Account',
    'gui.accounts.col.kind': 'Type',
    'gui.accounts.col.uuid': 'UUID',
    'gui.accounts.col.state': 'In use',
    'gui.accounts.button.add': 'Add account',
    'gui.accounts.add.offline': 'Offline account',
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

ZH = {
    'gui.accounts.col.name': '账号',
    'gui.accounts.col.kind': '类型',
    'gui.accounts.col.uuid': 'UUID',
    'gui.accounts.col.state': '当前',
    'gui.accounts.button.add': '添加账号',
    'gui.accounts.add.offline': '离线账号',
    'gui.accounts.add.thirdparty': '第三方账号',
    'gui.accounts.add.microsoft': '微软账号',
    'gui.accounts.button.active': '设为当前',
    'gui.accounts.button.clear': '不使用账号',
    'gui.accounts.button.remove': '删除',
    'gui.accounts.button.open_dir': '打开文件夹',
    'gui.accounts.hint': '选中的账号用于登录目标服务器: 上行的名字和 UUID 用账号本身的, '
                         '第三方 / 微软账号还会代做会话加入(session join), '
                         '这样会校验登录会话的服务器才放浏览器客户端进来。'
                         '微软账号每次进入服务器前会自动刷新登录凭据; 刷新失败会断开连接, '
                         '原因显示在游戏聊天栏。选"不使用账号"则维持原行为: 用客户端自己请求的名字。',
    'gui.accounts.data_dir': '账号文件: %(path)s',
    'gui.accounts.need_selection': '请先在列表里选择一个账号。',
    'gui.accounts.selected': '已改用账号 %(name)s',
    'gui.accounts.cleared': '已取消账号, 客户端重新使用自己的名字',
    'gui.accounts.removed': '已删除账号 %(name)s',
    'gui.accounts.remove.title': '删除账号',
    'gui.accounts.remove.ask': '确定删除账号 %(name)s 吗?',
    'gui.accounts.offline.prompt': '角色名',
    'gui.accounts.offline.bad_name': '这个名字不能使用：内容为空或只包含控制字符。'
                                    '长度和允许使用的字符由目标服务器决定。',
    'gui.accounts.thirdparty.title': '添加第三方账号',
    'gui.accounts.thirdparty.server': '账号服务地址',
    'gui.accounts.thirdparty.username': '用户名/邮箱',
    'gui.accounts.thirdparty.password': '密码',
    'gui.accounts.thirdparty.note': '填第三方账号服务提供的 API 根地址。',
    'gui.accounts.thirdparty.submit': '登录并添加',
    'gui.accounts.thirdparty.busy': '正在登录...',
    'gui.accounts.thirdparty.added': '已添加第三方账号 %(name)s',
    'gui.accounts.thirdparty.missing': '请把地址、用户名和密码都填上。',
    'gui.accounts.ms.title': '添加微软账号',
    'gui.accounts.ms.intro': '浏览器会打开 microsoft.com/link, 请在页面里输入下面的代码并登录微软账号; '
                             '浏览器没弹出来的话, 点下面的按钮。登录完成后本窗口会自动继续。',
    'gui.accounts.ms.code_label': '代码:',
    'gui.accounts.ms.starting': '正在向微软申请登录代码...',
    'gui.accounts.ms.waiting': '正在等待浏览器中完成登录...',
    'gui.accounts.ms.code_copied': '登录代码已复制到剪贴板',
    'gui.accounts.ms.copy': '复制代码',
    'gui.accounts.ms.open': '在浏览器中打开',
    'gui.accounts.ms.open_failed': '无法自动打开浏览器; 请点「在浏览器中打开」, 或在浏览器地址栏粘贴登录链接',
    'gui.accounts.ms.added': '已添加微软账号 %(name)s',
    'gui.accounts.ms.ssl_title': '证书验证失败',
    'gui.accounts.ms.ssl_ask': '无法验证与微软的安全连接:\n\n%(detail)s\n\n'
                               '如果要忽略 SSL 证书错误并继续, 请点「是」; '
                               '如果不忽略, 请点「否」。\n\n'
                               '忽略后, 这条连接上的数据可能被网络中的其他人读取。',
    'gui.accounts.ms.renewing': '微软没有接受这个登录代码, 正在重新获取...',
    'gui.accounts.ms.retrying_ssl': '已跳过证书检查, 正在重新获取登录代码...',
    'gui.accounts.legal': '如添加离线账号或第三方账号, 代表您已确认您拥有我的世界微软账号。',
    'gui.accounts.none': '还没有账号，请在上方添加。',
    'gui.accounts.added_offline': '已添加离线账号: %(name)s',
}
