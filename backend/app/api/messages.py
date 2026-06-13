"""API: message handling — group message processing + KP commands.

Messages flow through the Orchestrator pipeline:
  save -> build context -> classify -> RAG retrieve -> suggest -> trace

Endpoints:
  POST /api/messages/handle      — process group message via Orchestrator
  POST /api/messages/kp-command  — KP command execution
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
from app.harness.orchestrator import Orchestrator

router = APIRouter()


# ── Request/Response models ──────────────────────

class HandleMessageRequest(BaseModel):
    campaign_id: str = Field(..., description="Campaign ID")
    sender: str = Field(..., description="Sender display name")
    content: str = Field(..., description="Message content")


class HandleMessageResponse(BaseModel):
    need_kp_notify: bool = False
    kp_suggestion: str = ""
    public_reply: str = ""
    message_type: str = "unknown"


class KPCommandRequest(BaseModel):
    campaign_id: str = Field(..., description="Campaign ID")
    command: str = Field(..., description="Command name")
    args: str = Field("", description="Command arguments")


class KPCommandResponse(BaseModel):
    success: bool = True
    message: str = ""
    suggestion: str = ""


# ── Group message handling (via Orchestrator) ───

@router.post("/handle", response_model=HandleMessageResponse)
async def handle_message(
    body: HandleMessageRequest,
    session: AsyncSession = Depends(get_session),
):
    """Process a group chat message through the Orchestrator.

    1. Save message
    2. Build campaign context
    3. Classify message (LLM)
    4. RAG retrieval (if needed)
    5. Build KP suggestion
    6. Record trace
    """
    orchestrator = Orchestrator(session)
    result = await orchestrator.process(
        campaign_id=body.campaign_id,
        sender=body.sender,
        content=body.content,
    )

    return HandleMessageResponse(
        need_kp_notify=result.get("need_kp_notify", False),
        kp_suggestion=result.get("kp_suggestion", ""),
        public_reply=result.get("public_reply", ""),
        message_type=result.get("message_type", "unknown"),
    )


# ── KP command handling ──────────────────────────

@router.post("/kp-command", response_model=KPCommandResponse)
async def kp_command(
    body: KPCommandRequest,
    session: AsyncSession = Depends(get_session),
):
    """Process KP commands.

    Supported commands:
    - advice: get current state + suggestions for KP
    """
    command = body.command.strip().lower()
    campaign_id = body.campaign_id

    if command in ("advice", "建议"):
        msg_repo = MessageRepository(session)
        scene_repo = SceneRepository(session)
        clue_repo = ClueRepository(session)
        npc_repo = NPCRepository(session)

        recent_messages = await msg_repo.get_recent(campaign_id, limit=10)
        active_scene = await scene_repo.get_active(campaign_id)
        scene_name = active_scene.name if active_scene else "unknown"
        undiscovered = await clue_repo.get_undiscovered(campaign_id)
        discovered = await clue_repo.get_discovered(campaign_id)
        all_npcs = await npc_repo.get_by_campaign(campaign_id)
        npc_names = [n.name for n in all_npcs]

        lines = ["Current Campaign Advice", "=" * 20]
        lines.append("\nScene: {}".format(scene_name))

        if npc_names:
            lines.append("NPCs: {}".format(", ".join(npc_names)))

        if undiscovered:
            lines.append("\nUndiscovered clues:")
            for c in undiscovered[:5]:
                hint = " ({})".format(c.location) if c.location else ""
                hidden = " [Hidden]" if c.is_hidden else ""
                lines.append("  - {}{}{}".format(c.name, hint, hidden))

        if recent_messages:
            lines.append("\nRecent messages ({}):".format(len(recent_messages)))
            for msg in recent_messages[-5:]:
                lines.append("  {}: {}".format(msg.sender, msg.content[:80]))

        suggestion = "\n".join(lines)

        return KPCommandResponse(
            success=True,
            message="Advice generated",
            suggestion=suggestion,
        )

    return KPCommandResponse(
        success=False,
        message="Unknown command: " + command,
        suggestion="",
    )
