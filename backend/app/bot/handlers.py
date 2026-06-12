"""NoneBot2 event handlers - group message + KP private commands."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, PrivateMessageEvent,
)

from app.bot.api_client import api_client
from app.bot.binding import store
from app.bot.commands import parse_command, get_help_text, REMOTE_COMMANDS, LOCAL_COMMANDS


# ── Group message handler ──────────────────────────

group_msg = on_message(priority=1, block=False)


@group_msg.handle()
async def handle_group_message(
    bot: Bot,
    event: GroupMessageEvent,
):
    group_id = str(event.group_id)
    user_id = str(event.user_id)
    raw_text = str(event.get_message()).strip()

    if not raw_text:
        return

    # Get campaign from cache, then try API
    campaign_id = store.get_campaign_for_group(group_id)
    if not campaign_id:
        return  # no binding yet

    sender_name = event.sender.card or event.sender.nickname or user_id

    try:
        result = await api_client.handle_message(
            campaign_id=campaign_id,
            sender=sender_name,
            content=raw_text,
        )
    except Exception:
        return

    need_notify = result.get("need_kp_notify", False)
    if not need_notify:
        return

    # Look up KP QQ from backend (persistent, supports multiple KPs)
    try:
        kp_qq = await api_client.get_kp_qq(campaign_id)
        if kp_qq:
            await bot.send_private_msg(
                user_id=int(kp_qq),
                message=format_kp_notification(result),
            )
    except Exception:
        pass


# ── KP private message handler ─────────────────────

private_msg = on_message(priority=1, block=False)


@private_msg.handle()
async def handle_private_message(
    bot: Bot,
    event: PrivateMessageEvent,
):
    user_id = str(event.user_id)
    raw_text = str(event.get_message()).strip()

    if not raw_text:
        return

    parsed = parse_command(raw_text)
    if parsed is None:
        return

    command, args = parsed

    if command in LOCAL_COMMANDS:
        await handle_local_command(bot, user_id, command, args)
    elif command in REMOTE_COMMANDS:
        await handle_remote_command(bot, user_id, command, args)
    else:
        await bot.send_private_msg(
            user_id=int(user_id),
            message="未知指令: /" + command + "\n\n" + get_help_text(),
        )


# ── Local commands (no backend needed) ─────────────

async def handle_local_command(
    bot: Bot, user_id: str, command: str, args: str
):
    if command == "help" or command == "帮助":
        await bot.send_private_msg(
            user_id=int(user_id),
            message=get_help_text(),
        )

    elif command == "绑定团":
        if not args:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="用法: /绑定团 <campaign_id>\n例如: /绑定团 27d1ae68-8b85-4fc4-beb1-f0a44686e7ba",
            )
            return
        campaign_id = args.strip()
        try:
            await api_client.bind_kp(campaign_id, user_id)
            store.bind_kp(user_id, campaign_id)
            await bot.send_private_msg(
                user_id=int(user_id),
                message="已绑定团: " + campaign_id + "\n使用 /当前状态 查看剧情信息。",
            )
        except Exception as e:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="绑定失败: " + str(e)[:100],
            )

    elif command == "解绑团":
        campaign_id = store.get_campaign_for_kp(user_id)
        if not campaign_id:
            try:
                data = await api_client.get_campaign_by_kp(user_id)
                campaign_id = data.get("id")
            except Exception:
                pass
        if not campaign_id:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="未绑定任何团。",
            )
            return
        try:
            await api_client.unbind_kp(campaign_id)
            store.unbind_kp(user_id)
            await bot.send_private_msg(
                user_id=int(user_id),
                message="已解绑团: " + campaign_id,
            )
        except Exception as e:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="解绑失败: " + str(e)[:100],
            )

    elif command == "群绑定":
        parts = args.split(None, 1)
        if len(parts) < 2:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="用法: /群绑定 <群号> <campaign_id>",
            )
            return
        group_id, cid = parts[0], parts[1]
        store.bind_group(group_id, cid)
        await bot.send_private_msg(
            user_id=int(user_id),
            message="群 " + group_id + " 已绑定到团: " + cid,
        )


# ── Remote commands (via FastAPI backend) ──────────

async def handle_remote_command(
    bot: Bot, user_id: str, command: str, args: str
):
    # Try local cache first, then API
    campaign_id = store.get_campaign_for_kp(user_id)
    if not campaign_id:
        # Fall back to API lookup
        try:
            data = await api_client.get_campaign_by_kp(user_id)
            if data.get("id"):
                campaign_id = data["id"]
                store.bind_kp(user_id, campaign_id)  # cache it
        except Exception:
            pass

    if not campaign_id:
        await bot.send_private_msg(
            user_id=int(user_id),
            message="请先 /绑定团 <campaign_id> 绑定跑团项目。",
        )
        return

    try:
        if command in ("查线索", "search"):
            if not args:
                await bot.send_private_msg(
                    user_id=int(user_id),
                    message="用法: /查线索 <关键词>",
                )
                return
            result = await api_client.rag_query(campaign_id, args)
            await send_rag_result(bot, user_id, result)

        elif command in ("当前状态", "status"):
            result = await api_client.get_campaign_state(campaign_id)
            await send_state_result(bot, user_id, result)

        elif command in ("建议", "advice"):
            result = await api_client.kp_command(campaign_id, "advice", args)
            await bot.send_private_msg(
                user_id=int(user_id),
                message=result.get("suggestion", "暂无建议。"),
            )

        elif command in ("总结", "summary"):
            result = await api_client.generate_summary(campaign_id)
            summary = result.get("markdown", "")
            if summary:
                await bot.send_private_msg(
                    user_id=int(user_id),
                    message=summary[:1500],
                )
            else:
                await bot.send_private_msg(
                    user_id=int(user_id),
                    message="团录尚未生成。",
                )

    except Exception as e:
        await bot.send_private_msg(
            user_id=int(user_id),
            message="指令执行失败: " + str(e)[:200],
        )


# ── Message formatting ─────────────────────────────

def format_kp_notification(result: dict) -> str:
    parts = []
    suggestion = result.get("kp_suggestion", "")
    msg_type = result.get("message_type", "action")

    if msg_type == "player_action":
        parts.append("[玩家行动]")
    elif msg_type == "roleplay":
        parts.append("[角色扮演]")
    elif msg_type == "rule_question":
        parts.append("[规则问题]")
    else:
        parts.append("[消息提醒]")

    if suggestion:
        parts.append("\n\n" + suggestion[:800])

    return "\n".join(parts)


async def send_rag_result(bot: Bot, user_id: str, result: dict):
    sources = result.get("sources", [])
    if not sources:
        await bot.send_private_msg(
            user_id=int(user_id),
            message="未找到相关结果。",
        )
        return

    lines = ["检索结果", "=" * 20]
    for i, src in enumerate(sources[:5], 1):
        text = src.get("text", "")[:150]
        score = src.get("score", 0)
        vis = src.get("visibility", "player_visible")
        tag = " [仅KP可见]" if vis == "kp_only" else ""
        lines.append("\n{}. (相关度: {:.2f}){}".format(i, score, tag))
        lines.append("   " + text)

    await bot.send_private_msg(
        user_id=int(user_id),
        message="\n".join(lines)[:1500],
    )


async def send_state_result(bot: Bot, user_id: str, result: dict):
    lines = ["当前状态", "=" * 20]

    current = result.get("current_scene")
    if current:
        lines.append("\n场景: " + current.get("name", "?"))
        summary = current.get("summary", "")[:200]
        if summary:
            lines.append("  " + summary)
    else:
        lines.append("\n场景: 未设定")

    npcs = result.get("active_npcs", [])
    if npcs:
        names = [n.get("name", "?") for n in npcs]
        lines.append("\nNPC: " + ", ".join(names))

    discovered = result.get("discovered_clues", [])
    if discovered:
        names = [c.get("name", "?") for c in discovered]
        lines.append("\n已发现线索 ({}): ".format(len(discovered)) + ", ".join(names))

    undiscovered = result.get("undiscovered_clues", [])
    if undiscovered:
        names = [c.get("name", "?") for c in undiscovered]
        lines.append("\n未发现线索 ({}): ".format(len(undiscovered)) + ", ".join(names))

    await bot.send_private_msg(
        user_id=int(user_id),
        message="\n".join(lines)[:1500],
    )
