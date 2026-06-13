"""API: campaign management - CRUD, state query, KP binding"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_session
from app.storage.campaign_repo import CampaignRepository
from app.storage.scene_repo import SceneRepository
from app.storage.clue_repo import ClueRepository
from app.storage.npc_repo import NPCRepository

router = APIRouter()


@router.get("")
async def list_campaigns(
    session: AsyncSession = Depends(get_session),
):
    repo = CampaignRepository(session)
    campaigns = await repo.get_active_campaigns()
    return {
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "system_type": c.system_type,
                "description": c.description,
                "created_at": str(c.created_at),
            }
            for c in campaigns
        ],
        "total": len(campaigns),
    }


@router.post("")
async def create_campaign(
    name: str,
    system_type: str = "coc",
    description: str = "",
    session: AsyncSession = Depends(get_session),
):
    repo = CampaignRepository(session)
    campaign = await repo.create(
        name=name,
        system_type=system_type,
        description=description,
    )
    return {
        "id": campaign.id,
        "name": campaign.name,
        "system_type": campaign.system_type,
        "status": "created",
    }


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = CampaignRepository(session)
    campaign = await repo.get(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {
        "id": campaign.id,
        "name": campaign.name,
        "system_type": campaign.system_type,
        "description": campaign.description,
        "kp_qq": campaign.kp_qq or "",
        "created_at": str(campaign.created_at),
    }


@router.get("/by-kp/{kp_qq}")
async def get_campaign_by_kp(
    kp_qq: str,
    session: AsyncSession = Depends(get_session),
):
    repo = CampaignRepository(session)
    campaign = await repo.get_by_kp_qq(kp_qq)
    if not campaign:
        raise HTTPException(status_code=404, detail="No campaign bound for this KP")
    return {
        "id": campaign.id,
        "name": campaign.name,
        "system_type": campaign.system_type,
        "kp_qq": campaign.kp_qq,
    }


@router.put("/{campaign_id}/bind-kp")
async def bind_kp(
    campaign_id: str,
    kp_qq: str,
    session: AsyncSession = Depends(get_session),
):
    repo = CampaignRepository(session)
    campaign = await repo.get(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await repo.update(campaign_id, kp_qq=kp_qq)
    return {"status": "bound", "campaign_id": campaign_id, "kp_qq": kp_qq}


@router.delete("/{campaign_id}/bind-kp")
async def unbind_kp(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = CampaignRepository(session)
    campaign = await repo.get(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await repo.update(campaign_id, kp_qq="")
    return {"status": "unbound", "campaign_id": campaign_id}


@router.get("/{campaign_id}/state")
async def get_campaign_state(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
):
    scene_repo = SceneRepository(session)
    active_scene = await scene_repo.get_active(campaign_id)

    clue_repo = ClueRepository(session)
    all_clues = await clue_repo.get_by_campaign(campaign_id)
    discovered = [c for c in all_clues if c.discovered]
    undiscovered = [c for c in all_clues if not c.discovered]

    npc_repo = NPCRepository(session)
    npcs = await npc_repo.get_by_campaign(campaign_id)

    scenes = await scene_repo.get_by_campaign(campaign_id)

    return {
        "current_scene": {
            "id": active_scene.id,
            "name": active_scene.name,
            "summary": active_scene.summary,
        } if active_scene else None,
        "active_npcs": [
            {"id": n.id, "name": n.name, "personality": n.personality}
            for n in npcs
        ],
        "discovered_clues": [
            {"id": c.id, "name": c.name, "location": c.location}
            for c in discovered
        ],
        "undiscovered_clues": [
            {"id": c.id, "name": c.name, "location": c.location}
            for c in undiscovered
        ],
        "scenes": [
            {
                "id": s.id,
                "name": s.name,
                "order": s.order,
                "is_active": s.is_active,
            }
            for s in scenes
        ],
    }


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = CampaignRepository(session)
    campaign = await repo.get(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await repo.delete(campaign_id)
    return {"status": "deleted"}
