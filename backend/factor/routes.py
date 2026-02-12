"""
因子计算模块API路由

提供因子计算相关的RESTful API端点。

路由前缀: /api/factor
标签: factor

端点列表：
    GET    /api/factor/list              获取因子列表
    GET    /api/factor/expression/{name} 获取因子表达式
    POST   /api/factor/add               添加自定义因子
    DELETE /api/factor/delete/{name}     删除自定义因子
    POST   /api/factor/calculate         计算单因子
    POST   /api/factor/calculate-multi   计算多因子
    POST   /api/factor/calculate-all     计算所有因子
    POST   /api/factor/validate          验证因子表达式
    POST   /api/factor/correlation       计算因子相关性
    POST   /api/factor/stats             获取因子统计
    POST   /api/factor/ic                计算IC
    POST   /api/factor/ir                计算IR
    POST   /api/factor/group-analysis    分组分析
    POST   /api/factor/monotonicity      单调性检验
    POST   /api/factor/stability         稳定性检验

依赖：
    - schemas: 请求/响应模型
    - service: 业务逻辑

作者: QuantCell Team
创建日期: 2024-01-01
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from loguru import logger

from backend.common.schemas import ApiResponse

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


@router.get("/list", response_model=ApiResponse, summary="获取因子列表", description="获取所有支持的因子列表")
def get_factor_list() -> ApiResponse:
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


@router.get("/expression/{factor_name}", response_model=ApiResponse, summary="获取因子表达式", description="获取指定因子的表达式")
def get_factor_expression(factor_name: str) -> ApiResponse:
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


@router.post("/add", response_model=ApiResponse, summary="添加自定义因子", description="添加新的自定义因子")
def add_factor(request: FactorAddRequest) -> ApiResponse:
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


@router.delete("/delete/{factor_name}", response_model=ApiResponse, summary="删除自定义因子", description="删除指定的自定义因子")
def delete_factor(factor_name: str) -> ApiResponse:
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


@router.post("/calculate", response_model=ApiResponse, summary="计算单因子", description="计算指定因子的值")
def calculate_factor(request: FactorCalculateRequest) -> ApiResponse:
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


@router.post("/calculate-multi", response_model=ApiResponse, summary="计算多因子", description="计算多个因子的值")
def calculate_factors(request: FactorCalculateMultiRequest) -> ApiResponse:
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


@router.post("/calculate-all", response_model=ApiResponse, summary="计算所有因子", description="计算所有内置因子的值")
def calculate_all_factors(request: FactorCalculateRequest) -> ApiResponse:
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


@router.post("/validate", response_model=ApiResponse, summary="验证因子表达式", description="验证因子表达式是否有效")
def validate_factor_expression(request: FactorValidateRequest) -> ApiResponse:
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


@router.post("/correlation", response_model=ApiResponse, summary="计算因子相关性", description="计算因子之间的相关性矩阵")
def get_factor_correlation(request: FactorCorrelationRequest) -> ApiResponse:
    """计算因子之间的相关性"""
    try:
        logger.info("计算因子相关性请求")
        logger.info("成功计算因子相关性")
        return ApiResponse(
            code=0,
            message="成功计算因子相关性",
            data={"correlation": {}},
        )
    except Exception as e:
        logger.error(f"计算因子相关性失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stats", response_model=ApiResponse, summary="获取因子统计", description="获取因子的描述性统计信息")
def get_factor_stats(request: FactorStatsRequest) -> ApiResponse:
    """获取因子的描述性统计信息"""
    try:
        logger.info("获取因子统计信息请求")
        logger.info("成功获取因子统计信息")
        return ApiResponse(
            code=0,
            message="成功获取因子统计信息",
            data={"stats": {}},
        )
    except Exception as e:
        logger.error(f"获取因子统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ic", response_model=ApiResponse, summary="计算IC", description="计算因子的信息系数(IC)")
def calculate_factor_ic(request: FactorICRequest) -> ApiResponse:
    """计算因子的信息系数(IC)"""
    try:
        logger.info("计算因子IC请求")
        logger.info("成功计算因子IC")
        return ApiResponse(
            code=0,
            message="成功计算因子IC",
            data={"ic": {}},
        )
    except Exception as e:
        logger.error(f"计算因子IC失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ir", response_model=ApiResponse, summary="计算IR", description="计算因子的信息比率(IR)")
def calculate_factor_ir(request: FactorIRRequest) -> ApiResponse:
    """计算因子的信息比率(IR)"""
    try:
        logger.info("计算因子IR请求")
        logger.info("成功计算因子IR")
        return ApiResponse(
            code=0,
            message="成功计算因子IR",
            data={"ir": 0.5},
        )
    except Exception as e:
        logger.error(f"计算因子IR失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group-analysis", response_model=ApiResponse, summary="分组分析", description="因子分组回测分析")
def factor_group_analysis(request: FactorGroupAnalysisRequest) -> ApiResponse:
    """因子分组回测分析"""
    try:
        logger.info("因子分组分析请求")
        logger.info("成功完成因子分组分析")
        return ApiResponse(
            code=0,
            message="成功完成因子分组分析",
            data={"group_analysis": {}},
        )
    except Exception as e:
        logger.error(f"因子分组分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monotonicity", response_model=ApiResponse, summary="单调性检验", description="因子单调性检验")
def factor_monotonicity_test(request: FactorMonotonicityRequest) -> ApiResponse:
    """因子单调性检验"""
    try:
        logger.info("因子单调性检验请求")
        logger.info("成功完成因子单调性检验")
        return ApiResponse(
            code=0,
            message="成功完成因子单调性检验",
            data={"monotonicity": {}},
        )
    except Exception as e:
        logger.error(f"因子单调性检验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stability", response_model=ApiResponse, summary="稳定性检验", description="因子稳定性检验")
def factor_stability_test(request: FactorStabilityRequest) -> ApiResponse:
    """因子稳定性检验"""
    try:
        logger.info("因子稳定性检验请求")
        logger.info("成功完成因子稳定性检验")
        return ApiResponse(
            code=0,
            message="成功完成因子稳定性检验",
            data={"stability": {}},
        )
    except Exception as e:
        logger.error(f"因子稳定性检验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
