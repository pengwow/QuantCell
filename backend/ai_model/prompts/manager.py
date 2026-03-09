"""提示词管理模块

提供模板加载、分类管理和变量替换功能
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any


class PromptCategory(str, Enum):
    """提示词模板分类"""

    STRATEGY_GENERATION = "strategy_generation"
    CODE_OPTIMIZATION = "code_optimization"
    STRATEGY_EXPLANATION = "strategy_explanation"


class PromptManager:
    """提示词管理器

    负责加载和管理提示词模板，支持变量替换功能
    """

    _instance: PromptManager | None = None
    _templates: dict[PromptCategory, str] = {}

    def __new__(cls, *args, **kwargs) -> PromptManager:
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        """初始化提示词管理器

        Args:
            templates_dir: 模板文件目录路径，默认为当前文件所在目录的 templates 子目录
        """
        if hasattr(self, "_initialized"):
            return

        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"
        else:
            templates_dir = Path(templates_dir)

        self._templates_dir = templates_dir
        self._initialized = True

        # 自动加载所有模板
        self._load_all_templates()

    def _load_all_templates(self) -> None:
        """加载所有分类的模板文件"""
        for category in PromptCategory:
            template_path = self._templates_dir / f"{category.value}.txt"
            if template_path.exists():
                self._templates[category] = template_path.read_text(encoding="utf-8")

    def get_template(self, category: PromptCategory) -> str:
        """获取指定分类的模板内容

        Args:
            category: 模板分类

        Returns:
            模板内容字符串

        Raises:
            KeyError: 如果指定分类的模板不存在
        """
        if category not in self._templates:
            raise KeyError(f"模板分类 '{category.value}' 不存在或未加载")
        return self._templates[category]

    def render(self, category: PromptCategory, **variables: Any) -> str:
        """渲染模板，替换变量

        使用 {{variable_name}} 格式进行变量替换

        Args:
            category: 模板分类
            **variables: 要替换的变量键值对

        Returns:
            替换变量后的模板内容

        Raises:
            KeyError: 如果指定分类的模板不存在
        """
        template = self.get_template(category)

        # 使用正则表达式替换 {{variable}} 格式的变量
        def replace_variable(match: re.Match) -> str:
            var_name = match.group(1).strip()
            if var_name in variables:
                return str(variables[var_name])
            # 如果变量未提供，保留原样
            return match.group(0)

        return re.sub(r"\{\{(\w+)\}\}", replace_variable, template)

    def reload_template(self, category: PromptCategory) -> None:
        """重新加载指定分类的模板

        Args:
            category: 模板分类
        """
        template_path = self._templates_dir / f"{category.value}.txt"
        if template_path.exists():
            self._templates[category] = template_path.read_text(encoding="utf-8")

    def reload_all(self) -> None:
        """重新加载所有模板"""
        self._templates.clear()
        self._load_all_templates()

    def list_available_templates(self) -> list[str]:
        """获取所有可用的模板分类名称列表"""
        return [cat.value for cat in self._templates.keys()]

    def has_template(self, category: PromptCategory) -> bool:
        """检查指定分类的模板是否存在

        Args:
            category: 模板分类

        Returns:
            模板是否存在
        """
        return category in self._templates
