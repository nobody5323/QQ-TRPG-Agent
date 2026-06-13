"""NoneBot2 event handlers."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot

from app.bot.api_client import api_client
from app.bot.binding import store
from app.bot.commands import parse_command, get_help_text, REMOTE_COMMANDS, LOCAL_COMMANDS


def _trace(msg):
    with open("/app/debug_handler.log", "a") as f:
        f.write(msg + "\n")


_trace("=== v5 **kwargs ===")

msg_matcher = on_message(priority=1, block=False)


@msg_matcher.handle()
async def handle_all(**kwargs):
    _trace(">>> HANDLER ENTERED v5 <<<")
    _trace("  kwargs keys: " + str(list(kwargs.keys())))

    bot = kwargs.get("bot")
    event = kwargs.get("event")

    if bot is None or event is None:
        _trace("  MISSING bot or event")
        return

    _trace("  bot type: " + type(bot).__name__)
    _trace("  event type: " + type(event).__name__)

    if hasattr(event, "message_type") and hasattr(event, "user_id"):
        _trace("  msg_type=" + str(event.message_type) + " user=" + str(event.user_id))

    if hasattr(event, "get_plaintext"):
        raw_text = event.get_plaintext().strip()
    elif hasattr(event, "raw_message"):
        raw_text = str(event.raw_message).strip()
    else:
        raw_text = ""
    _trace("  text=" + raw_text[:100])

    # ECHO
    if hasattr(event, "message_type") and event.message_type == "private":
        try:
            await bot.send_private_msg(
                user_id=int(event.user_id),
                message="[v5] 收到: " + raw_text[:30],
            )
            _trace("  ECHO OK")
        except Exception as e:
            _trace("  ECHO FAIL: " + str(e))
