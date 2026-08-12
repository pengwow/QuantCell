"""因子计算模块API路由 — 因子列表/CRUD/计算/分析"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request

from common.schemas import ApiResponse
from utils.auth import jwt_auth_required
from utils.logger import get_logger, LogType
from .schemas import (
    FactorAddRequest,
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
)
from .service import FactorService

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
    for inst, values in data.items():
        for v in values:
            rows.append(v)
    return pd.Series(rows, dtype=float)

# 创建路由
router = APIRouter(
    prefix="/api/factor",
    tags=["factor"],
    responses={
        200: {"description": "成功", "model": ApiResponse},
        500: {"description": "服务器错误"},
    },
)

# 创建服务实例
factor_service = FactorService()


@jwt_auth_required
@router.get("/list", response_model=ApiResponse, summary="获取因子列表", description="获取所有支持的因子列表")
def get_factor_list(request: Request, ) -> ApiResponse:
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


@jwt_auth_required
@router.get("/expression/{factor_name}", response_model=ApiResponse, summary="获取因子表达式", description="获取指定因子的表达式")
def get_factor_expression(request: Request, factor_name: str) -> ApiResponse:
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


@jwt_auth_required
@router.post("/add", response_model=ApiResponse, summary="添加自定义因子", description="添加新的自定义因子")
def add_factor(http_request: Request, request: FactorAddRequest) -> ApiResponse:
    """添加自定义因子"""
    try:
        logger.info(f"添加因子请求，因子名称: {request.factor_name}, 表达式: {request.expression}")
        result = factor_service.add_factor(request.factor_name, request.expression)
        if result:
            logger.info(f"成功添加因子 {request.factor_name}")
            return ApiResponse(
                code=0,
                message=f"成功添加因子 {request.factor_name}",
                data={"factor_name": request.factor_name, "expression": request.expression},
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


@jwt_auth_required
@router.delete("/delete/{factor_name}", response_model=ApiResponse, summary="删除自定义因子", description="删除指定的自定义因子")
def delete_factor(request: Request, factor_name: str) -> ApiResponse:
    """删除自定义因子"""
    try:
        logger.info(f"删除因子请求，因子名称: {factor_name}")
        result = factor_service.delete_factor(factor_name)
        if result:
            logger.info(f"成功删除因子 {factor_name}")
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


@jwt_auth_required
@router.post("/calculate", response_model=ApiResponse, summary="计算单因子", description="计算指定因子的值")
def calculate_factor(http_request: Request, request: FactorCalculateRequest) -> ApiResponse:
    """计算指定因子的值"""
    try:
        logger.info(f"计算因子请求，因子名称: {request.factor_name}")
        factor_data = factor_service.calculate_factor(
            factor_name=request.factor_name,
            instruments=request.instruments,
            start_time=request.start_time,
            end_time=request.end_time,
            freq=request.freq,
        )
        if factor_data is not None:
            factor_dict = factor_data.reset_index().to_dict(orient="records")
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
        else:
            logger.error(f"计算因子 {request.factor_name} 失败")
            return ApiResponse(
                code=1,
                message=f"计算因子 {request.factor_name} 失败",
                data={},
            )
    except Exception as e:
        logger.error(f"计算因子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@jwt_auth_required
@router.post("/calculate-multi", response_model=ApiResponse, summary="计算多因子", description="计算多个因子的值")
def calculate_factors(http_request: Request, request: FactorCalculateMultiRequest) -> ApiResponse:
    """计算多个因子的值"""
    try:
        logger.info(f"计算多个因子请求，因子数量: {len(request.factor_names)}")
        factor_data = factor_service.calculate_factors(
            factor_names=request.factor_names,
            instruments=request.instruments,
            start_time=request.start_time,
            end_time=request.end_time,
            freq=request.freq,
        )
        if factor_data is not None:
            factor_dict = factor_data.reset_index().to_dict(orient="records")
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
        else:
            logger.error("计算多个因子失败")
            return ApiResponse(
                code=1,
                message="计算多个因子失败",
                data={},
            )
    except Exception as e:
        logger.error(f"计算多个因子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@jwt_auth_required
@router.post("/calculate-all", response_model=ApiResponse, summary="计算所有因子", description="计算所有内置因子的值")
def calculate_all_factors(http_request: Request, request: FactorCalculateRequest) -> ApiResponse:
    """计算所有因子的值"""
    try:
        logger.info("计算所有因子请求")
        factor_data = factor_service.calculate_all_factors(
            instruments=request.instruments,
            start_time=request.start_time,
            end_time=request.end_time,
            freq=request.freq,
        )
        if factor_data is not None:
            factor_dict = factor_data.reset_index().to_dict(orient="records")
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
        else:
            logger.error("计算所有因子失败")
            return ApiResponse(
                code=1,
                message="计算所有因子失败",
                data={},
            )
    except Exception as e:
        logger.error(f"计算所有因子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@jwt_auth_required
@router.post("/validate", response_model=ApiResponse, summary="验证因子表达式", description="验证因子表达式是否有效")
def validate_factor_expression(http_request: Request, request: FactorValidateRequest) -> ApiResponse:
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


@jwt_auth_required
@router.post("/correlation", response_model=ApiResponse, summary="计算因子相关性", description="计算因子之间的相关性矩阵")
def get_factor_correlation(http_request: Request, request: FactorCorrelationRequest) -> ApiResponse:
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


@jwt_auth_required
@router.post("/stats", response_model=ApiResponse, summary="获取因子统计", description="获取因子的描述性统计信息")
def get_factor_stats(http_request: Request, request: FactorStatsRequest) -> ApiResponse:
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


@jwt_auth_required
@router.post("/ic", response_model=ApiResponse, summary="计算IC", description="计算因子的信息系数(IC)")
def calculate_factor_ic(http_request: Request, request: FactorICRequest) -> ApiResponse:
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


@jwt_auth_required
@router.post("/ir", response_model=ApiResponse, summary="计算IR", description="计算因子的信息比率(IR)")
def calculate_factor_ir(http_request: Request, request: FactorIRRequest) -> ApiResponse:
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


@jwt_auth_required
@router.post("/group-analysis", response_model=ApiResponse, summary="分组分析", description="因子分组回测分析")
def factor_group_analysis(http_request: Request, request: FactorGroupAnalysisRequest) -> ApiResponse:
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
                "long_short_return": _sanitize(result["long_short_return"].sum()) if "long_short_return" in result else None,
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


@jwt_auth_required
@router.post("/monotonicity", response_model=ApiResponse, summary="单调性检验", description="因子单调性检验")
def factor_monotonicity_test(http_request: Request, request: FactorMonotonicityRequest) -> ApiResponse:
    """因子单调性检验"""
    try:
        factor_df = _dict_to_df(request.factor_data)
        return_series = _returns_dict_to_series(request.return_data)
        result = factor_service.factor_monotonicity_test(
            factor_df, return_series, n_groups=request.n_groups
        )
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


@jwt_auth_required
@router.post("/stability", response_model=ApiResponse, summary="稳定性检验", description="因子稳定性检验")
def factor_stability_test(http_request: Request, request: FactorStabilityRequest) -> ApiResponse:
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
                    result["rolling_autocorr"].mean().mean()
                    if "rolling_autocorr" in result
                    else None
                ),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子稳定性检验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
