"""MCJS 服务器协议转换。

把普通的 Minecraft 服务器(TCP 协议, 例如 Hypixel)转换为本地 wss:// 端点,
供 MCJS 等浏览器端客户端连接 —— 浏览器端只允许建立 wss:// WebSocket 连接,
本工具在本地把 WebSocket 帧还原成原始 TCP 字节流, 与目标服务器双向转发。

整个转发过程不解析、不修改任何游戏数据包。
"""

from .version import APP_NAME, TAGLINE, VERSION

__all__ = ['APP_NAME', 'VERSION', 'TAGLINE']