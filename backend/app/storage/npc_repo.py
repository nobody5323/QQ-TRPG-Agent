"""NPC Repository"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.storage.base_repo import BaseRepository
from app.storage.models import NPC


class NPCRepository(BaseRepository[NPC]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, NPC)

    async def get_by_campaign(self, campaign_id: str) -> List[NPC]:
        stmt = select(NPC).where(NPC.campaign_id == campaign_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, campaign_id: str, name: str) -> Optional[NPC]:
        stmt = select(NPC).where(
            NPC.campaign_id == campaign_id,
            NPC.name == name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_in_scene(self, scene_id: str) -> List[NPC]:
        """获取某个场景中的活跃 NPC"""
        stmt = select(NPC).where(
            NPC.campaign_id == scene_id  # TODO: 通过 Scene.active_npcs 关联查询
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
