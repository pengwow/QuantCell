"""数据池管理API路由

提供数据池的创建、查询、更新、删除以及资产管理功能
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from loguru import logger

from ..db import DataPoolBusiness as DataPool
from ..schemas import ApiResponse
from ..schemas_data_pool import (
    CollectionSymbolsResponse,
    DataPoolAssetAdd,
    DataPoolAssetAddResponse,
    DataPoolAssetRemove,
    DataPoolAssetRemoveResponse,
    DataPoolAssetsResponse,
    DataPoolCreate,
    DataPoolCreateResponse,
    DataPoolDeleteResponse,
    DataPoolUpdate,
    DataPoolUpdateResponse,
)

# 导入JWT认证装饰器
try:
    from utils.auth import jwt_auth_required_sync
except ImportError:
    # 如果认证模块不存在，创建一个空装饰器
    def jwt_auth_required_sync(func):
        return func

# 创建API路由实例
router = APIRouter(
    prefix="/api/data-pools",
    tags=["数据池管理"],
    responses={
        401: {"description": "未授权，需要JWT认证"},
        403: {"description": "禁止访问"},
        404: {"description": "资源不存在"},
        500: {"description": "服务器内部错误"},
    },
)


@router.get(
    "/",
    response_model=ApiResponse,
    summary="获取所有数据池",
    description="获取系统中所有数据池列表，支持按类型过滤",
    response_description="成功返回数据池列表",
)
def get_all_pools(
    type: Optional[str] = Query(
        default=None,
        description="数据池类型过滤",
        examples=["crypto"],
        pattern="^(stock|crypto)$",
    )
):
    """获取所有数据池
    
    返回系统中所有数据池的列表，可以通过type参数过滤特定类型的数据池
    
    Args:
        type: 数据池类型过滤（stock/crypto）
        
    Returns:
        ApiResponse: 包含所有数据池的响应
        
    Example:
        ```
        GET /api/data-pools/?type=crypto
        ```
    """
    try:
        logger.info(f"开始获取所有数据池，类型过滤: {type}")
        
        # 获取所有数据池
        pools = DataPool.get_all(type=type)
        
        logger.info(f"成功获取所有数据池，共 {len(pools)} 个")
        
        return ApiResponse(
            code=0,
            message="获取所有数据池成功",
            data=pools
        )
    except Exception as e:
        logger.error(f"获取所有数据池失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/{pool_id}",
    response_model=ApiResponse,
    summary="获取指定数据池",
    description="根据ID获取单个数据池的详细信息",
    response_description="成功返回数据池详情或不存在提示",
    responses={
        200: {"description": "成功获取数据池"},
        404: {"description": "数据池不存在"},
    },
)
def get_pool(
    pool_id: int = Path(
        ...,
        description="数据池ID",
        examples=[1],
        ge=1,
    )
):
    """获取指定ID的数据池
    
    根据数据池ID获取详细信息，如果数据池不存在则返回相应提示
    
    Args:
        pool_id: 数据池ID
        
    Returns:
        ApiResponse: 包含数据池详情的响应
        
    Example:
        ```
        GET /api/data-pools/1
        ```
    """
    try:
        logger.info(f"开始获取数据池: {pool_id}")
        
        # 获取数据池
        pool = DataPool.get(pool_id)
        
        if pool:
            logger.info(f"成功获取数据池: {pool_id}")
            return ApiResponse(
                code=0,
                message="获取数据池成功",
                data=pool
            )
        else:
            logger.warning(f"数据池不存在: {pool_id}")
            return ApiResponse(
                code=1,
                message="数据池不存在",
                data={"pool_id": pool_id}
            )
    except Exception as e:
        logger.error(f"获取数据池失败: pool_id={pool_id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建数据池",
    description="创建新的数据池，需要提供名称和类型",
    response_description="成功创建数据池",
    responses={
        201: {"description": "数据池创建成功"},
        400: {"description": "请求参数错误，缺少必填字段"},
        500: {"description": "创建数据池失败"},
    },
)
def create_pool(pool: DataPoolCreate):
    """创建新数据池
    
    创建新的数据池，需要提供名称和类型，其他字段可选
    
    Args:
        pool: 数据池创建信息
        
    Returns:
        ApiResponse: 包含创建结果的响应
        
    Example:
        ```
        POST /api/data-pools/
        {
            "name": "我的自选",
            "type": "crypto",
            "description": "常用加密货币",
            "color": "#1890ff",
            "tags": ["热门", "主流"]
        }
        ```
    """
    try:
        logger.info(f"开始创建数据池: name={pool.name}, type={pool.type}")
        
        # 创建数据池
        pool_id = DataPool.create(
            name=pool.name,
            type=pool.type,
            description=pool.description,
            color=pool.color,
            tags=pool.tags
        )
        
        if pool_id:
            logger.info(f"成功创建数据池: id={pool_id}, name={pool.name}")
            return ApiResponse(
                code=0,
                message="创建数据池成功",
                data=DataPoolCreateResponse(
                    pool_id=pool_id,
                    name=pool.name,
                    type=pool.type
                )
            )
        else:
            logger.error(f"创建数据池失败: name={pool.name}, type={pool.type}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建数据池失败"
            )
    except Exception as e:
        logger.error(f"创建数据池失败: error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put(
    "/{pool_id}",
    response_model=ApiResponse,
    summary="更新数据池",
    description="更新指定数据池的信息",
    response_description="成功更新数据池",
    responses={
        200: {"description": "数据池更新成功"},
        404: {"description": "数据池不存在"},
        500: {"description": "更新数据池失败"},
    },
)
def update_pool(
    pool_id: int = Path(
        ...,
        description="数据池ID",
        examples=[1],
        ge=1,
    ),
    pool: DataPoolUpdate = ...,
):
    """更新数据池
    
    更新指定数据池的信息，只更新提供的字段
    
    Args:
        pool_id: 数据池ID
        pool: 数据池更新信息
        
    Returns:
        ApiResponse: 包含更新结果的响应
        
    Example:
        ```
        PUT /api/data-pools/1
        {
            "name": "更新后的名称",
            "description": "更新后的描述"
        }
        ```
    """
    try:
        logger.info(f"开始更新数据池: pool_id={pool_id}")
        
        # 构建更新参数，只包含非None的字段
        update_kwargs = {}
        if pool.name is not None:
            update_kwargs['name'] = pool.name
        if pool.description is not None:
            update_kwargs['description'] = pool.description
        if pool.color is not None:
            update_kwargs['color'] = pool.color
        if pool.type is not None:
            update_kwargs['type'] = pool.type
        
        # 更新数据池
        success = DataPool.update(pool_id, **update_kwargs)
        
        if success:
            logger.info(f"成功更新数据池: pool_id={pool_id}")
            return ApiResponse(
                code=0,
                message="更新数据池成功",
                data=DataPoolUpdateResponse(pool_id=pool_id)
            )
        else:
            logger.error(f"更新数据池失败: pool_id={pool_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="更新数据池失败"
            )
    except Exception as e:
        logger.error(f"更新数据池失败: pool_id={pool_id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete(
    "/{pool_id}",
    response_model=ApiResponse,
    summary="删除数据池",
    description="删除指定数据池及其所有资产关联",
    response_description="成功删除数据池",
    responses={
        200: {"description": "数据池删除成功"},
        401: {"description": "未授权，需要JWT认证"},
        404: {"description": "数据池不存在"},
        500: {"description": "删除数据池失败"},
    },
)
@jwt_auth_required_sync
def delete_pool(
    request: Request,
    pool_id: int = Path(
        ...,
        description="数据池ID",
        examples=[1],
        ge=1,
    )
):
    """删除数据池
    
    删除指定数据池及其所有资产关联，需要JWT认证
    
    Args:
        pool_id: 数据池ID
        
    Returns:
        ApiResponse: 包含删除结果的响应
        
    Example:
        ```
        DELETE /api/data-pools/1
        Authorization: Bearer {jwt_token}
        ```
    """
    try:
        logger.info(f"开始删除数据池: pool_id={pool_id}")
        
        # 删除数据池
        success = DataPool.delete(pool_id)
        
        if success:
            logger.info(f"成功删除数据池: pool_id={pool_id}")
            return ApiResponse(
                code=0,
                message="删除数据池成功",
                data=DataPoolDeleteResponse(pool_id=pool_id)
            )
        else:
            logger.error(f"删除数据池失败: pool_id={pool_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="删除数据池失败"
            )
    except Exception as e:
        logger.error(f"删除数据池失败: pool_id={pool_id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/{pool_id}/assets",
    response_model=ApiResponse,
    summary="获取数据池资产",
    description="获取指定数据池包含的所有资产（交易标的）",
    response_description="成功返回资产列表",
    responses={
        200: {"description": "成功获取资产列表"},
        404: {"description": "数据池不存在"},
        500: {"description": "获取资产列表失败"},
    },
)
def get_pool_assets(
    pool_id: int = Path(
        ...,
        description="数据池ID",
        examples=[1],
        ge=1,
    )
):
    """获取数据池包含的资产
    
    获取指定数据池包含的所有资产（交易标的代码列表）
    
    Args:
        pool_id: 数据池ID
        
    Returns:
        ApiResponse: 包含资产列表的响应
        
    Example:
        ```
        GET /api/data-pools/1/assets
        ```
    """
    try:
        logger.info(f"开始获取数据池资产: pool_id={pool_id}")
        
        # 获取数据池资产
        assets = DataPool.get_assets(pool_id)
        
        logger.info(f"成功获取数据池资产，共 {len(assets)} 个")
        return ApiResponse(
            code=0,
            message="获取数据池资产成功",
            data=DataPoolAssetsResponse(
                pool_id=pool_id,
                assets=assets
            )
        )
    except Exception as e:
        logger.error(f"获取数据池资产失败: pool_id={pool_id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/{pool_id}/assets",
    response_model=ApiResponse,
    summary="添加资产到数据池",
    description="向指定数据池批量添加资产",
    response_description="成功添加资产",
    responses={
        200: {"description": "资产添加成功"},
        400: {"description": "请求参数错误"},
        404: {"description": "数据池不存在"},
        500: {"description": "添加资产失败"},
    },
)
def add_pool_assets(
    pool_id: int = Path(
        ...,
        description="数据池ID",
        examples=[1],
        ge=1,
    ),
    assets: DataPoolAssetAdd = ...,
):
    """向数据池添加资产
    
    向指定数据池批量添加资产，需要提供资产列表和资产类型
    
    Args:
        pool_id: 数据池ID
        assets: 资产添加请求
        
    Returns:
        ApiResponse: 包含添加结果的响应
        
    Example:
        ```
        POST /api/data-pools/1/assets
        {
            "assets": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
            "asset_type": "crypto"
        }
        ```
    """
    try:
        logger.info(
            f"开始向数据池添加资产: pool_id={pool_id}, "
            f"asset_count={len(assets.assets)}, asset_type={assets.asset_type}"
        )
        
        # 批量添加资产
        success = DataPool.add_assets(pool_id, assets.assets, assets.asset_type)
        
        if success:
            logger.info(f"成功向数据池添加资产: pool_id={pool_id}")
            return ApiResponse(
                code=0,
                message="向数据池添加资产成功",
                data=DataPoolAssetAddResponse(
                    pool_id=pool_id,
                    added_count=len(assets.assets)
                )
            )
        else:
            logger.error(f"向数据池添加资产失败: pool_id={pool_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="向数据池添加资产失败"
            )
    except Exception as e:
        logger.error(f"向数据池添加资产失败: pool_id={pool_id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/collection/symbols",
    response_model=ApiResponse,
    summary="获取采集页面品种选项",
    description="获取数据采集页面的品种选项数据，包含数据池和直接货币对",
    response_description="成功返回品种选项数据",
)
def get_collection_symbols(
    type: Optional[str] = Query(
        default=None,
        description="交易类型",
        examples=["spot"],
    ),
    exchange: Optional[str] = Query(
        default=None,
        description="交易所",
        examples=["binance"],
    )
):
    """获取数据采集页面的品种选项数据
    
    包含资产池和直接货币对数据，用于数据采集页面的品种选择
    
    Args:
        type: 交易类型，如 spot 或合约
        exchange: 交易所，如 binance
    
    Returns:
        ApiResponse: 包含资产池和直接货币对数据的响应
        
    Example:
        ```
        GET /api/data-pools/collection/symbols?type=spot&exchange=binance
        ```
    """
    try:
        logger.info(f"开始获取数据采集页面的品种选项数据，type={type}, exchange={exchange}")
        
        # 1. 获取所有加密货币数据池
        asset_pools = DataPool.get_all(type="crypto")
        
        # 2. 构建数据池数据，包含数据池ID、名称和包含的资产列表
        pool_data = []
        for pool in asset_pools:
            # 获取数据池包含的资产
            assets = DataPool.get_assets(pool["id"])
            pool_data.append({
                "id": pool["id"],
                "name": pool["name"],
                "symbols": assets
            })
        
        # 3. 获取直接货币对数据
        # 从数据库中获取有效的加密货币符号
        from collector.db.models import CryptoSymbol
        from collector.db.database import SessionLocal, init_database_config
        
        init_database_config()
        db = SessionLocal()
        try:
            # 查询所有有效的加密货币符号
            crypto_symbols = db.query(CryptoSymbol)
            crypto_symbols = crypto_symbols.filter_by(active=True, is_deleted=False)
            crypto_symbols = crypto_symbols.filter(CryptoSymbol.symbol.isnot(None))
            
            # 添加类型和交易所过滤
            if type:
                crypto_symbols = crypto_symbols.filter_by(type=type)
            if exchange:
                crypto_symbols = crypto_symbols.filter_by(exchange=exchange)
            
            crypto_symbols = crypto_symbols.all()
            
            # 提取symbol字段，去重并排序
            direct_symbols = list(set([symbol.symbol for symbol in crypto_symbols if symbol.symbol]))
            direct_symbols.sort()
        finally:
            db.close()
        
        logger.info(
            f"成功获取数据采集页面的品种选项数据: "
            f"data_pools_count={len(pool_data)}, direct_symbols_count={len(direct_symbols)}"
        )
        
        return ApiResponse(
            code=0,
            message="获取品种选项数据成功",
            data=CollectionSymbolsResponse(
                data_pools=pool_data,
                direct_symbols=direct_symbols
            )
        )
    except Exception as e:
        logger.error(f"获取数据采集页面的品种选项数据失败: error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete(
    "/{pool_id}/assets",
    response_model=ApiResponse,
    summary="从数据池移除资产",
    description="从指定数据池批量移除资产",
    response_description="成功移除资产",
    responses={
        200: {"description": "资产移除成功"},
        400: {"description": "请求参数错误"},
        401: {"description": "未授权，需要JWT认证"},
        404: {"description": "数据池不存在"},
        500: {"description": "移除资产失败"},
    },
)
@jwt_auth_required_sync
def remove_pool_assets(
    request: Request,
    pool_id: int = Path(
        ...,
        description="数据池ID",
        examples=[1],
        ge=1,
    ),
    assets: DataPoolAssetRemove = ...,
):
    """从数据池移除资产
    
    从指定数据池批量移除资产，需要JWT认证
    
    Args:
        pool_id: 数据池ID
        assets: 资产移除请求
        
    Returns:
        ApiResponse: 包含移除结果的响应
        
    Example:
        ```
        DELETE /api/data-pools/1/assets
        Authorization: Bearer {jwt_token}
        {
            "assets": ["BTC/USDT", "ETH/USDT"]
        }
        ```
    """
    try:
        logger.info(f"开始从数据池移除资产: pool_id={pool_id}, asset_count={len(assets.assets)}")
        
        # 批量移除资产
        success = DataPool.remove_assets(pool_id, assets.assets)
        
        if success:
            logger.info(f"成功从数据池移除资产: pool_id={pool_id}")
            return ApiResponse(
                code=0,
                message="从数据池移除资产成功",
                data=DataPoolAssetRemoveResponse(
                    pool_id=pool_id,
                    removed_count=len(assets.assets)
                )
            )
        else:
            logger.error(f"从数据池移除资产失败: pool_id={pool_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="从数据池移除资产失败"
            )
    except Exception as e:
        logger.error(f"从数据池移除资产失败: pool_id={pool_id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
