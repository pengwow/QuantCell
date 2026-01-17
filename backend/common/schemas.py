# 共享数据模型定义
# 用于所有服务的统一API响应模型和通用数据结构

from datetime import datetime
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
        json_schema_extra={"example": 0},
    )
    message: str = Field(
        ...,
        description="响应消息，描述操作结果",
        json_schema_extra={"example": "操作成功"},
    )
    data: Optional[Any] = Field(
        None,
        description="响应数据，可选",
        json_schema_extra={"example": {"key": "value"}},
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="响应时间戳",
        json_schema_extra={"example": "2023-01-01T00:00:00"},
    )


class PaginationRequest(BaseModel):
    """
    分页请求模型
    用于获取分页数据的通用请求结构
    """
    page: int = Field(
        default=1,
        description="页码，从1开始",
        json_schema_extra={"example": 1},
        ge=1,
    )
    limit: int = Field(
        default=10,
        description="每页记录数",
        json_schema_extra={"example": 10},
        ge=1,
        le=100,
    )


class PaginationResponse(BaseModel):
    """
    分页响应模型
    用于返回分页数据的通用响应结构
    """
    total: int = Field(
        ...,
        description="总记录数",
        json_schema_extra={"example": 100},
    )
    page: int = Field(
        ...,
        description="当前页码",
        json_schema_extra={"example": 1},
    )
    limit: int = Field(
        ...,
        description="每页记录数",
        json_schema_extra={"example": 10},
    )
    pages: int = Field(
        ...,
        description="总页数",
        json_schema_extra={"example": 10},
    )
