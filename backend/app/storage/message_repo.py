"""Message Repository"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.storage.base_repo import BaseRepository
from app.storage.models import Message


class MessageRepository(BaseRepository[Message]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Message)

    async def get_recent(
        self, campaign_id: str, limit: int = 50
    ) -> List[Message]:
        stmt = select(Message).where(
            Message.campaign_id == campaign_id
        ).order_by(desc(Message.timestamp)).limit(limit)
        result = await self.session.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def get_by_range(
        self, campaign_id: str, skip: int = 0, limit: int = 500
    ) -> List[Message]:
        stmt = select(Message).where(
            Message.campaign_id == campaign_id
        ).order_by(Message.timestamp.asc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_timestamp(self, campaign_id: str) -> Optional[str]:
        stmt = select(Message.timestamp).where(
            Message.campaign_id == campaign_id
        ).order_by(desc(Message.timestamp)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar()
