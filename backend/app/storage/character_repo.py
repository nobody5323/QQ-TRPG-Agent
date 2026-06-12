"""Character Repository — Player State management for Phase 2."""

from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.storage.base_repo import BaseRepository
from app.storage.models import Character


class CharacterRepository(BaseRepository[Character]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Character)

    async def get_by_campaign(self, campaign_id: str) -> List[Character]:
        stmt = select(Character).where(Character.campaign_id == campaign_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_player_qq(
        self, campaign_id: str, player_qq: str
    ) -> Optional[Character]:
        stmt = select(Character).where(
            Character.campaign_id == campaign_id,
            Character.player_qq == player_qq,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_player_name(
        self, campaign_id: str, player_name: str
    ) -> Optional[Character]:
        stmt = select(Character).where(
            Character.campaign_id == campaign_id,
            Character.player_name == player_name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self, character_id: str, status_update: dict
    ) -> Optional[Character]:
        char = await self.get(character_id)
        if not char:
            return None
        current = dict(char.status or {})
        current.update(status_update)
        return await self.update(character_id, status=current)

    async def apply_player_diff(
        self,
        campaign_id: str,
        player_qq: str,
        diff: Dict[str, Any],
    ) -> Optional[Character]:
        """Apply a Player State diff from the State Tracking Agent.

        If the character doesn't exist, creates one automatically.
        Respects KP overrides: if last_modified_by == "kp", don't overwrite
        SAN or inventory changes unless the diff comes from a KP action.
        """
        char = await self.get_by_player_qq(campaign_id, player_qq)
        if not char:
            char = await self.create(
                Character(
                    campaign_id=campaign_id,
                    player_qq=player_qq,
                    player_name=player_qq,
                    character_name=player_qq,
                    sanity=50,
                    skills={},
                    inventory=[],
                    personal_clues=[],
                    status_effects=[],
                    relationships={},
                    state_version=0,
                    last_modified_by="system",
                )
            )
            if not char:
                return None

        skip_auto = char.last_modified_by == "kp"

        updates = {}

        san_change = diff.get("sanity_change", 0)
        if san_change != 0 and not skip_auto:
            updates["sanity"] = (char.sanity or 50) + san_change

        skill_growth = diff.get("skill_growth", {})
        if skill_growth:
            current_skills = dict(char.skills or {})
            current_skills.update(skill_growth)
            updates["skills"] = current_skills

        inv_add = diff.get("inventory_add", [])
        inv_remove = diff.get("inventory_remove", [])
        if inv_add or inv_remove:
            current_inv = list(char.inventory or [])
            for item in inv_add:
                current_inv.append(item)
            for name in inv_remove:
                current_inv = [
                    i for i in current_inv
                    if i.get("name", i) != name
                ]
            updates["inventory"] = current_inv

        clue_add = diff.get("personal_clues_add", [])
        if clue_add:
            current_clues = list(char.personal_clues or [])
            for cid in clue_add:
                if cid not in current_clues:
                    current_clues.append(cid)
            updates["personal_clues"] = current_clues

        status_add = diff.get("status_add", [])
        status_remove = diff.get("status_remove", [])
        if status_add or status_remove:
            current_effects = list(char.status_effects or [])
            for effect in status_add:
                current_effects.append(effect)
            for name in status_remove:
                current_effects = [
                    e for e in current_effects
                    if e.get("effect", e) != name
                ]
            updates["status_effects"] = current_effects

        rel_changes = diff.get("relationship_change", [])
        if rel_changes:
            current_rels = dict(char.relationships or {})
            for rc in rel_changes:
                npc_name = rc.get("npc_name", "")
                change = rc.get("change", "")
                if npc_name and change:
                    current_rels[npc_name] = change
            updates["relationships"] = current_rels

        if not updates:
            return char

        updates["state_version"] = (char.state_version or 0) + 1
        updates["last_modified_by"] = "system"

        return await self.update(char.id, **updates)

    async def set_kp_override(
        self,
        character_id: str,
        field: str,
        value: Any,
    ) -> Optional[Character]:
        """KP manually overrides a Player State field."""
        updates = {
            field: value,
            "last_modified_by": "kp",
            "state_version": 0,
        }
        return await self.update(character_id, **updates)
