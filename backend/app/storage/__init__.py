"""ChronicleAgent 数据存储层

使用方式：
    from app.storage.database import get_session
    from app.storage.campaign_repo import CampaignRepository

    async with get_session() as session:
        repo = CampaignRepository(session)
        campaign = await repo.create(name="测试团")
"""

from app.storage.database import Base, engine, get_session, create_tables, check_db_connection
from app.storage.models import (
    Campaign, Module, Character, NPC, Scene, Clue, Message, AgentTrace,
)
from app.storage.campaign_repo import CampaignRepository
from app.storage.module_repo import ModuleRepository
from app.storage.message_repo import MessageRepository
from app.storage.scene_repo import SceneRepository
from app.storage.npc_repo import NPCRepository
from app.storage.clue_repo import ClueRepository
from app.storage.trace_repo import TraceRepository
from app.storage.character_repo import CharacterRepository
from app.storage.qdrant import qdrant_store
from app.storage.redis import redis_client

__all__ = [
    "Base", "engine", "get_session", "create_tables", "check_db_connection",
    "Campaign", "Module", "Character", "NPC", "Scene", "Clue", "Message", "AgentTrace",
    "CampaignRepository", "ModuleRepository", "MessageRepository",
    "SceneRepository", "NPCRepository", "ClueRepository",
    "TraceRepository", "CharacterRepository",
    "qdrant_store", "redis_client",
]
