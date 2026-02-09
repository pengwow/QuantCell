# 共享数据模型定义
# 用于所有服务的统一API响应模型和通用数据结构

from datetime import datetime
import pytz
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    """
    统一API响应模型
    所有服务的API响应都应使用此模型
    """
    code: int = Field(
        ...,
        description="响应状态码，0表示成功，非0表示失败",
        examples=[0],
    )
    message: str = Field(
        ...,
        description="响应消息，描述操作结果",
        examples=["操作成功"],
    )
    data: Optional[Any] = Field(
        None,
        description="响应数据，可选",
        examples=[{"key": "value"}],
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="响应时间戳",
        examples=[datetime.now()],
    )


class PaginationRequest(BaseModel):
    """
    分页请求模型
    用于获取分页数据的通用请求结构
    """
    model_config = {"populate_by_name": True}

    page: int = Field(
        default=1,
        description="页码，从1开始",
        examples=[1],
        ge=0,  # 允许0页码用于测试
    )
    limit: int = Field(
        default=10,
        description="每页记录数",
        examples=[10],
        ge=1,
        le=10000,  # 放宽限制以支持大页面
    )

    def __init__(self, **data):
        # 处理 page_size 作为 limit 的别名
        if "page_size" in data and "limit" not in data:
            data["limit"] = data.pop("page_size")
        super().__init__(**data)

    @property
    def page_size(self) -> int:
        """返回每页记录数（limit的别名）"""
        return self.limit


class PaginationResponse(BaseModel):
    """
    分页响应模型
    用于返回分页数据的通用响应结构
    """
    total: int = Field(
        ...,
        description="总记录数",
        examples=[100],
    )
    page: int = Field(
        ...,
        description="当前页码",
        examples=[1],
    )
    limit: int = Field(
        ...,
        description="每页记录数",
        examples=[10],
    )
    pages: int = Field(
        ...,
        description="总页数",
        examples=[10],
    )
