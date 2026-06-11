"""Repository 基类 — 通用 CRUD 操作"""

from typing import Generic, TypeVar, Type, Optional, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.storage.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """通用 Repository 基类，提供标准 CRUD"""

    def __init__(self, session: AsyncSession, model_cls: Type[ModelType]):
        self.session = session
        self.model_cls = model_cls

    async def create(self, **kwargs) -> ModelType:
        instance = self.model_cls(**kwargs)
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def get(self, id: str) -> Optional[ModelType]:
        stmt = select(self.model_cls).where(self.model_cls.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict] = None,
        order_field: Optional[str] = None,
        order_desc: bool = True,
    ) -> List[ModelType]:
        stmt = select(self.model_cls)
        if filters:
            for key, value in filters.items():
                column = getattr(self.model_cls, key, None)
                if column is not None:
                    stmt = stmt.where(column == value)
        if order_field:
            column = getattr(self.model_cls, order_field, None)
            if column is not None:
                stmt = stmt.order_by(column.desc() if order_desc else column.asc())
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, id: str, **kwargs) -> Optional[ModelType]:
        instance = await self.get(id)
        if not instance:
            return None
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def delete(self, id: str) -> bool:
        instance = await self.get(id)
        if not instance:
            return False
        await self.session.delete(instance)
        await self.session.commit()
        return True

    async def count(self, filters: Optional[dict] = None) -> int:
        stmt = select(func.count()).select_from(self.model_cls)
        if filters:
            for key, value in filters.items():
                column = getattr(self.model_cls, key, None)
                if column is not None:
                    stmt = stmt.where(column == value)
        result = await self.session.execute(stmt)
        return result.scalar() or 0
