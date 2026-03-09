"""策略模板库模块

提供策略模板的加载、管理和渲染功能，支持从YAML文件加载策略模板，
并根据参数渲染生成可执行的策略代码。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TemplateParameter:
    """模板参数定义"""

    name: str
    type: str
    default: Any
    min: float | None = None
    max: float | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        result = {
            "name": self.name,
            "type": self.type,
            "default": self.default,
            "description": self.description,
        }
        if self.min is not None:
            result["min"] = self.min
        if self.max is not None:
            result["max"] = self.max
        return result


@dataclass
class StrategyTemplate:
    """策略模板定义"""

    id: str
    name: str
    category: str
    description: str
    author: str
    version: str
    tags: list[str] = field(default_factory=list)
    parameters: list[TemplateParameter] = field(default_factory=list)
    code_template: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "tags": self.tags,
            "parameters": [p.to_dict() for p in self.parameters],
        }

    def get_default_params(self) -> dict[str, Any]:
        """获取默认参数字典"""
        return {p.name: p.default for p in self.parameters}

    def validate_params(self, params: dict[str, Any]) -> tuple[bool, list[str]]:
        """验证参数是否有效

        Args:
            params: 要验证的参数

        Returns:
            (是否有效, 错误信息列表)
        """
        errors = []
        param_dict = {p.name: p for p in self.parameters}

        for name, value in params.items():
            if name not in param_dict:
                errors.append(f"未知参数: {name}")
                continue

            param = param_dict[name]

            # 类型检查
            if param.type == "int":
                if not isinstance(value, int):
                    try:
                        int(value)
                    except (ValueError, TypeError):
                        errors.append(f"参数 {name} 应为整数类型")
                        continue
            elif param.type == "float":
                if not isinstance(value, (int, float)):
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        errors.append(f"参数 {name} 应为数值类型")
                        continue

            # 范围检查
            if param.min is not None and value < param.min:
                errors.append(f"参数 {name} 不能小于 {param.min}")
            if param.max is not None and value > param.max:
                errors.append(f"参数 {name} 不能大于 {param.max}")

        return len(errors) == 0, errors


@dataclass
class TemplateCategory:
    """模板分类定义"""

    id: str
    name: str
    description: str

    def to_dict(self) -> dict[str, str]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
        }


class TemplateLibrary:
    """策略模板库

    管理策略模板的单例类，提供模板加载、查询和渲染功能。

    Attributes:
        _instance: 单例实例
        _templates: 模板字典，key为模板ID
        _categories: 分类字典，key为分类ID
    """

    _instance: TemplateLibrary | None = None
    _templates: dict[str, StrategyTemplate] = {}
    _categories: dict[str, TemplateCategory] = {}
    _library_file: Path | None = None

    def __new__(cls, *args, **kwargs) -> TemplateLibrary:
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, library_file: str | Path | None = None) -> None:
        """初始化模板库

        Args:
            library_file: 模板库YAML文件路径，默认为当前目录下的 strategy_library.yaml
        """
        if hasattr(self, "_initialized"):
            return

        if library_file is None:
            library_file = Path(__file__).parent / "templates" / "strategy_library.yaml"
        else:
            library_file = Path(library_file)

        self._library_file = library_file
        self._initialized = True

        # 自动加载模板
        self.load_templates()

    def load_templates(self) -> None:
        """从YAML文件加载模板"""
        if not self._library_file or not self._library_file.exists():
            raise FileNotFoundError(f"模板库文件不存在: {self._library_file}")

        with open(self._library_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 加载分类
        self._categories.clear()
        for cat_data in data.get("categories", []):
            category = TemplateCategory(
                id=cat_data["id"],
                name=cat_data["name"],
                description=cat_data.get("description", ""),
            )
            self._categories[category.id] = category

        # 加载模板
        self._templates.clear()
        for tmpl_data in data.get("templates", []):
            # 解析参数
            parameters = []
            for param_data in tmpl_data.get("parameters", []):
                param = TemplateParameter(
                    name=param_data["name"],
                    type=param_data["type"],
                    default=param_data["default"],
                    min=param_data.get("min"),
                    max=param_data.get("max"),
                    description=param_data.get("description", ""),
                )
                parameters.append(param)

            template = StrategyTemplate(
                id=tmpl_data["id"],
                name=tmpl_data["name"],
                category=tmpl_data["category"],
                description=tmpl_data.get("description", ""),
                author=tmpl_data.get("author", "Unknown"),
                version=tmpl_data.get("version", "1.0.0"),
                tags=tmpl_data.get("tags", []),
                parameters=parameters,
                code_template=tmpl_data.get("code_template", ""),
            )
            self._templates[template.id] = template

    def get_all_templates(self, category: str | None = None) -> list[StrategyTemplate]:
        """获取所有模板列表

        Args:
            category: 可选的分类过滤，如果提供则只返回该分类的模板

        Returns:
            模板列表
        """
        templates = list(self._templates.values())
        if category:
            templates = [t for t in templates if t.category == category]
        return templates

    def get_template(self, template_id: str) -> StrategyTemplate | None:
        """获取单个模板

        Args:
            template_id: 模板ID

        Returns:
            模板对象，如果不存在则返回None
        """
        return self._templates.get(template_id)

    def render_template(
        self, template_id: str, strategy_name: str | None = None, **params: Any
    ) -> str:
        """渲染模板生成代码

        使用提供的参数替换模板中的变量，生成可执行的策略代码。
        变量格式为 {{variable_name}}。

        Args:
            template_id: 模板ID
            strategy_name: 策略类名，如果为None则使用默认名称
            **params: 模板参数

        Returns:
            渲染后的代码字符串

        Raises:
            KeyError: 如果模板不存在
            ValueError: 如果参数验证失败
        """
        template = self._templates.get(template_id)
        if not template:
            raise KeyError(f"模板 '{template_id}' 不存在")

        # 合并默认参数和用户参数
        render_params = template.get_default_params()
        render_params.update(params)

        # 添加策略名称
        if strategy_name:
            render_params["strategy_name"] = strategy_name
        elif "strategy_name" not in render_params:
            render_params["strategy_name"] = "GeneratedStrategy"

        # 验证参数（排除 strategy_name，因为它是渲染变量而非策略参数）
        validation_params = {k: v for k, v in render_params.items() if k != "strategy_name"}
        is_valid, errors = template.validate_params(validation_params)
        if not is_valid:
            raise ValueError(f"参数验证失败: {'; '.join(errors)}")

        # 渲染模板
        code = template.code_template

        # 替换 {{variable}} 格式的变量
        def replace_variable(match: re.Match) -> str:
            var_name = match.group(1).strip()
            if var_name in render_params:
                return str(render_params[var_name])
            # 如果变量未提供，保留原样
            return match.group(0)

        return re.sub(r"\{\{(\w+)\}\}", replace_variable, code)

    def get_categories(self) -> list[TemplateCategory]:
        """获取所有分类列表

        Returns:
            分类列表
        """
        return list(self._categories.values())

    def get_category(self, category_id: str) -> TemplateCategory | None:
        """获取单个分类

        Args:
            category_id: 分类ID

        Returns:
            分类对象，如果不存在则返回None
        """
        return self._categories.get(category_id)

    def get_templates_by_category(self, category_id: str) -> list[StrategyTemplate]:
        """获取指定分类的所有模板

        Args:
            category_id: 分类ID

        Returns:
            模板列表
        """
        return [t for t in self._templates.values() if t.category == category_id]

    def search_templates(self, query: str) -> list[StrategyTemplate]:
        """搜索模板

        根据名称、描述或标签搜索模板。

        Args:
            query: 搜索关键词

        Returns:
            匹配的模板列表
        """
        query = query.lower()
        results = []
        for template in self._templates.values():
            if (
                query in template.name.lower()
                or query in template.description.lower()
                or any(query in tag.lower() for tag in template.tags)
            ):
                results.append(template)
        return results

    def reload(self) -> None:
        """重新加载模板库"""
        self.load_templates()

    def list_template_ids(self) -> list[str]:
        """获取所有模板ID列表"""
        return list(self._templates.keys())

    def list_category_ids(self) -> list[str]:
        """获取所有分类ID列表"""
        return list(self._categories.keys())

    def has_template(self, template_id: str) -> bool:
        """检查模板是否存在

        Args:
            template_id: 模板ID

        Returns:
            是否存在
        """
        return template_id in self._templates

    def get_library_info(self) -> dict[str, Any]:
        """获取模板库信息

        Returns:
            包含版本、描述、模板数量等信息的字典
        """
        if not self._library_file or not self._library_file.exists():
            return {
                "version": "unknown",
                "description": "",
                "template_count": 0,
                "category_count": 0,
            }

        with open(self._library_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return {
            "version": data.get("version", "unknown"),
            "description": data.get("description", ""),
            "template_count": len(self._templates),
            "category_count": len(self._categories),
        }
