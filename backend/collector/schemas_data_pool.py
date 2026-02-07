"""数据池管理API的数据模型

使用Pydantic定义数据验证模型，用于请求和响应的数据验证和序列化
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ==================== 数据池基础模型 ====================

class DataPoolBase(BaseModel):
    """数据池基础模型
    
    包含数据池的基本字段，用于创建和更新操作
    """
    name: str = Field(
        ...,
        description="数据池名称",
        examples=["我的自选"],
        min_length=1,
        max_length=100,
    )
    type: str = Field(
        ...,
        description="数据池类型",
        examples=["crypto"],
        pattern="^(stock|crypto)$",
    )
    description: Optional[str] = Field(
        default=None,
        description="数据池描述",
        examples=["常用加密货币"],
        max_length=500,
    )
    color: Optional[str] = Field(
        default=None,
        description="数据池颜色（十六进制）",
        examples=["#1890ff"],
        pattern="^#[0-9A-Fa-f]{6}$",
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="数据池标签列表",
        examples=[["热门", "主流"]],
    )
    is_public: bool = Field(
        default=True,
        description="是否公开",
        examples=[True],
    )
    is_default: bool = Field(
        default=False,
        description="是否为默认数据池",
        examples=[False],
    )


class DataPoolCreate(DataPoolBase):
    """创建数据池请求模型
    
    用于创建数据池时的数据验证
    """
    pass


class DataPoolUpdate(BaseModel):
    """更新数据池请求模型
    
    用于更新数据池时的数据验证，所有字段都是可选的
    """
    name: Optional[str] = Field(
        default=None,
        description="数据池名称",
        examples=["更新后的名称"],
        min_length=1,
        max_length=100,
    )
    type: Optional[str] = Field(
        default=None,
        description="数据池类型",
        examples=["crypto"],
        pattern="^(stock|crypto)$",
    )
    description: Optional[str] = Field(
        default=None,
        description="数据池描述",
        examples=["更新后的描述"],
        max_length=500,
    )
    color: Optional[str] = Field(
        default=None,
        description="数据池颜色（十六进制）",
        examples=["#52c41a"],
        pattern="^#[0-9A-Fa-f]{6}$",
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="数据池标签列表",
        examples=[["热门", "主流", "更新"]],
    )
    is_public: Optional[bool] = Field(
        default=None,
        description="是否公开",
        examples=[True],
    )
    is_default: Optional[bool] = Field(
        default=None,
        description="是否为默认数据池",
        examples=[False],
    )


class DataPoolResponse(BaseModel):
    """数据池响应模型
    
    用于返回数据池数据时的序列化
    """
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(
        ...,
        description="数据池唯一标识",
        examples=[1],
    )
    name: str = Field(
        ...,
        description="数据池名称",
        examples=["我的自选"],
    )
    type: str = Field(
        ...,
        description="数据池类型：stock 或 crypto",
        examples=["crypto"],
    )
    description: Optional[str] = Field(
        default=None,
        description="数据池描述",
        examples=["常用加密货币"],
    )
    color: Optional[str] = Field(
        default=None,
        description="数据池颜色（十六进制）",
        examples=["#1890ff"],
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="数据池标签列表",
        examples=[["热门", "主流"]],
    )
    is_public: bool = Field(
        ...,
        description="是否公开",
        examples=[True],
    )
    is_default: bool = Field(
        ...,
        description="是否为默认数据池",
        examples=[True],
    )
    asset_count: int = Field(
        ...,
        description="资产数量",
        examples=[5],
    )
    created_at: datetime = Field(
        ...,
        description="创建时间",
        examples=["2024-01-15T10:30:00"],
    )
    updated_at: datetime = Field(
        ...,
        description="更新时间",
        examples=["2024-01-20T14:25:00"],
    )


class DataPoolListResponse(BaseModel):
    """数据池列表响应模型
    
    用于返回数据池列表
    """
    pools: List[DataPoolResponse] = Field(
        ...,
        description="数据池列表",
    )


# ==================== 数据池资产模型 ====================

class DataPoolAssetAdd(BaseModel):
    """添加资产到数据池请求模型
    
    用于向数据池批量添加资产
    """
    assets: List[str] = Field(
        ...,
        description="资产列表（交易标的代码）",
        examples=[["BTC/USDT", "ETH/USDT", "BNB/USDT"]],
        min_length=1,
    )
    asset_type: str = Field(
        ...,
        description="资产类型：stock 或 crypto",
        examples=["crypto"],
        pattern="^(stock|crypto)$",
    )


class DataPoolAssetRemove(BaseModel):
    """从数据池移除资产请求模型
    
    用于从数据池批量移除资产
    """
    assets: List[str] = Field(
        ...,
        description="要移除的资产列表",
        examples=[["BTC/USDT", "ETH/USDT"]],
        min_length=1,
    )


class DataPoolAssetsResponse(BaseModel):
    """数据池资产响应模型
    
    用于返回数据池包含的资产列表
    """
    pool_id: int = Field(
        ...,
        description="数据池ID",
        examples=[1],
    )
    assets: List[str] = Field(
        ...,
        description="资产列表（交易标的代码）",
        examples=[["BTC/USDT", "ETH/USDT", "BNB/USDT"]],
    )


# ==================== 采集页面品种选项模型 ====================

class CollectionSymbolPool(BaseModel):
    """采集页面的数据池选项模型
    
    包含数据池ID、名称和资产列表
    """
    id: int = Field(
        ...,
        description="数据池ID",
        examples=[1],
    )
    name: str = Field(
        ...,
        description="数据池名称",
        examples=["我的自选"],
    )
    symbols: List[str] = Field(
        ...,
        description="数据池包含的交易标的",
        examples=[["BTC/USDT", "ETH/USDT", "BNB/USDT"]],
    )


class CollectionSymbolsResponse(BaseModel):
    """采集页面品种选项响应模型
    
    包含数据池和直接货币对数据
    """
    data_pools: List[CollectionSymbolPool] = Field(
        ...,
        description="数据池列表",
    )
    direct_symbols: List[str] = Field(
        ...,
        description="直接可用的交易标的列表",
        examples=[["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]],
    )


# ==================== 操作结果模型 ====================

class DataPoolCreateResponse(BaseModel):
    """创建数据池响应数据模型
    
    用于返回创建数据池的结果
    """
    pool_id: int = Field(
        ...,
        description="新创建的数据池ID",
        examples=[1],
    )
    name: str = Field(
        ...,
        description="数据池名称",
        examples=["我的自选"],
    )
    type: str = Field(
        ...,
        description="数据池类型",
        examples=["crypto"],
    )


class DataPoolUpdateResponse(BaseModel):
    """更新数据池响应数据模型
    
    用于返回更新数据池的结果
    """
    pool_id: int = Field(
        ...,
        description="更新的数据池ID",
        examples=[1],
    )


class DataPoolDeleteResponse(BaseModel):
    """删除数据池响应数据模型
    
    用于返回删除数据池的结果
    """
    pool_id: int = Field(
        ...,
        description="删除的数据池ID",
        examples=[1],
    )


class DataPoolAssetAddResponse(BaseModel):
    """添加资产响应数据模型
    
    用于返回添加资产的结果
    """
    pool_id: int = Field(
        ...,
        description="数据池ID",
        examples=[1],
    )
    added_count: int = Field(
        ...,
        description="成功添加的资产数量",
        examples=[3],
    )


class DataPoolAssetRemoveResponse(BaseModel):
    """移除资产响应数据模型
    
    用于返回移除资产的结果
    """
    pool_id: int = Field(
        ...,
        description="数据池ID",
        examples=[1],
    )
    removed_count: int = Field(
        ...,
        description="成功移除的资产数量",
        examples=[2],
    )
