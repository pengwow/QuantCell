"""提示词管理模块

提供统一的提示词模板管理功能，支持模板加载、分类管理和变量替换。

使用示例:
    >>> from ai_model.prompts import PromptManager, PromptCategory
    >>>
    >>> manager = PromptManager()
    >>> template = manager.get_template(PromptCategory.STRATEGY_GENERATION)
    >>>
    >>> # 变量替换
    >>> rendered = manager.render(
    ...     PromptCategory.STRATEGY_GENERATION,
    ...     strategy_name="MyStrategy",
    ...     user_description="双均线策略"
    ... )
"""

from .manager import PromptCategory
from .manager import PromptManager

__all__ = ["PromptManager", "PromptCategory"]
