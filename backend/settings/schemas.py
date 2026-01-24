# 系统设置相关的Pydantic模型
# 用于定义API请求和响应的详细结构，以便FastAPI自动生成完整的API文档

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    """统一的API响应格式"""
    code: int = Field(..., description="响应状态码，0表示成功，非0表示失败")
    message: str = Field(..., description="响应消息")
    data: Any = Field(..., description="响应数据")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="响应时间戳")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": 0,
                "message": "操作成功",
                "data": {"key": "value"},
                "timestamp": "2026-01-24T10:00:00.000000"
            }
        }


class SystemConfigItem(BaseModel):
    """单个系统配置项的详细信息"""
    key: str = Field(..., description="配置项键名")
    value: str = Field(..., description="配置项值")
    description: Optional[str] = Field(None, description="配置项描述")
    plugin: Optional[str] = Field(None, description="插件名称，用于区分是插件配置还是基础配置")
    name: Optional[str] = Field(None, description="配置名称，用于区分系统配置页面的子菜单名称")
    is_sensitive: bool = Field(default=False, description="是否敏感配置，敏感配置API不返回真实值")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    
    class Config:
        json_schema_extra = {
            "example": {
                "key": "qlib_data_dir",
                "value": "data/crypto_data",
                "description": "QLib数据目录",
                "plugin": None,
                "name": "数据配置",
                "is_sensitive": False,
                "created_at": "2026-01-24T10:00:00.000000",
                "updated_at": "2026-01-24T10:00:00.000000"
            }
        }


class SystemConfigSimple(BaseModel):
    """简化的系统配置项，仅包含键值对"""
    key: str = Field(..., description="配置项键名")
    value: str = Field(..., description="配置项值")
    
    class Config:
        json_schema_extra = {
            "example": {
                "qlib_data_dir": "data/crypto_data",
                "max_workers": "4"
            }
        }


class ConfigUpdateRequest(BaseModel):
    """更新或创建单个系统配置项的请求"""
    key: str = Field(..., description="配置项键名")
    value: str = Field(..., description="配置项值")
    description: Optional[str] = Field(None, description="配置项描述")
    plugin: Optional[str] = Field(None, description="插件名称")
    name: Optional[str] = Field(None, description="配置名称")
    is_sensitive: bool = Field(default=False, description="是否为敏感配置")
    
    class Config:
        json_schema_extra = {
            "example": {
                "key": "new_config",
                "value": "new_value",
                "description": "新的配置项",
                "plugin": None,
                "name": "基础配置",
                "is_sensitive": False
            }
        }


class ConfigBatchUpdateItem(BaseModel):
    """批量更新中的单个配置项"""
    key: str = Field(..., description="配置项键名")
    value: str = Field(..., description="配置项值")
    description: Optional[str] = Field(None, description="配置项描述")
    plugin: Optional[str] = Field(None, description="插件名称")
    name: Optional[str] = Field(None, description="配置名称")
    is_sensitive: bool = Field(default=False, description="是否为敏感配置")
    
    class Config:
        json_schema_extra = {
            "example": {
                "key": "config1",
                "value": "value1",
                "description": "配置项1",
                "plugin": None,
                "name": "基础配置",
                "is_sensitive": False
            }
        }


class ConfigBatchUpdateRequest(BaseModel):
    """批量更新系统配置的请求"""
    configs: Union[Dict[str, str], List[ConfigBatchUpdateItem]] = Field(
        ..., 
        description="配置项列表，可以是键值对字典或配置项对象列表"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "summary": "字典格式",
                    "value": {
                        "config1": "value1",
                        "config2": "value2"
                    }
                },
                {
                    "summary": "列表格式",
                    "value": [
                        {
                            "key": "config1",
                            "value": "value1",
                            "description": "配置项1",
                            "plugin": None,
                            "name": "基础配置",
                            "is_sensitive": False
                        },
                        {
                            "key": "config2",
                            "value": "value2",
                            "description": "配置项2",
                            "plugin": None,
                            "name": "基础配置",
                            "is_sensitive": False
                        }
                    ]
                }
            ]
        }


class ConfigBatchUpdateResponse(BaseModel):
    """批量更新系统配置的响应"""
    updated_count: int = Field(..., description="成功更新的配置项数量")
    
    class Config:
        json_schema_extra = {
            "example": {
                "updated_count": 2
            }
        }


class VersionInfo(BaseModel):
    """系统版本信息"""
    system_version: str = Field(..., description="系统版本号")
    python_version: str = Field(..., description="Python版本号")
    build_date: str = Field(..., description="系统构建日期")
    
    class Config:
        json_schema_extra = {
            "example": {
                "system_version": "1.0.0",
                "python_version": "3.12.12",
                "build_date": "2025-11-30"
            }
        }


class RunningStatus(BaseModel):
    """系统运行状态"""
    uptime: str = Field(..., description="系统运行时间")
    status: str = Field(..., description="系统状态")
    status_color: str = Field(..., description="状态颜色")
    last_check: datetime = Field(..., description="最后检查时间")
    
    class Config:
        json_schema_extra = {
            "example": {
                "uptime": "0 天 0 小时",
                "status": "running",
                "status_color": "green",
                "last_check": "2026-01-24T10:00:00.000000"
            }
        }


class ResourceUsage(BaseModel):
    """系统资源使用情况"""
    cpu_usage: float = Field(..., description="CPU使用率(%)")
    memory_usage: str = Field(..., description="内存使用情况")
    disk_space: str = Field(..., description="磁盘空间使用情况")
    
    class Config:
        json_schema_extra = {
            "example": {
                "cpu_usage": 24.9,
                "memory_usage": "5.25GB / 16.0GB",
                "disk_space": "11.43GB / 228.27GB"
            }
        }


class SystemInfo(BaseModel):
    """系统信息"""
    version: VersionInfo = Field(..., description="版本信息")
    running_status: RunningStatus = Field(..., description="运行状态")
    resource_usage: ResourceUsage = Field(..., description="资源使用情况")
    
    class Config:
        json_schema_extra = {
            "example": {
                "version": {
                    "system_version": "1.0.0",
                    "python_version": "3.12.12",
                    "build_date": "2025-11-30"
                },
                "running_status": {
                    "uptime": "0 天 0 小时",
                    "status": "running",
                    "status_color": "green",
                    "last_check": "2026-01-24T10:00:00.000000"
                },
                "resource_usage": {
                    "cpu_usage": 24.9,
                    "memory_usage": "5.25GB / 16.0GB",
                    "disk_space": "11.43GB / 228.27GB"
                }
            }
        }