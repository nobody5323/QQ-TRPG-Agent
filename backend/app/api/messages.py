"""API：消息处理 — 群聊消息接收 + KP 指令处理

由 NoneBot2 独立进程通过 HTTP 调用，不直接处理 QQ 协议。

端点：
  POST /api/messages/handle     — 群聊消息处理
  POST /api/messages/kp-command — KP 指令处理
"""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_session
from app.storage.message_repo import MessageRepository
from app.storage.scene_repo import SceneRepository
from app.storage.clue_repo import ClueRepository
from app.storage.npc_repo import NPCRepository
from app.rag.retriever import retriever
from app.rag.embedding import embedding_service

router = APIRouter()


# ── 请求/响应模型 ──────────────────────────────────

class HandleMessageRequest(BaseModel):
    campaign_id: str = Field(..., description="跑团项目 ID")
    sender: str = Field(..., description="发送者昵称")
    content: str = Field(..., description="消息内容")


class HandleMessageResponse(BaseModel):
    need_kp_notify: bool = False
    kp_suggestion: str = ""
    message_type: str = "unknown"


class KPCommandRequest(BaseModel):
    campaign_id: str = Field(..., description="跑团项目 ID")
    command: str = Field(..., description="指令名称")
    args: str = Field("", description="指令参数")


class KPCommandResponse(BaseModel):
    success: bool = True
    message: str = ""
    suggestion: str = ""


# ── Phase 1 简单的消息类型分类 ───────────────────
# Phase 2 将替换为 Classifier Agent

SIMPLE_RULES = {
    "调查": "player_action",
    "搜索": "player_action",
    "检查": "player_action",
    "查看": "player_action",
    "询问": "player_action",
    "对话": "roleplay",
    "我想": "player_action",
    "我要": "player_action",
    "使用": "player_action",
    "走": "player_action",
    "去": "player_action",
}


def simple_classify(content: str) -> dict:
    """简单的基于关键词的消息分类

    Returns:
        {message_type, need_rag, need_kp_suggestion, need_state_update}
    """
    for keyword, msg_type in SIMPLE_RULES.items():
        if keyword in content:
            return {
                "message_type": msg_type,
                "need_rag": True,
                "need_kp_suggestion": True,
                "need_state_update": True,
            }

    # 含问句或骰点指令
    if "?" in content or "？" in content or content.startswith(".r") or content.startswith("。"):
        return {
            "message_type": "player_action",
            "need_rag": True,
            "need_kp_suggestion": True,
            "need_state_update": False,
        }

    # 默认
    return {
        "message_type": "chat",
        "need_rag": False,
        "need_kp_suggestion": False,
        "need_state_update": False,
    }


# ── 群聊消息处理 ──────────────────────────────────

@router.post("/handle", response_model=HandleMessageResponse)
async def handle_message(
    body: HandleMessageRequest,
    session: AsyncSession = Depends(get_session),
):
    """处理群聊消息

    1. 保存消息到数据库
    2. 分类消息类型
    3. 如果需要，执行 RAG 检索
    4. 组装 KP 建议
    5. 返回是否需要通知 KP
    """
    # 1. 保存消息
    msg_repo = MessageRepository(session)
    await msg_repo.create(
        campaign_id=body.campaign_id,
        sender=body.sender,
        content=body.content,
        msg_type="group",
        role="player",
    )

    # 2. 简单分类
    classification = simple_classify(body.content)

    if not classification["need_kp_suggestion"]:
        return HandleMessageResponse(
            need_kp_notify=False,
            kp_suggestion="",
            message_type=classification["message_type"],
        )

    # 3. 获取剧情上下文
    scene_repo = SceneRepository(session)
    clue_repo = ClueRepository(session)
    npc_repo = NPCRepository(session)

    active_scene = await scene_repo.get_active(body.campaign_id)
    scene_name = active_scene.name if active_scene else None

    undiscovered = await clue_repo.get_undiscovered(body.campaign_id)
    undiscovered_names = [c.name for c in undiscovered]

    all_npcs = await npc_repo.get_by_campaign(body.campaign_id)
    npc_names = [n.name for n in all_npcs]

    # 4. 执行 RAG 检索
    try:
        result = await retriever.search(
            query=body.content,
            campaign_id=body.campaign_id,
            scene_context=scene_name,
            active_npcs=npc_names,
            undiscovered_clue_names=undiscovered_names,
            top_k=5,
        )

        search_results = result.get("results", [])
        meta = result.get("meta", {})

        # 5. 组装建议
        suggestion_parts = [
            f"消息来源：{body.sender}",
            f"消息内容：{body.content}",
            f"\n类型：{classification['message_type']}",
        ]

        if scene_name:
            suggestion_parts.append(f"\n当前场景：{scene_name}")

        if search_results:
            suggestion_parts.append(f"\n🔍 相关模组内容（检索用时 {meta.get('latency_ms', '?')}ms）：")
            for i, r in enumerate(search_results[:3], 1):
                payload = r.get("payload", {}) or {}
                text = payload.get("text", "")[:200]
                visibility = payload.get("visibility", "player_visible")
                title = payload.get("title", "")
                prefix = f"[{title}] " if title else ""
                tag = "（🔒 KP Only）" if visibility == "kp_only" else ""
                suggestion_parts.append(f"\n{i}. {prefix}{text}{tag}")

        suggestion = "\n".join(suggestion_parts)

    except Exception as e:
        suggestion = f"检索异常：{str(e)[:200]}"

    return HandleMessageResponse(
        need_kp_notify=True,
        kp_suggestion=suggestion,
        message_type=classification["message_type"],
    )


# ── KP 指令处理 ──────────────────────────────────

@router.post("/kp-command", response_model=KPCommandResponse)
async def kp_command(
    body: KPCommandRequest,
    session: AsyncSession = Depends(get_session),
):
    """处理 KP 指令

    支持的指令：
    - 建议：获取当前建议（基于最新消息 + RAG 检索）
    - 修正状态：手动修正剧情状态
    """
    command = body.command.strip().lower()
    campaign_id = body.campaign_id

    # 建议指令
    if command == "建议":
        msg_repo = MessageRepository(session)
        scene_repo = SceneRepository(session)
        clue_repo = ClueRepository(session)
        npc_repo = NPCRepository(session)

        # 获取最近消息
        recent_messages = await msg_repo.get_recent(campaign_id, limit=10)

        # 获取剧情状态
        active_scene = await scene_repo.get_active(campaign_id)
        scene_name = active_scene.name if active_scene else "未知"
        undiscovered = await clue_repo.get_undiscovered(campaign_id)
        all_npcs = await npc_repo.get_by_campaign(campaign_id)
        npc_names = [n.name for n in all_npcs]

        lines = ["📋 当前跑团建议", "=" * 20]

        lines.append(f"\n📍 当前场景：{scene_name}")

        if npc_names:
            lines.append(f"👥 活跃 NPC：{'、'.join(npc_names)}")

        if undiscovered:
            lines.append(f"\n🔒 未发现线索：")
            for c in undiscovered[:5]:
                hint = f"（{c.location}）" if c.location else ""
                hidden = "🔑隐藏" if c.is_hidden else ""
                lines.append(f"  - {c.name} {hint} {hidden}")

        if recent_messages:
            lines.append(f"\n💬 最近消息（{len(recent_messages)} 条）：")
            for msg in recent_messages[-5:]:
                content = msg.content[:80]
                lines.append(f"  {msg.sender}：{content}")

        suggestion = "\n".join(lines)

        return KPCommandResponse(
            success=True,
            message="建议生成完成",
            suggestion=suggestion,
        )

    # 默认
    return KPCommandResponse(
        success=False,
        message=f"未知指令：{command}",
        suggestion="",
    )
