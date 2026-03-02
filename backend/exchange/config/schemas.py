# 交易所配置相关的Pydantic模型
# 用于定义API请求和响应的数据结构

from typing import Optional

from pydantic import BaseModel, Field


class ExchangeConfigBase(BaseModel):
    """交易所配置基础模型"""
    exchange_id: str = Field(..., description="交易所ID，如binance、okx等", examples=["binance"])
    name: str = Field(..., description="交易所名称，用于显示", examples=["币安"])
    # 交易设置
    trading_mode: str = Field(default="spot", description="交易模式：spot(现货), futures(合约), margin(杠杆)")
    quote_currency: str = Field(default="USDT", description="计价货币")
    commission_rate: float = Field(default=0.001, description="手续费率")
    # 代理设置
    proxy_enabled: bool = Field(default=False, description="是否启用代理")
    proxy_url: Optional[str] = Field(None, description="代理地址", examples=["http://proxy.example.com:8080"])
    proxy_username: Optional[str] = Field(None, description="代理用户名")
    proxy_password: Optional[str] = Field(None, description="代理密码")
    # 状态设置
    is_default: bool = Field(default=False, description="是否为默认交易所")
    is_enabled: bool = Field(default=True, description="是否启用")


class ExchangeConfigCreate(ExchangeConfigBase):
    """创建交易所配置请求模型"""
    api_key: Optional[str] = Field(None, description="API密钥")
    api_secret: Optional[str] = Field(None, description="API密钥密钥")


class ExchangeConfigUpdate(BaseModel):
    """更新交易所配置请求模型"""
    exchange_id: Optional[str] = Field(None, description="交易所ID")
    name: Optional[str] = Field(None, description="交易所名称")
    # 交易设置
    trading_mode: Optional[str] = Field(None, description="交易模式")
    quote_currency: Optional[str] = Field(None, description="计价货币")
    commission_rate: Optional[float] = Field(None, description="手续费率")
    # API认证
    api_key: Optional[str] = Field(None, description="API密钥")
    api_secret: Optional[str] = Field(None, description="API密钥密钥")
    # 代理设置
    proxy_enabled: Optional[bool] = Field(None, description="是否启用代理")
    proxy_url: Optional[str] = Field(None, description="代理地址")
    proxy_username: Optional[str] = Field(None, description="代理用户名")
    proxy_password: Optional[str] = Field(None, description="代理密码")
    # 状态设置
    is_default: Optional[bool] = Field(None, description="是否为默认交易所")
    is_enabled: Optional[bool] = Field(None, description="是否启用")


class ExchangeConfigResponse(ExchangeConfigBase):
    """交易所配置响应模型"""
    id: int = Field(..., description="配置ID")
    api_key_masked: Optional[str] = Field(None, description="脱敏显示的API密钥")
    api_secret_masked: Optional[str] = Field(None, description="脱敏显示的API密钥密钥")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class ExchangeConfigListResponse(BaseModel):
    """交易所配置列表响应模型"""
    items: list[ExchangeConfigResponse] = Field(..., description="配置列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    limit: int = Field(..., description="每页记录数")
    pages: int = Field(..., description="总页数")


class ExchangeConfigQueryParams(BaseModel):
    """交易所配置查询参数模型"""
    page: int = Field(default=1, description="页码，从1开始", ge=1)
    limit: int = Field(default=10, description="每页记录数", ge=1, le=100)
    exchange_id: Optional[str] = Field(None, description="按交易所ID筛选")
    is_enabled: Optional[bool] = Field(None, description="按启用状态筛选")
    sort_by: str = Field(default="created_at", description="排序字段")
    sort_order: str = Field(default="desc", description="排序顺序，asc或desc")
