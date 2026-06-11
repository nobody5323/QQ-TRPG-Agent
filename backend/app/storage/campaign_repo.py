"""Campaign Repository"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.storage.base_repo import BaseRepository
from app.storage.models import Campaign


class CampaignRepository(BaseRepository[Campaign]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Campaign)

    async def get_by_name(self, name: str) -> Optional[Campaign]:
        stmt = select(Campaign).where(Campaign.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_campaigns(self) -> List[Campaign]:
        """获取最近活跃的跑团项目"""
        stmt = select(Campaign).order_by(Campaign.created_at.desc()).limit(20)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
