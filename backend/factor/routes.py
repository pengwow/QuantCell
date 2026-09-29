"""因子计算模块API路由 — 因子列表/CRUD/计算/分析"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from common.schemas import ApiResponse
from factor.catalog_service import CatalogError, FactorCatalogService
from factor.models import FactorCatalog, FactorSnapshot
from quality.parquet_provider import ParquetDataProvider
from utils.auth import get_current_user
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

from .schemas import (
    FactorAddRequest,
    FactorAnalyzeRequest,
    FactorCalculateBase,
    FactorCalculateMultiRequest,
    FactorCalculateRequest,
    FactorCorrelationRequest,
    FactorGroupAnalysisRequest,
    FactorICRequest,
    FactorIRRequest,
    FactorMonotonicityRequest,
    FactorStabilityRequest,
    FactorStatsRequest,
    FactorValidateRequest,
    LifecycleUpdateRequest,
)
from .service import (
    FactorError,
    FactorNotFoundError,
    FactorService,
    _EngineExprError,
)

logger = get_logger(__name__, LogType.APPLICATION)


def _sanitize(obj: Any) -> Any:
    """递归替换 NaN/inf 为 None，确保 JSON 可序列化"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.floating, np.integer)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return _sanitize(obj.to_dict(orient="records"))
    if isinstance(obj, pd.Series):
        return _sanitize(obj.to_dict())
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj


def _dict_to_df(data: dict[str, Any]) -> pd.DataFrame:
    """将 {factor: {instrument: [values]}} 转为宽表 DataFrame（列=因子或标的）"""
    frames = {}
    for factor_name, instruments in data.items():
        if isinstance(instruments, dict):
            for inst, values in instruments.items():
                col = f"{factor_name}__{inst}" if len(data) > 1 else inst
                frames[col] = values
        else:
            frames[factor_name] = instruments
    return pd.DataFrame(frames)


def _returns_dict_to_series(data: dict[str, Any]) -> pd.Series:
    """将 {instrument: [returns]} 转为扁平 Series"""
    rows = []
    for values in data.values():
        for v in values:
            rows.append(v)
    return pd.Series(rows, dtype=float)


# 创建路由
router = APIRouter(
    prefix="/api/v1/factor",
    tags=["factor"],
    responses={
        200: {"description": "成功", "model": ApiResponse},
        500: {"description": "服务器错误"},
    },
)

# 创建服务实例
factor_service = FactorService()

# 因子档案服务：快照落 backend/data/factor/snapshots，删除归档到 backend/.trash
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_SNAPSHOTS_DIR = _BACKEND_DIR / "data" / "factor" / "snapshots"
_TRASH_DIR = _BACKEND_DIR / ".trash"
_catalog_service = FactorCatalogService(
    factor_service=factor_service,
    snapshots_dir=_SNAPSHOTS_DIR,
    trash_dir=_TRASH_DIR,
    backend_dir=_BACKEND_DIR,
)


@router.get(
    "/list",
    response_model=ApiResponse,
    summary="获取因子列表",
    description="获取所有支持的因子列表",
)
def get_factor_list(
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    """获取所有支持的因子列表"""
    try:
        logger.info("获取因子列表请求")
        factors = factor_service.get_factor_list()
        logger.info(f"成功获取因子列表，共 {len(factors)} 个因子")
        return ApiResponse(
            code=0,
            message="获取因子列表成功",
            data={"factors": factors},
        )
    except Exception as e:
        logger.error(f"获取因子列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/expression/{factor_name}",
    response_model=ApiResponse,
    summary="获取因子表达式",
    description="获取指定因子的表达式",
)
def get_factor_expression(factor_name: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """获取因子的表达式"""
    try:
        logger.info(f"获取因子表达式请求，因子名称: {factor_name}")
        expression = factor_service.get_factor_expression(factor_name)
        if expression:
            logger.info(f"成功获取因子 {factor_name} 的表达式")
            return ApiResponse(
                code=0,
                message="获取因子表达式成功",
                data={"factor_name": factor_name, "expression": expression},
            )
        else:
            logger.error(f"因子 {factor_name} 不存在")
            return ApiResponse(
                code=1,
                message=f"因子 {factor_name} 不存在",
                data={},
            )
    except Exception as e:
        logger.error(f"获取因子表达式失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/add",
    response_model=ApiResponse,
    summary="添加自定义因子",
    description="添加新的自定义因子",
)
def add_factor(request: FactorAddRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """添加自定义因子"""
    try:
        logger.info(f"添加因子请求，因子名称: {request.factor_name}, 表达式: {request.expression}")
        result = factor_service.add_factor(request.factor_name, request.expression)
        if result:
            logger.info(f"成功添加因子 {request.factor_name}")
            # ---- add 成功后建档（派生数据，失败不阻断表达式新增）----
            try:
                with get_db_session() as db:
                    _catalog_service.sync_builtins(db)  # 确保内置已在，自定义 upsert 不依赖顺序
                    details = [d for d in factor_service.get_factor_details() if d["name"] == request.factor_name]
                    if details:
                        _catalog_service.upsert_custom(db, details[0])
            except Exception as hook_err:
                logger.warning(f"因子档案建档失败（不影响表达式保存）: {hook_err}")
            return ApiResponse(
                code=0,
                message=f"成功添加因子 {request.factor_name}",
                data={
                    "factor_name": request.factor_name,
                    "expression": request.expression,
                },
            )
        else:
            logger.error(f"添加因子 {request.factor_name} 失败")
            return ApiResponse(
                code=1,
                message=f"添加因子 {request.factor_name} 失败",
                data={},
            )
    except Exception as e:
        logger.error(f"添加因子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/delete/{factor_name}",
    response_model=ApiResponse,
    summary="删除自定义因子",
    description="删除指定的自定义因子",
)
def delete_factor(factor_name: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """删除自定义因子"""
    try:
        logger.info(f"删除因子请求，因子名称: {factor_name}")
        result = factor_service.delete_factor(factor_name)
        if result:
            logger.info(f"成功删除因子 {factor_name}")
            try:
                with get_db_session() as db:
                    _catalog_service.on_factor_deleted(db, factor_name)
            except Exception as hook_err:
                logger.warning(f"因子档案删除失败（不影响表达式删除）: {hook_err}")
            return ApiResponse(
                code=0,
                message=f"成功删除因子 {factor_name}",
                data={"factor_name": factor_name},
            )
        else:
            logger.error(f"因子 {factor_name} 不存在")
            return ApiResponse(
                code=1,
                message=f"因子 {factor_name} 不存在",
                data={},
            )
    except Exception as e:
        logger.error(f"删除因子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/calculate",
    response_model=ApiResponse,
    summary="计算单因子",
    description="计算指定因子的值",
)
def calculate_factor(request: FactorCalculateRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """计算指定因子的值"""
    try:
        logger.info(f"计算因子请求，因子名称: {request.factor_name}")
        factor_data = factor_service.calculate_factor(
            factor_name=request.factor_name,
            instruments=request.instruments,
            start_time=request.start_time,
            end_time=request.end_time,
            interval=request.interval,
            candle_type=request.candle_type,
        )
        factor_dict = _sanitize(factor_data.reset_index().to_dict(orient="records"))
        logger.info(f"成功计算因子 {request.factor_name}")
        return ApiResponse(
            code=0,
            message=f"成功计算因子 {request.factor_name}",
            data={
                "factor_name": request.factor_name,
                "data": factor_dict,
                "shape": factor_data.shape,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"计算因子失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/calculate-multi",
    response_model=ApiResponse,
    summary="计算多因子",
    description="计算多个因子的值",
)
def calculate_factors(
    request: FactorCalculateMultiRequest, current_user: dict = Depends(get_current_user)
) -> ApiResponse:
    """计算多个因子的值"""
    try:
        logger.info(f"计算多个因子请求，因子数量: {len(request.factor_names)}")
        factor_data = factor_service.calculate_factors(
            factor_names=request.factor_names,
            instruments=request.instruments,
            start_time=request.start_time,
            end_time=request.end_time,
            interval=request.interval,
            candle_type=request.candle_type,
        )
        factor_dict = _sanitize(factor_data.reset_index().to_dict(orient="records"))
        logger.info(f"成功计算多个因子，共 {len(request.factor_names)} 个因子")
        return ApiResponse(
            code=0,
            message="成功计算多个因子",
            data={
                "factor_names": request.factor_names,
                "data": factor_dict,
                "shape": factor_data.shape,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"计算多个因子失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/calculate-all",
    response_model=ApiResponse,
    summary="计算所有因子",
    description="计算所有内置因子的值",
)
def calculate_all_factors(request: FactorCalculateBase, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """计算所有可计算因子的值"""
    try:
        logger.info("计算所有因子请求")
        factor_data = factor_service.calculate_all_factors(
            instruments=request.instruments,
            start_time=request.start_time,
            end_time=request.end_time,
            interval=request.interval,
            candle_type=request.candle_type,
        )
        factor_dict = _sanitize(factor_data.reset_index().to_dict(orient="records"))
        logger.info(f"成功计算所有因子，共 {len(factor_data.columns)} 个因子")
        return ApiResponse(
            code=0,
            message="成功计算所有因子",
            data={
                "factor_names": list(factor_data.columns),
                "data": factor_dict,
                "shape": factor_data.shape,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"计算所有因子失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/validate",
    response_model=ApiResponse,
    summary="验证因子表达式",
    description="验证因子表达式是否有效",
)
def validate_factor_expression(
    request: FactorValidateRequest, current_user: dict = Depends(get_current_user)
) -> ApiResponse:
    """验证因子表达式是否有效"""
    try:
        logger.info(f"验证因子表达式请求，表达式: {request.expression}")
        result = factor_service.validate_factor_expression(request.expression)
        if result:
            logger.info("因子表达式验证通过")
            return ApiResponse(
                code=0,
                message="因子表达式验证通过",
                data={"valid": True, "expression": request.expression},
            )
        else:
            logger.error("因子表达式验证失败")
            return ApiResponse(
                code=1,
                message="因子表达式验证失败",
                data={"valid": False, "expression": request.expression},
            )
    except Exception as e:
        logger.error(f"验证因子表达式失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/correlation",
    response_model=ApiResponse,
    summary="计算因子相关性",
    description="计算因子之间的相关性矩阵",
)
def get_factor_correlation(
    request: FactorCorrelationRequest, current_user: dict = Depends(get_current_user)
) -> ApiResponse:
    """计算因子之间的相关性矩阵"""
    try:
        df = _dict_to_df(request.factor_data)
        corr = factor_service.get_factor_correlation(df)
        if corr is None:
            raise HTTPException(status_code=400, detail="相关性计算失败，数据格式可能不正确")
        return ApiResponse(
            code=0,
            message="成功计算因子相关性",
            data={"correlation": _sanitize(corr)},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"计算因子相关性失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/stats",
    response_model=ApiResponse,
    summary="获取因子统计",
    description="获取因子的描述性统计信息",
)
def get_factor_stats(request: FactorStatsRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """获取因子的描述性统计信息"""
    try:
        df = _dict_to_df(request.factor_data)
        stats = factor_service.get_factor_descriptive_stats(df)
        if stats is None:
            raise HTTPException(status_code=400, detail="统计计算失败，数据格式可能不正确")
        return ApiResponse(
            code=0,
            message="成功获取因子统计信息",
            data={"stats": _sanitize(stats)},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取因子统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/ic",
    response_model=ApiResponse,
    summary="计算IC",
    description="计算因子的信息系数(IC)",
)
def calculate_factor_ic(request: FactorICRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """计算因子的信息系数(IC)"""
    try:
        factor_df = _dict_to_df(request.factor_data)
        return_series = _returns_dict_to_series(request.return_data)
        ic = factor_service.calculate_ic(factor_df, return_series, method=request.method)
        if ic is None:
            raise HTTPException(status_code=400, detail="IC计算失败，请检查数据格式")
        return ApiResponse(
            code=0,
            message="成功计算因子IC",
            data={
                "ic": _sanitize(ic),
                "ic_mean": _sanitize(ic.mean()) if len(ic) > 0 else None,
                "ic_std": _sanitize(ic.std()) if len(ic) > 1 else None,
                "method": request.method,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"计算因子IC失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/ir",
    response_model=ApiResponse,
    summary="计算IR",
    description="计算因子的信息比率(IR)",
)
def calculate_factor_ir(request: FactorIRRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """计算因子的信息比率(IR)"""
    try:
        factor_df = _dict_to_df(request.factor_data)
        return_series = _returns_dict_to_series(request.return_data)
        ir = factor_service.calculate_ir(factor_df, return_series, method=request.method)
        if ir is None:
            raise HTTPException(status_code=400, detail="IR计算失败，请检查数据格式")
        ic = factor_service.calculate_ic(factor_df, return_series, method=request.method)
        return ApiResponse(
            code=0,
            message="成功计算因子IR",
            data={
                "ir": _sanitize(ir),
                "ic_mean": _sanitize(ic.mean()) if ic is not None and len(ic) > 0 else None,
                "ic_std": _sanitize(ic.std()) if ic is not None and len(ic) > 1 else None,
                "method": request.method,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"计算因子IR失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/group-analysis",
    response_model=ApiResponse,
    summary="分组分析",
    description="因子分组回测分析",
)
def factor_group_analysis(
    request: FactorGroupAnalysisRequest, current_user: dict = Depends(get_current_user)
) -> ApiResponse:
    """因子分组回测分析"""
    try:
        factor_df = _dict_to_df(request.factor_data)
        return_series = _returns_dict_to_series(request.return_data)
        result = factor_service.group_analysis(factor_df, return_series, n_groups=request.n_groups)
        if result is None:
            raise HTTPException(status_code=400, detail="分组分析失败，请检查数据格式")
        return ApiResponse(
            code=0,
            message="成功完成因子分组分析",
            data={
                "n_groups": request.n_groups,
                "long_short_return": _sanitize(result["long_short_return"].sum())
                if "long_short_return" in result
                else None,
                "group_returns_mean": _sanitize(
                    result["group_returns"].groupby(level=0).mean() if "group_returns" in result else {}
                ),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子分组分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/monotonicity",
    response_model=ApiResponse,
    summary="单调性检验",
    description="因子单调性检验",
)
def factor_monotonicity_test(
    request: FactorMonotonicityRequest, current_user: dict = Depends(get_current_user)
) -> ApiResponse:
    """因子单调性检验"""
    try:
        factor_df = _dict_to_df(request.factor_data)
        return_series = _returns_dict_to_series(request.return_data)
        result = factor_service.factor_monotonicity_test(factor_df, return_series, n_groups=request.n_groups)
        if result is None:
            raise HTTPException(status_code=400, detail="单调性检验失败，请检查数据格式")
        return ApiResponse(
            code=0,
            message="成功完成因子单调性检验",
            data=_sanitize(result),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子单调性检验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/stability",
    response_model=ApiResponse,
    summary="稳定性检验",
    description="因子稳定性检验",
)
def factor_stability_test(
    request: FactorStabilityRequest, current_user: dict = Depends(get_current_user)
) -> ApiResponse:
    """因子稳定性检验"""
    try:
        factor_df = _dict_to_df(request.factor_data)
        result = factor_service.factor_stability_test(factor_df, window=request.window)
        if result is None:
            raise HTTPException(status_code=400, detail="稳定性检验失败，请检查数据格式")
        return ApiResponse(
            code=0,
            message="成功完成因子稳定性检验",
            data={
                "window": request.window,
                "mean_autocorr": _sanitize(
                    result["rolling_autocorr"].mean().mean() if "rolling_autocorr" in result else None
                ),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子稳定性检验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/list-detail",
    response_model=ApiResponse,
    summary="获取因子明细列表",
    description="获取内置+自定义因子的分类、表达式、是否可计算等明细",
)
def get_factor_detail_list(current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """获取因子明细列表（因子库）"""
    try:
        return ApiResponse(code=0, message="ok", data={"factors": factor_service.get_factor_details()})
    except Exception as e:
        logger.error(f"获取因子明细失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/analyze",
    response_model=ApiResponse,
    summary="一站式因子分析",
    description="取数→因子→前瞻收益→IC/IR/分组多空/单调性/稳定性/序列",
)
def analyze_factor(request: FactorAnalyzeRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """一站式因子分析"""
    try:
        result = factor_service.analyze(
            factor_name=request.factor_name,
            symbols=request.instruments,
            interval=request.interval,
            candle_type=request.candle_type,
            start=request.start_time,
            end=request.end_time,
            method=request.method,
            n_groups=request.n_groups,
            window=request.window,
            forward=request.forward,
        )
        return ApiResponse(code=0, message="分析完成", data=_sanitize(result))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子分析失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/instruments",
    response_model=ApiResponse,
    summary="获取可分析品种与周期",
    description="按市场类型扫描本地 parquet，返回品种及其可用 K 线周期",
)
def list_instruments(
    candle_type: str = "spot",
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    """获取可分析品种与周期"""
    if candle_type not in {"spot", "future"}:
        raise HTTPException(status_code=400, detail="candle_type 必须为 spot 或 future")
    try:
        data = ParquetDataProvider().list_available_symbols(candle_type=candle_type)
        return ApiResponse(code=0, message="ok", data={"symbols": data})
    except Exception as e:
        logger.error(f"获取品种列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalog", response_model=ApiResponse, summary="获取因子档案列表")
def list_catalog(current_user: dict = Depends(get_current_user)) -> ApiResponse:
    try:
        with get_db_session() as db:
            created = _catalog_service.sync_builtins(db)
            if created:
                logger.info(f"因子档案惰性同步新建 {created} 个内置因子")
            rows = db.query(FactorCatalog).order_by(FactorCatalog.is_builtin.desc(), FactorCatalog.name).all()
            counts = dict(
                db.query(FactorSnapshot.factor_name, func.count(FactorSnapshot.id))
                .group_by(FactorSnapshot.factor_name)
                .all()
            )
            factors = [
                {
                    "name": r.name,
                    "label": r.label,
                    "category": r.category,
                    "expression": r.expression,
                    "builtin": r.is_builtin,
                    "supported": r.supported,
                    "lifecycle_status": r.lifecycle_status,
                    "last_metrics": json.loads(r.last_metrics) if r.last_metrics else None,
                    "last_snapshot_at": r.last_snapshot_at.isoformat() if r.last_snapshot_at else None,
                    "snapshot_count": counts.get(r.name, 0),
                }
                for r in rows
            ]
        return ApiResponse(code=0, message="ok", data={"factors": factors})
    except Exception as e:
        logger.error(f"获取因子档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _catalog_error(exc: CatalogError) -> HTTPException:
    return HTTPException(
        status_code={"not_found": 404, "forbidden": 403}.get(exc.kind, 400),
        detail=str(exc),
    )


@router.post(
    "/catalog/{factor_name}/lifecycle",
    response_model=ApiResponse,
    summary="因子生命周期流转",
)
def update_lifecycle(
    factor_name: str,
    request: LifecycleUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    try:
        with get_db_session() as db:
            row = _catalog_service.transition(db, factor_name, request.status)
            return ApiResponse(
                code=0,
                message="ok",
                data={"name": row.name, "lifecycle_status": row.lifecycle_status},
            )
    except CatalogError as e:
        raise _catalog_error(e)
    except Exception as e:
        logger.error(f"生命周期流转失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/snapshots", response_model=ApiResponse, summary="收藏因子分析快照（服务端重算）")
def save_snapshot(
    request: FactorAnalyzeRequest,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    try:
        params = request.model_dump()
        with get_db_session() as db:
            summary = _catalog_service.save_snapshot(db, params)
        return ApiResponse(code=0, message="快照已保存", data=_sanitize(summary))
    except CatalogError as e:
        raise _catalog_error(e)
    except (FactorError, FactorNotFoundError, _EngineExprError) as e:
        logger.error(f"快照收藏失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"快照收藏失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshots", response_model=ApiResponse, summary="查询因子快照历史")
def list_snapshots(
    factor_name: str,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    try:
        with get_db_session() as db:
            items = _catalog_service.list_snapshots(db, factor_name, limit=min(max(limit, 1), 500))
        return ApiResponse(code=0, message="ok", data={"snapshots": _sanitize(items)})
    except Exception as e:
        logger.error(f"快照查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/snapshots/{snapshot_id}", response_model=ApiResponse, summary="删除因子快照（parquet 归档）")
def delete_snapshot(snapshot_id: int, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    try:
        with get_db_session() as db:
            _catalog_service.delete_snapshot(db, snapshot_id)
        return ApiResponse(code=0, message="快照已删除")
    except CatalogError as e:
        raise _catalog_error(e)
    except Exception as e:
        logger.error(f"快照删除失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
