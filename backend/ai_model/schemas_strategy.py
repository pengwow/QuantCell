"""
策略生成API相关的Pydantic模型

用于定义策略生成API请求和响应的数据结构
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class StrategyGenerateRequest(BaseModel):
    """策略生成请求模型

    用于接收用户提交的策略生成请求参数
    """

    requirement: str = Field(
        ...,
        description="策略需求描述，描述您想要的策略功能",
        examples=["创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出"],
        min_length=1,
        max_length=5000,
    )
    model_id: Optional[str] = Field(
        default=None,
        description="使用的模型ID（用于内部标识），不传则使用默认模型",
        examples=["gpt-4", "claude-3-opus-20240229"],
    )
    model_name: Optional[str] = Field(
        default=None,
        description="使用的模型名称（用于API调用），不传则使用model_id",
        examples=["gpt-4", "claude-3-opus-20240229"],
    )
    temperature: Optional[float] = Field(
        default=None,
        description="生成温度参数(0-2)，值越高创造性越强，越低越稳定",
        examples=[0.7],
        ge=0.0,
        le=2.0,
    )
    template_vars: Optional[Dict[str, Any]] = Field(
        default=None,
        description="模板变量，用于替换提示词中的占位符",
        examples=[
            {
                "strategy_name": "DualMAStrategy",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
            }
        ],
    )

    @field_validator("requirement")
    @classmethod
    def validate_requirement(cls, v: str) -> str:
        """验证需求描述不为空且长度合理"""
        if not v or not v.strip():
            raise ValueError("策略需求描述不能为空")
        if len(v.strip()) < 10:
            raise ValueError("策略需求描述至少需要10个字符")
        return v.strip()


class StrategyGenerateResponse(BaseModel):
    """策略生成同步响应模型

    用于返回同步策略生成的完整结果
    """

    code: str = Field(
        ...,
        description="生成的策略代码",
        examples=["class MyStrategy:\n    def __init__(self):\n        pass"],
    )
    explanation: Optional[str] = Field(
        default=None,
        description="策略说明文档",
        examples=["这是一个基于双均线的趋势跟踪策略..."],
    )
    model_used: str = Field(
        ...,
        description="实际使用的模型ID",
        examples=["gpt-4"],
    )
    tokens_used: Optional[Dict[str, int]] = Field(
        default=None,
        description="Token使用情况",
        examples=[{"prompt_tokens": 500, "completion_tokens": 800, "total_tokens": 1300}],
    )
    elapsed_time: Optional[float] = Field(
        default=None,
        description="生成耗时(秒)",
        examples=[3.5],
    )
    request_id: Optional[str] = Field(
        default=None,
        description="请求ID，用于追踪",
        examples=["req_1234567890"],
    )


class StrategyGenerateStreamResponse(BaseModel):
    """策略生成流式响应模型

    用于SSE流式响应的单个数据块
    """

    type: str = Field(
        ...,
        description="消息类型: content(内容块), done(完成), error(错误)",
        examples=["content", "done", "error"],
    )
    content: Optional[str] = Field(
        default=None,
        description="生成的内容片段(仅type=content时)",
        examples=["class DualMAStrategy:"],
    )
    code: Optional[str] = Field(
        default=None,
        description="完整提取的代码(仅type=done时)",
        examples=["class DualMAStrategy:\n    pass"],
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="生成元数据(仅type=done时)",
        examples=[
            {
                "request_id": "stream_123456",
                "model": "gpt-4",
                "elapsed_time": 2.5,
                "chunk_count": 42,
            }
        ],
    )
    error: Optional[str] = Field(
        default=None,
        description="错误信息(仅type=error时)",
        examples=["API密钥无效或已过期"],
    )
    error_code: Optional[str] = Field(
        default=None,
        description="错误代码(仅type=error时)",
        examples=["api_authentication_error"],
    )
    request_id: Optional[str] = Field(
        default=None,
        description="请求ID",
        examples=["stream_123456"],
    )


class StrategyValidateRequest(BaseModel):
    """策略代码验证请求模型"""

    code: str = Field(
        ...,
        description="需要验证的策略代码",
        examples=["class MyStrategy:\n    def __init__(self):\n        pass"],
        min_length=1,
    )


class StrategyValidateResponse(BaseModel):
    """策略代码验证响应模型"""

    valid: bool = Field(
        ...,
        description="代码是否有效",
        examples=[True],
    )
    errors: List[str] = Field(
        default_factory=list,
        description="错误列表，如果valid为false则包含具体错误",
        examples=[["语法错误: 第5行缩进错误"]],
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="警告列表",
        examples=[["警告: 代码中未找到类定义"]],
    )


class StrategyHistoryCreate(BaseModel):
    """策略历史记录创建模型"""

    requirement: str = Field(
        ...,
        description="策略需求描述",
        examples=["创建一个双均线策略"],
        min_length=1,
        max_length=5000,
    )
    code: str = Field(
        ...,
        description="生成的策略代码",
        examples=["class MyStrategy:\n    pass"],
    )
    model_id: Optional[str] = Field(
        default=None,
        description="使用的模型ID",
        examples=["gpt-4"],
    )
    explanation: Optional[str] = Field(
        default=None,
        description="策略说明文档",
    )


class StrategyHistoryUpdate(BaseModel):
    """策略历史记录更新模型"""

    requirement: Optional[str] = Field(
        default=None,
        description="策略需求描述",
        examples=["创建一个双均线策略"],
        max_length=5000,
    )
    code: Optional[str] = Field(
        default=None,
        description="生成的策略代码",
        examples=["class MyStrategy:\n    pass"],
    )
    explanation: Optional[str] = Field(
        default=None,
        description="策略说明文档",
    )


class StrategyHistoryResponse(BaseModel):
    """策略历史记录响应模型"""

    id: str = Field(
        ...,
        description="历史记录ID",
        examples=["hist_1234567890"],
    )
    user_id: str = Field(
        ...,
        description="用户ID",
        examples=["user_123"],
    )
    requirement: str = Field(
        ...,
        description="策略需求描述",
    )
    code: str = Field(
        ...,
        description="生成的策略代码",
    )
    model_id: Optional[str] = Field(
        default=None,
        description="使用的模型ID",
    )
    explanation: Optional[str] = Field(
        default=None,
        description="策略说明文档",
    )
    status: str = Field(
        default="success",
        description="生成状态: success/failed/pending",
        examples=["success"],
    )
    tokens_used: Optional[Dict[str, int]] = Field(
        default=None,
        description="Token使用情况",
    )
    elapsed_time: Optional[float] = Field(
        default=None,
        description="生成耗时(秒)",
    )
    created_at: datetime = Field(
        ...,
        description="创建时间",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="更新时间",
    )


class StrategyTemplateResponse(BaseModel):
    """策略模板响应模型"""

    id: str = Field(
        ...,
        description="模板ID",
        examples=["tpl_1234567890"],
    )
    name: str = Field(
        ...,
        description="模板名称",
        examples=["双均线策略模板"],
    )
    description: Optional[str] = Field(
        default=None,
        description="模板描述",
        examples=["基于双均线的趋势跟踪策略模板"],
    )
    category: str = Field(
        ...,
        description="模板分类",
        examples=["trend_following"],
    )
    code_template: str = Field(
        ...,
        description="代码模板",
        examples=["class {{strategy_name}}(Strategy):\n    pass"],
    )
    variables: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="模板变量定义",
        examples=[[
            {"name": "strategy_name", "type": "string", "required": True},
            {"name": "fast_period", "type": "int", "default": 10},
        ]],
    )
    tags: List[str] = Field(
        default_factory=list,
        description="标签列表",
        examples=[["趋势", "均线"]],
    )
    created_at: datetime = Field(
        ...,
        description="创建时间",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="更新时间",
    )


class CodeValidationRequest(BaseModel):
    """代码验证请求模型"""

    code: str = Field(
        ...,
        description="需要验证的代码",
        examples=["class MyStrategy:\n    pass"],
        min_length=1,
    )
    language: str = Field(
        default="python",
        description="代码语言",
        examples=["python"],
    )


class CodeValidationResponse(BaseModel):
    """代码验证响应模型"""

    valid: bool = Field(
        ...,
        description="代码是否有效",
        examples=[True],
    )
    errors: List[str] = Field(
        default_factory=list,
        description="错误列表",
        examples=[["语法错误: 第5行缩进错误"]],
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="警告列表",
        examples=[["警告: 未检测到策略基类继承"]],
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="改进建议",
        examples=[["建议使用类型注解"]],
    )


class PerformanceStatsResponse(BaseModel):
    """性能统计响应模型"""

    total_generations: int = Field(
        ...,
        description="总生成次数",
        examples=[100],
    )
    successful_generations: int = Field(
        ...,
        description="成功生成次数",
        examples=[95],
    )
    failed_generations: int = Field(
        ...,
        description="失败生成次数",
        examples=[5],
    )
    success_rate: float = Field(
        ...,
        description="成功率(%)",
        examples=[95.0],
    )
    average_generation_time: float = Field(
        ...,
        description="平均生成时间(秒)",
        examples=[3.5],
    )
    total_tokens_used: int = Field(
        ...,
        description="总Token使用量",
        examples=[50000],
    )
    model_usage_stats: Dict[str, int] = Field(
        default_factory=dict,
        description="各模型使用统计",
        examples=[{"gpt-4": 80, "claude-3": 20}],
    )
    daily_stats: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="每日统计",
        examples=[[
            {"date": "2026-03-07", "count": 10, "success": 9},
            {"date": "2026-03-08", "count": 15, "success": 15},
        ]],
    )
    period_start: Optional[datetime] = Field(
        default=None,
        description="统计周期开始时间",
    )
    period_end: Optional[datetime] = Field(
        default=None,
        description="统计周期结束时间",
    )


class StrategyGenerateFromTemplateRequest(BaseModel):
    """基于模板生成策略请求模型"""

    template_id: str = Field(
        ...,
        description="模板ID",
        examples=["tpl_1234567890"],
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="模板变量值",
        examples=[
            {
                "strategy_name": "DualMAStrategy",
                "fast_period": 10,
                "slow_period": 20,
            }
        ],
    )
    model_id: Optional[str] = Field(
        default=None,
        description="使用的模型ID（用于内部标识），不传则使用默认模型",
        examples=["gpt-4"],
    )
    model_name: Optional[str] = Field(
        default=None,
        description="使用的模型名称（用于API调用），不传则使用model_id",
        examples=["gpt-4"],
    )
    temperature: Optional[float] = Field(
        default=None,
        description="生成温度参数(0-2)",
        examples=[0.7],
        ge=0.0,
        le=2.0,
    )
    additional_requirement: Optional[str] = Field(
        default=None,
        description="额外需求描述",
        examples=["添加止损逻辑"],
    )
