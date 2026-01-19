"""数据验证和序列化模型

使用Pydantic定义数据验证模型，用于请求和响应的数据验证和序列化
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


# 系统配置模型
class SystemConfigBase(BaseModel):
    """系统配置基础模型
    
    包含系统配置的基本字段
    """
    value: str
    description: Optional[str] = None
    plugin: Optional[str] = None  # 插件名称，用于区分是插件配置还是基础配置
    name: Optional[str] = None  # 配置名称，用于区分系统配置页面的子菜单名称


class SystemConfigCreate(SystemConfigBase):
    """创建系统配置模型
    
    用于创建系统配置时的数据验证
    """
    key: str


class SystemConfigUpdate(SystemConfigBase):
    """更新系统配置模型
    
    用于更新系统配置时的数据验证
    使用exclude_unset=True可以只更新提供的字段
    """
    pass


class SystemConfig(SystemConfigBase):
    """系统配置响应模型
    
    用于返回系统配置数据时的序列化
    """
    key: str
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# 任务进度模型
class TaskProgress(BaseModel):
    """任务进度模型
    
    包含任务进度的相关字段
    """
    total: int = 0
    completed: int = 0
    failed: int = 0
    current: str = ""
    percentage: int = 0


# 任务模型
class TaskBase(BaseModel):
    """任务基础模型
    
    包含任务的基本字段
    """
    task_type: str
    status: str
    params: Dict[str, Any] = {}


class TaskCreate(TaskBase):
    """创建任务模型
    
    用于创建任务时的数据验证
    """
    task_id: str


class TaskUpdate(BaseModel):
    """更新任务模型
    
    用于更新任务时的数据验证
    """
    status: Optional[str] = None
    progress: Optional[TaskProgress] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None


class Task(TaskBase):
    """任务响应模型
    
    用于返回任务数据时的序列化
    """
    task_id: str
    progress: TaskProgress
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class TaskPaginatedResponse(BaseModel):
    """任务分页响应模型
    
    用于返回分页任务列表时的序列化
    """
    tasks: list[Task]
    pagination: Dict[str, Any]


# 特征模型
class FeatureBase(BaseModel):
    """特征基础模型
    
    包含特征的基本字段
    """
    symbol: str
    feature_name: str
    freq: str


class FeatureCreate(FeatureBase):
    """创建特征模型
    
    用于创建特征时的数据验证
    """
    pass


class FeatureUpdate(BaseModel):
    """更新特征模型
    
    用于更新特征时的数据验证
    """
    symbol: Optional[str] = None
    feature_name: Optional[str] = None
    freq: Optional[str] = None


class Feature(FeatureBase):
    """特征响应模型
    
    用于返回特征数据时的序列化
    """
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
