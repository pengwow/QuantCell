"""
报告生成器
用于生成完整的验证报告
"""

from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from ..core.base import ValidationResult, ValidationSuite
from .formatters import MarkdownFormatter, JSONFormatter, HTMLFormatter


class ReportGenerator:
    """
    报告生成器

    用于生成各种格式的验证报告
    """

    def __init__(self):
        self.formatters = {
            "markdown": MarkdownFormatter(),
            "json": JSONFormatter(),
            "html": HTMLFormatter(),
        }

    def generate(
        self,
        results: List[ValidationResult],
        summary: Dict[str, Any],
        format_type: str = "markdown",
    ) -> str:
        """
        生成报告

        Args:
            results: 验证结果列表
            summary: 验证摘要
            format_type: 报告格式 (markdown, json, html)

        Returns:
            str: 格式化后的报告内容
        """
        if format_type not in self.formatters:
            raise ValueError(f"不支持的报告格式: {format_type}")

        formatter = self.formatters[format_type]
        return formatter.format(results, summary)

    def save(
        self,
        results: List[ValidationResult],
        summary: Dict[str, Any],
        output_path: str,
        format_type: Optional[str] = None,
    ) -> Path:
        """
        保存报告到文件

        Args:
            results: 验证结果列表
            summary: 验证摘要
            output_path: 输出文件路径
            format_type: 报告格式，如果为None则从文件扩展名推断

        Returns:
            Path: 保存的文件路径
        """
        path = Path(output_path)

        # 推断格式
        if format_type is None:
            suffix = path.suffix.lower()
            format_map = {
                ".md": "markdown",
                ".json": "json",
                ".html": "html",
            }
            format_type = format_map.get(suffix, "markdown")

        # 生成报告
        report_content = self.generate(results, summary, format_type)

        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"验证报告已保存: {path}")
        return path

    def generate_from_suite(
        self,
        suite: ValidationSuite,
        format_type: str = "markdown",
    ) -> str:
        """
        从验证套件生成报告

        Args:
            suite: 验证套件
            format_type: 报告格式

        Returns:
            str: 格式化后的报告内容
        """
        summary = suite.get_summary()
        return self.generate(suite.results, summary, format_type)

    def save_from_suite(
        self,
        suite: ValidationSuite,
        output_dir: str,
        formats: List[str] = None,
    ) -> Dict[str, Path]:
        """
        从验证套件保存多种格式的报告

        Args:
            suite: 验证套件
            output_dir: 输出目录
            formats: 要生成的格式列表，默认生成所有格式

        Returns:
            Dict[str, Path]: 格式到文件路径的映射
        """
        if formats is None:
            formats = ["markdown", "json", "html"]

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suite_name = suite.name.replace(" ", "_").lower()

        saved_files = {}
        summary = suite.get_summary()

        format_extensions = {
            "markdown": "md",
            "json": "json",
            "html": "html",
        }

        for fmt in formats:
            if fmt not in self.formatters:
                logger.warning(f"跳过不支持的格式: {fmt}")
                continue

            ext = format_extensions.get(fmt, fmt)
            filename = f"{suite_name}_validation_report_{timestamp}.{ext}"
            filepath = output_dir / filename

            self.save(suite.results, summary, str(filepath), fmt)
            saved_files[fmt] = filepath

        return saved_files


class ValidationReporter:
    """
    验证报告器

    提供便捷的报告生成和输出功能
    """

    def __init__(self):
        self.generator = ReportGenerator()

    def console_report(self, results: List[ValidationResult], summary: Dict[str, Any]):
        """
        输出控制台报告

        Args:
            results: 验证结果列表
            summary: 验证摘要
        """
        print("\n" + "=" * 60)
        print("回测引擎验证报告".center(60))
        print("=" * 60)

        print(f"\n验证套件: {summary.get('suite_name', 'N/A')}")
        print(f"总验证项: {summary.get('total', 0)}")
        print(f"通过: {summary.get('passed', 0)}")
        print(f"失败: {summary.get('failed', 0)}")
        print(f"通过率: {summary.get('pass_rate', 0)*100:.2f}%")

        severity_counts = summary.get('severity_counts', {})
        if severity_counts:
            print("\n严重程度分布:")
            for severity, count in severity_counts.items():
                emoji = {"info": "✅", "warning": "⚠️", "error": "❌", "critical": "🚨"}.get(severity, "")
                print(f"  {emoji} {severity.upper()}: {count}")

        # 显示失败的验证
        failed_results = [r for r in results if not r.passed]
        if failed_results:
            print("\n" + "-" * 60)
            print("失败的验证项:")
            print("-" * 60)
            for result in failed_results:
                print(f"\n❌ {result.validator_name}")
                print(f"   消息: {result.message}")
                if result.difference_pct is not None:
                    print(f"   差异: {result.difference_pct:.4f}%")

        print("\n" + "=" * 60)

    def quick_report(self, suite: ValidationSuite, output_dir: Optional[str] = None):
        """
        快速生成并输出报告

        Args:
            suite: 验证套件
            output_dir: 可选的输出目录
        """
        summary = suite.get_summary()

        # 控制台输出
        self.console_report(suite.results, summary)

        # 保存文件报告
        if output_dir:
            saved = self.generator.save_from_suite(suite, output_dir)
            print(f"\n报告已保存到:")
            for fmt, path in saved.items():
                print(f"  - {fmt}: {path}")
