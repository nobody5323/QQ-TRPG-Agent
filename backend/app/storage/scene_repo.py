"""Scene Repository"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.storage.base_repo import BaseRepository
from app.storage.models import Scene


class SceneRepository(BaseRepository[Scene]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Scene)

    async def get_active(self, campaign_id: str) -> Optional[Scene]:
        stmt = select(Scene).where(
            Scene.campaign_id == campaign_id,
            Scene.is_active == True,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_campaign(self, campaign_id: str) -> List[Scene]:
        stmt = select(Scene).where(
            Scene.campaign_id == campaign_id
        ).order_by(Scene.order.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_active(self, campaign_id: str, scene_id: str) -> Optional[Scene]:
        """将指定场景设为活跃，同时取消其他场景的活跃状态"""
        # 先取消所有活跃
        stmt = select(Scene).where(
            Scene.campaign_id == campaign_id,
            Scene.is_active == True,
        )
        result = await self.session.execute(stmt)
        for scene in result.scalars().all():
            scene.is_active = False
        # 设置新活跃
        return await self.update(scene_id, is_active=True)
