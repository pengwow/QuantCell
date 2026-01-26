# 系统设置相关的Pydantic模型
# 用于定义API请求和响应的详细结构，以便FastAPI自动生成完整的API文档

from datetime import datetime
import pytz
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_serializer


class ApiResponse(BaseModel):
    """统一的API响应格式"""
    code: int = Field(..., description="响应状态码，0表示成功，非0表示失败", examples=[0])
    message: str = Field(..., description="响应消息", examples=["操作成功"])
    data: Any = Field(..., description="响应数据", examples=[{"key": "value"}])
    timestamp: str = Field(default_factory=lambda: datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'), description="响应时间戳", examples=["2026-01-24 18:00:00"])


class SystemConfigItem(BaseModel):
    """单个系统配置项的详细信息"""
    key: str = Field(..., description="配置项键名", examples=["qlib_data_dir"])
    value: str = Field(..., description="配置项值", examples=["data/crypto_data"])
    description: Optional[str] = Field(None, description="配置项描述", examples=["QLib数据目录"])
    plugin: Optional[str] = Field(None, description="插件名称，用于区分是插件配置还是基础配置")
    name: Optional[str] = Field(None, description="配置名称，用于区分系统配置页面的子菜单名称", examples=["数据配置"])
    is_sensitive: bool = Field(default=False, description="是否敏感配置，敏感配置API不返回真实值", examples=[False])
    created_at: Optional[str] = Field(None, description="创建时间", examples=["2026-01-24 18:00:00"])
    updated_at: Optional[str] = Field(None, description="更新时间", examples=["2026-01-24 18:00:00"])


class SystemConfigSimple(BaseModel):
    """简化的系统配置项，仅包含键值对"""
    key: str = Field(..., description="配置项键名", examples=["qlib_data_dir"])
    value: str = Field(..., description="配置项值", examples=["data/crypto_data"])


class ConfigUpdateRequest(BaseModel):
    """更新或创建单个系统配置项的请求"""
    key: str = Field(..., description="配置项键名", examples=["new_config"])
    value: str = Field(..., description="配置项值", examples=["new_value"])
    description: Optional[str] = Field(None, description="配置项描述", examples=["新的配置项"])
    plugin: Optional[str] = Field(None, description="插件名称")
    name: Optional[str] = Field(None, description="配置名称", examples=["基础配置"])
    is_sensitive: bool = Field(default=False, description="是否为敏感配置", examples=[False])


class ConfigBatchUpdateItem(BaseModel):
    """批量更新中的单个配置项"""
    key: str = Field(..., description="配置项键名", examples=["config1"])
    value: str = Field(..., description="配置项值", examples=["value1"])
    description: Optional[str] = Field(None, description="配置项描述", examples=["配置项1"])
    plugin: Optional[str] = Field(None, description="插件名称")
    name: Optional[str] = Field(None, description="配置名称", examples=["基础配置"])
    is_sensitive: bool = Field(default=False, description="是否为敏感配置", examples=[False])


class ConfigBatchUpdateRequest(BaseModel):
    """批量更新系统配置的请求"""
    configs: Union[Dict[str, str], List[ConfigBatchUpdateItem]] = Field(
        ..., 
        description="配置项列表，可以是键值对字典或配置项对象列表",
        examples=[
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
    )


class ConfigBatchUpdateResponse(BaseModel):
    """批量更新系统配置的响应"""
    updated_count: int = Field(..., description="成功更新的配置项数量", examples=[2])


class VersionInfo(BaseModel):
    """系统版本信息"""
    system_version: str = Field(..., description="系统版本号", examples=["1.0.0"])
    python_version: str = Field(..., description="Python版本号", examples=["3.12.12"])
    build_date: str = Field(..., description="系统构建日期", examples=["2025-11-30"])


class RunningStatus(BaseModel):
    """系统运行状态"""
    uptime: str = Field(..., description="系统运行时间", examples=["0 天 0 小时"])
    status: str = Field(..., description="系统状态", examples=["running"])
    status_color: str = Field(..., description="状态颜色", examples=["green"])
    last_check: str = Field(..., description="最后检查时间", examples=["2026-01-24 18:00:00"])


class ResourceUsage(BaseModel):
    """系统资源使用情况"""
    cpu_usage: float = Field(..., description="CPU使用率(%)", examples=[24.9])
    memory_usage: str = Field(..., description="内存使用情况", examples=["5.25GB / 16.0GB"])
    disk_space: str = Field(..., description="磁盘空间使用情况", examples=["11.43GB / 228.27GB"])


class SystemInfo(BaseModel):
    """系统信息"""
    version: VersionInfo = Field(..., description="版本信息")
    running_status: RunningStatus = Field(..., description="运行状态")
    resource_usage: ResourceUsage = Field(..., description="资源使用情况")