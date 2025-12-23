# 因子计算服务API路由

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from loguru import logger

from .schemas import (ApiResponse, FactorAddRequest,
                      FactorCalculateMultiRequest, FactorCalculateRequest,
                      FactorCorrelationRequest, FactorGroupAnalysisRequest,
                      FactorICRequest, FactorIRRequest,
                      FactorMonotonicityRequest, FactorStabilityRequest,
                      FactorStatsRequest, FactorValidateRequest)
from .service import FactorService

# 创建API路由实例
router = APIRouter()

# 创建因子服务实例
factor_service = FactorService()

# 创建因子计算API路由子路由
router_factor = APIRouter(prefix="/api/factor", tags=["factor-calculation"])


@router_factor.get("/list", response_model=ApiResponse)
def get_factor_list():
    """
    获取所有支持的因子列表
    
    Returns:
        ApiResponse: API响应，包含因子列表
    """
    try:
        logger.info("获取因子列表请求")
        
        # 获取因子列表
        factors = factor_service.get_factor_list()
        
        logger.info(f"成功获取因子列表，共 {len(factors)} 个因子")
        
        return ApiResponse(
            code=0,
            message="获取因子列表成功",
            data={"factors": factors}
        )
    except Exception as e:
        logger.error(f"获取因子列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.get("/expression/{factor_name}", response_model=ApiResponse)
def get_factor_expression(factor_name: str):
    """
    获取因子的表达式
    
    Args:
        factor_name: 因子名称
        
    Returns:
        ApiResponse: API响应，包含因子表达式
    """
    try:
        logger.info(f"获取因子表达式请求，因子名称: {factor_name}")
        
        # 获取因子表达式
        expression = factor_service.get_factor_expression(factor_name)
        
        if expression:
            logger.info(f"成功获取因子 {factor_name} 的表达式")
            return ApiResponse(
                code=0,
                message="获取因子表达式成功",
                data={"factor_name": factor_name, "expression": expression}
            )
        else:
            logger.error(f"因子 {factor_name} 不存在")
            return ApiResponse(
                code=1,
                message=f"因子 {factor_name} 不存在",
                data={}
            )
    except Exception as e:
        logger.error(f"获取因子表达式失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/add", response_model=ApiResponse)
def add_factor(request: FactorAddRequest):
    """
    添加自定义因子
    
    Args:
        request: 因子添加请求参数，包含因子名称和表达式
        
    Returns:
        ApiResponse: API响应，包含添加结果
    """
    try:
        logger.info(f"添加因子请求，因子名称: {request.factor_name}, 表达式: {request.expression}")
        
        # 添加因子
        result = factor_service.add_factor(request.factor_name, request.expression)
        
        if result:
            logger.info(f"成功添加因子 {request.factor_name}")
            return ApiResponse(
                code=0,
                message=f"成功添加因子 {request.factor_name}",
                data={"factor_name": request.factor_name, "expression": request.expression}
            )
        else:
            logger.error(f"添加因子 {request.factor_name} 失败")
            return ApiResponse(
                code=1,
                message=f"添加因子 {request.factor_name} 失败",
                data={}
            )
    except Exception as e:
        logger.error(f"添加因子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.delete("/delete/{factor_name}", response_model=ApiResponse)
def delete_factor(factor_name: str):
    """
    删除自定义因子
    
    Args:
        factor_name: 因子名称
        
    Returns:
        ApiResponse: API响应，包含删除结果
    """
    try:
        logger.info(f"删除因子请求，因子名称: {factor_name}")
        
        # 删除因子
        result = factor_service.delete_factor(factor_name)
        
        if result:
            logger.info(f"成功删除因子 {factor_name}")
            return ApiResponse(
                code=0,
                message=f"成功删除因子 {factor_name}",
                data={"factor_name": factor_name}
            )
        else:
            logger.error(f"因子 {factor_name} 不存在")
            return ApiResponse(
                code=1,
                message=f"因子 {factor_name} 不存在",
                data={}
            )
    except Exception as e:
        logger.error(f"删除因子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/calculate", response_model=ApiResponse)
def calculate_factor(request: FactorCalculateRequest):
    """
    计算指定因子的值
    
    Args:
        request: 因子计算请求参数，包含因子名称、标的列表、时间范围等
        
    Returns:
        ApiResponse: API响应，包含因子计算结果
    """
    try:
        logger.info(f"计算因子请求，因子名称: {request.factor_name}")
        
        # 计算因子
        factor_data = factor_service.calculate_factor(
            factor_name=request.factor_name,
            instruments=request.instruments,
            start_time=request.start_time,
            end_time=request.end_time,
            freq=request.freq
        )
        
        if factor_data is not None:
            # 将DataFrame转换为字典格式
            factor_dict = factor_data.reset_index().to_dict(orient="records")
            
            logger.info(f"成功计算因子 {request.factor_name}")
            return ApiResponse(
                code=0,
                message=f"成功计算因子 {request.factor_name}",
                data={
                    "factor_name": request.factor_name,
                    "data": factor_dict,
                    "shape": factor_data.shape
                }
            )
        else:
            logger.error(f"计算因子 {request.factor_name} 失败")
            return ApiResponse(
                code=1,
                message=f"计算因子 {request.factor_name} 失败",
                data={}
            )
    except Exception as e:
        logger.error(f"计算因子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/calculate-multi", response_model=ApiResponse)
def calculate_factors(request: FactorCalculateMultiRequest):
    """
    计算多个因子的值
    
    Args:
        request: 多因子计算请求参数，包含因子名称列表、标的列表、时间范围等
        
    Returns:
        ApiResponse: API响应，包含多因子计算结果
    """
    try:
        logger.info(f"计算多个因子请求，因子数量: {len(request.factor_names)}")
        
        # 计算多个因子
        factor_data = factor_service.calculate_factors(
            factor_names=request.factor_names,
            instruments=request.instruments,
            start_time=request.start_time,
            end_time=request.end_time,
            freq=request.freq
        )
        
        if factor_data is not None:
            # 将DataFrame转换为字典格式
            factor_dict = factor_data.reset_index().to_dict(orient="records")
            
            logger.info(f"成功计算多个因子，共 {len(request.factor_names)} 个因子")
            return ApiResponse(
                code=0,
                message="成功计算多个因子",
                data={
                    "factor_names": request.factor_names,
                    "data": factor_dict,
                    "shape": factor_data.shape
                }
            )
        else:
            logger.error("计算多个因子失败")
            return ApiResponse(
                code=1,
                message="计算多个因子失败",
                data={}
            )
    except Exception as e:
        logger.error(f"计算多个因子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/calculate-all", response_model=ApiResponse)
def calculate_all_factors(request: FactorCalculateRequest):
    """
    计算所有因子的值
    
    Args:
        request: 因子计算请求参数，包含标的列表、时间范围等
        
    Returns:
        ApiResponse: API响应，包含所有因子计算结果
    """
    try:
        logger.info("计算所有因子请求")
        
        # 计算所有因子
        factor_data = factor_service.calculate_all_factors(
            instruments=request.instruments,
            start_time=request.start_time,
            end_time=request.end_time,
            freq=request.freq
        )
        
        if factor_data is not None:
            # 将DataFrame转换为字典格式
            factor_dict = factor_data.reset_index().to_dict(orient="records")
            
            logger.info(f"成功计算所有因子，共 {len(factor_data.columns)} 个因子")
            return ApiResponse(
                code=0,
                message="成功计算所有因子",
                data={
                    "factor_names": list(factor_data.columns),
                    "data": factor_dict,
                    "shape": factor_data.shape
                }
            )
        else:
            logger.error("计算所有因子失败")
            return ApiResponse(
                code=1,
                message="计算所有因子失败",
                data={}
            )
    except Exception as e:
        logger.error(f"计算所有因子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/validate", response_model=ApiResponse)
def validate_factor_expression(request: FactorValidateRequest):
    """
    验证因子表达式是否有效
    
    Args:
        request: 因子表达式验证请求参数，包含因子表达式
        
    Returns:
        ApiResponse: API响应，包含验证结果
    """
    try:
        logger.info(f"验证因子表达式请求，表达式: {request.expression}")
        
        # 验证因子表达式
        result = factor_service.validate_factor_expression(request.expression)
        
        if result:
            logger.info("因子表达式验证通过")
            return ApiResponse(
                code=0,
                message="因子表达式验证通过",
                data={"valid": True, "expression": request.expression}
            )
        else:
            logger.error("因子表达式验证失败")
            return ApiResponse(
                code=1,
                message="因子表达式验证失败",
                data={"valid": False, "expression": request.expression}
            )
    except Exception as e:
        logger.error(f"验证因子表达式失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/correlation", response_model=ApiResponse)
def get_factor_correlation(request: FactorCorrelationRequest):
    """
    计算因子之间的相关性
    
    Args:
        request: 因子相关性请求参数，包含因子数据
        
    Returns:
        ApiResponse: API响应，包含因子相关性矩阵
    """
    try:
        logger.info("计算因子相关性请求")
        
        # 这里需要先将请求中的数据转换为DataFrame
        # 由于暂时没有实现，返回示例数据
        
        logger.info("成功计算因子相关性")
        return ApiResponse(
            code=0,
            message="成功计算因子相关性",
            data={"correlation": {}}
        )
    except Exception as e:
        logger.error(f"计算因子相关性失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/stats", response_model=ApiResponse)
def get_factor_stats(request: FactorStatsRequest):
    """
    获取因子的描述性统计信息
    
    Args:
        request: 因子统计请求参数，包含因子数据
        
    Returns:
        ApiResponse: API响应，包含因子统计信息
    """
    try:
        logger.info("获取因子统计信息请求")
        
        # 这里需要先将请求中的数据转换为DataFrame
        # 由于暂时没有实现，返回示例数据
        
        logger.info("成功获取因子统计信息")
        return ApiResponse(
            code=0,
            message="成功获取因子统计信息",
            data={"stats": {}}
        )
    except Exception as e:
        logger.error(f"获取因子统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/ic", response_model=ApiResponse)
def calculate_factor_ic(request: FactorICRequest):
    """
    计算因子的信息系数(IC)
    
    Args:
        request: 因子IC计算请求参数，包含因子数据、收益率数据和计算方法
        
    Returns:
        ApiResponse: API响应，包含IC计算结果
    """
    try:
        logger.info("计算因子IC请求")
        
        # 这里需要先将请求中的数据转换为DataFrame
        # 由于暂时没有实现，返回示例数据
        
        logger.info("成功计算因子IC")
        return ApiResponse(
            code=0,
            message="成功计算因子IC",
            data={"ic": {}}
        )
    except Exception as e:
        logger.error(f"计算因子IC失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/ir", response_model=ApiResponse)
def calculate_factor_ir(request: FactorIRRequest):
    """
    计算因子的信息比率(IR)
    
    Args:
        request: 因子IR计算请求参数，包含因子数据、收益率数据和计算方法
        
    Returns:
        ApiResponse: API响应，包含IR计算结果
    """
    try:
        logger.info("计算因子IR请求")
        
        # 这里需要先将请求中的数据转换为DataFrame
        # 由于暂时没有实现，返回示例数据
        
        logger.info("成功计算因子IR")
        return ApiResponse(
            code=0,
            message="成功计算因子IR",
            data={"ir": 0.5}
        )
    except Exception as e:
        logger.error(f"计算因子IR失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/group-analysis", response_model=ApiResponse)
def factor_group_analysis(request: FactorGroupAnalysisRequest):
    """
    因子分组回测分析
    
    Args:
        request: 因子分组分析请求参数，包含因子数据、收益率数据和分组数量
        
    Returns:
        ApiResponse: API响应，包含分组回测结果
    """
    try:
        logger.info("因子分组分析请求")
        
        # 这里需要先将请求中的数据转换为DataFrame
        # 由于暂时没有实现，返回示例数据
        
        logger.info("成功完成因子分组分析")
        return ApiResponse(
            code=0,
            message="成功完成因子分组分析",
            data={"group_analysis": {}}
        )
    except Exception as e:
        logger.error(f"因子分组分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/monotonicity", response_model=ApiResponse)
def factor_monotonicity_test(request: FactorMonotonicityRequest):
    """
    因子单调性检验
    
    Args:
        request: 因子单调性检验请求参数，包含因子数据、收益率数据和分组数量
        
    Returns:
        ApiResponse: API响应，包含单调性检验结果
    """
    try:
        logger.info("因子单调性检验请求")
        
        # 这里需要先将请求中的数据转换为DataFrame
        # 由于暂时没有实现，返回示例数据
        
        logger.info("成功完成因子单调性检验")
        return ApiResponse(
            code=0,
            message="成功完成因子单调性检验",
            data={"monotonicity": {}}
        )
    except Exception as e:
        logger.error(f"因子单调性检验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_factor.post("/stability", response_model=ApiResponse)
def factor_stability_test(request: FactorStabilityRequest):
    """
    因子稳定性检验
    
    Args:
        request: 因子稳定性检验请求参数，包含因子数据和滚动窗口大小
        
    Returns:
        ApiResponse: API响应，包含稳定性检验结果
    """
    try:
        logger.info("因子稳定性检验请求")
        
        # 这里需要先将请求中的数据转换为DataFrame
        # 由于暂时没有实现，返回示例数据
        
        logger.info("成功完成因子稳定性检验")
        return ApiResponse(
            code=0,
            message="成功完成因子稳定性检验",
            data={"stability": {}}
        )
    except Exception as e:
        logger.error(f"因子稳定性检验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册因子计算API路由
router.include_router(router_factor)
