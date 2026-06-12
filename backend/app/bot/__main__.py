"""QQ Bot startup — ChronicleAgent."""

import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    print("=" * 50)
    print("  ChronicleAgent QQ Bot")
    print("=" * 50)

    from app.bot.config import bot_settings
    ws_url = bot_settings.napcat_ws_url
    os.environ["ONEBOT_WS_URLS"] = json.dumps([ws_url])

    import nonebot
    from nonebot import on_message, logger
    from nonebot.adapters.onebot.v11 import Bot as V11Bot, Adapter

    nonebot.init(driver="~httpx+~websockets", onebot_ws_urls=[ws_url])
    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)

    # Lazy imports (after nonebot.init)
    from app.bot.api_client import api_client
    from app.bot.binding import store
    from app.bot.commands import parse_command, get_help_text, REMOTE_COMMANDS, LOCAL_COMMANDS

    msg = on_message(priority=1, block=False)

    @msg.handle()
    async def handle_all(bot: V11Bot, event):
        user_id = str(event.user_id) if hasattr(event, "user_id") else ""
        raw_text = event.get_plaintext().strip() if hasattr(event, "get_plaintext") else ""

        if not raw_text or not user_id:
            return

        logger.info("MSG from=%s text=%s", user_id, raw_text[:100])

        is_private = hasattr(event, "message_type") and event.message_type == "private"
        is_group = hasattr(event, "message_type") and event.message_type == "group"

        if is_private:
            await _handle_private(bot, user_id, raw_text)
        elif is_group:
            await _handle_group(bot, event, user_id, raw_text)

    async def _handle_private(bot: V11Bot, user_id: str, text: str):
        parsed = parse_command(text)
        if parsed is None:
            return
        cmd, args = parsed
        logger.info("CMD from=%s cmd=%s args=%s", user_id, cmd, args)

        if cmd in LOCAL_COMMANDS:
            await _handle_local_cmd(bot, user_id, cmd, args)
        elif cmd in REMOTE_COMMANDS:
            await _handle_remote_cmd(bot, user_id, cmd, args)
        else:
            await bot.send_private_msg(
                user_id=int(user_id),
                message="未知指令: /" + cmd + "\n\n" + get_help_text(),
            )

    async def _handle_local_cmd(bot: V11Bot, user_id: str, cmd: str, args: str):
        if cmd in ("help", "帮助"):
            await bot.send_private_msg(user_id=int(user_id), message=get_help_text())

        elif cmd == "绑定团":
            if not args:
                await bot.send_private_msg(user_id=int(user_id), message="用法: /绑定团 <campaign_id>")
                return
            cid = args.strip()
            try:
                await api_client.bind_kp(cid, user_id)
                store.bind_kp(user_id, cid)
                await bot.send_private_msg(user_id=int(user_id), message="已绑定团: " + cid + "\n使用 /当前状态 查看剧情信息。")
            except Exception as e:
                await bot.send_private_msg(user_id=int(user_id), message="绑定失败: " + str(e)[:100])

        elif cmd == "解绑团":
            cid = store.get_campaign_for_kp(user_id)
            if not cid:
                try:
                    data = await api_client.get_campaign_by_kp(user_id)
                    cid = data.get("id") if data else None
                except Exception:
                    pass
            if not cid:
                await bot.send_private_msg(user_id=int(user_id), message="未绑定任何团。")
                return
            try:
                await api_client.unbind_kp(cid)
                store.unbind_kp(user_id)
                await bot.send_private_msg(user_id=int(user_id), message="已解绑团: " + cid)
            except Exception as e:
                await bot.send_private_msg(user_id=int(user_id), message="解绑失败: " + str(e)[:100])

        elif cmd == "群绑定":
            parts = args.split(None, 1)
            if len(parts) < 2:
                await bot.send_private_msg(user_id=int(user_id), message="用法: /群绑定 <群号> <campaign_id>")
                return
            store.bind_group(parts[0], parts[1])
            await bot.send_private_msg(user_id=int(user_id), message="群 " + parts[0] + " -> " + parts[1])

    async def _handle_remote_cmd(bot: V11Bot, user_id: str, cmd: str, args: str):
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

        try:
            if cmd in ("查线索", "search"):
                if not args:
                    await bot.send_private_msg(user_id=int(user_id), message="用法: /查线索 <关键词>")
                    return
                result = await api_client.rag_query(cid, args)
                sources = result.get("sources", [])
                if not sources:
                    await bot.send_private_msg(user_id=int(user_id), message="未找到相关结果。")
                    return
                lines = ["检索结果 " + "=" * 20]
                for i, s in enumerate(sources[:5], 1):
                    t = s.get("text", "")[:150]
                    sc = s.get("score", 0)
                    tag = " [KP]" if s.get("visibility") == "kp_only" else ""
                    lines.append("\n{}. (相关度:{:.2f}){}".format(i, sc, tag))
                    lines.append("   " + t)
                await bot.send_private_msg(user_id=int(user_id), message="\n".join(lines)[:1500])

            elif cmd in ("当前状态", "status"):
                result = await api_client.get_campaign_state(cid)
                lines = ["当前状态 " + "=" * 20]
                cur = result.get("current_scene")
                if cur:
                    lines.append("\n场景: " + cur.get("name", "?"))
                    s = cur.get("summary", "")[:200]
                    if s: lines.append("  " + s)
                else:
                    lines.append("\n场景: 未设定")
                npcs = result.get("active_npcs", [])
                if npcs:
                    lines.append("\nNPC: " + ", ".join(n.get("name","?") for n in npcs))
                disc = result.get("discovered_clues", [])
                if disc:
                    lines.append("\n已发现: " + ", ".join(c.get("name","?") for c in disc))
                undisc = result.get("undiscovered_clues", [])
                if undisc:
                    lines.append("\n未发现: " + ", ".join(c.get("name","?") for c in undisc))
                await bot.send_private_msg(user_id=int(user_id), message="\n".join(lines)[:1500])

            elif cmd in ("建议", "advice"):
                result = await api_client.kp_command(cid, "advice", args)
                await bot.send_private_msg(user_id=int(user_id), message=result.get("suggestion", "暂无建议。"))

            elif cmd in ("总结", "summary"):
                result = await api_client.generate_summary(cid)
                s = result.get("markdown", "")
                await bot.send_private_msg(user_id=int(user_id), message=s[:1500] if s else "团录尚未生成。")

        except Exception as e:
            await bot.send_private_msg(user_id=int(user_id), message="指令执行失败: " + str(e)[:200])

    async def _handle_group(bot: V11Bot, event, user_id: str, text: str):
        group_id = str(event.group_id)
        cid = store.get_campaign_for_group(group_id)
        if not cid:
            return

        sender = (event.sender.card or event.sender.nickname or user_id) if hasattr(event, "sender") else user_id
        try:
            result = await api_client.handle_message(campaign_id=cid, sender=sender, content=text)
        except Exception:
            return

        if not result.get("need_kp_notify", False):
            return

        try:
            kp_qq = await api_client.get_kp_qq(cid)
            if kp_qq:
                parts = ["[消息提醒]"]
                if result.get("message_type") == "player_action":
                    parts[0] = "[玩家行动]"
                elif result.get("message_type") == "roleplay":
                    parts[0] = "[角色扮演]"
                sug = result.get("kp_suggestion", "")
                if sug: parts.append("\n\n" + sug[:800])
                await bot.send_private_msg(user_id=int(kp_qq), message="\n".join(parts))
        except Exception:
            pass

    print("  API:  ", bot_settings.api_base_url)
    print("  NapCat:", bot_settings.napcat_ws_url)
    print("  Bot QQ:", bot_settings.bot_qq or "?")
    print()
    nonebot.run()


if __name__ == "__main__":
    main()
