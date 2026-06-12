"""Clue Repository"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.storage.base_repo import BaseRepository
from app.storage.models import Clue


class ClueRepository(BaseRepository[Clue]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Clue)

    async def get_by_campaign(self, campaign_id: str) -> List[Clue]:
        stmt = select(Clue).where(Clue.campaign_id == campaign_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_undiscovered(self, campaign_id: str) -> List[Clue]:
        stmt = select(Clue).where(
            Clue.campaign_id == campaign_id,
            Clue.discovered == False,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_discovered(self, campaign_id: str) -> List[Clue]:
        stmt = select(Clue).where(
            Clue.campaign_id == campaign_id,
            Clue.discovered == True,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_discovered(self, clue_id: str, discovered: bool = True) -> Optional[Clue]:
        return await self.update(clue_id, discovered=discovered)

    async def set_locked(self, clue_id: str, locked: bool = True, reason: str = "") -> Optional[Clue]:
        """Mark a clue as locked (dice failure prevented discovery)."""
        clue = await self.get(clue_id)
        if not clue:
            return None
        status = {}
        status["locked"] = locked
        if reason:
            status["lock_reason"] = reason
        return await self.update(clue_id, status=status)

    async def get_by_location(self, campaign_id: str, location: str) -> List[Clue]:
        stmt = select(Clue).where(
            Clue.campaign_id == campaign_id,
            Clue.location.ilike(f"%{location}%"),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
