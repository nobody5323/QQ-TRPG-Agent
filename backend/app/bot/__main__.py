"""QQ Bot startup — ChronicleAgent Phase 2."""
import json, os, sys, re, base64
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

    from app.bot.api_client import api_client
    from app.bot.binding import store
    from app.bot.commands import parse_command, get_help_text, REMOTE_COMMANDS, LOCAL_COMMANDS
    from app.bot.dice_parser import is_dice_message, parse_dice_message

    # ── Matcher 1: @bot messages (commands + group processing) ─
    msg = on_message(priority=1, block=False)
    _upload_waiting = set()

    # ── Matcher 2: ALL group messages (passive dice monitoring) ─
    dice_monitor = on_message(priority=99, block=False)

    def _is_at_bot(event, user_id: str) -> bool:
        bot_qq = bot_settings.bot_qq
        if not bot_qq:
            return False
        if hasattr(event, "message"):
            for seg in event.message:
                if hasattr(seg, "type") and seg.type == "at":
                    qq = seg.data.get("qq", "") if hasattr(seg, "data") else ""
                    if str(qq) == str(bot_qq):
                        return True
        return False

    def _get_file_segment(event):
        if hasattr(event, "message"):
            for seg in event.message:
                if hasattr(seg, "type") and seg.type == "file":
                    return seg
        return None


    # ═══════════════════════════════════════════════════════════
    #  Matcher 1: @bot handler
    # ═══════════════════════════════════════════════════════════

    @msg.handle()
    async def handle_all(bot: V11Bot, event):
        user_id = str(event.user_id) if hasattr(event, "user_id") else ""
        raw_text = event.get_plaintext().strip() if hasattr(event, "get_plaintext") else ""

        if not user_id:
            return

        logger.info("MSG from=%s text=%s", user_id, raw_text[:100])

        is_private = hasattr(event, "message_type") and event.message_type == "private"
        is_group = hasattr(event, "message_type") and event.message_type == "group"

        if is_private:
            file_seg = _get_file_segment(event)
            if file_seg and user_id in _upload_waiting:
                _upload_waiting.discard(user_id)
                await _handle_file_upload(bot, user_id, file_seg)
            elif raw_text:
                await _handle_private(bot, user_id, raw_text)
        elif is_group:
            if raw_text:
                if not _is_at_bot(event, user_id):
                    return
                await _handle_group(bot, event, user_id, raw_text)


    # ═══════════════════════════════════════════════════════════
    #  Matcher 2: passive dice monitoring (no @mention needed)
    # ═══════════════════════════════════════════════════════════

    @dice_monitor.handle()
    async def monitor_dice(bot: V11Bot, event):
        is_group = hasattr(event, "message_type") and event.message_type == "group"
        if not is_group:
            return
        raw_text = event.get_plaintext().strip() if hasattr(event, "get_plaintext") else ""
        if not raw_text:
            return
        if not is_dice_message(raw_text):
            return
        group_id = str(event.group_id) if hasattr(event, "group_id") else ""
        cid = store.get_campaign_for_group(group_id)
        if not cid:
            return
        dice = parse_dice_message(raw_text)
        if not dice:
            return
        sender = str(event.user_id)
        try:
            # Fire-and-forget: send dice result to backend for state tracking
            await api_client.handle_message(
                campaign_id=cid, sender=sender, content=raw_text)
        except Exception:
            pass


    # ═══════════════════════════════════════════════════════════
    #  Handler functions
    # ═══════════════════════════════════════════════════════════

    async def _handle_file_upload(bot: V11Bot, user_id: str, file_seg):
        file_name = file_seg.data.get("file", "unknown.md") if hasattr(file_seg, "data") else "unknown.md"
        file_id_val = file_seg.data.get("file_id", "") if hasattr(file_seg, "data") else ""
        ext = os.path.splitext(file_name)[1].lower()
        if ext not in (".md", ".txt", ".markdown", ".pdf"):
            await bot.send_private_msg(user_id=int(user_id),
                message="不支持的文件格式: {}\n支持: .md, .txt, .markdown, .pdf".format(ext))
            return
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
            await bot.send_private_msg(user_id=int(user_id),
                message="请先 /绑定团 <campaign_id> 绑定跑团项目，再上传模组文件。")
            return
        await bot.send_private_msg(user_id=int(user_id),
            message="正在接收并解析模组: {} ...".format(file_name))
        file_content = None
        try:
            if file_id_val:
                result = await bot.get_file(file_id=file_id_val)
                file_field = result.get("file", "") if isinstance(result, dict) else ""
                if file_field.startswith("base64://"):
                    file_content = base64.b64decode(file_field[9:])
                elif file_field.startswith("http"):
                    import httpx
                    async with httpx.AsyncClient(timeout=30) as client:
                        resp = await client.get(file_field)
                        resp.raise_for_status()
                        file_content = resp.content
                else:
                    url = result.get("url", "") if isinstance(result, dict) else ""
                    if url:
                        import httpx
                        async with httpx.AsyncClient(timeout=30) as client:
                            resp = await client.get(url)
                            resp.raise_for_status()
                            file_content = resp.content
        except Exception as e:
            logger.warning("File download failed: %s", str(e))
        if file_content is None:
            await bot.send_private_msg(user_id=int(user_id),
                message="文件下载失败，请重新发送。")
            return
        try:
            result = await api_client.upload_module(cid, file_name, file_content)
            lines = [
                "模组解析完成: " + str(result.get("title", file_name)),
                "场景: " + str(result.get("scenes", 0)) + " 个",
                "NPC: " + str(result.get("npcs", 0)) + " 个",
                "线索: " + str(result.get("clues", 0)) + " 个",
                "文本块: " + str(result.get("chunks", 0)) + " 个",
            ]
            await bot.send_private_msg(user_id=int(user_id), message="\n".join(lines))
        except Exception as e:
            await bot.send_private_msg(user_id=int(user_id),
                message="模组解析失败: " + str(e)[:200])


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
            await bot.send_private_msg(user_id=int(user_id),
                message="未知指令: /" + cmd + "\n\n" + get_help_text())


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
                await bot.send_private_msg(user_id=int(user_id),
                    message="已绑定团: " + cid + "\n使用 /当前状态 查看剧情信息。")
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
            parts = args.split(None, 2) if args else []
            if len(parts) < 2:
                await bot.send_private_msg(user_id=int(user_id),
                    message="用法: /群绑定 <群号> <campaign_id>")
                return
            # Verify KP owns this campaign
            kp_cid = store.get_campaign_for_kp(user_id)
            if kp_cid != parts[1]:
                await bot.send_private_msg(user_id=int(user_id),
                    message="你不是该团的 KP，无法进行群绑定。请先 /绑定团 " + parts[1])
                return
            store.bind_group(parts[0], parts[1])
            await bot.send_private_msg(user_id=int(user_id),
                message="群 " + parts[0] + " 已绑定到团 " + parts[1])
        elif cmd == "上传模组":
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
                await bot.send_private_msg(user_id=int(user_id),
                    message="请先 /绑定团 <campaign_id> 绑定跑团项目，再上传模组文件。")
                return
            _upload_waiting.add(user_id)
            await bot.send_private_msg(user_id=int(user_id),
                message="请发送模组文件（.md / .txt / .pdf），60 秒内有效。")


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
            await bot.send_private_msg(user_id=int(user_id),
                message="请先 /绑定团 <campaign_id> 绑定跑团项目。")
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
                    if s:
                        lines.append("  " + s)
                else:
                    lines.append("\n场景: 未设定")
                npcs = result.get("active_npcs", [])
                if npcs:
                    lines.append("\nNPC: " + ", ".join(n.get("name", "?") for n in npcs))
                disc = result.get("discovered_clues", [])
                if disc:
                    lines.append("\n已发现: " + ", ".join(c.get("name", "?") for c in disc))
                undisc = result.get("undiscovered_clues", [])
                if undisc:
                    lines.append("\n未发现: " + ", ".join(c.get("name", "?") for c in undisc))
                await bot.send_private_msg(user_id=int(user_id), message="\n".join(lines)[:1500])
            elif cmd in ("建议", "advice"):
                result = await api_client.kp_command(cid, "advice", args)
                await bot.send_private_msg(user_id=int(user_id),
                    message=result.get("suggestion", "暂无建议。"))
            elif cmd in ("总结", "summary"):
                result = await api_client.generate_summary(cid)
                s = result.get("markdown", "")
                await bot.send_private_msg(user_id=int(user_id),
                    message=s[:1500] if s else "团录尚未生成。")
        except Exception as e:
            await bot.send_private_msg(user_id=int(user_id),
                message="指令执行失败: " + str(e)[:200])


    async def _handle_group(bot: V11Bot, event, user_id: str, text: str):
        group_id = str(event.group_id)
        cid = store.get_campaign_for_group(group_id)
        if not cid:
            return

        sender = (event.sender.card or event.sender.nickname or user_id) if hasattr(event, "sender") else user_id
        try:
            result = await api_client.handle_message(
                campaign_id=cid, sender=sender, content=text)
        except Exception as e:
            logger.error("handle_message failed: %s", e)
            return

        # ── Send public reply to group ──
        public_reply = result.get("public_reply", "")
        if public_reply:
            try:
                await bot.send(event, public_reply[:1000])
            except Exception as e:
                logger.error("send group reply failed: %s", e)

        # ── Notify KP if needed ──
        if result.get("need_kp_notify", False):
            try:
                kp_qq = await api_client.get_kp_qq(cid)
                if kp_qq:
                    parts = ["[消息提醒]"]
                    mt = result.get("message_type", "")
                    if mt == "player_action":
                        parts[0] = "[玩家行动]"
                    elif mt == "roleplay":
                        parts[0] = "[角色扮演]"
                    sug = result.get("kp_suggestion", "")
                    if sug:
                        parts.append("\n\n" + sug[:800])
                    await bot.send_private_msg(user_id=int(kp_qq), message="\n".join(parts))
            except Exception:
                pass


    # ═══════════════════════════════════════════════════════════
    #  Boot
    # ═══════════════════════════════════════════════════════════
    print("  API:  ", bot_settings.api_base_url)
    print("  NapCat:", bot_settings.napcat_ws_url)
    print("  Bot QQ:", bot_settings.bot_qq or "?")
    print()
    nonebot.run()


if __name__ == "__main__":
    main()
