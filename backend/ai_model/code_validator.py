"""代码验证模块

提供对Python代码的语法、结构和风格验证功能。
支持策略代码的完整性检查，包括必需类和方法的检测。
"""

import ast
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
@dataclass
class ValidationError:
    """验证错误信息"""

    type: str
    line: int
    column: int
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "line": self.line,
            "column": self.column,
            "message": self.message,
        }


@dataclass
class ValidationWarning:
    """验证警告信息"""

    type: str
    line: int
    column: int
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "line": self.line,
            "column": self.column,
            "message": self.message,
        }


class CodeValidator:
    """代码验证器

    提供对Python代码的全面验证功能，包括：
    - 语法验证：使用ast模块检查Python语法正确性
    - 结构验证：检查是否包含必需的类和方法
    - 风格验证：检查代码风格问题（行长度、缩进等）

    Attributes:
        max_line_length: 最大行长度限制，默认120字符
        required_class_name: 必需的类名，默认"Strategy"
        required_methods: 必需的方法列表
    """

    DEFAULT_MAX_LINE_LENGTH = 120
    DEFAULT_REQUIRED_CLASS_NAME = "Strategy"
    DEFAULT_REQUIRED_METHODS = ["on_bar"]

    def __init__(
        self,
        max_line_length: int = DEFAULT_MAX_LINE_LENGTH,
        required_class_name: str = DEFAULT_REQUIRED_CLASS_NAME,
        required_methods: Optional[List[str]] = None,
    ):
        """初始化代码验证器

        Args:
            max_line_length: 最大行长度限制
            required_class_name: 必需的类名
            required_methods: 必需的方法列表
        """
        self.max_line_length = max_line_length
        self.required_class_name = required_class_name
        self.required_methods = (required_methods or self.DEFAULT_REQUIRED_METHODS).copy()

        logger.debug(
            f"CodeValidator初始化完成，最大行长度: {max_line_length}, "
            f"必需类名: {required_class_name}, 必需方法: {self.required_methods}"
        )

    def validate_syntax(self, code: str) -> Tuple[List[ValidationError], List[ValidationWarning]]:
        """验证Python语法

        使用ast模块解析代码，检查语法正确性。

        Args:
            code: 要验证的Python代码

        Returns:
            Tuple包含错误列表和警告列表
        """
        errors: List[ValidationError] = []
        warnings: List[ValidationWarning] = []

        if not code or not code.strip():
            errors.append(
                ValidationError(
                    type="syntax_error",
                    line=0,
                    column=0,
                    message="代码为空",
                )
            )
            return errors, warnings

        try:
            ast.parse(code)
            logger.debug("语法验证通过")
        except IndentationError as e:
            # IndentationError是SyntaxError的子类，需要优先捕获
            errors.append(
                ValidationError(
                    type="indentation_error",
                    line=e.lineno or 1,
                    column=e.offset or 0,
                    message=f"缩进错误: {e.msg}",
                )
            )
            logger.debug(f"缩进错误: {e.msg} (第{e.lineno}行)")
        except SyntaxError as e:
            errors.append(
                ValidationError(
                    type="syntax_error",
                    line=e.lineno or 1,
                    column=e.offset or 0,
                    message=f"语法错误: {e.msg}",
                )
            )
            logger.debug(f"语法错误: {e.msg} (第{e.lineno}行)")
        except Exception as e:
            errors.append(
                ValidationError(
                    type="parse_error",
                    line=0,
                    column=0,
                    message=f"解析错误: {str(e)}",
                )
            )
            logger.debug(f"解析错误: {str(e)}")

        return errors, warnings

    def validate_structure(self, code: str) -> Tuple[List[ValidationError], List[ValidationWarning]]:
        """验证代码结构

        检查代码是否包含必需的类和方法。

        Args:
            code: 要验证的Python代码

        Returns:
            Tuple包含错误列表和警告列表
        """
        errors: List[ValidationError] = []
        warnings: List[ValidationWarning] = []

        if not code or not code.strip():
            errors.append(
                ValidationError(
                    type="structure_error",
                    line=0,
                    column=0,
                    message="代码为空",
                )
            )
            return errors, warnings

        try:
            tree = ast.parse(code)
        except SyntaxError:
            # 语法错误已在validate_syntax中处理
            return errors, warnings

        # 查找所有类定义
        classes: List[ast.ClassDef] = [
            node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        ]

        if not classes:
            errors.append(
                ValidationError(
                    type="structure_error",
                    line=0,
                    column=0,
                    message="未找到类定义，策略必须包含至少一个类",
                )
            )
            return errors, warnings

        # 检查是否包含必需的类名（作为基类或类名的一部分）
        strategy_classes: List[ast.ClassDef] = []
        for cls in classes:
            # 检查类名是否包含Strategy
            if self.required_class_name in cls.name:
                strategy_classes.append(cls)
            else:
                # 检查基类
                for base in cls.bases:
                    if isinstance(base, ast.Name) and self.required_class_name in base.id:
                        strategy_classes.append(cls)
                        break
                    elif isinstance(base, ast.Attribute):
                        if self.required_class_name in base.attr:
                            strategy_classes.append(cls)
                            break

        if not strategy_classes:
            warnings.append(
                ValidationWarning(
                    type="structure_warning",
                    line=classes[0].lineno,
                    column=classes[0].col_offset,
                    message=f"未找到包含'{self.required_class_name}'的类，建议类名或基类包含'Strategy'",
                )
            )
        else:
            # 检查必需方法
            for cls in strategy_classes:
                method_names: Set[str] = {
                    node.name
                    for node in ast.walk(cls)
                    if isinstance(node, ast.FunctionDef)
                }

                for required_method in self.required_methods:
                    if required_method not in method_names:
                        errors.append(
                            ValidationError(
                                type="structure_error",
                                line=cls.lineno,
                                column=cls.col_offset,
                                message=f"类'{cls.name}'缺少必需方法'{required_method}'",
                            )
                        )

        # 检查是否有__init__方法（推荐但不强制）
        has_init = any(
            isinstance(node, ast.FunctionDef) and node.name == "__init__"
            for node in ast.walk(tree)
        )
        if not has_init:
            warnings.append(
                ValidationWarning(
                    type="structure_warning",
                    line=0,
                    column=0,
                    message="建议添加__init__方法进行初始化",
                )
            )

        return errors, warnings

    def validate_style(self, code: str) -> Tuple[List[ValidationError], List[ValidationWarning]]:
        """验证代码风格

        检查代码风格问题，包括行长度、缩进等。

        Args:
            code: 要验证的Python代码

        Returns:
            Tuple包含错误列表和警告列表
        """
        errors: List[ValidationError] = []
        warnings: List[ValidationWarning] = []

        if not code or not code.strip():
            return errors, warnings

        lines = code.split("\n")

        for line_num, line in enumerate(lines, start=1):
            # 检查行长度
            if len(line) > self.max_line_length:
                warnings.append(
                    ValidationWarning(
                        type="style_warning",
                        line=line_num,
                        column=self.max_line_length,
                        message=f"行长度{len(line)}超过限制{self.max_line_length}字符",
                    )
                )

            # 检查缩进（使用空格而非Tab）
            if "\t" in line:
                tab_pos = line.find("\t")
                warnings.append(
                    ValidationWarning(
                        type="style_warning",
                        line=line_num,
                        column=tab_pos,
                        message="使用Tab缩进，建议使用4个空格",
                    )
                )

            # 检查行尾空格
            if line.rstrip() != line:
                warnings.append(
                    ValidationWarning(
                        type="style_warning",
                        line=line_num,
                        column=len(line.rstrip()),
                        message="行尾存在多余空格",
                    )
                )

            # 检查空行（连续多个空行）
            if line_num > 1 and not line.strip() and not lines[line_num - 2].strip():
                # 跳过类定义和方法定义之间的空行（这是允许的）
                pass

        # 检查文件末尾空行
        if code and not code.endswith("\n"):
            warnings.append(
                ValidationWarning(
                    type="style_warning",
                    line=len(lines),
                    column=len(lines[-1]) if lines else 0,
                    message="文件末尾缺少换行符",
                )
            )
        elif code.endswith("\n\n"):
            warnings.append(
                ValidationWarning(
                    type="style_warning",
                    line=len(lines),
                    column=0,
                    message="文件末尾存在多余空行",
                )
            )

        return errors, warnings

    def validate(self, code: str) -> Dict[str, Any]:
        """综合验证

        执行所有验证步骤，返回完整的验证结果。

        Args:
            code: 要验证的Python代码

        Returns:
            Dict包含:
                - valid: 是否通过验证（无错误）
                - errors: 错误列表
                - warnings: 警告列表
                - summary: 验证摘要
        """
        all_errors: List[ValidationError] = []
        all_warnings: List[ValidationWarning] = []

        logger.debug("开始代码验证")

        # 语法验证
        syntax_errors, syntax_warnings = self.validate_syntax(code)
        all_errors.extend(syntax_errors)
        all_warnings.extend(syntax_warnings)

        # 如果语法错误，跳过后续验证
        if not syntax_errors:
            # 结构验证
            structure_errors, structure_warnings = self.validate_structure(code)
            all_errors.extend(structure_errors)
            all_warnings.extend(structure_warnings)

            # 风格验证
            style_errors, style_warnings = self.validate_style(code)
            all_errors.extend(style_errors)
            all_warnings.extend(style_warnings)

        result = {
            "valid": len(all_errors) == 0,
            "errors": [e.to_dict() for e in all_errors],
            "warnings": [w.to_dict() for w in all_warnings],
            "summary": {
                "total_errors": len(all_errors),
                "total_warnings": len(all_warnings),
                "syntax_valid": len(syntax_errors) == 0,
            },
        }

        logger.debug(
            f"验证完成: {len(all_errors)}个错误, {len(all_warnings)}个警告"
        )

        return result

    def validate_strategy_code(self, code: str) -> Dict[str, Any]:
        """专门验证策略代码

        针对策略代码的特定验证，包含更严格的检查。

        Args:
            code: 策略代码

        Returns:
            Dict包含验证结果
        """
        result = self.validate(code)

        # 额外的策略特定检查
        if result["summary"]["syntax_valid"]:
            try:
                tree = ast.parse(code)

                # 检查是否导入必要的模块
                imports: Set[str] = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.add(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.add(node.module)

                # 检查是否有策略相关的导入
                strategy_imports = [
                    "strategy.core",
                    "nautilus_trader",
                    "backtrader",
                    "Strategy",
                ]
                has_strategy_import = any(
                    any(s in imp for s in strategy_imports)
                    for imp in imports
                )

                if not has_strategy_import:
                    result["warnings"].append({
                        "type": "strategy_warning",
                        "line": 0,
                        "column": 0,
                        "message": "未检测到策略框架导入，建议导入strategy.core或其他策略框架",
                    })
                    result["summary"]["total_warnings"] += 1

            except SyntaxError:
                pass

        return result
