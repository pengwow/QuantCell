# 资产池管理API路由

from fastapi import APIRouter, HTTPException, Request
from typing import Optional, Dict, Any, List
from loguru import logger

from ..schemas import ApiResponse
from ..db import DataPoolBusiness as DataPool

# 创建API路由实例
router = APIRouter(prefix="/api/data-pools", tags=["data-pool-management"])


@router.get("/", response_model=ApiResponse)
def get_all_pools(type: Optional[str] = None):
    """获取所有资产池，支持按类型过滤
    
    Args:
        type: 资产池类型过滤（stock/crypto）
        
    Returns:
        ApiResponse: 包含所有资产池的响应
    """
    try:
        logger.info(f"开始获取所有资产池，类型过滤: {type}")
        
        # 获取所有资产池
        pools = DataPool.get_all(type=type)
        
        logger.info(f"成功获取所有资产池，共 {len(pools)} 个")
        
        return ApiResponse(
            code=0,
            message="获取所有资产池成功",
            data=pools
        )
    except Exception as e:
        logger.error(f"获取所有资产池失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pool_id}", response_model=ApiResponse)
def get_pool(pool_id: int):
    """获取指定ID的资产池
    
    Args:
        pool_id: 资产池ID
        
    Returns:
        ApiResponse: 包含资产池详情的响应
    """
    try:
        logger.info(f"开始获取资产池: {pool_id}")
        
        # 获取资产池
        pool = DataPool.get(pool_id)
        
        if pool:
            logger.info(f"成功获取资产池: {pool_id}")
            return ApiResponse(
                code=0,
                message="获取资产池成功",
                data=pool
            )
        else:
            logger.warning(f"资产池不存在: {pool_id}")
            return ApiResponse(
                code=1,
                message="资产池不存在",
                data={"pool_id": pool_id}
            )
    except Exception as e:
        logger.error(f"获取资产池失败: pool_id={pool_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=ApiResponse)
def create_pool(pool: Dict[str, Any]):
    """创建新资产池
    
    Args:
        pool: 资产池信息，包含name、type、description、color、tags等字段
        
    Returns:
        ApiResponse: 包含创建结果的响应
    """
    try:
        # 验证请求数据
        if "name" not in pool or "type" not in pool:
            raise HTTPException(status_code=400, detail="请求数据必须包含name和type字段")
        
        name = pool["name"]
        type = pool["type"]
        description = pool.get("description")
        color = pool.get("color")
        tags = pool.get("tags")
        
        logger.info(f"开始创建资产池: name={name}, type={type}")
        
        # 创建资产池
        pool_id = DataPool.create(name, type, description, color, tags)
        
        if pool_id:
            logger.info(f"成功创建资产池: id={pool_id}, name={name}")
            return ApiResponse(
                code=0,
                message="创建资产池成功",
                data={"pool_id": pool_id, "name": name, "type": type}
            )
        else:
            logger.error(f"创建资产池失败: name={name}, type={type}")
            raise HTTPException(status_code=500, detail="创建资产池失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建资产池失败: error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{pool_id}", response_model=ApiResponse)
def update_pool(pool_id: int, pool: Dict[str, Any]):
    """更新资产池
    
    Args:
        pool_id: 资产池ID
        pool: 资产池更新信息，包含name、description、color、tags等字段
        
    Returns:
        ApiResponse: 包含更新结果的响应
    """
    try:
        name = pool.get("name")
        description = pool.get("description")
        color = pool.get("color")
        tags = pool.get("tags")
        
        logger.info(f"开始更新资产池: pool_id={pool_id}")
        
        # 更新资产池
        success = DataPool.update(pool_id, name, description, color, tags)
        
        if success:
            logger.info(f"成功更新资产池: pool_id={pool_id}")
            return ApiResponse(
                code=0,
                message="更新资产池成功",
                data={"pool_id": pool_id}
            )
        else:
            logger.error(f"更新资产池失败: pool_id={pool_id}")
            raise HTTPException(status_code=500, detail="更新资产池失败")
    except Exception as e:
        logger.error(f"更新资产池失败: pool_id={pool_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{pool_id}", response_model=ApiResponse)
def delete_pool(pool_id: int):
    """删除资产池
    
    Args:
        pool_id: 资产池ID
        
    Returns:
        ApiResponse: 包含删除结果的响应
    """
    try:
        logger.info(f"开始删除资产池: pool_id={pool_id}")
        
        # 删除资产池
        success = DataPool.delete(pool_id)
        
        if success:
            logger.info(f"成功删除资产池: pool_id={pool_id}")
            return ApiResponse(
                code=0,
                message="删除资产池成功",
                data={"pool_id": pool_id}
            )
        else:
            logger.error(f"删除资产池失败: pool_id={pool_id}")
            raise HTTPException(status_code=500, detail="删除资产池失败")
    except Exception as e:
        logger.error(f"删除资产池失败: pool_id={pool_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pool_id}/assets", response_model=ApiResponse)
def get_pool_assets(pool_id: int):
    """获取资产池包含的资产
    
    Args:
        pool_id: 资产池ID
        
    Returns:
        ApiResponse: 包含资产列表的响应
    """
    try:
        logger.info(f"开始获取资产池资产: pool_id={pool_id}")
        
        # 获取资产池资产
        assets = DataPool.get_assets(pool_id)
        
        logger.info(f"成功获取资产池资产，共 {len(assets)} 个")
        return ApiResponse(
            code=0,
            message="获取资产池资产成功",
            data={"pool_id": pool_id, "assets": assets}
        )
    except Exception as e:
        logger.error(f"获取资产池资产失败: pool_id={pool_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{pool_id}/assets", response_model=ApiResponse)
def add_pool_assets(pool_id: int, assets: Dict[str, Any]):
    """向资产池添加资产
    
    Args:
        pool_id: 资产池ID
        assets: 资产添加请求，包含assets列表和asset_type字段
        
    Returns:
        ApiResponse: 包含添加结果的响应
    """
    try:
        # 验证请求数据
        if "assets" not in assets or "asset_type" not in assets:
            raise HTTPException(status_code=400, detail="请求数据必须包含assets列表和asset_type字段")
        
        asset_list = assets["assets"]
        asset_type = assets["asset_type"]
        
        logger.info(f"开始向资产池添加资产: pool_id={pool_id}, asset_count={len(asset_list)}, asset_type={asset_type}")
        
        # 批量添加资产
        success = DataPool.add_assets(pool_id, asset_list, asset_type)
        
        if success:
            logger.info(f"成功向资产池添加资产: pool_id={pool_id}, asset_count={len(asset_list)}")
            return ApiResponse(
                code=0,
                message="向资产池添加资产成功",
                data={"pool_id": pool_id, "added_count": len(asset_list)}
            )
        else:
            logger.error(f"向资产池添加资产失败: pool_id={pool_id}")
            raise HTTPException(status_code=500, detail="向资产池添加资产失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"向资产池添加资产失败: pool_id={pool_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{pool_id}/assets", response_model=ApiResponse)
def remove_pool_assets(pool_id: int, assets: Dict[str, Any]):
    """从资产池移除资产
    
    Args:
        pool_id: 资产池ID
        assets: 资产移除请求，包含assets列表
        
    Returns:
        ApiResponse: 包含移除结果的响应
    """
    try:
        # 验证请求数据
        if "assets" not in assets:
            raise HTTPException(status_code=400, detail="请求数据必须包含assets列表")
        
        asset_list = assets["assets"]
        
        logger.info(f"开始从资产池移除资产: pool_id={pool_id}, asset_count={len(asset_list)}")
        
        # 批量移除资产
        success = DataPool.remove_assets(pool_id, asset_list)
        
        if success:
            logger.info(f"成功从资产池移除资产: pool_id={pool_id}, asset_count={len(asset_list)}")
            return ApiResponse(
                code=0,
                message="从资产池移除资产成功",
                data={"pool_id": pool_id, "removed_count": len(asset_list)}
            )
        else:
            logger.error(f"从资产池移除资产失败: pool_id={pool_id}")
            raise HTTPException(status_code=500, detail="从资产池移除资产失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"从资产池移除资产失败: pool_id={pool_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))
