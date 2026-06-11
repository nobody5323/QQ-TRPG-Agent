"""Bot 独立进程配置 — NoneBot2 侧

与 backend/app/config.py 分开，因为这个进程只跑 NoneBot2，
不需要导入 FastAPI 相关依赖。
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BotSettings:
    """Bot 进程配置，从环境变量读取"""
    # FastAPI 后端地址
    api_base_url: str = field(
        default_factory=lambda: os.getenv("API_BASE_URL", "http://backend:8000")
    )
    # NapCatQQ WebSocket 地址
    napcat_ws_url: str = field(
        default_factory=lambda: os.getenv("NAPCAT_WS_URL", "ws://napcat:8080")
    )
    # Bot 自身的 QQ 号
    bot_qq: Optional[str] = field(
        default_factory=lambda: os.getenv("BOT_QQ", None)
    )
    # 调试模式
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )


bot_settings = BotSettings()
