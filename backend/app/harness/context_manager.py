"""Context Manager — assembles campaign state for message processing.

Builds a snapshot of the current game state from the database:
- Active scene
- Active NPCs
- Undiscovered / discovered clues
- Recent messages
- Plot stage

This context is injected into the Orchestrator pipeline for:
1. Query enhancement (RAG)
2. Message classification (classifier needs to know what's happening)
3. Suggestion generation (KP needs full picture)
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.scene_repo import SceneRepository
from app.storage.npc_repo import NPCRepository
from app.storage.clue_repo import ClueRepository
from app.storage.message_repo import MessageRepository
from app.storage.campaign_repo import CampaignRepository
from app.config import settings


class ContextManager:
    """Assembles campaign state for message processing."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.scene_repo = SceneRepository(session)
        self.npc_repo = NPCRepository(session)
        self.clue_repo = ClueRepository(session)
        self.msg_repo = MessageRepository(session)
        self.campaign_repo = CampaignRepository(session)

    async def build(self, campaign_id: str) -> Dict[str, Any]:
        """Build complete campaign context.

        Returns dict with:
        - campaign_id, campaign_name
        - active_scene: {name, summary, order}
        - active_npcs: [{name, personality, visibility}]
        - undiscovered_clues: [{name, location, is_hidden}]
        - discovered_clues: [{name, location}]
        - recent_messages: [{sender, content, msg_type}]
        - scene_count, npc_count, clue_counts
        """
        context = {
            "campaign_id": campaign_id,
            "campaign_name": "",
            "active_scene": None,
            "active_npcs": [],
            "undiscovered_clues": [],
            "discovered_clues": [],
            "recent_messages": [],
            "scene_count": 0,
            "npc_count": 0,
            "discovered_count": 0,
            "undiscovered_count": 0,
        }

        # Campaign info
        campaign = await self.campaign_repo.get(campaign_id)
        if campaign:
            context["campaign_name"] = campaign.name

        # Active scene
        active_scene = await self.scene_repo.get_active(campaign_id)
        if active_scene:
            context["active_scene"] = {
                "id": active_scene.id,
                "name": active_scene.name,
                "summary": active_scene.summary or "",
                "order": active_scene.order,
            }

        # All scenes (for scene count)
        all_scenes = await self.scene_repo.get_by_campaign(campaign_id)
        context["scene_count"] = len(all_scenes)

        # NPCs
        all_npcs = await self.npc_repo.get_by_campaign(campaign_id)
        context["active_npcs"] = [
            {
                "id": n.id,
                "name": n.name,
                "personality": n.personality or "",
                "visibility": n.visibility or "kp_only",
            }
            for n in all_npcs
        ]
        context["npc_count"] = len(all_npcs)

        # Clues
        all_clues = await self.clue_repo.get_by_campaign(campaign_id)
        discovered = [c for c in all_clues if c.discovered]
        undiscovered = [c for c in all_clues if not c.discovered]
        context["discovered_clues"] = [
            {"id": c.id, "name": c.name, "location": c.location or ""}
            for c in discovered
        ]
        context["undiscovered_clues"] = [
            {"id": c.id, "name": c.name, "location": c.location or "",
             "is_hidden": c.is_hidden, "trigger_condition": c.trigger_condition or ""}
            for c in undiscovered
        ]
        context["discovered_count"] = len(discovered)
        context["undiscovered_count"] = len(undiscovered)

        # Recent messages
        recent = await self.msg_repo.get_recent(
            campaign_id, limit=settings.MESSAGE_CONTEXT_SIZE
        )
        context["recent_messages"] = [
            {
                "id": m.id,
                "sender": m.sender,
                "content": m.content[:200],
                "msg_type": m.msg_type,
                "role": m.role,
            }
            for m in recent
        ]

        return context

    async def build_rag_context(self, campaign_id: str) -> Dict[str, Any]:
        """Lightweight context specifically for RAG query enhancement.

        Returns only what the retriever needs:
        - scene_name
        - npc_names
        - undiscovered_clue_names
        """
        active_scene = await self.scene_repo.get_active(campaign_id)
        scene_name = active_scene.name if active_scene else None

        all_npcs = await self.npc_repo.get_by_campaign(campaign_id)
        npc_names = [n.name for n in all_npcs]

        undiscovered = await self.clue_repo.get_undiscovered(campaign_id)
        undiscovered_names = [c.name for c in undiscovered]

        return {
            "scene_name": scene_name,
            "npc_names": npc_names,
            "undiscovered_clue_names": undiscovered_names,
        }


async def build_context(session: AsyncSession, campaign_id: str) -> Dict[str, Any]:
    """Convenience function: build full context in one call."""
    cm = ContextManager(session)
    return await cm.build(campaign_id)


async def build_rag_context(session: AsyncSession, campaign_id: str) -> Dict[str, Any]:
    """Convenience function: build RAG context in one call."""
    cm = ContextManager(session)
    return await cm.build_rag_context(campaign_id)
