"""NoneBot2 event handlers."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot

from app.bot.api_client import api_client
from app.bot.binding import store
from app.bot.commands import parse_command, get_help_text, REMOTE_COMMANDS, LOCAL_COMMANDS


def _trace(msg):
    with open("/app/debug_handler.log", "a") as f:
        f.write(msg + "\n")


_trace("=== v4 NO TYPE HINTS ===")

# Single matcher for ALL messages
msg_matcher = on_message(priority=1, block=False)


@msg_matcher.handle()
async def handle_all(bot, event):
    _trace("ENTER handler")
    _trace("  type(bot)=" + type(bot).__name__)
    _trace("  type(event)=" + type(event).__name__)

    # Direct echo test - no imports needed
    if hasattr(event, 'user_id') and hasattr(event, 'message_type') and event.message_type == 'private':
        try:
            await bot.send_private_msg(user_id=int(event.user_id), message="[echo v4] saw your message")
            _trace("  ECHO OK")
        except Exception as e:
            _trace("  ECHO FAIL: " + str(e))

        raw_text = str(event.get_plaintext()).strip() if hasattr(event, 'get_plaintext') else str(event.raw_message).strip()
        _trace("  text=" + raw_text)

        parsed = parse_command(raw_text)
        if parsed:
            cmd, args = parsed
            _trace("  cmd=" + cmd + " args=" + args)
            if cmd in LOCAL_COMMANDS:
                _trace("  -> LOCAL")
                if cmd == "绑定团" and args:
                    try:
                        await api_client.bind_kp(args.strip(), str(event.user_id))
                        store.bind_kp(str(event.user_id), args.strip())
                        await bot.send_private_msg(user_id=int(event.user_id), message="已绑定: " + args.strip())
                        _trace("  BIND OK")
                    except Exception as e:
                        _trace("  BIND FAIL: " + str(e))
    else:
        _trace("  not private, skipping")
