#!/usr/bin/env python3
"""Patch bot __main__.py with debug logging for group message tracing."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/opt/QQ-TRPG-Agent/backend/app/bot/__main__.py"

with open(path, "r") as f:
    content = f.read()

# Patch 1: Add debug logging before _is_at_bot check in elif is_group block
old1 = """        elif is_group:
            if raw_text:
                if not _is_at_bot(event, user_id):
                    return
                await _handle_group(bot, event, user_id, raw_text)"""

new1 = """        elif is_group:
            if raw_text:
                logger.info("AT_CHECK: bot_qq=%s, msg_type=%s, has_msg=%s, text=%s",
                    bot_settings.bot_qq,
                    event.message_type if hasattr(event, "message_type") else "?",
                    hasattr(event, "message"),
                    raw_text[:80])
                if not _is_at_bot(event, user_id):
                    logger.info("AT_CHECK: _is_at_bot returned False, skipping")
                    return
                group_id = str(event.group_id) if hasattr(event, "group_id") else "?"
                cid = store.get_campaign_for_group(group_id)
                logger.info("GROUP_HANDLE: group_id=%s, cid=%s", group_id, cid)
                await _handle_group(bot, event, user_id, raw_text)"""

if old1 in content:
    content = content.replace(old1, new1)
    print("Patch 1 applied: elif is_group debug logging")
else:
    print("WARNING: Patch 1 pattern not found!")
    # Try finding partial match for diagnosis
    if "elif is_group:" in content:
        print("  Found 'elif is_group:' in file")
        idx = content.index("elif is_group:")
        print("  Context:", repr(content[idx:idx+200]))
    else:
        print("  'elif is_group:' NOT found!")

# Patch 2: Add debug logging to _handle_group function
old2 = """    async def _handle_group(bot: V11Bot, event, user_id: str, text: str):
        group_id = str(event.group_id)
        cid = store.get_campaign_for_group(group_id)
        if not cid:
            return"""

new2 = """    async def _handle_group(bot: V11Bot, event, user_id: str, text: str):
        group_id = str(event.group_id)
        cid = store.get_campaign_for_group(group_id)
        logger.info("_handle_group ENTER: group_id=%s, cid=%s, text=%s", group_id, cid, text[:100])
        if not cid:
            logger.info("_handle_group: no cid for group %s, returning", group_id)
            return"""

if old2 in content:
    content = content.replace(old2, new2)
    print("Patch 2 applied: _handle_group debug logging")
else:
    print("WARNING: Patch 2 pattern not found!")
    if "async def _handle_group" in content:
        idx = content.index("async def _handle_group")
        print("  Context:", repr(content[idx:idx+300]))
    else:
        print("  'async def _handle_group' NOT found!")

# Patch 3: Add debug logging when calling api_client.handle_message
old3 = """        try:
            result = await api_client.handle_message(
                campaign_id=cid, sender=sender, content=text)
        except Exception as e:"""

new3 = """        try:
            logger.info("_handle_group: calling api_client.handle_message cid=%s sender=%s", cid, sender)
            result = await api_client.handle_message(
                campaign_id=cid, sender=sender, content=text)
            logger.info("_handle_group: api returned need_kp=%s public_reply_len=%s",
                result.get("need_kp_notify"), len(result.get("public_reply", "")))
        except Exception as e:"""

if old3 in content:
    content = content.replace(old3, new3)
    print("Patch 3 applied: api_client.handle_message debug logging")
else:
    print("WARNING: Patch 3 pattern not found!")
    if "api_client.handle_message" in content:
        idx = content.index("api_client.handle_message")
        print("  Context:", repr(content[idx-50:idx+200]))
    else:
        print("  'api_client.handle_message' NOT found!")

# Patch 4: Add debug logging after sending public_reply
old4 = """        if public_reply:
            try:
                await bot.send(event, public_reply[:1000])
            except Exception as e:"""

new4 = """        if public_reply:
            try:
                await bot.send(event, public_reply[:1000])
                logger.info("_handle_group: sent public_reply to group")
            except Exception as e:"""

if old4 in content:
    content = content.replace(old4, new4)
    print("Patch 4 applied: send reply debug logging")
else:
    print("WARNING: Patch 4 pattern not found!")

with open(path, "w") as f:
    f.write(content)

print("Done. File written to", path)
