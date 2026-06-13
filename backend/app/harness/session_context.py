"""Per-request session storage via contextvars.

Avoids putting SQLAlchemy AsyncSession into AgentState (which is checkpointed by
LangGraph and fails msgpack serialization).  Instead, the orchestrator sets the
session here before graph invocation, and nodes read it via get_session().
"""

import contextvars
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

_current_session: contextvars.ContextVar[Optional[AsyncSession]] = (
    contextvars.ContextVar("current_session", default=None)
)


def set_session(session: Optional[AsyncSession]) -> None:
    _current_session.set(session)


def get_session() -> Optional[AsyncSession]:
    return _current_session.get()
