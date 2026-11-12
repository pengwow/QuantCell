"""标的池 API 路由（P2-03）。

池 CRUD + 成分增删 + 快照历史。业务错误由 service 抛 UniverseError 子类，
这里统一映射 HTTP 状态码（404/409/400）。
"""

from fastapi import APIRouter, Depends, HTTPException

from common.schemas import ApiResponse
from universe import service as universe_service
from universe.schemas import UniverseCreateRequest, UniverseMembersRequest, UniverseUpdateRequest
from utils.auth import get_current_user
from utils.logger import LogType, get_logger

router = APIRouter(prefix="/api/v1/universes", tags=["universes"])

logger = get_logger(__name__, LogType.APPLICATION)


def _to_http_error(error: universe_service.UniverseError) -> HTTPException:
    """service 业务错误 → HTTP 状态码映射。"""
    if isinstance(error, universe_service.UniverseNotFoundError):
        status = 404
    elif isinstance(error, universe_service.DuplicateUniverseError):
        status = 409
    else:
        status = 400
    return HTTPException(status_code=status, detail=str(error))


@router.get("", response_model=ApiResponse, summary="标的池列表", description="返回全部标的池及当前成分数")
def list_universes(current_user: dict = Depends(get_current_user)) -> ApiResponse:
    try:
        return ApiResponse(code=0, message="获取标的池列表成功", data=universe_service.list_universes())
    except universe_service.UniverseError as e:
        logger.warning(f"标的池列表失败: {e}")
        raise _to_http_error(e) from e


@router.post("", response_model=ApiResponse, summary="创建标的池", description="创建池，可选附带初始成分")
def create_universe(
    request: UniverseCreateRequest,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    try:
        owner_id: int | None = None
        try:
            owner_id = int(current_user.get("user_id"))
        except TypeError, ValueError:
            owner_id = None  # 单用户/匿名模式不记归属
        data = universe_service.create_universe(
            name=request.name,
            description=request.description,
            symbols=request.symbols,
            owner_id=owner_id,
        )
        return ApiResponse(code=0, message="创建标的池成功", data=data)
    except universe_service.UniverseError as e:
        logger.warning(f"创建标的池失败: {e}")
        raise _to_http_error(e) from e


@router.get("/{universe_id}", response_model=ApiResponse, summary="标的池详情", description="返回池字段与当前成分列表")
def get_universe(universe_id: int, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    try:
        return ApiResponse(code=0, message="获取标的池成功", data=universe_service.get_universe(universe_id))
    except universe_service.UniverseError as e:
        raise _to_http_error(e) from e


@router.put(
    "/{universe_id}", response_model=ApiResponse, summary="更新标的池", description="更新名称/描述（至少提供其一）"
)
def update_universe(
    universe_id: int,
    request: UniverseUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    try:
        data = universe_service.update_universe(universe_id, name=request.name, description=request.description)
        return ApiResponse(code=0, message="更新标的池成功", data=data)
    except universe_service.UniverseError as e:
        raise _to_http_error(e) from e


@router.delete(
    "/{universe_id}", response_model=ApiResponse, summary="删除标的池", description="删除池并级联清理成分历史与快照"
)
def delete_universe(universe_id: int, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    try:
        universe_service.delete_universe(universe_id)
        return ApiResponse(code=0, message="删除标的池成功", data={"deleted": True})
    except universe_service.UniverseError as e:
        raise _to_http_error(e) from e


@router.post(
    "/{universe_id}/members",
    response_model=ApiResponse,
    summary="加入成分",
    description="批量加入标的，池内已有活跃成员自动跳过",
)
def add_members(
    universe_id: int,
    request: UniverseMembersRequest,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    try:
        data = universe_service.add_members(universe_id, request.symbols)
        return ApiResponse(code=0, message="成分已加入", data=data)
    except universe_service.UniverseError as e:
        raise _to_http_error(e) from e


@router.post(
    "/{universe_id}/members/remove",
    response_model=ApiResponse,
    summary="移出成分",
    description="批量移出标的（保留历史成分记录），并写入变更快照",
)
def remove_members(
    universe_id: int,
    request: UniverseMembersRequest,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    try:
        data = universe_service.remove_members(universe_id, request.symbols)
        return ApiResponse(code=0, message="成分已移出", data=data)
    except universe_service.UniverseError as e:
        raise _to_http_error(e) from e


@router.get(
    "/{universe_id}/snapshots", response_model=ApiResponse, summary="快照历史", description="按时间倒序返回成分变更快照"
)
def list_snapshots(universe_id: int, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    try:
        return ApiResponse(code=0, message="获取快照成功", data=universe_service.list_snapshots(universe_id))
    except universe_service.UniverseError as e:
        raise _to_http_error(e) from e
