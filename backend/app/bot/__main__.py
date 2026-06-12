"""QQ Bot startup — minimal test."""

import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=" * 50)
    print("  ChronicleAgent QQ Bot (MINIMAL TEST)")
    print("=" * 50)

    from app.bot.config import bot_settings
    ws_url = bot_settings.napcat_ws_url
    print("  WebSocket target:", ws_url)

    os.environ["ONEBOT_WS_URLS"] = json.dumps([ws_url])

    import nonebot
    from nonebot import on_message, logger
    from nonebot.adapters.onebot.v11 import Bot as V11Bot, Adapter

    nonebot.init(driver="~httpx+~websockets", onebot_ws_urls=[ws_url])

    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)

    # ── INLINE MINIMAL HANDLER ──
    msg = on_message(priority=1, block=True)

    @msg.handle()
    async def _(bot: V11Bot, event):
        logger.error("!!! HANDLER FIRED !!!")
        logger.error("  bot: %s", type(bot).__name__)
        logger.error("  event: %s", type(event).__name__)

        if hasattr(event, "get_plaintext"):
            text = event.get_plaintext().strip()
        elif hasattr(event, "raw_message"):
            text = str(event.raw_message).strip()
        else:
            text = "[no text]"
        logger.error("  text: %s", text[:100])

        if hasattr(event, "message_type") and event.message_type == "private":
            try:
                await bot.send_private_msg(
                    user_id=int(event.user_id),
                    message="[bot] " + text[:30],
                )
                logger.error("  REPLY SENT")
            except Exception as e:
                logger.error("  REPLY FAILED: %s", e)
                import traceback
                traceback.print_exc()

    # Don't import handlers.py at all
    print("  Handler registered inline")
    print()
    nonebot.run()

if __name__ == "__main__":
    main()
