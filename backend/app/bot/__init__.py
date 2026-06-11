"""ChronicleAgent QQ Bot 模块

架构：
  NoneBot2 独立进程，通过 OneBot v11 协议连接 NapCatQQ。
  群消息和 KP 指令通过 HTTP 转发给 FastAPI 后端处理。

文件说明：
  __main__.py   — NoneBot2 启动入口（python -m app.bot）
  config.py     — Bot 侧配置（环境变量读取）
  api_client.py — FastAPI 后端 HTTP 客户端
  binding.py    — 群/KP 与跑团项目的绑定管理
  commands.py   — KP 指令解析
  handlers.py   — NoneBot2 事件处理器（群聊 + 私聊）
"""
