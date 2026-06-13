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
        ).order_by(Scene.order.asc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_campaign(self, campaign_id: str) -> List[Scene]:
        stmt = select(Scene).where(
            Scene.campaign_id == campaign_id
        ).order_by(Scene.order.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_active(self, campaign_id: str, scene_id: str) -> Optional[Scene]:
        """Set a scene as active, deactivating all others in the campaign."""
        stmt = select(Scene).where(
            Scene.campaign_id == campaign_id,
            Scene.is_active == True,
        )
        result = await self.session.execute(stmt)
        for scene in result.scalars().all():
            scene.is_active = False
        return await self.update(scene_id, is_active=True)

    async def transition_to(self, campaign_id: str, scene_name: str) -> Optional[Scene]:
        """Transition to a scene by name. Creates it if it doesn't exist."""
        stmt = select(Scene).where(
            Scene.campaign_id == campaign_id,
            Scene.name == scene_name,
        )
        result = await self.session.execute(stmt)
        scene = result.scalar_one_or_none()
        if scene:
            return await self.set_active(campaign_id, scene.id)
        new_scene = await self.create(Scene(
            campaign_id=campaign_id,
            name=scene_name,
            summary="",
            active_npcs=[],
            discovered_clues=[],
            order=0,
            is_active=True,
        ))
        if new_scene:
            stmt = select(Scene).where(
                Scene.campaign_id == campaign_id,
                Scene.id != new_scene.id,
                Scene.is_active == True,
            )
            result = await self.session.execute(stmt)
            for s in result.scalars().all():
                s.is_active = False
        return new_scene
