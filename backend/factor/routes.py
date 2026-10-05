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

from axon_bridge.llm import create_llm_backend
from common.schemas import ApiResponse
from factor.catalog_service import CatalogError, FactorCatalogService
from factor.job_manager import JobStatus, job_manager
from factor.llm_miner import LLMMineParams, run_llm_mining
from factor.models import FactorCatalog, FactorSnapshot
from factor.sandbox import SandboxError
from quality.parquet_provider import ParquetDataProvider
from utils.auth import get_current_user
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

from .schemas import (
    CodeFactorAddRequest,
    CodeFactorValidateRequest,
    FactorAddRequest,
    FactorAnalyzeRequest,
    FactorCalculateBase,
    FactorCalculateMultiRequest,
    FactorCalculateRequest,
    FactorCompareRequest,
    FactorCompositeAddRequest,
    FactorCorrelationRequest,
    FactorGroupAnalysisRequest,
    FactorICRequest,
    FactorIRRequest,
    FactorMineLLMRequest,
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
            horizons=request.horizons,
            cost_bps=request.cost_bps,
        )
        return ApiResponse(code=0, message="分析完成", data=_sanitize(result))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子分析失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/compare",
    response_model=ApiResponse,
    summary="多因子横向对比（2-5 个因子共用参数）",
)
def compare_factors(request: FactorCompareRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """多因子横向对比：逐因子分析 + IC 时序按时间轴 outer 对齐。"""
    try:
        data = factor_service.compare_factors(
            factor_names=request.factor_names,
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
        return ApiResponse(code=0, message="ok", data=_sanitize(data))
    except Exception as e:
        logger.error(f"多因子对比失败: {e}")
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


@router.post("/snapshots", response_model=ApiResponse, summary="保存因子分析快照（服务端重算）")
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
        logger.error(f"快照保存失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"快照保存失败: {e}")
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


# ---------------- 异步任务（analyze/compare） ----------------


def _run_analyze_job(params: dict[str, Any]):
    """构造 analyze 异步任务 runner（工作线程内执行，进度经 WS factor:job 推送）。"""

    def runner(on_progress, _on_stage):
        on_progress(30, "data", "读取数据…")
        on_progress(90, "computing", "计算因子指标…")
        return factor_service.analyze(
            factor_name=params["factor_name"],
            symbols=params["instruments"],
            interval=params["interval"],
            candle_type=params["candle_type"],
            start=params["start_time"],
            end=params["end_time"],
            method=params["method"],
            n_groups=params["n_groups"],
            window=params["window"],
            forward=params["forward"],
            horizons=params.get("horizons"),
            cost_bps=params.get("cost_bps", 0.0),
        )

    return runner


def _run_compare_job(params: dict[str, Any]):
    """构造 compare 异步任务 runner：逐因子推进度，再共用 _assemble_compare 组装。"""
    names = params["factor_names"]

    def runner(on_progress, _on_stage):
        on_progress(20, "data", "读取数据…")
        results = {}
        for i, name in enumerate(names):
            on_progress(20 + i / len(names) * 70, "computing", f"{name} ({i + 1}/{len(names)})")
            results[name] = factor_service.analyze(
                factor_name=name,
                symbols=params["instruments"],
                interval=params["interval"],
                candle_type=params["candle_type"],
                start=params["start_time"],
                end=params["end_time"],
                method=params["method"],
                n_groups=params["n_groups"],
                window=params["window"],
                forward=params["forward"],
                horizons=params.get("horizons"),
                cost_bps=params.get("cost_bps", 0.0),
            )
        on_progress(95, "assembling", "汇总对比…")
        details = {d["name"]: d for d in factor_service.get_factor_details()}
        labels = {n: details.get(n, {}).get("label", n) for n in names}
        return FactorService._assemble_compare(results, labels)

    return runner


def _resolve_llm_config(model_id: str | None = None) -> dict[str, Any] | None:
    """解析默认 AI 提供商配置（同步读系统配置，必须在提交 job 前的请求线程完成）。"""
    try:
        from ai_model.config_utils import get_default_provider_and_models

        result = get_default_provider_and_models()
    except Exception as e:
        logger.warning(f"读取 AI 模型配置失败: {e}")
        return None
    if not result:
        return None
    provider = result["provider"]
    api_key = provider.get("api_key")
    if not api_key:
        return None
    enabled = result.get("enabled_models") or []
    model_name = ""
    if model_id:
        model_name = next((m.get("name") for m in enabled if m.get("id") == model_id), model_id)
    elif enabled:
        model_name = enabled[0].get("name", "")
    return {"api_key": api_key, "base_url": provider.get("api_host"), "model": model_name}


def _run_llm_mine_job(params: dict[str, Any], llm_cfg: dict[str, Any]):
    """构造 llm_mine 任务 runner（工作线程内建 backend，进度经 WS factor:job 推送）。"""

    def runner(on_progress, _on_stage):
        backend = create_llm_backend(
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg["base_url"],
            model=llm_cfg["model"],
            temperature=float(params.get("temperature", 0.8)),
            # reasoning 模型思考链较长：8192 会被思考耗尽而 content 为空（实测
            # DeepSeek-V4-Flash 单次思考可达 9k token），提到 16384 留足正文预算
            max_tokens=16384,
            timeout_secs=180,
        )
        mine_params = LLMMineParams(
            symbols=params["instruments"],
            interval=params["interval"],
            candle_type=params["candle_type"],
            start=params["start_time"],
            end=params["end_time"],
            n_candidates=params["n_candidates"],
            n_rounds=params["n_rounds"],
            top_k=params["top_k"],
            temperature=params["temperature"],
            model_id=params.get("model_id"),
            model_name=llm_cfg["model"],
            test_ratio=float(params.get("test_ratio", 0.3)),
            wf_folds=int(params.get("wf_folds", 0) or 0),
            dedup_corr=float(params.get("dedup_corr", 0.9)),
            compose=bool(params.get("compose", True)),
        )
        return run_llm_mining(mine_params, backend=backend, progress=on_progress)

    return runner


@router.post("/analyze-async", response_model=ApiResponse, summary="异步因子分析（返回 job_id，进度走 WS factor:job）")
def analyze_async(request: FactorAnalyzeRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    params = request.model_dump()
    job_id = job_manager.submit("analyze", params, _run_analyze_job(params))
    return ApiResponse(code=0, message="ok", data={"job_id": job_id, "status": "pending"})


@router.post("/compare-async", response_model=ApiResponse, summary="异步多因子对比")
def compare_async(request: FactorCompareRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    params = request.model_dump()
    job_id = job_manager.submit("compare", params, _run_compare_job(params))
    return ApiResponse(code=0, message="ok", data={"job_id": job_id, "status": "pending"})


@router.post("/code/validate", response_model=ApiResponse, summary="校验代码因子（静态策略+合成数据沙箱执行）")
def validate_code_factor(
    request: CodeFactorValidateRequest, current_user: dict = Depends(get_current_user)
) -> ApiResponse:
    try:
        factor_service._sandbox.validate(request.code)
        return ApiResponse(code=0, message="代码校验通过", data={"valid": True})
    except SandboxError as e:
        return ApiResponse(
            code=1,
            message="代码校验失败",
            data={"valid": False, "error_type": type(e).__name__, "message": str(e)},
        )


@router.post("/code/add", response_model=ApiResponse, summary="新增代码因子（沙箱校验通过后入库）")
def add_code_factor(request: CodeFactorAddRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    try:
        factor_service.save_code_factor(
            request.factor_name,
            request.code,
            request.description or "",
            provenance={"source": "manual_or_llm"},
        )
        # ---- 保存成功后建档（派生数据，失败不阻断代码保存；模式同表达式 add_factor）----
        try:
            with get_db_session() as db:
                _catalog_service.sync_builtins(db)  # 确保内置已在，自定义 upsert 不依赖顺序
                details = [d for d in factor_service.get_factor_details() if d["name"] == request.factor_name]
                if details:
                    _catalog_service.upsert_custom(db, details[0])
        except Exception as hook_err:
            logger.warning(f"代码因子档案建档失败（不影响代码保存）: {hook_err}")
        return ApiResponse(
            code=0,
            message=f"代码因子 {request.factor_name} 已保存",
            data={"factor_name": request.factor_name},
        )
    except (FactorError, FactorNotFoundError, _EngineExprError, SandboxError) as e:
        logger.info(f"代码因子入库被拒: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/code/{factor_name}", response_model=ApiResponse, summary="删除代码因子")
def delete_code_factor(factor_name: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    try:
        factor_service.delete_code_factor(factor_name)
        # 代码已从 JSON 删除：清理 DB 档案行与快照行；钩子失败不阻断接口（仅 warning 暴露残留）
        try:
            with get_db_session() as db:
                _catalog_service.on_factor_deleted(db, factor_name)
        except Exception as hook_err:
            logger.warning(f"代码因子档案删除失败（代码已从 JSON 删除）: {hook_err}")
        return ApiResponse(code=0, message=f"代码因子 {factor_name} 已删除")
    except FactorNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/composite/add",
    response_model=ApiResponse,
    summary="新增合成因子（IC 加权 zscore，成分代码沙箱校验通过后入库）",
)
def add_composite_factor(
    request: FactorCompositeAddRequest, current_user: dict = Depends(get_current_user)
) -> ApiResponse:
    """保存挖掘产出的合成因子：名称互斥 + 每成分沙箱校验 + 冻结权重/时序统计落盘。"""
    try:
        factor_service.save_composite(
            request.factor_name,
            request.description or "",
            codes=[c.code for c in request.constituents],
            weights=[c.weight for c in request.constituents],
            ts_stats_list=[c.ts_stats for c in request.constituents],
            train_window=request.train_window.model_dump(),
            provenance={"source": "llm_mining_composite"},
        )
        # ---- 保存成功后建档（派生数据，失败不阻断保存；模式同 /code/add）----
        try:
            with get_db_session() as db:
                _catalog_service.sync_builtins(db)
                details = [d for d in factor_service.get_factor_details() if d["name"] == request.factor_name]
                if details:
                    _catalog_service.upsert_custom(db, details[0])
        except Exception as hook_err:
            logger.warning(f"合成因子档案建档失败（不影响合成因子保存）: {hook_err}")
        return ApiResponse(
            code=0,
            message=f"合成因子 {request.factor_name} 已保存",
            data={"factor_name": request.factor_name},
        )
    except (FactorError, FactorNotFoundError, _EngineExprError, SandboxError) as e:
        logger.info(f"合成因子入库被拒: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/composite/{factor_name}", response_model=ApiResponse, summary="删除合成因子")
def delete_composite_factor(factor_name: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """删除合成因子 JSON 条目，并级联清理因子档案行与快照行（钩子失败仅 warning）。"""
    try:
        factor_service.delete_composite(factor_name)
        try:
            with get_db_session() as db:
                _catalog_service.on_factor_deleted(db, factor_name)
        except Exception as hook_err:
            logger.warning(f"合成因子档案删除失败（因子已从 JSON 删除）: {hook_err}")
        return ApiResponse(code=0, message=f"合成因子 {factor_name} 已删除")
    except FactorNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/mine/llm",
    response_model=ApiResponse,
    summary="提交 LLM 因子挖掘任务（异步，进度走 WS factor:job）",
)
def mine_llm_factors(request: FactorMineLLMRequest, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    llm_cfg = _resolve_llm_config(request.model_id)
    if llm_cfg is None:
        raise HTTPException(status_code=400, detail="未配置可用的默认 AI 模型或 API Key，请先在模型管理中配置")
    params = request.model_dump()
    job_id = job_manager.submit("llm_mine", params, _run_llm_mine_job(params, llm_cfg))
    return ApiResponse(code=0, message="ok", data={"job_id": job_id, "status": "pending"})


@router.get("/jobs/{job_id}", response_model=ApiResponse, summary="查询因子任务状态")
def get_factor_job(job_id: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    status = job_manager.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return ApiResponse(code=0, message="ok", data=_sanitize(status))


@router.get("/jobs/{job_id}/result", response_model=ApiResponse, summary="获取因子任务结果")
def get_factor_job_result(job_id: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
        raise HTTPException(status_code=409, detail=f"任务尚未完成（{job.status}）")
    if job.status == JobStatus.FAILED:
        raise HTTPException(status_code=410, detail=job.error or "任务失败")
    return ApiResponse(code=0, message="ok", data=_sanitize(job.result))
