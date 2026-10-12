"""AI 文本润色 — 公共接口的 Pydantic 模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AIPolishRequest(BaseModel):
    """AI 文本润色请求。

    target 决定 prompt 模板；context 提供生成所需的上下文（因子名/表达式/代码等）；
    max_length 限制返回文本长度（字符数）。
    """

    target: Literal["label", "description", "name", "summary"] = Field(
        ...,
        description="生成目标类型：label=中文展示名，description=一句话描述，name=英文标识，summary=摘要",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="生成上下文，如 factor_name/expression/code/category 等",
    )
    max_length: int = Field(
        200,
        ge=1,
        le=2000,
        description="返回文本最大长度（字符数）",
    )
    model_id: str | None = Field(
        default=None,
        description="指定模型 ID；缺省使用系统默认模型",
    )


class AIPolishResponse(BaseModel):
    """AI 文本润色响应。"""

    content: str = Field(..., description="生成的文本内容")
