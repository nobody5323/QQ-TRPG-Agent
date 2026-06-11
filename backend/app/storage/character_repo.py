"""Character Repository"""

from typing import Optional, List
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
        """更新角色状态（HP/SAN/物品等）"""
        char = await self.get(character_id)
        if not char:
            return None
        current = dict(char.status or {})
        current.update(status_update)
        return await self.update(character_id, status=current)
