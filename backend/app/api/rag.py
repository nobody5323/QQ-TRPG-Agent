"""API: RAG retrieval - module knowledge query"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_session
from app.storage.scene_repo import SceneRepository
from app.storage.clue_repo import ClueRepository
from app.storage.npc_repo import NPCRepository
from app.storage.message_repo import MessageRepository
from app.rag.retriever import retriever

router = APIRouter()


class RAGQuery(BaseModel):
    campaign_id: str = Field(..., description="campaign ID")
    query: str = Field(..., description="query text")
    scene_context: Optional[str] = Field(None, description="manual scene context, auto if empty")
    active_npcs: Optional[List[str]] = Field(None, description="manual active NPCs, auto if empty")
    top_k: int = Field(5, ge=1, le=20, description="number of results")
    enable_enhancement: bool = Field(True, description="enable state-aware query enhancement")
    enable_keyword: bool = Field(True, description="enable keyword search")


class RAGSource(BaseModel):
    chunk_id: str
    text: str
    score: float
    type: str = ""
    title: str = ""
    location: str = ""
    visibility: str = "player_visible"
    boost_detail: Optional[dict] = None


class RAGResponse(BaseModel):
    answer: str
    sources: List[RAGSource]
    meta: Optional[dict] = None


class RAGDebugResponse(BaseModel):
    query: dict
    enhancement: dict
    retrieval: dict
    sources: List[RAGSource]


@router.post("/query", response_model=RAGResponse)
async def rag_query(
    body: RAGQuery,
    session: AsyncSession = Depends(get_session),
):
    scene_repo = SceneRepository(session)
    clue_repo = ClueRepository(session)
    npc_repo = NPCRepository(session)

    active_scene = await scene_repo.get_active(body.campaign_id)
    scene_name = body.scene_context
    if not scene_name and active_scene:
        scene_name = active_scene.name
        if active_scene.summary:
            scene_name = f"{active_scene.name} ({active_scene.summary[:100]})"

    npc_names = body.active_npcs
    if not npc_names and active_scene:
        all_npcs = await npc_repo.get_by_campaign(body.campaign_id)
        npc_names = [n.name for n in all_npcs]

    undiscovered = await clue_repo.get_undiscovered(body.campaign_id)
    undiscovered_names = [c.name for c in undiscovered]

    result = await retriever.search(
        query=body.query,
        campaign_id=body.campaign_id,
        scene_context=scene_name,
        active_npcs=npc_names,
        undiscovered_clue_names=undiscovered_names,
        top_k=body.top_k,
        enable_enhancement=body.enable_enhancement,
        enable_keyword=body.enable_keyword,
    )

    meta = result["meta"]
    search_results = result["results"]

    sources = []
    for r in search_results:
        payload = r.get("payload", {}) or {}
        sources.append(RAGSource(
            chunk_id=str(payload.get("chunk_id", r.get("id", ""))),
            text=payload.get("text", "")[:400],
            score=r.get("rerank_score", r.get("score", 0)),
            type=payload.get("type", "text"),
            title=payload.get("title", ""),
            location=payload.get("location", ""),
            visibility=payload.get("visibility", "player_visible"),
            boost_detail=r.get("_boost_detail"),
        ))

    answer_parts = []
    for s in sources[:3]:
        prefix = ""
        if s.visibility == "kp_only":
            prefix = "[KP Only] "
        if s.location:
            prefix += f"[{s.location}] "
        if s.text:
            answer_parts.append(f"{prefix}{s.text}")

    answer = "\n\n---\n\n".join(answer_parts) if answer_parts else "no relevant info found"

    return RAGResponse(
        answer=answer,
        sources=sources,
        meta=meta,
    )


@router.post("/debug", response_model=RAGDebugResponse)
async def rag_debug(
    body: RAGQuery,
    session: AsyncSession = Depends(get_session),
):
    scene_repo = SceneRepository(session)
    clue_repo = ClueRepository(session)
    npc_repo = NPCRepository(session)

    active_scene = await scene_repo.get_active(body.campaign_id)
    scene_name = body.scene_context
    if not scene_name and active_scene:
        if active_scene.summary:
            scene_name = f"{active_scene.name} ({active_scene.summary[:100]})"
        else:
            scene_name = active_scene.name

    all_npcs = await npc_repo.get_by_campaign(body.campaign_id)
    npc_names = body.active_npcs or [n.name for n in all_npcs]

    undiscovered = await clue_repo.get_undiscovered(body.campaign_id)
    undiscovered_names = [c.name for c in undiscovered]
    discovered = await clue_repo.get_discovered(body.campaign_id)
    discovered_names = [c.name for c in discovered]

    result = await retriever.search(
        query=body.query,
        campaign_id=body.campaign_id,
        scene_context=scene_name,
        active_npcs=npc_names,
        undiscovered_clue_names=undiscovered_names,
        top_k=body.top_k,
        enable_enhancement=body.enable_enhancement,
        enable_keyword=body.enable_keyword,
    )

    meta = result["meta"]

    sources = []
    for r in result["results"]:
        payload = r.get("payload", {}) or {}
        sources.append(RAGSource(
            chunk_id=str(payload.get("chunk_id", r.get("id", ""))),
            text=payload.get("text", "")[:400],
            score=r.get("rerank_score", r.get("score", 0)),
            type=payload.get("type", "text"),
            title=payload.get("title", ""),
            location=payload.get("location", ""),
            visibility=payload.get("visibility", "player_visible"),
            boost_detail=r.get("_boost_detail"),
        ))

    return RAGDebugResponse(
        query={
            "original": body.query,
            "enhanced": meta.get("query_enhanced", body.query),
        },
        enhancement={
            "active_scene": scene_name,
            "active_npcs": npc_names,
            "undiscovered_clues": undiscovered_names,
            "discovered_clues": discovered_names,
            "enhancement_enabled": body.enable_enhancement,
        },
        retrieval={
            "fusion_method": meta.get("fusion_method", "unknown"),
            "vector_results_count": meta.get("vector_count", 0),
            "keyword_results_count": meta.get("keyword_count", 0),
            "merged_count": meta.get("merged_count", 0),
            "final_count": len(sources),
            "latency_ms": meta.get("latency_ms", 0),
            "within_500ms_target": meta.get("within_target", False),
        },
        sources=sources,
    )


@router.get("/state/{campaign_id}")
async def get_retrieval_state(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
):
    scene_repo = SceneRepository(session)
    clue_repo = ClueRepository(session)
    npc_repo = NPCRepository(session)

    active_scene = await scene_repo.get_active(campaign_id)
    all_scenes = await scene_repo.get_by_campaign(campaign_id)
    all_npcs = await npc_repo.get_by_campaign(campaign_id)
    undiscovered = await clue_repo.get_undiscovered(campaign_id)
    discovered = await clue_repo.get_discovered(campaign_id)

    return {
        "campaign_id": campaign_id,
        "active_scene": {
            "name": active_scene.name,
            "summary": active_scene.summary,
            "order": active_scene.order,
        } if active_scene else None,
        "all_scenes": [
            {"name": s.name, "order": s.order, "is_active": s.is_active}
            for s in all_scenes
        ],
        "npcs": [
            {"name": n.name, "personality": n.personality[:100], "visibility": n.visibility}
            for n in all_npcs
        ],
        "undiscovered_clues": [
            {"name": c.name, "location": c.location, "is_hidden": c.is_hidden}
            for c in undiscovered
        ],
        "discovered_clues": [
            {"name": c.name, "location": c.location}
            for c in discovered
        ],
    }
