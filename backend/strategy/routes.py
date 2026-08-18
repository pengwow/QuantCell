"""策略模块API路由

路由前缀: /api/strategy
"""

import re

from fastapi import APIRouter, HTTPException, Path, Request

from common.schemas import ApiResponse
from utils.auth import jwt_auth_required_sync
from utils.logger import LogType, get_logger

from .schemas import (
    StrategyDetailRequest,
    StrategyGenerateRequest,
    StrategyGenerateResponse,
    StrategyListData,
    StrategyListResponse,
    StrategyUploadRequest,
    StrategyUploadResponse,
)
from .service import StrategyService

logger = get_logger(__name__, LogType.APPLICATION)

_strategy_service: StrategyService | None = None

# ponytail: 策略名只允许字母、数字、下划线、连字符
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$", re.ASCII)


def _validate_strategy_name(name: str) -> None:
    """拒绝路径遍历等不安全的策略名"""
    if not name or not _SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="策略名称不合法")


def get_strategy_service() -> StrategyService:
    global _strategy_service
    if _strategy_service is None:
        _strategy_service = StrategyService()
    return _strategy_service


router = APIRouter(
    prefix="/api/strategy",
    tags=["strategy"],
)


@router.get("/list", response_model=StrategyListResponse)
def get_strategy_list() -> StrategyListResponse:
    try:
        strategies = get_strategy_service().list_strategies()
        return StrategyListResponse(
            code=0,
            message="获取策略列表成功",
            data=StrategyListData(strategies=strategies),
        )
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detail", response_model=ApiResponse)
def get_strategy_detail(request: StrategyDetailRequest) -> ApiResponse:
    _validate_strategy_name(request.strategy_name)
    try:
        strategy_info = get_strategy_service().get_strategy(request.strategy_name)
        if not strategy_info:
            raise HTTPException(status_code=404, detail="策略不存在")
        return ApiResponse(code=0, message="获取策略详情成功", data=strategy_info)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取策略详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=StrategyUploadResponse)
@jwt_auth_required_sync
def upload_strategy(request: Request, strategy_request: StrategyUploadRequest) -> StrategyUploadResponse:
    _validate_strategy_name(strategy_request.strategy_name)
    try:
        get_strategy_service().save_strategy(
            strategy_request.strategy_name,
            strategy_request.file_content,
        )
        return StrategyUploadResponse(
            code=0,
            message="策略文件上传成功",
            data={"strategy_name": strategy_request.strategy_name},
        )
    except Exception as e:
        logger.error(f"上传策略文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse", response_model=ApiResponse)
def parse_strategy(request: StrategyDetailRequest) -> ApiResponse:
    _validate_strategy_name(request.strategy_name)
    if not request.file_content or not request.file_content.strip():
        raise HTTPException(status_code=400, detail="文件内容不能为空")
    try:
        info = get_strategy_service()._parse_strategy_file(request.strategy_name, request.file_content)
        if not info:
            raise HTTPException(status_code=400, detail="解析策略脚本失败")
        return ApiResponse(code=0, message="策略脚本解析成功", data=info)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解析策略脚本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{strategy_name}", response_model=ApiResponse)
@jwt_auth_required_sync
def delete_strategy(
    request: Request,
    strategy_name: str = Path(..., description="策略名称"),
) -> ApiResponse:
    _validate_strategy_name(strategy_name)
    try:
        success = get_strategy_service().delete_strategy(strategy_name)
        if success:
            return ApiResponse(
                code=0,
                message="删除策略成功",
                data={"strategy_name": strategy_name},
            )
        else:
            raise HTTPException(status_code=404, detail="策略不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=StrategyGenerateResponse)
@jwt_auth_required_sync
def generate_strategy(
    request: Request,
    generate_request: StrategyGenerateRequest,
) -> StrategyGenerateResponse:
    try:
        result = get_strategy_service().generate_strategy(
            prompt=generate_request.prompt,
            model_id=generate_request.model_id,
            model_name=generate_request.model_name,
            provider=generate_request.provider,
            conversation_id=generate_request.conversation_id,
        )
        return StrategyGenerateResponse(
            code=0,
            message="策略生成成功",
            data=result,
        )
    except Exception as e:
        logger.error(f"AI生成策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
