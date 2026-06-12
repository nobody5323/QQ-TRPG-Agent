"""QQ Bot startup — ChronicleAgent."""

import json, os, sys, base64
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

        if not user_id:
            return

        logger.info("MSG from=%s text=%s", user_id, raw_text[:100])

        is_private = hasattr(event, "message_type") and event.message_type == "private"
        is_group = hasattr(event, "message_type") and event.message_type == "group"

        if is_private:
            file_seg = _get_file_segment(event)
            if file_seg:
                await _handle_file_upload(bot, user_id, file_seg)
            if raw_text:
                await _handle_private(bot, user_id, raw_text)
        elif is_group:
            if raw_text:
                await _handle_group(bot, event, user_id, raw_text)

    def _get_file_segment(event):
        """Extract file segment from message if present."""
        if hasattr(event, "message"):
            for seg in event.message:
                if hasattr(seg, "type") and seg.type == "file":
                    return seg
        return None

    async def _handle_file_upload(bot: V11Bot, user_id: str, file_seg):
        """Handle KP file upload: download file → POST to backend → reply result."""
        file_name = file_seg.data.get("file", "unknown.md") if hasattr(file_seg, "data") else "unknown.md"
        file_id_val = file_seg.data.get("file_id", "") if hasattr(file_seg, "data") else ""

        ext = os.path.splitext(file_name)[1].lower()
        if ext not in (".md", ".txt", ".markdown", ".pdf"):
            await bot.send_private_msg(
                user_id=int(user_id),
                message="不支持的文件格式: {}\n支持: .md, .txt, .markdown, .pdf".format(ext),
            )
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
            await bot.send_private_msg(
                user_id=int(user_id),
                message="请先 /绑定团 <campaign_id> 绑定跑团项目，再上传模组文件。",
            )
            return

        await bot.send_private_msg(
            user_id=int(user_id),
            message="正在接收并解析模组: {} ...".format(file_name),
        )

        # Download file via OneBot get_file API
        file_content = None
        try:
            if file_id_val:
                result = await bot.get_file(file_id=file_id_val)
                file_field = result.get("file", "") if isinstance(result, dict) else ""
                if file_field.startswith("base64://"):
                    file_content = base64.b64decode(file_field[9:])
                elif file_field.startswith("http://") or file_field.startswith("https://"):
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
            await bot.send_private_msg(
                user_id=int(user_id),
                message="文件下载失败，NapCat 可能未返回可下载的文件链接。请尝试重新发送文件，或在 WebUI 上传模组。",
            )
            return

        # POST to backend
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
            await bot.send_private_msg(
                user_id=int(user_id),
                message="模组解析失败: " + str(e)[:200],
            )

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

        elif cmd == "上传模组":
            await bot.send_private_msg(
                user_id=int(user_id),
                message="直接发送 .md / .txt / .pdf 模组文件给 Bot 即可自动解析入库。\n无需额外指令，把文件拖进聊天框发送即可。",
            )

    async def _handle_remote_cmd(bot: V11Bot, user_id: str, cmd: str, args: str):
        cid = store.get_campaign_for_kp(user_id)
        if not cid:
            try:
                data = await api_client.get_c