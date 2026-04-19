"""
Pydantic 请求/响应模型定义

定义参数管理系统使用的所有数据结构
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ParamTemplateItem(BaseModel):
    """参数模板项"""

    type: str = Field(..., description="参数类型: string, integer, float, boolean")
    required: bool = Field(default=False, description="是否必填")
    sensitive: bool = Field(default=False, description="是否敏感信息")
    default: Any = Field(default=None, description="默认值")
    env_key: Optional[str] = Field(default=None, description="对应的环境变量名")
    description: str = Field(default="", description="参数描述")
    validation: Optional[Dict[str, Any]] = Field(
        default=None, description="验证规则 (如 {'min': 1, 'max': 10})"
    )


class ToolParamTemplate(BaseModel):
    """工具参数模板"""

    name: str = Field(..., description="工具名称")
    description: Optional[str] = Field(default=None, description="工具描述")
    params: Dict[str, ParamTemplateItem] = Field(
        default_factory=dict, description="参数字典"
    )


class ParamValueInfo(BaseModel):
    """参数值信息（API响应）"""

    value: Any = Field(..., description="参数值（敏感值可能被脱敏）")
    configured: bool = Field(..., description="是否已在数据库中配置")
    source: str = Field(
        ..., description="值的来源: database | environment | default"
    )
    sensitive: bool = Field(default=False, description="是否敏感参数")
    type: Optional[str] = Field(default=None, description="参数类型")
    description: str = Field(default="", description="参数描述")


class ToolParamsResponse(BaseModel):
    """工具参数响应"""

    tool_name: str = Field(..., description="工具名称")
    params: Dict[str, ParamValueInfo] = Field(
        default_factory=dict, description="参数详情"
    )


class ToolListItem(BaseModel):
    """工具列表项"""

    name: str = Field(..., description="工具名称")
    param_count: int = Field(..., description="总参数数量")
    configured_count: int = Field(..., description="已配置参数数量")
    has_required_params: bool = Field(
        default=False, description="是否所有必需参数都已配置"
    )


class SetValueRequest(BaseModel):
    """设置参数值请求"""

    value: Any = Field(..., description="参数值")


class BatchUpdateRequest(BaseModel):
    """批量更新请求"""

    params: Dict[str, Any] = Field(..., description="参数字典 {param_name: value}")
    overwrite: bool = Field(default=False, description="是否覆盖已有值")


class ImportConfigRequest(BaseModel):
    """导入配置请求"""

    config: Dict[str, Any] = Field(..., description="导入的配置数据")
    overwrite: bool = Field(default=False, description="是否覆盖已有值")


class BatchUpdateResult(BaseModel):
    """批量操作结果"""

    updated: List[str] = Field(default_factory=list, description="成功更新的参数名")
    skipped: List[str] = Field(default_factory=list, description="跳过的参数名")
    errors: List[str] = Field(default_factory=list, description="错误信息")


class ExportConfigResponse(BaseModel):
    """导出配置响应"""

    export_time: str = Field(..., description="导出时间 (ISO格式)")
    version: str = Field(default="1.0", description="配置版本")
    tools: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="工具配置字典"
    )


class ImportExportResult(BaseModel):
    """导入导出结果"""

    imported: int = Field(default=0, description="成功导入数量")
    skipped: int = Field(default=0, description="跳过数量")
    errors: List[str] = Field(default_factory=list, description="错误列表")
