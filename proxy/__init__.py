"""Server Protocol Bridge.

Turns an ordinary Minecraft server (plain TCP, e.g. Hypixel) into a local
wss:// endpoint for browser clients such as MCJS: browsers only accept wss://
WebSocket connections, so this tool unwraps WebSocket frames back into the
original TCP byte stream locally and forwards data in both directions.

Game packets are never parsed or modified along the way.
"""

from .version import APP_NAME, VERSION, app_name, tagline

__all__ = ['APP_NAME', 'VERSION', 'app_name', 'tagline']
