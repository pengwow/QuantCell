# AI模型配置相关的Pydantic模型
# 用于定义API请求和响应的数据结构

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class AIModelBase(BaseModel):
    """AI模型配置基础模型"""
    provider: str = Field(..., description="厂商名称，如openai、anthropic等", examples=["openai"])
    name: str = Field(..., description="配置名称，用于显示", examples=["OpenAI GPT-4"])
    api_host: Optional[str] = Field(None, description="API主机地址，可选", examples=["https://api.openai.com"])
    is_default: bool = Field(default=False, description="是否为默认配置")
    is_enabled: bool = Field(default=True, description="是否启用")
    # 代理设置字段
    proxy_enabled: bool = Field(default=False, description="是否启用代理")
    proxy_url: Optional[str] = Field(None, description="代理地址", examples=["http://proxy.example.com:8080"])
    proxy_username: Optional[str] = Field(None, description="代理用户名")
    proxy_password: Optional[str] = Field(None, description="代理密码")


class AIModelCreate(AIModelBase):
    """创建AI模型配置请求模型"""
    api_key: str = Field(..., description="API密钥", examples=["sk-xxxxxxxxxxxxxxxxxxxxxxxx"])
    models: Optional[List[str]] = Field(None, description="可用模型列表", examples=[["gpt-4", "gpt-3.5-turbo"]])


class AIModelUpdate(BaseModel):
    """更新AI模型配置请求模型"""
    provider: Optional[str] = Field(None, description="厂商名称")
    name: Optional[str] = Field(None, description="配置名称")
    api_key: Optional[str] = Field(None, description="API密钥")
    api_host: Optional[str] = Field(None, description="API主机地址")
    models: Optional[List[str]] = Field(None, description="可用模型列表")
    is_default: Optional[bool] = Field(None, description="是否为默认配置")
    is_enabled: Optional[bool] = Field(None, description="是否启用")
    # 代理设置字段
    proxy_enabled: Optional[bool] = Field(None, description="是否启用代理")
    proxy_url: Optional[str] = Field(None, description="代理地址")
    proxy_username: Optional[str] = Field(None, description="代理用户名")
    proxy_password: Optional[str] = Field(None, description="代理密码")


class AIModelResponse(AIModelBase):
    """AI模型配置响应模型"""
    id: int = Field(..., description="配置ID")
    api_key_masked: str = Field(..., description="脱敏显示的API密钥", examples=["sk-xxxxxxxxxxxxxxxxxxxxxxxx"])
    models: Optional[List[str]] = Field(None, description="可用模型列表")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class AIModelListResponse(BaseModel):
    """AI模型配置列表响应模型"""
    items: List[AIModelResponse] = Field(..., description="配置列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    limit: int = Field(..., description="每页记录数")
    pages: int = Field(..., description="总页数")


class AIModelQueryParams(BaseModel):
    """AI模型配置查询参数模型"""
    page: int = Field(default=1, description="页码，从1开始", ge=1)
    limit: int = Field(default=10, description="每页记录数", ge=1, le=100)
    provider: Optional[str] = Field(None, description="按厂商筛选")
    is_enabled: Optional[bool] = Field(None, description="按启用状态筛选")
    sort_by: str = Field(default="created_at", description="排序字段")
    sort_order: str = Field(default="desc", description="排序顺序，asc或desc")

    @field_validator('sort_order')
    @classmethod
    def validate_sort_order(cls, v):
        if v not in ['asc', 'desc']:
            return 'desc'
        return v


class AIModelCheckRequest(BaseModel):
    """模型可用性检查请求模型"""
    provider: str = Field(..., description="厂商名称", examples=["openai"])
    api_key: str = Field(..., description="API密钥", examples=["sk-xxxxxxxxxxxxxxxxxxxxxxxx"])
    api_host: Optional[str] = Field(None, description="API主机地址", examples=["https://api.openai.com"])
    # 代理设置字段
    proxy_enabled: Optional[bool] = Field(None, description="是否启用代理")
    proxy_url: Optional[str] = Field(None, description="代理地址")
    proxy_username: Optional[str] = Field(None, description="代理用户名")
    proxy_password: Optional[str] = Field(None, description="代理密码")


class AIModelCheckResponse(BaseModel):
    """模型可用性检查响应模型"""
    available: bool = Field(..., description="服务是否可用")
    message: str = Field(..., description="检查结果消息")
    models: Optional[List[Dict[str, Any]]] = Field(None, description="可用模型列表")
    error: Optional[str] = Field(None, description="错误信息，如果检查失败")


class AIModelAvailableModelsResponse(BaseModel):
    """获取可用模型列表响应模型"""
    provider: str = Field(..., description="厂商名称")
    models: List[Dict[str, Any]] = Field(..., description="可用模型列表")
    total: int = Field(..., description="模型总数")
