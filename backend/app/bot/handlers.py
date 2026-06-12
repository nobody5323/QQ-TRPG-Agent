"""NoneBot2 event handlers - group message + KP private commands."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, PrivateMessageEvent, MessageSegment,
)
from nonebot.params import EventMessage

import sys
from app.bot.api_client import api_client
from app.bot.binding import store
from app.bot.commands import parse_command, get_help_text, REMOTE_COMMANDS, LOCAL_COMMANDS


# ── Group message handler ──────────────────────────

group_msg = on_message(priority=1, block=False)


@group_msg.handle()
async def handle_group_message(
    bot: Bot,
    event: GroupMessageEvent,
    message: MessageSegment = EventMessage(),
):
    group_id = str(event.group_id)
    user_id = str(event.user_id)
    raw_text = event.raw_message.strip()

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
    message: MessageSegment = EventMessage(),
):
    user_id = str(event.user_id)
    raw_text = event.raw_message.strip()

    sys.stderr.write(f"[BOT] PRIVATE from {user_id}: {raw_text}\n")
    sys.stderr.flush()

    if not raw_text:
        return

    try:
        await bot.send_private_msg(
            user_id=int(user_id),
            message=f"收到: {raw_text}",
        )
        sys.stderr.write(f"[BOT] Reply sent OK\n")
        sys.stderr.flush()
    except Exception as e:
        sys.stderr.write(f"[BOT] Reply FAILED: {e}\n")
        sys.stderr.flush()

    parsed = parse_command(raw_text)
    if parsed is None:
        return

    command, args = parsed

    if command in LOCAL_COMMANDS:
        await handle_local_command(bot, user_id, command, args)
    elif command in REMOTE_COMMANDS:
        await handle_remote_command(bot, user_id, command, args)


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
                message="Usage: /bind <campaign_id>\nPlease provide a campaign ID.",
            )
            return
        campaign_id = args.strip()
        print(f"[DEBUG] Binding KP: user={user_id}, campaign={campaign_id}")
        # Persist binding to database via API
        try:
            result = await api_client.bind_kp(campaign_id, user_id)
            print(f"[DEBUG] API bind result: {result}")
            # Also cache locally for fast lookup
            store.bind_kp(user_id, campaign_id)
            await bot.send_private_msg(
                user_id=int(user_id),
                message="Bound campaign: " + campaign_id + "\nUse /status to check.",
            )
            print(f"[DEBUG] Bind success reply sent")
        except Exception as e:
            print(f"[DEBUG] Bind exception: {e}")
            import traceback
            traceback.print_exc()
            await bot.send_private_msg(
                user_id=int(user_id),
                message="Bind failed: " + str(e)[:100],
            )

    elif command == "解绑团":
        campaign_id = store.get_campaign_for_kp(user_id)
        if not campaign_id:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="No campaign bound yet.",
            )
            return
        try:
            await api_client.unbind_kp(campaign_id)
            store.unbind_kp(user_id)
            await bot.send_private_msg(
                user_id=int(user_id),
                message="Unbound campaign: " + campaign_id,
            )
        except Exception as e:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="Unbind failed: " + str(e)[:100],
            )

    elif command == "群绑定":
        parts = args.split(None, 1)
        if len(parts) < 2:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="Usage: /group-bind <group_id> <campaign_id>",
            )
            return
        group_id, cid = parts[0], parts[1]
        store.bind_group(group_id, cid)
        await bot.send_private_msg(
            user_id=int(user_id),
            message="Bound group " + group_id + " -> " + cid,
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
            message="Please /bind <campaign_id> first.",
        )
        return

    try:
        if command in ("查线索", "search"):
            if not args:
                await bot.send_private_msg(
                    user_id=int(user_id),
                    message="Usage: /search <keyword>",
                )
                return
            result = await api_client.rag_query(campaign_id, args)
            await send_rag_result(bot, user_id, result)

        elif command in ("当前状态", "status"):
            result = await api_client.get_campaign_state(campaign_id)
            await send_state_result(bot, user_id, result)

        elif command == "建议":
            result = await api_client.kp_command(campaign_id, "advice", args)
            await bot.send_private_msg(
                user_id=int(user_id),
                message=result.get("suggestion", "No advice available."),
            )

        elif command == "总结":
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
                    message="Summary not ready yet.",
                )

    except Exception as e:
        await bot.send_private_msg(
            user_id=int(user_id),
            message="Command failed: " + str(e)[:200],
        )


# ── Message formatting ─────────────────────────────

def format_kp_notification(result: dict) -> str:
    parts = []
    suggestion = result.get("kp_suggestion", "")
    msg_type = result.get("message_type", "action")

    if msg_type == "player_action":
        parts.append("[Player Action Detected]")
    elif msg_type == "roleplay":
        parts.append("[Roleplay]")
    elif msg_type == "rule_question":
        parts.append("[Rule Question]")
    else:
        parts.append("[Message Alert]")

    if suggestion:
        parts.append("\n\n" + suggestion[:800])

    return "\n".join(parts)


async def send_rag_result(bot: Bot, user_id: str, result: dict):
    sources = result.get("sources", [])
    if not sources:
        await bot.send_private_msg(
            user_id=int(user_id),
            message="No relevant results found.",
        )
        return

    lines = ["Search Results", "=" * 20]
    for i, src in enumerate(sources[:5], 1):
        text = src.get("text", "")[:150]
        score = src.get("score", 0)
        vis = src.get("visibility", "player_visible")
        tag = " [KP Only]" if vis == "kp_only" else ""
        lines.append("\n{}. (score: {:.2f}){}".format(i, score, tag))
        lines.append("   " + text)

    await bot.send_private_msg(
        user_id=int(user_id),
        message="\n".join(lines)[:1500],
    )


async def send_state_result(bot: Bot, user_id: str, result: dict):
    lines = ["Current State", "=" * 20]

    current = result.get("current_scene")
    if current:
        lines.append("\nScene: " + current.get("name", "?"))
        summary = current.get("summary", "")[:200]
        if summary:
            lines.append("  " + summary)
    else:
        lines.append("\nScene: not set")

    npcs = result.get("active_npcs", [])
    if npcs:
        names = [n.get("name", "?") for n in npcs]
        lines.append("\nNPCs: " + ", ".join(names))

    discovered = result.get("discovered_clues", [])
    if discovered:
        names = [c.get("name", "?") for c in discovered]
        lines.append("\nDiscovered ({}): ".format(len(discovered)) + ", ".join(names))

    undiscovered = result.get("undiscovered_clues", [])
    if undiscovered:
        names = [c.get("name", "?") for c in undiscovered]
        lines.append("\nUndiscovered ({}): ".format(len(undiscovered)) + ", ".join(names))

    await bot.send_private_msg(
        user_id=int(user_id),
        message="\n".join(lines)[:1500],
    )
