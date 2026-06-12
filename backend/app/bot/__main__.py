"""QQ Bot 启动入口（NoneBot2 独立进程）

启动方式：python -m app.bot

连接架构：
  NapCatQQ（协议端，WebSocket Server）:8080
    ↑ WebSocket 连接 ↓
  NoneBot2（Bot 框架，WebSocket Client）
    ↑ HTTP ↓
  FastAPI（后端服务）:8000

配置（环境变量）：
  API_BASE_URL    — FastAPI 地址（默认 http://backend:8000）
  NAPCAT_WS_URL   — NapCatQQ WebSocket 地址（默认 ws://napcat:8080）
  KP_QQ           — KP 的 QQ 号
  DEBUG           — 调试模式
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    """启动 NoneBot2 QQ Bot"""
    print("=" * 50)
    print("  ChronicleAgent QQ Bot")
    print("  Starting NoneBot2 with OneBot v11...")
    print("=" * 50)

    # 初始化 NoneBot2
    from app.bot.config import bot_settings
    # 设置 WebSocket 连接方式：NoneBot2 作为客户端连接 NapCatQQ
    os.environ.setdefault("ONEBOT_WS_URLS", json.dumps([bot_settings.napcat_ws_url]))

    import nonebot
    from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

    # NoneBot2 初始化（读取环境变量中的配置）
    nonebot.init()

    # 注册 OneBot v11 适配器
    driver = nonebot.get_driver()
    driver.register_adapter(OneBotV11Adapter)

    # 加载事件处理器
    import app.bot.handlers  # noqa: F401 — 注册事件处理器

    # 应用配置
    from app.bot.config import bot_settings
    print(f"  API 后端: {bot_settings.api_base_url}")
    print(f"  NapCat:   {bot_settings.napcat_ws_url}")
    print(f"  Bot QQ:   {bot_settings.bot_qq or '未配置'}")
    print()

    # 运行 NoneBot2
    nonebot.run()


if __name__ == "__main__":
    main()
