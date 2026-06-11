"""NoneBot2 事件处理器 — 群聊监听 + KP 私聊指令"""

import re
from nonebot import on_message
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, PrivateMessageEvent, MessageSegment,
)
from nonebot.params import EventMessage

from app.bot.api_client import api_client
from app.bot.binding import store
from app.bot.commands import parse_command, get_help_text, REMOTE_COMMANDS, LOCAL_COMMANDS
from app.bot.config import bot_settings


# ════════════════════════════════════════════════════
# 群聊消息处理器
# ════════════════════════════════════════════════════

group_msg = on_message(priority=1, block=False)


@group_msg.handle()
async def handle_group_message(
    bot: Bot,
    event: GroupMessageEvent,
    message: MessageSegment = EventMessage(),
):
    """处理群聊消息：转发给 FastAPI，需要时提醒 KP"""
    group_id = str(event.group_id)
    user_id = str(event.user_id)
    raw_text = event.raw_message.strip()

    # 忽略空消息和系统消息
    if not raw_text:
        return

    # 获取群绑定的 campaign
    campaign_id = store.get_campaign_for_group(group_id)

    # 如果没有绑定，尝试从消息中获取用户昵称
    sender_name = event.sender.card or event.sender.nickname or user_id

    # 调用 FastAPI 处理消息
    try:
        result = await api_client.handle_message(
            campaign_id=campaign_id or "",
            sender=sender_name,
            content=raw_text,
        )
    except Exception as e:
        # FastAPI 不可用时静默降级（不影响群聊）
        return

    # 如果需要通知 KP
    need_notify = result.get("need_kp_notify", False)
    suggestion = result.get("kp_suggestion", "")

    if need_notify and suggestion and bot_settings.kp_qq:
        try:
            kp_qq = int(bot_settings.kp_qq)
            # 私聊发送给 KP
            await bot.send_private_msg(
                user_id=kp_qq,
                message=format_kp_notification(result),
            )
        except Exception as e:
            pass  # 私聊失败静默处理


# ════════════════════════════════════════════════════
# KP 私聊指令处理器
# ════════════════════════════════════════════════════

private_msg = on_message(priority=1, block=False)


@private_msg.handle()
async def handle_private_message(
    bot: Bot,
    event: PrivateMessageEvent,
    message: MessageSegment = EventMessage(),
):
    """处理 KP 私聊指令"""
    user_id = str(event.user_id)
    raw_text = event.raw_message.strip()

    if not raw_text:
        return

    # 解析指令
    parsed = parse_command(raw_text)
    if parsed is None:
        # 不是指令，忽略
        return

    command, args = parsed

    if command in LOCAL_COMMANDS:
        await handle_local_command(bot, user_id, command, args)
    elif command in REMOTE_COMMANDS:
        await handle_remote_command(bot, user_id, command, args)
    else:
        await bot.send_private_msg(
            user_id=int(user_id),
            message=f"未知指令：/{command}\n\n{get_help_text()}",
        )


# ════════════════════════════════════════════════════
# 本地指令处理（Bot 侧完成，不需要 FastAPI）
# ════════════════════════════════════════════════════

async def handle_local_command(
    bot: Bot, user_id: str, command: str, args: str
):
    """处理不需要后端参与的指令"""
    if command == "帮助":
        await bot.send_private_msg(
            user_id=int(user_id),
            message=get_help_text(),
        )

    elif command == "绑定团":
        if not args:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="用法：/绑定团 <campaign_id>\n请提供跑团项目 ID。",
            )
            return
        campaign_id = args.strip()
        store.bind_kp(user_id, campaign_id)
        await bot.send_private_msg(
            user_id=int(user_id),
            message=f"✅ 已绑定跑团项目：{campaign_id}\n可使用 /当前状态 查看。",
        )

    elif command == "群绑定":
        parts = args.split(None, 1)
        if len(parts) < 2:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="用法：/群绑定 <群号> <campaign_id>",
            )
            return
        group_id, cid = parts[0], parts[1]
        store.bind_group(group_id, cid)
        await bot.send_private_msg(
            user_id=int(user_id),
            message=f"✅ 已绑定群 {group_id} → 项目 {cid}",
        )


# ════════════════════════════════════════════════════
# 远端指令处理（转发 FastAPI）
# ════════════════════════════════════════════════════

async def handle_remote_command(
    bot: Bot, user_id: str, command: str, args: str
):
    """处理需要调用后端的指令"""
    # 获取 KP 绑定的 campaign
    campaign_id = store.get_campaign_for_kp(user_id)
    if not campaign_id:
        await bot.send_private_msg(
            user_id=int(user_id),
            message="⚠️ 请先使用 /绑定团 <campaign_id>\n绑定后再使用此指令。",
        )
        return

    try:
        if command == "查线索":
            if not args:
                await bot.send_private_msg(
                    user_id=int(user_id),
                    message="用法：/查线索 <关键词>\n例如：/查线索 书房",
                )
                return
            result = await api_client.rag_query(campaign_id, args)
            await send_rag_result(bot, user_id, result)

        elif command == "当前状态":
            result = await api_client.get_campaign_state(campaign_id)
            await send_state_result(bot, user_id, result)

        elif command == "建议":
            result = await api_client.kp_command(campaign_id, "建议", args)
            await bot.send_private_msg(
                user_id=int(user_id),
                message=result.get("suggestion", "暂无建议"),
            )

        elif command == "总结":
            result = await api_client.generate_summary(campaign_id)
            summary = result.get("markdown", "")
            if summary:
                await bot.send_private_msg(
                    user_id=int(user_id),
                    message=summary[:1500],  # QQ 私聊长度限制
                )
            else:
                await bot.send_private_msg(
                    user_id=int(user_id),
                    message="团录生成中，请稍后重试。",
                )

    except Exception as e:
        await bot.send_private_msg(
            user_id=int(user_id),
            message=f"❌ 指令执行失败：{str(e)[:200]}",
        )


# ════════════════════════════════════════════════════
# 消息格式化
# ════════════════════════════════════════════════════

def format_kp_notification(result: dict) -> str:
    """格式化 KP 通知消息"""
    parts = []
    suggestion = result.get("kp_suggestion", "")

    msg_type = result.get("message_type", "action")
    if msg_type == "player_action":
        parts.append("🎲 【玩家行动检测】")
    elif msg_type == "roleplay":
        parts.append("💬 【角色扮演】")
    elif msg_type == "rule_question":
        parts.append("📖 【规则问题】")
    else:
        parts.append("📝 【消息提醒】")

    if suggestion:
        parts.append(f"\n\n{suggestion[:800]}")

    return "\n".join(parts)


async def send_rag_result(bot: Bot, user_id: str, result: dict):
    """格式化并发送 RAG 检索结果"""
    sources = result.get("sources", [])
    if not sources:
        await bot.send_private_msg(
            user_id=int(user_id),
            message="未找到相关信息。",
        )
        return

    lines = ["🔍 检索结果", "=" * 20]
    for i, src in enumerate(sources[:5], 1):
        text = src.get("text", "")[:150]
        score = src.get("score", 0)
        vis = src.get("visibility", "player_visible")
        tag = " [KP Only]" if vis == "kp_only" else ""
        lines.append(f"\n{i}. (score: {score:.2f}){tag}")
        lines.append(f"   {text}")

    await bot.send_private_msg(
        user_id=int(user_id),
        message="\n".join(lines)[:1500],
    )


async def send_state_result(bot: Bot, user_id: str, result: dict):
    """格式化并发送剧情状态"""
    lines = ["📊 当前剧情状态", "=" * 20]

    # 当前场景
    current = result.get("current_scene")
    if current:
        lines.append(f"\n📍 当前场景：{current.get('name', '?')}")
        lines.append(f"   {current.get('summary', '')[:200]}")
    else:
        lines.append("\n📍 当前场景：未设置")

    # 活跃 NPC
    npcs = result.get("active_npcs", [])
    if npcs:
        names = [n.get("name", "?") for n in npcs]
        lines.append(f"\n👥 活跃 NPC：{'、'.join(names)}")

    # 已发现线索
    discovered = result.get("discovered_clues", [])
    if discovered:
        names = [c.get("name", "?") for c in discovered]
        lines.append(f"\n🔓 已发现线索（{len(discovered)}）：{'、'.join(names)}")

    # 未发现线索
    undiscovered = result.get("undiscovered_clues", [])
    if undiscovered:
        names = [c.get("name", "?") for c in undiscovered]
        lines.append(f"\n🔒 未发现线索（{len(undiscovered)}）：{'、'.join(names)}")

    # 所有场景
    scenes = result.get("scenes", [])
    if scenes:
        lines.append(f"\n🗺️ 场景进度：")
        for s in scenes:
            marker = "📍" if s.get("is_active") else "  "
            lines.append(f"  {marker} {s.get('name', '?')}")

    await bot.send_private_msg(
        user_id=int(user_id),
        message="\n".join(lines)[:1500],
    )
