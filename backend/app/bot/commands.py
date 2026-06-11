"""KP 指令解析 — 处理 KP 私聊发来的指令

指令列表：
  /绑定团 <campaign_id>   — 绑定 KP 到跑团项目
  /查线索 <关键词>         — RAG 检索模组内容
  /当前状态               — 查看剧情状态
  /建议                   — 获取当前建议
  /总结                   — 生成团录
  /帮助                   — 显示帮助
  /群绑定 <group_id> <campaign_id>  — 绑定群到团（仅限绑定过的 KP）
"""

import re
from typing import Optional, Tuple


COMMAND_PREFIXES = ["/", "／", "。"]


def parse_command(text: str) -> Optional[Tuple[str, str]]:
    """解析消息中的指令

    Args:
        text: 消息文本

    Returns:
        (command, args) 元组，如果不是指令则返回 None
    """
    stripped = text.strip()

    # 检查是否以指令前缀开头
    prefix = None
    for p in COMMAND_PREFIXES:
        if stripped.startswith(p):
            prefix = p
            break

    if prefix is None:
        return None

    # 去掉前缀
    cmd_text = stripped[len(prefix):].strip()

    # 用空格切分命令和参数
    parts = cmd_text.split(None, 1)
    command = parts[0].lower() if parts else ""
    args = parts[1].strip() if len(parts) > 1 else ""

    return (command, args)


COMMAND_DESCRIPTIONS = {
    "绑定团": "绑定跑团项目：/绑定团 <campaign_id>",
    "查线索": "检索模组内容：/查线索 <关键词>",
    "当前状态": "查看当前剧情状态：/当前状态",
    "建议": "获取当前 KP 建议：/建议",
    "总结": "生成团录：/总结",
    "群绑定": "绑定群到跑团：/群绑定 <群号> <campaign_id>",
    "帮助": "显示本帮助：/帮助",
}


def get_help_text() -> str:
    """生成帮助文本"""
    lines = ["📖 ChronicleAgent 指令帮助", "=" * 30]
    for cmd, desc in COMMAND_DESCRIPTIONS.items():
        lines.append(f"\n/{cmd}")
        lines.append(f"  {desc}")
    return "\n".join(lines)


# 模拟指令处理（Bot 侧只做简单校验和转发，真正的逻辑在 FastAPI）
REMOTE_COMMANDS = {"查线索", "当前状态", "建议", "总结"}
LOCAL_COMMANDS = {"绑定团", "群绑定", "帮助"}
