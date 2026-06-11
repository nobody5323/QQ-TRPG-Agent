"""AgentTrace Repository"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.storage.base_repo import BaseRepository
from app.storage.models import AgentTrace


class TraceRepository(BaseRepository[AgentTrace]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, AgentTrace)

    async def get_by_campaign(
        self, campaign_id: str, limit: int = 100
    ) -> List[AgentTrace]:
        stmt = select(AgentTrace).where(
            AgentTrace.campaign_id == campaign_id
        ).order_by(desc(AgentTrace.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_agent(
        self, campaign_id: str, agent_name: str, limit: int = 50
    ) -> List[AgentTrace]:
        stmt = select(AgentTrace).where(
            AgentTrace.campaign_id == campaign_id,
            AgentTrace.agent_name == agent_name,
        ).order_by(desc(AgentTrace.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_by_message(
        self, campaign_id: str, message_id: str
    ) -> Optional[AgentTrace]:
        """获取与某条消息关联的最近 Agent Trace"""
        stmt = select(AgentTrace).where(
            AgentTrace.campaign_id == campaign_id,
        ).order_by(desc(AgentTrace.created_at)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
