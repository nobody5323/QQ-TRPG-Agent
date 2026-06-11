"""API：团录总结"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/generate")
async def generate_summary():
    """生成团录总结（占位）"""
    return {"markdown": "", "status": "pending"}
