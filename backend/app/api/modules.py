"""API：模组管理 — 上传、解析、查询"""

import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_session
from app.storage.module_repo import ModuleRepository
from app.storage.npc_repo import NPCRepository
from app.storage.clue_repo import ClueRepository
from app.storage.scene_repo import SceneRepository
from app.storage.qdrant import qdrant_store
from app.rag.document_parser import ParserFactory
from app.rag.chunker import Chunker
from app.rag.extractor import extract_from_parse_result
from app.rag.embedding import embedding_service

router = APIRouter()

UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "uploads",
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}


@router.post("/upload")
async def upload_module(
    campaign_id: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    file_id = str(uuid.uuid4())
    safe_name = f"{file_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    module_repo = ModuleRepository(session)
    module = await module_repo.create(
        campaign_id=campaign_id,
        title=file.filename or safe_name,
        status="parsing",
    )

    try:
        parser = ParserFactory.get_parser(file_path)
        parse_result = parser.parse(file_path)

        chunker = Chunker()
        chunks = chunker.chunk(parse_result.sections, parse_result.title)

        extraction = extract_from_parse_result(parse_result)

        npc_repo = NPCRepository(session)
        for npc_data in extraction.npcs:
            await npc_repo.create(
                campaign_id=campaign_id,
                name=npc_data.name,
                personality=npc_data.personality,
                secret=npc_data.secret,
                visibility=npc_data.visibility,
            )

        clue_repo = ClueRepository(session)
        for clue_data in extraction.clues:
            await clue_repo.create(
                campaign_id=campaign_id,
                name=clue_data.name,
                description=clue_data.description,
                location=clue_data.location,
                trigger_condition=clue_data.trigger_condition,
                is_hidden=clue_data.is_hidden,
            )

        scene_repo = SceneRepository(session)
        for i, scene_data in enumerate(extraction.scenes):
            await scene_repo.create(
                campaign_id=campaign_id,
                name=scene_data.name,
                summary=scene_data.description,
                order=scene_data.order,
                is_active=(i == 0),  # 只有第一个场景激活
            )

        if chunks:
            texts = [chunk.text for chunk in chunks]
            vectors = await embedding_service.embed_batch(texts)
            points = []
            for i, chunk in enumerate(chunks):
                points.append({
                    "id": chunk.chunk_id,
                    "vector": vectors[i],
                    "payload": {
                        "campaign_id": campaign_id,
                        "module_id": module.id,
                        "chunk_id": chunk.chunk_id,
                        "type": chunk.type,
                        "title": chunk.title,
                        "text": chunk.text[:1000],
                        "location": chunk.location,
                        "visibility": chunk.visibility,
                        "related_nodes": chunk.related_nodes,
                        "section_ref": chunk.section_ref,
                    },
                })
            qdrant_store.upsert_points(points)

        await module_repo.update(
            module.id,
            title=parse_result.title,
            raw_text=parse_result.raw_text[:10000],
            parsed_json={
                "chunk_count": len(chunks),
                "npc_count": len(extraction.npcs),
                "clue_count": len(extraction.clues),
                "scene_count": len(extraction.scenes),
                "summary": extraction.summary,
            },
            chunk_count=len(chunks),
            status="parsed",
        )

        return {
            "module_id": module.id,
            "status": "parsed",
            "title": parse_result.title,
            "chunks": len(chunks),
            "npcs": len(extraction.npcs),
            "clues": len(extraction.clues),
            "scenes": len(extraction.scenes),
        }

    except Exception as e:
        await module_repo.update(module.id, status="error")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@router.get("")
async def list_modules(
    campaign_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    repo = ModuleRepository(session)
    filters = {}
    if campaign_id:
        filters["campaign_id"] = campaign_id
    modules = await repo.get_multi(
        filters=filters, order_field="created_at", order_desc=True,
    )
    return {
        "modules": [
            {
                "id": m.id,
                "title": m.title,
                "status": m.status,
                "chunk_count": m.chunk_count,
                "created_at": str(m.created_at),
            }
            for m in modules
        ],
        "total": len(modules),
    }


@router.get("/{module_id}")
async def get_module(
    module_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = ModuleRepository(session)
    module = await repo.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模组不存在")
    return {
        "id": module.id,
        "campaign_id": module.campaign_id,
        "title": module.title,
        "status": module.status,
        "chunk_count": module.chunk_count,
        "parsed_json": module.parsed_json,
        "created_at": str(module.created_at),
    }


@router.delete("/{module_id}")
async def delete_module(
    module_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = ModuleRepository(session)
    module = await repo.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模组不存在")
    if module.campaign_id:
        qdrant_store.delete_by_campaign(module.campaign_id)
    await repo.delete(module_id)
   