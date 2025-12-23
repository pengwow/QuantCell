from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VersionInfo(BaseModel):
    """版本信息模型"""
    system_version: str = Field(..., description="系统版本")
    python_version: str = Field(..., description="Python版本")
    build_date: str = Field(..., description="构建日期")


class RunningStatus(BaseModel):
    """运行状态模型"""
    uptime: str = Field(..., description="运行时间，格式为'X 天 X 小时'")
    status: str = Field(..., description="服务状态，'running'表示正常运行")
    status_color: str = Field(..., description="状态颜色，'green'表示正常，'red'表示异常")
    last_check: datetime = Field(..., description="最后检查时间")


class ResourceUsage(BaseModel):
    """资源使用模型"""
    cpu_usage: float = Field(..., description="CPU使用率，单位为%")
    memory_usage: str = Field(..., description="内存使用情况，格式为'已用GB / 总GB'")
    disk_space: str = Field(..., description="磁盘空间使用情况，格式为'已用GB / 总GB'")


class SystemInfoResponse(BaseModel):
    """系统信息响应模型"""
    version: VersionInfo = Field(..., description="版本信息")
    running_status: RunningStatus = Field(..., description="运行状态")
    resource_usage: ResourceUsage = Field(..., description="资源使用情况")
