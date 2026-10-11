"""策略模块API路由

路由前缀: /api/strategy
"""

import re
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from common.schemas import ApiResponse
from utils.auth import get_current_user
from utils.logger import LogType, get_logger

from .schemas import (
    StrategyDetailRequest,
    StrategyGenerateRequest,
    StrategyGenerateResponse,
    StrategyListData,
    StrategyListResponse,
    StrategyParseRequest,
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
    prefix="/api/v1/strategy",
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
def upload_strategy(
    strategy_request: StrategyUploadRequest,
    current_user: dict = Depends(get_current_user),
) -> StrategyUploadResponse:
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
def parse_strategy(request: StrategyParseRequest) -> ApiResponse:
    # file_content 在 StrategyParseRequest 中为必填(min_length=1)，
    # 缺失/空字符串由 Pydantic 返回 422，而非路由手工返回 400。
    _validate_strategy_name(request.strategy_name)
    if not request.file_content.strip():
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
def delete_strategy(
    strategy_name: str = Path(..., description="策略名称"),
    current_user: dict = Depends(get_current_user),
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
def generate_strategy(
    generate_request: StrategyGenerateRequest,
    current_user: dict = Depends(get_current_user),
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


# —— 因子独立 CRUD ——


@router.get("/{strategy_name}/factors", response_model=ApiResponse, summary="获取策略因子列表")
def api_get_factors(
    strategy_name: str = Path(..., description="策略名称"),
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    _validate_strategy_name(strategy_name)
    factors = get_strategy_service().get_factors(strategy_name)
    return ApiResponse(code=0, message="ok", data=factors)


@router.put("/{strategy_name}/factors", response_model=ApiResponse, summary="整体覆盖策略因子列表")
def api_replace_factors(
    strategy_name: str = Path(..., description="策略名称"),
    factors: list[dict[str, Any]] = Body(..., description="新因子列表"),
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    _validate_strategy_name(strategy_name)
    ok = get_strategy_service().replace_factors(strategy_name, factors)
    if not ok:
        raise HTTPException(status_code=404, detail=f"策略不存在: {strategy_name}")
    return ApiResponse(code=0, message="因子列表已更新", data=factors)


@router.post("/{strategy_name}/factors", response_model=ApiResponse, summary="给策略添加一个因子")
def api_add_factor(
    strategy_name: str = Path(..., description="策略名称"),
    factor: dict[str, Any] = Body(..., description="因子对象，必须有 name 字段"),
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    _validate_strategy_name(strategy_name)
    if not factor.get("name"):
        raise HTTPException(status_code=400, detail="因子必须有 name 字段")
    ok = get_strategy_service().add_factor(strategy_name, factor)
    if not ok:
        raise HTTPException(status_code=404, detail=f"策略不存在: {strategy_name}")
    return ApiResponse(code=0, message="因子已添加", data=factor)


@router.delete("/{strategy_name}/factors/{factor_name}", response_model=ApiResponse, summary="删除策略的一个因子")
def api_remove_factor(
    strategy_name: str = Path(..., description="策略名称"),
    factor_name: str = Path(..., description="因子名称"),
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    _validate_strategy_name(strategy_name)
    ok = get_strategy_service().remove_factor(strategy_name, factor_name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"策略或因子不存在: {strategy_name}/{factor_name}")
    return ApiResponse(code=0, message="因子已删除", data={"removed": factor_name})


@router.patch(
    "/{strategy_name}/factors/{factor_name}", response_model=ApiResponse, summary="更新单个因子字段（不可改 name）"
)
def api_update_factor(
    strategy_name: str = Path(..., description="策略名称"),
    factor_name: str = Path(..., description="因子名称"),
    patch: dict[str, Any] = Body(..., description="要更新的字段，name 会被忽略"),
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    _validate_strategy_name(strategy_name)
    ok = get_strategy_service().update_factor(strategy_name, factor_name, patch)
    if not ok:
        raise HTTPException(status_code=404, detail=f"策略或因子不存在: {strategy_name}/{factor_name}")
    return ApiResponse(code=0, message="因子已更新", data={"factor_name": factor_name})


# —— 重新解析（AST 扫源码，覆盖 DB 里的 params + factors）——


def _clean_parse_info(raw: dict[str, Any]) -> dict[str, Any]:
    """把 _parse_strategy_file 返回的 dict 里不可 JSON 化的对象转成字符串。

    - StrategyType enum → .value
    - datetime → .isoformat()
    - 去掉 code（太长，前端可单独调详情）
    """
    import datetime as _dt
    from enum import Enum

    result: dict[str, Any] = {}
    for k, v in raw.items():
        if k == "code":
            continue
        if isinstance(v, Enum):
            result[k] = v.value
        elif isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


@router.post(
    "/{strategy_name}/reparse", response_model=ApiResponse, summary="重新解析策略源码（覆盖 DB 里的 params + factors）"
)
def api_reparse_strategy(
    strategy_name: str = Path(..., description="策略名称"),
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    _validate_strategy_name(strategy_name)
    info = get_strategy_service().reparse_strategy(strategy_name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"策略不存在: {strategy_name}")
    return ApiResponse(code=0, message="重新解析完成", data=_clean_parse_info(info))
