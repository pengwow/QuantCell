"""AI 文本润色 — 公共路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from common.schemas import ApiResponse
from utils.auth import get_current_user
from utils.logger import LogType, get_logger

from .schemas import AIPolishRequest, AIPolishResponse
from .service import AIPolishError, polish_text

logger = get_logger(__name__, LogType.APPLICATION)

router = APIRouter(
    prefix="/api/v1/ai",
    tags=["ai"],
    responses={
        200: {"description": "成功", "model": ApiResponse},
        500: {"description": "服务器错误"},
    },
)


@router.post(
    "/polish",
    response_model=ApiResponse,
    summary="AI 文本润色",
    description=(
        "通用 AI 短文本生成接口：根据 target（label/description/name/summary）"
        "和 context 生成文本，支持 max_length 长度限制。"
        "供因子表单等需要 AI 辅助生成展示名/描述的场景复用。"
    ),
)
async def ai_polish(
    request: AIPolishRequest,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    try:
        content = await polish_text(
            target=request.target,
            context=request.context,
            max_length=request.max_length,
            model_id=request.model_id,
        )
        return ApiResponse(code=0, message="ok", data=AIPolishResponse(content=content).model_dump())
    except AIPolishError as e:
        # 未配置/鉴权/超时等用户可理解的错误 → 400，前端展示可读文案
        logger.warning(f"AI 润色失败 [{e.error_type}]: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"AI 润色未预期异常: {e}")
        raise HTTPException(status_code=500, detail=f"AI 润色失败：{e}")
