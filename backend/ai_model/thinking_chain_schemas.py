"""思维链API相关的Pydantic模型

用于定义思维链API请求和响应的数据结构
"""

from typing import TYPE_CHECKING, Any

import toml
from pydantic import BaseModel, Field, field_validator, model_validator

if TYPE_CHECKING:
    from datetime import datetime


class ThinkingChainStep(BaseModel):
    """思维链步骤模型

    定义单个思维链步骤的结构
    """

    title: str = Field(
        ...,
        description="步骤标题",
        examples=["需求分析", "策略设计", "代码生成", "代码验证"],
        min_length=1,
        max_length=100,
    )
    description: str = Field(
        ...,
        description="步骤详细描述",
        examples=["分析用户需求，提取关键策略要素"],
        min_length=1,
        max_length=2000,
    )
    order: int = Field(
        ...,
        description="步骤顺序，从1开始递增",
        examples=[1, 2, 3, 4],
        ge=1,
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """验证步骤标题不为空且长度合理"""
        if not v or not v.strip():
            msg = "步骤标题不能为空"
            raise ValueError(msg)
        return v.strip()

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        """验证步骤描述不为空且长度合理"""
        if not v or not v.strip():
            msg = "步骤描述不能为空"
            raise ValueError(msg)
        return v.strip()


class ThinkingChainCreate(BaseModel):
    """思维链创建请求模型

    用于接收用户提交的思维链创建请求参数
    """

    chain_type: str = Field(
        ...,
        description="思维链类型: strategy_generation(策略生成) / indicator_generation(指标生成)",
        examples=["strategy_generation"],
        min_length=1,
        max_length=50,
    )
    name: str = Field(
        ...,
        description="思维链名称",
        examples=["策略生成思维链"],
        min_length=1,
        max_length=255,
    )
    description: str | None = Field(
        default=None,
        description="思维链描述",
        examples=["用于生成交易策略的标准思维链流程"],
        max_length=2000,
    )
    steps: list[ThinkingChainStep] = Field(
        ...,
        description="思维链步骤列表",
        min_length=1,
    )
    is_active: bool = Field(
        default=True,
        description="是否激活",
        examples=[True],
    )

    @field_validator("chain_type")
    @classmethod
    def validate_chain_type(cls, v: str) -> str:
        """验证思维链类型"""
        valid_types = ["strategy_generation", "indicator_generation"]
        if v not in valid_types:
            msg = f"无效的思维链类型，必须是: {', '.join(valid_types)}"
            raise ValueError(msg)
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """验证思维链名称不为空且长度合理"""
        if not v or not v.strip():
            msg = "思维链名称不能为空"
            raise ValueError(msg)
        return v.strip()

    @model_validator(mode="after")
    def validate_steps_order(self) -> ThinkingChainCreate:
        """验证步骤顺序是否连续且从1开始"""
        steps = self.steps
        if not steps:
            return self

        orders = [step.order for step in steps]
        sorted_orders = sorted(orders)

        # 检查是否从1开始
        if sorted_orders[0] != 1:
            msg = "步骤顺序必须从1开始"
            raise ValueError(msg)

        # 检查是否连续
        for i in range(len(sorted_orders) - 1):
            if sorted_orders[i + 1] - sorted_orders[i] != 1:
                msg = "步骤顺序必须连续递增"
                raise ValueError(msg)

        return self


class ThinkingChainUpdate(BaseModel):
    """思维链更新请求模型

    用于接收用户提交的思维链更新请求参数
    """

    chain_type: str | None = Field(
        default=None,
        description="思维链类型",
        examples=["strategy_generation"],
        max_length=50,
    )
    name: str | None = Field(
        default=None,
        description="思维链名称",
        examples=["策略生成思维链"],
        max_length=255,
    )
    description: str | None = Field(
        default=None,
        description="思维链描述",
        examples=["用于生成交易策略的标准思维链流程"],
        max_length=2000,
    )
    steps: list[ThinkingChainStep] | None = Field(
        default=None,
        description="思维链步骤列表",
    )
    is_active: bool | None = Field(
        default=None,
        description="是否激活",
        examples=[True],
    )

    @field_validator("chain_type")
    @classmethod
    def validate_chain_type(cls, v: str | None) -> str | None:
        """验证思维链类型"""
        if v is None:
            return v
        valid_types = ["strategy_generation", "indicator_generation"]
        if v not in valid_types:
            msg = f"无效的思维链类型，必须是: {', '.join(valid_types)}"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_steps_order(self) -> ThinkingChainUpdate:
        """验证步骤顺序是否连续且从1开始"""
        steps = self.steps
        if not steps:
            return self

        orders = [step.order for step in steps]
        sorted_orders = sorted(orders)

        # 检查是否从1开始
        if sorted_orders[0] != 1:
            msg = "步骤顺序必须从1开始"
            raise ValueError(msg)

        # 检查是否连续
        for i in range(len(sorted_orders) - 1):
            if sorted_orders[i + 1] - sorted_orders[i] != 1:
                msg = "步骤顺序必须连续递增"
                raise ValueError(msg)

        return self


class ThinkingChainResponse(BaseModel):
    """思维链响应模型

    用于返回思维链的完整信息
    """

    id: str = Field(
        ...,
        description="思维链ID",
        examples=["chain_1234567890"],
    )
    chain_type: str = Field(
        ...,
        description="思维链类型",
        examples=["strategy_generation"],
    )
    name: str = Field(
        ...,
        description="思维链名称",
        examples=["策略生成思维链"],
    )
    description: str | None = Field(
        default=None,
        description="思维链描述",
    )
    steps: list[ThinkingChainStep] = Field(
        ...,
        description="思维链步骤列表",
    )
    is_active: bool = Field(
        ...,
        description="是否激活",
        examples=[True],
    )
    created_at: datetime = Field(
        ...,
        description="创建时间",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="更新时间",
    )


class ThinkingChainListResponse(BaseModel):
    """思维链列表响应模型

    用于返回思维链列表
    """

    items: list[ThinkingChainResponse] = Field(
        ...,
        description="思维链列表",
    )
    total: int = Field(
        ...,
        description="总数",
        examples=[10],
    )
    page: int = Field(
        ...,
        description="当前页码",
        examples=[1],
    )
    page_size: int = Field(
        ...,
        description="每页数量",
        examples=[20],
    )


class ThinkingChainConfig(BaseModel):
    """思维链配置模型

    用于TOML配置文件的结构定义
    """

    name: str = Field(
        ...,
        description="思维链名称",
        examples=["策略生成思维链"],
    )
    chain_type: str = Field(
        ...,
        description="思维链类型",
        examples=["strategy_generation"],
    )
    description: str | None = Field(
        default=None,
        description="思维链描述",
    )
    steps: list[ThinkingChainStep] = Field(
        ...,
        description="思维链步骤列表",
        min_length=1,
    )


class ThinkingChainTOMLConfig(BaseModel):
    """TOML配置文件根模型

    用于解析整个TOML配置文件
    """

    thinking_chain: ThinkingChainConfig = Field(
        ...,
        description="思维链配置",
    )


# TOML配置文件解析函数


def parse_thinking_chain_toml(toml_content: str) -> ThinkingChainConfig:
    """解析TOML格式的思维链配置

    Args:
        toml_content: TOML格式的配置内容字符串

    Returns:
        ThinkingChainConfig: 解析后的思维链配置对象

    Raises:
        ValueError: 当TOML格式无效或配置结构不正确时
    """
    try:
        # 解析TOML内容
        data = toml.loads(toml_content)
    except toml.TomlDecodeError as e:
        msg = f"TOML格式解析错误: {e}"
        raise ValueError(msg)

    # 验证必要字段
    if "thinking_chain" not in data:
        msg = "TOML配置缺少必需的 [thinking_chain] 部分"
        raise ValueError(msg)

    chain_data = data["thinking_chain"]

    # 验证必需字段
    required_fields = ["name", "chain_type", "steps"]
    for field in required_fields:
        if field not in chain_data:
            msg = f"TOML配置缺少必需字段: {field}"
            raise ValueError(msg)

    # 验证步骤结构
    steps = chain_data.get("steps", [])
    if not steps:
        msg = "思维链步骤列表不能为空"
        raise ValueError(msg)

    # 使用Pydantic模型验证整个配置
    try:
        config = ThinkingChainTOMLConfig.model_validate(data)
        return config.thinking_chain
    except Exception as e:
        msg = f"配置验证错误: {e}"
        raise ValueError(msg)


def load_thinking_chain_from_file(file_path: str) -> ThinkingChainConfig:
    """从文件加载TOML格式的思维链配置

    Args:
        file_path: TOML配置文件路径

    Returns:
        ThinkingChainConfig: 解析后的思维链配置对象

    Raises:
        FileNotFoundError: 当文件不存在时
        ValueError: 当TOML格式无效或配置结构不正确时
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        msg = f"配置文件不存在: {file_path}"
        raise FileNotFoundError(msg)
    except Exception as e:
        msg = f"读取配置文件失败: {e}"
        raise ValueError(msg)

    return parse_thinking_chain_toml(content)


def validate_thinking_chain_steps(
    steps: list[dict[str, Any]],
) -> list[ThinkingChainStep]:
    """验证并转换思维链步骤列表

    Args:
        steps: 步骤字典列表

    Returns:
        List[ThinkingChainStep]: 验证后的步骤模型列表

    Raises:
        ValueError: 当步骤结构无效时
    """
    if not steps:
        msg = "步骤列表不能为空"
        raise ValueError(msg)

    validated_steps = []
    orders = set()

    for i, step_data in enumerate(steps):
        # 验证必需字段
        if "title" not in step_data:
            msg = f"第{i + 1}个步骤缺少必需的 'title' 字段"
            raise ValueError(msg)
        if "description" not in step_data:
            msg = f"第{i + 1}个步骤缺少必需的 'description' 字段"
            raise ValueError(msg)
        if "order" not in step_data:
            msg = f"第{i + 1}个步骤缺少必需的 'order' 字段"
            raise ValueError(msg)

        order = step_data["order"]
        if order in orders:
            msg = f"步骤顺序重复: order={order}"
            raise ValueError(msg)
        orders.add(order)

        try:
            step = ThinkingChainStep.model_validate(step_data)
            validated_steps.append(step)
        except Exception as e:
            msg = f"第{i + 1}个步骤验证失败: {e}"
            raise ValueError(msg)

    # 验证顺序连续性
    sorted_orders = sorted(orders)
    if sorted_orders[0] != 1:
        msg = "步骤顺序必须从1开始"
        raise ValueError(msg)

    for i in range(len(sorted_orders) - 1):
        if sorted_orders[i + 1] - sorted_orders[i] != 1:
            msg = "步骤顺序必须连续递增"
            raise ValueError(msg)

    # 按order排序返回
    return sorted(validated_steps, key=lambda x: x.order)


def convert_toml_to_create_model(config: ThinkingChainConfig) -> ThinkingChainCreate:
    """将TOML配置转换为创建模型

    Args:
        config: TOML配置对象

    Returns:
        ThinkingChainCreate: 思维链创建模型
    """
    return ThinkingChainCreate(
        chain_type=config.chain_type,
        name=config.name,
        description=config.description,
        steps=config.steps,
        is_active=True,
    )
