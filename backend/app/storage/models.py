"""ChronicleAgent ORM models - 8 tables based on design.md Section 9."""

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
    return str(uuid.uuid4())


# ── Campaign ──────────────────────────────────
class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    system_type = Column(String(64), default="coc")
    description = Column(Text, default="")
    kp_qq = Column(String(32), default="", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    modules = relationship("Module", back_populates="campaign", cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="campaign", cascade="all, delete-orphan")
    npcs = relationship("NPC", back_populates="campaign", cascade="all, delete-orphan")
    scenes = relationship("Scene", back_populates="campaign", cascade="all, delete-orphan")
    clues = relationship("Clue", back_populates="campaign", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="campaign", cascade="all, delete-orphan")
    traces = relationship("AgentTrace", back_populates="campaign", cascade="all, delete-orphan")


# ── Module ─────────────────────────────────────
class Module(Base):
    __tablename__ = "modules"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    title = Column(String(255), default="")
    raw_text = Column(Text, default="")
    parsed_json = Column(JSON, default=dict)
    chunk_count = Column(Integer, default=0)
    status = Column(String(32), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="modules")


# ── Character ─────────────────────────────────
class Character(Base):
    __tablename__ = "characters"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    player_name = Column(String(255), default="")
    character_name = Column(String(255), default="")
    profile = Column(JSON, default=dict)
    status = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="characters")


# ── NPC ────────────────────────────────────
class NPC(Base):
    __tablename__ = "npcs"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    personality = Column(Text, default="")
    secret = Column(Text, default="")
    relationship_state = Column(JSON, default=dict)
    visibility = Column(String(32), default="kp_only")
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="npcs")


# ── Scene ──────────────────────────────────
class Scene(Base):
    __tablename__ = "scenes"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    summary = Column(Text, default="")
    active_npcs = Column(JSON, default=list)
    discovered_clues = Column(JSON, default=list)
    order = Column(Integer, default=0)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="scenes")


# ── Clue ───────────────────────────────────
class Clue(Base):
    __tablename__ = "clues"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), default="")
    trigger_condition = Column(Text, default="")
    description = Column(Text, default="")
    is_hidden = Column(Boolean, default=True)
    discovered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="clues")


# ── Message ────────────────────────────────
class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    sender = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    msg_type = Column(String(32), default="group")
    role = Column(String(32), default="player")
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    campaign = relationship("Campaign", back_populates="messages")


# ── AgentTrace ─────────────────────────────
class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id = Column(String(36), primary_key=True, default=_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    agent_name = Column(String(128), nullable=False)
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    retrieved_context = Column(JSON, default=dict)
    tool_calls = Column(JSON, default=list)
    critic_result = Column(JSON, default=dict)
    latency_ms = Column(Integer, default=0)
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="traces")
