# Server Protocol Bridge — Android 原生 APK

在 Android 上，程序以 **Chaquopy**（Android Studio Gradle 插件）嵌入 Python 运行。
pywebview 在 Android 不可用，所以控制面板是**内置 WebView** 加载程序自带的
Flask Web UI（`http://127.0.0.1:8765`），代理服务由面板里的「启动服务」控制，
与桌面/浏览器界面完全一致。

## 前置要求

- **Android Studio**（含 Android SDK），SDK Platform 35 + Build-Tools
- **JDK 17**（Android Studio 自带 JBR 即可）
- 可访问外网（首次构建需下载 Gradle 8.9、AGP 8.7.3、Chaquopy 17.2.0、
  Python 3.13 及 pip 依赖）

## 构建 APK

1. 用 Android Studio **打开本目录**（`android/`），等待 Gradle 同步完成
   （首次会下载 Gradle 8.9 与依赖）。
2. 菜单 **Build → Build Bundle(s) / APK(s) → Build APK(s)**。
3. APK 输出：`android/app/build/outputs/apk/release/app-release.apk`
   （release 用 debug 签名，可直接安装）。

命令行构建（需要先有 Gradle wrapper，可在 Android Studio 里
`File → Sync` 生成，或用本机 Gradle 执行 `gradle wrapper`）：

```
gradlew assembleRelease
```

APK 包含两个 ABI：`arm64-v8a`（真机）与 `x86_64`（模拟器）。

## 安装与运行

```
adb install app-release.apk
```

打开「Server Protocol Bridge」应用：内置 WebView 显示控制面板，与桌面版
相同。程序数据（config.json、证书、账户）写在应用私有目录：

```
/data/data/com.serverprotocolbridge/files/ServerProtocolBridge/
```

可在 Android Studio 的 **Device Explorer**（View → Tool Windows → Device
Explorer）中查看与编辑。

## 说明

- **证书信任**：代理的 wss:// 使用自签 CA。桌面端安装 CA 证书后客户端才
  信任连接；Android 上同样需要把 `certs/cert.pem` 安装到系统/用户受信 CA
  （设置 → 安全 → 加密与凭据 → 安装证书），否则网页版客户端连接
  `wss://127.0.0.1:8443` 会报证书错误。此限制与桌面版一致，非 APK 特有。
- **网络权限**：`INTERNET` + `ACCESS_NETWORK_STATE` 已在 Manifest 声明；
  明文 `http://127.0.0.1` 仅在 network_security_config 中放行（localhost），
  其余流量一律走安全默认（禁明文）。
- **账户登录**：面板里的微软/Java 账户登录调用 `window.open`，会在**系统
  浏览器**中打开授权页，登录后回到面板。
- **数据目录**：`proxy/utils.py` 的 `data_dir()` 在 Android 上解析到
  `$HOME/ServerProtocolBridge`（`HOME` = 应用内部存储，Chaquopy 保证可写、
  卸载前持久）。
- **证书生成**：Android 无 openssl 二进制，`proxy/certs.py` 自动回退到纯
  Python（cryptography）生成器。
