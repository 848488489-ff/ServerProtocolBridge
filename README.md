# MCJS 服务器协议转换

把**普通 Minecraft 服务器**(例如 Hypixel, 原生 TCP 协议)转换为**本地 `wss://` 端点**,
让 MCJS 这类浏览器端客户端可以直接连上去。

原因很简单: 浏览器里跑的 MC 客户端只能通过 WebSocket 通信, 而且页面如果是 https,
就必须是 `wss://`(混合内容会被拦)。本工具在本机开一个 WebSocket 服务,
把收到的帧还原成原始 TCP 字节流, 再转发给真正的 Minecraft 服务器, **反向亦然**。

```
MCJS (浏览器)
    │  wss://127.0.0.1:8443        ← WebSocket(已 TLS 加密)
    ▼
MCJS 服务器协议转换(本工具, 仅监听 127.0.0.1)
    │  TCP mc.hypixel.net:25565    ← 原样转发的字节流
    ▼
Hypixel / 任意普通 Minecraft 服务器
```

转发过程**不解析、不修改、不记录任何游戏数据包**, 字节流与原版客户端直连完全一致,
所以 Hypixel 之类的服务器看不出中间有这一层。

---

## 1. 快速开始

### 方式一: 用打包好的 EXE(推荐)

1. 双击 `dist\MCJS-服务器协议转换.exe`(若只有源码, 先按第 3 节打包)。
2. 界面里确认 **转发目标**(默认 `mc.hypixel.net:25565`), 点 **启动服务**。
3. 点 **安装到系统信任库**(见下面第 4 节), 然后**重启浏览器**。
4. 在 MCJS 客户端的服务器地址栏填:

   ```
   wss://127.0.0.1:8443
   ```

   然后连接。日志窗口会显示 `#1 WSS 接入 127.0.0.1:xxxxx -> mc.hypixel.net:25565`。

### 方式二: 从源码运行

需要 Python 3.8+(Windows 官方安装包自带 tkinter 即可), 无任何第三方依赖:

```bat
python main.py
```

### 方式三: 命令行(无界面)

```bat
python main.py --no-gui --target mc.hypixel.net:25565 --port 8443
python main.py --check          :: 检查证书 + 目标服务器连通性
python main.py --install-cert   :: 生成并导入证书
```

---

## 2. 界面说明

| 区域 | 说明 |
| --- | --- |
| 基本设置 | 监听地址、wss 端口(默认 8443)、ws 端口(默认 8080, 备用明文)、转发目标、路径映射 |
| 证书 | 首次运行自动签发自签名证书; 可查看指纹、重新生成、一键导入系统信任库 |
| 高级 | 日志级别、WebSocket 心跳间隔、连接超时、WebSocket 单帧上限 |
| 运行日志 | 每条连接的上行/下行字节数、持续时间、关闭原因都在这里 |
| 状态栏 | 活动连接、累计连接、上行/下行字节、运行时长 |

**在 MCJS 中填写**: `wss://127.0.0.1:8443`(界面底部会实时显示这个地址, 可一键复制)。

---

## 3. 配置项(config.json)

界面里的改动会自动保存到程序目录下的 `config.json`, 也可以直接编辑或用命令行覆盖。

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `listen_host` | `127.0.0.1` | 监听地址。**默认只监听本机**, 改成 `0.0.0.0` 会暴露到局域网 |
| `wss_port` | `8443` | `wss://`(TLS)端口 |
| `ws_port` | `8080` | `ws://`(明文)备用端口, `0` 表示关闭。仅当 MCJS 页面本身是 `http://` 时才可能用到 |
| `target` | `mc.hypixel.net:25565` | 转发目标。支持 `host`、`host:port`、`mc://host:port`、`[IPv6]:port` |
| `routes` | `{}` | 路径映射, 例如 `{"/hypixel": "mc.hypixel.net:25565"}`, 于是 `wss://127.0.0.1:8443/hypixel` 会转到 Hypixel |
| `use_srv` | `true` | 目标**不带端口**时先查 `_minecraft._tcp.<域名>` 的 SRV 记录(与原版客户端一致), 查不到回落 25565 |
| `tls_enabled` | `true` | 是否启用 wss |
| `cert_dir` | `certs` | 证书目录(相对程序目录) |
| `cert_common_name` | `localhost` | 证书 CN |
| `cert_extra_names` | `[]` | 证书 SAN 里要额外包含的名称/IP, 例如 `["192.168.1.5", "mypc"]` |
| `cert_days` | `3650` | 证书有效期 |
| `cert_generator` | `auto` | `auto` / `python`(内置纯 Python 生成) / `openssl` |
| `connect_timeout` | `10.0` | 连接目标服务器的超时秒数 |
| `heartbeat_sec` | `30` | WebSocket 心跳间隔, `0` 关闭 |
| `max_payload_mb` | `16` | WebSocket 单帧上限 |
| `log_level` | `info` | `debug` / `info` / `warn` / `error` |

---

## 4. 信任证书(wss 的关键一步)

`wss://` 需要证书。本工具启动时会自动签发一张自签名证书到 `certs\cert.pem`
(SAN 包含 `localhost`、`127.0.0.1`、`::1` 和本机主机名), 但**浏览器默认不信任自签名证书**,
所以必须导入一次:

* **图形界面**: 点 **安装到系统信任库**(等价于下面的命令)。
* **命令行**:

  ```bat
  certutil -user -addstore root certs\cert.pem
  ```

  或 PowerShell(静默, 不弹窗):

  ```powershell
  Import-Certificate -FilePath certs\cert.pem -CertStoreLocation Cert:\CurrentUser\Root
  ```

* 之后**重启浏览器**。Chrome / Edge / IE 使用 Windows 证书库, 导入即生效。
* **Firefox 使用自己的证书库**, 需要单独导入:
  设置 → 隐私与安全 → 证书 → 查看证书 → 导入 → 选 `certs\cert.pem`,
  并勾选"信任由此证书颁发机构来标识网站"。

如果要用局域网 IP 或别的域名访问(例如 `wss://192.168.1.5:8443`),
在 **证书 → 额外名称** 里加上它, 再点 **重新生成证书** 并重新导入。

---

## 5. 常见问题

**Q: 客户端连不上, 提示证书错误 / `ERR_CERT_AUTHORITY_INVALID`**
没导入证书或没重启浏览器, 按第 4 节做一次。

**Q: 连上了但马上被踢掉**
- 日志里出现 `Outdated client!` / `你使用的版本过旧`: 客户端的 Minecraft 协议版本与服务器不匹配, 与本工具无关(Hypixel 需要 1.8.9 及以上)。
- 在线模式服务器(Hypixel 是)会要求登录账号, 需要客户端自身能完成微软账号登录流程, 本工具只做字节转发, 不参与认证。
- 日志里出现 `心跳超时`: 客户端所在环境把 WebSocket 心跳帧丢了, 把 `heartbeat_sec` 调大或改成 `0` 试试。

**Q: 日志显示"连接目标服务器失败"**
目标地址写错、端口被墙, 或者 DNS 解析不到。先用 `python main.py --check` 验证连通性。

**Q: 只能填 `ws://127.0.0.1:8080` 吗**
`ws://` 也能用(明文), 但如果 MCJS 页面是通过 https 打开的, 浏览器会以"混合内容"为由拦截,
只能走 `wss://` —— 所以默认开启 8080 端口只是为了方便排查问题。

**Q: 会影响我的账号吗**
本工具不解析任何内容, 不修改任何数据包, 也不保存凭据; 它只是把本机与目标服务器之间的字节流原样搬运。

**Q: 能同时连多个服务器吗**
可以。用 `routes` 做路径映射即可, 例如:

```json
"routes": {
  "/hypixel": "mc.hypixel.net:25565",
  "/本地": "127.0.0.1:25565"
}
```

对应 `wss://127.0.0.1:8443/hypixel`、`wss://127.0.0.1:8443/本地`。每条连接各自独立建立 TCP 连接。

---

## 6. 打包成 EXE

```bat
python tools\build.py
```

流程: `PyInstaller(onefile) → UPX 压缩 → MPRESS 压缩 → 冒烟验证`, 产物在 `dist\`:

| 产物 | 说明 |
| --- | --- |
| `dist\MCJS-服务器协议转换.exe` | 主程序(带控制台: 可以用 `--no-gui` / `--check` 等命令行参数) |
| `dist\MPRESS\MCJS-服务器协议转换.exe` | MPRESS 压缩版(体积更小, 备选) |
| `dist\build-report.txt` | 各阶段体积与 SHA256 |

要点:
* PyInstaller 打包时通过 `--upx-dir` 已经把 `python3x.dll`、tcl/tk 等内部文件用 **UPX** 压缩过一遍;
  之后脚本还会对 EXE 本身再压一次, 并**跑冒烟测试**, 一旦压缩导致无法启动会自动回退到未压缩版本。
* MPRESS(v2.19)处理 64 位程序需要 `-x` 参数, 脚本已带上; 结果不可用时不会保留该文件。
* 无控制台的纯 GUI 版: `python tools\build.py --windowed`。
* 压缩包被杀软误报是这类 PE 加壳的通病, 遇到时把文件加入白名单即可。

---

## 7. 目录结构

```
MCJS-服务器协议转换/
├── main.py                 入口(默认 GUI, --no-gui 走命令行)
├── mcjs_proxy/
│   ├── proxy.py            转发核心: 监听 -> WebSocket 握手 -> TCP 桥接
│   ├── wsproto.py          RFC 6455 握手与帧编解码(纯标准库)
│   ├── x509.py             纯 Python 自签名证书(RSA + SHA-256 + SAN)
│   ├── der.py              极简 DER/ASN.1 编码器
│   ├── certs.py            证书生成/校验/导入系统信任库
│   ├── resolver.py         SRV 解析(纯标准库 DNS 查询)与连通性探测
│   ├── config.py           配置读写、地址解析、校验
│   ├── gui.py              tkinter 图形界面
│   ├── cli.py              命令行模式
│   ├── logger.py           日志(控制台 + 界面回调)
│   └── utils.py            路径与格式化工具
├── tests/test_all.py       自检测试(证书真实握手 / 帧编解码 / 端到端转发)
├── tools/build.py          打包脚本(PyInstaller + UPX + MPRESS)
├── config.example.json     配置示例
└── README.md
```

测试:

```bat
python -m unittest discover -s tests -v
```

---

## 8. 实现要点

* **透明转发**: WebSocket 二进制帧的负载就是 Minecraft 协议字节; 反向从 TCP 读到的字节也原样塞进帧里。
* **不启用压缩**: 握手响应里不返回 `Sec-WebSocket-Extensions`, 浏览器就不会用 permessage-deflate, 帧里保持原始字节。
* **背压**: 两个方向都用阻塞式 `sendall`, 对端慢下来时自然反压, 不会把内存撑爆。
* **分片与控制帧**: 完整实现 RFC 6455 的分片消息、ping/pong、关闭握手与协议错误处理。
* **base64 兼容模式**: 少数老浏览器客户端会把数据放进文本帧, 程序会自动切换到 base64 模式, 也能识别 `Sec-WebSocket-Protocol: base64`。
* **证书**: 无第三方库, 用标准库手写 DER 编码 + RSA 密钥生成 + PKCS#1 v1.5 签名; 系统里有 openssl 时会优先用 openssl(更快)。测试里包含真实 TLS 握手校验(域名与 IP 两种 SAN)。
* **只监听 127.0.0.1**: 默认不对外开放。改成 `0.0.0.0` 等于把转发入口暴露给整个局域网, 请自行评估。