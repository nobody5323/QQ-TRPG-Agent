"""Module Repository"""

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.storage.base_repo import BaseRepository
from app.storage.models import Module


class ModuleRepository(BaseRepository[Module]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Module)

    async def get_by_campaign(self, campaign_id: str) -> List[Module]:
        stmt = select(Module).where(
            Module.campaign_id == campaign_id
        ).order_by(desc(Module.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(self, campaign_id: str, status: str) -> List[Module]:
        stmt = select(Module).where(
            Module.campaign_id == campaign_id,
            Module.status == status,
        ).order_by(desc(Module.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
