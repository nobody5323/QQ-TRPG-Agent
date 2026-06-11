"""
ChronicleAgent ORM 模型

基于 design.md 第 9 节数据库设计，包含 8 张表：
- Campaign         跑团项目
- Module           模组文档
- Character        玩家角色
- NPC              NPC 设定
- Scene            剧情场景
- Clue             线索
- Message          群聊消息
- AgentTrace       Agent 执行记录
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime,
    ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.storage.database import Base


def _uuid() -> str:
    """生成 UUID 主键"""
    return str(uuid.uuid4())


# ── Campaign: 跑团项目 ─────────────────────────────
class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    system_type = Column(String(64), default="coc")   # coc | dnd | generic
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    modules = relationship("Module", back_populates="campaign", cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="campaign", cascade="all, delete-orphan")
    npcs = relationship("NPC", back_populates="campaign", cascade="all, delete-orphan")
    scenes = relationship("Scene", back_populates="campaign", cascade="all, delete-orphan")
    clues = relationship("Clue", back_populates="campaign", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="campaign", cascade="all, delete-orphan")
    traces = relationship("AgentTrace", back_populates="campaign", cascade="all, delete-orphan")


# ── Module: 模组文档 ──────────────────────────────
class Module(Base):
    __tablename__ = "modules"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    title = Column(String(255), default="")
    raw_text = Column(Text, default="")
    parsed_json = Column(JSON, default=dict)
    chunk_count = Column(Integer, default=0)
    status = Column(String(32), default="pending")    # pending | parsing | parsed | error
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="modules")


# ── Character: 玩家角色 ──────────────────────────
class Character(Base):
    __tablename__ = "characters"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    player_name = Column(String(255), default="")        # QQ 昵称或群昵称
    character_name = Column(String(255), default="")     # 角色名
    profile = Column(JSON, default=dict)                  # 角色卡属性
    status = Column(JSON, default=dict)                   # HP/SAN/物品等状态
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="characters")


# ── NPC: NPC 设定 ─────────────────────────────────
class NPC(Base):
    __tablename__ = "npcs"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    personality = Column(Text, default="")                # 人设描述
    secret = Column(Text, default="")                     # 秘密（KP only）
    relationship_state = Column(JSON, default=dict)       # 关系状态
    visibility = Column(String(32), default="kp_only")    # player_visible | kp_only
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="npcs")


# ── Scene: 剧情场景 ───────────────────────────────
class Scene(Base):
    __tablename__ = "scenes"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    summary = Column(Text, default="")
    active_npcs = Column(JSON, default=list)              # 场景中活跃的 NPC ID 列表
    discovered_clues = Column(JSON, default=list)         # 已发现线索 ID 列表
    order = Column(Integer, default=0)                    # 场景顺序
    is_active = Column(Boolean, default=False)            # 当前是否活跃场景
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="scenes")


# ── Clue: 线索 ───────────────────────────────────
class Clue(Base):
    __tablename__ = "clues"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), default="")            # 线索所在位置
    trigger_condition = Column(Text, default="")           # 触发条件
    description = Column(Text, default="")                 # 描述
    is_hidden = Column(Boolean, default=True)              # 是否隐藏线索
    discovered = Column(Boolean, default=False)            # 是否已发现
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="clues")


# ── Message: 群聊消息 ─────────────────────────────
class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    sender = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    msg_type = Column(String(32), default="group")        # group | private | system
    role = Column(String(32), default="player")           # player | kp | npc | system
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    campaign = relationship("Campaign", back_populates="messages")


# ── AgentTrace: Agent 执行记录 ────────────────────
class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    agent_name = Column(String(128), nullable=False)       # classifier, rag, state, npc, ...
    input_data = Column(JSON, default=dict)                 # 输入
    output_data = Column(JSON, default=dict)                # 输出
    retrieved_context = Column(JSON, default=dict)          # 检索上下文
    tool_calls = Column(JSON, default=list)                 # 工具调用记录
    critic_result = Column(JSON, default=dict)              # Critic 检查结果
    latency_ms = Column(Integer, default=0)                 # 耗时（毫秒）
    token_count = Column(Integer, default=0)                # Token 消耗
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="traces")
