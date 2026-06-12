"""NoneBot2 event handlers."""

from nonebot import on_message, logger
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters import Event

from app.bot.api_client import api_client
from app.bot.binding import store
from app.bot.commands import parse_command, get_help_text, REMOTE_COMMANDS, LOCAL_COMMANDS


def _trace(msg):
    with open("/app/debug_handler.log", "a") as f:
        f.write(msg + "\n")


_trace("=== NEW MODULE v3 LOADED ===")

msg_matcher = on_message(priority=1, block=False)


@msg_matcher.handle()
async def handle_all_messages(bot: Bot, event: Event):
    _trace(">>> handle_all_messages ENTERED")

    try:
        # Check event type
        _trace("  event_type={}".format(type(event).__name__))
        _trace("  event_desc={}".format(str(event)[:200]))

        # Try to get text
        raw_text = ""
        if hasattr(event, 'get_plaintext'):
            raw_text = event.get_plaintext().strip()
        elif hasattr(event, 'get_message'):
            raw_text = str(event.get_message()).strip()
        elif hasattr(event, 'raw_message'):
            raw_text = str(event.raw_message).strip()
        _trace("  raw_text={}".format(raw_text))

        if not raw_text:
            _trace("  -> no text, skipping")
            return

        # Get user_id
        user_id = ""
        if hasattr(event, 'user_id'):
            user_id = str(event.user_id)
        _trace("  user_id={}".format(user_id))

        # Is it private message?
        is_private = hasattr(event, 'message_type') and event.message_type == 'private'
        _trace("  is_private={}".format(is_private))

        if is_private:
            # Echo immediately
            try:
                await bot.send_private_msg(
                    user_id=int(user_id),
                    message="[echo] " + raw_text[:50],
                )
                _trace("  echo OK")
            except Exception as e:
                _trace("  echo FAIL: {}".format(e))

            # Parse command
            parsed = parse_command(raw_text)
            _trace("  parsed={}".format(parsed))
            if parsed is None:
                return
            cmd, args = parsed
            _trace("  cmd={} args={}".format(cmd, args))

            if cmd in LOCAL_COMMANDS:
                await _handle_local(bot, user_id, cmd, args)
            elif cmd in REMOTE_COMMANDS:
                await _handle_remote(bot, user_id, cmd, args)
            else:
                await bot.send_private_msg(
                    user_id=int(user_id),
                    message="未知指令: /" + cmd + "\n\n" + get_help_text(),
                )

    except Exception as e:
        import traceback
        _trace("FATAL: {}\n{}".format(e, traceback.format_exc()))


async def _handle_local(bot, user_id, command, args):
    _trace("  _handle_local: {} {}".format(command, args))
    if command in ("help", "帮助"):
        await bot.send_private_msg(user_id=int(user_id), message=get_help_text())
    elif command == "绑定团":
        if not args:
            await bot.send_private_msg(user_id=int(user_id), message="用法: /绑定团 <campaign_id>")
            return
        cid = args.strip()
        await api_client.bind_kp(cid, user_id)
        store.bind_kp(user_id, cid)
        await bot.send_private_msg(user_id=int(user_id), message="已绑定团: " + cid)
    elif command == "群绑定":
        parts = args.split(None, 1)
        if len(parts) < 2:
            await bot.send_private_msg(user_id=int(user_id), message="用法: /群绑定 <群号> <campaign_id>")
            return
        store.bind_group(parts[0], parts[1])
        await bot.send_private_msg(user_id=int(user_id), message="群 {} -> {}".format(parts[0], parts[1]))


async def _handle_remote(bot, user_id, command, args):
    cid = store.get_campaign_for_kp(user_id)
    if not cid:
        try:
            data = await api_client.get_campaign_by_kp(user_id)
            if data and data.get("id"):
                cid = data["id"]
                store.bind_kp(user_id, cid)
        except Exception:
            pass
    if not cid:
        await bot.send_private_msg(user_id=int(user_id), message="请先 /绑定团 <campaign_id> 绑定跑团项目。")
        return
    # ... (rest similar)
    await bot.send_private_msg(user_id=int(user_id), message="远程指令: {} 参数: {}".format(command, args[:50]))
