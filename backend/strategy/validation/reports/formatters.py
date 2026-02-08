"""
报告格式化工具
支持多种格式的报告输出
"""

import json
from typing import Any, Dict, List
from datetime import datetime

from ..core.base import ValidationResult, ValidationSeverity


class BaseFormatter:
    """格式化器基类"""

    def format(self, results: List[ValidationResult], summary: Dict[str, Any]) -> str:
        """格式化报告"""
        raise NotImplementedError


class MarkdownFormatter(BaseFormatter):
    """Markdown格式报告"""

    def format(self, results: List[ValidationResult], summary: Dict[str, Any]) -> str:
        """生成Markdown格式报告"""
        lines = []

        # 标题
        lines.append("# 回测引擎验证报告\n")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # 摘要
        lines.append("## 验证摘要\n")
        lines.append(f"- **验证套件**: {summary.get('suite_name', 'N/A')}")
        lines.append(f"- **总验证项**: {summary.get('total', 0)}")
        lines.append(f"- **通过**: {summary.get('passed', 0)}")
        lines.append(f"- **失败**: {summary.get('failed', 0)}")
        lines.append(f"- **通过率**: {summary.get('pass_rate', 0)*100:.2f}%")
        lines.append("")

        # 严重程度统计
        severity_counts = summary.get('severity_counts', {})
        if severity_counts:
            lines.append("### 严重程度分布\n")
            for severity, count in severity_counts.items():
                emoji = {"info": "✅", "warning": "⚠️", "error": "❌", "critical": "🚨"}.get(severity, "")
                lines.append(f"- {emoji} **{severity.upper()}**: {count}")
            lines.append("")

        # 详细结果
        lines.append("## 详细验证结果\n")

        # 按严重程度分组
        critical_results = [r for r in results if r.severity == ValidationSeverity.CRITICAL]
        error_results = [r for r in results if r.severity == ValidationSeverity.ERROR]
        warning_results = [r for r in results if r.severity == ValidationSeverity.WARNING]
        info_results = [r for r in results if r.severity == ValidationSeverity.INFO]

        if critical_results:
            lines.append("### 🚨 严重错误\n")
            for result in critical_results:
                lines.extend(self._format_result(result))

        if error_results:
            lines.append("### ❌ 错误\n")
            for result in error_results:
                lines.extend(self._format_result(result))

        if warning_results:
            lines.append("### ⚠️ 警告\n")
            for result in warning_results:
                lines.extend(self._format_result(result))

        if info_results:
            lines.append("### ✅ 通过\n")
            for result in info_results:
                lines.extend(self._format_result(result))

        return "\n".join(lines)

    def _format_result(self, result: ValidationResult) -> List[str]:
        """格式化单个结果"""
        lines = []
        status = "✅ 通过" if result.passed else "❌ 失败"
        lines.append(f"#### {result.validator_name} - {status}\n")
        lines.append(f"**消息**: {result.message}\n")

        if result.expected_value is not None:
            lines.append(f"**期望值**: {result.expected_value}")
        if result.actual_value is not None:
            lines.append(f"**实际值**: {result.actual_value}")
        if result.difference is not None:
            lines.append(f"**差异**: {result.difference:.6f}")
        if result.difference_pct is not None:
            lines.append(f"**差异百分比**: {result.difference_pct:.4f}%")
        if result.threshold is not None:
            lines.append(f"**阈值**: {result.threshold}")

        lines.append("")
        return lines


class JSONFormatter(BaseFormatter):
    """JSON格式报告"""

    def format(self, results: List[ValidationResult], summary: Dict[str, Any]) -> str:
        """生成JSON格式报告"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "results": [r.to_dict() for r in results],
        }
        return json.dumps(report, indent=2, ensure_ascii=False)


class HTMLFormatter(BaseFormatter):
    """HTML格式报告"""

    def format(self, results: List[ValidationResult], summary: Dict[str, Any]) -> str:
        """生成HTML格式报告"""
        html = []

        html.append("<!DOCTYPE html>")
        html.append("<html>")
        html.append("<head>")
        html.append("<meta charset='UTF-8'>")
        html.append("<title>回测引擎验证报告</title>")
        html.append("<style>")
        html.append(self._get_css())
        html.append("</style>")
        html.append("</head>")
        html.append("<body>")

        # 标题
        html.append("<h1>回测引擎验证报告</h1>")
        html.append(f"<p class='timestamp'>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>")

        # 摘要
        html.append("<div class='summary'>")
        html.append("<h2>验证摘要</h2>")
        html.append("<table>")
        html.append(f"<tr><td>验证套件</td><td>{summary.get('suite_name', 'N/A')}</td></tr>")
        html.append(f"<tr><td>总验证项</td><td>{summary.get('total', 0)}</td></tr>")
        html.append(f"<tr><td>通过</td><td class='pass'>{summary.get('passed', 0)}</td></tr>")
        html.append(f"<tr><td>失败</td><td class='fail'>{summary.get('failed', 0)}</td></tr>")
        html.append(f"<tr><td>通过率</td><td>{summary.get('pass_rate', 0)*100:.2f}%</td></tr>")
        html.append("</table>")
        html.append("</div>")

        # 详细结果
        html.append("<div class='results'>")
        html.append("<h2>详细验证结果</h2>")

        for result in results:
            html.extend(self._format_result_html(result))

        html.append("</div>")
        html.append("</body>")
        html.append("</html>")

        return "\n".join(html)

    def _format_result_html(self, result: ValidationResult) -> List[str]:
        """格式化单个结果为HTML"""
        html = []

        severity_class = result.severity.value
        status = "通过" if result.passed else "失败"

        html.append(f"<div class='result {severity_class}'>")
        html.append(f"<h3>{result.validator_name} - {status}</h3>")
        html.append(f"<p class='message'>{result.message}</p>")

        html.append("<table>")
        if result.expected_value is not None:
            html.append(f"<tr><td>期望值</td><td>{result.expected_value}</td></tr>")
        if result.actual_value is not None:
            html.append(f"<tr><td>实际值</td><td>{result.actual_value}</td></tr>")
        if result.difference is not None:
            html.append(f"<tr><td>差异</td><td>{result.difference:.6f}</td></tr>")
        if result.difference_pct is not None:
            html.append(f"<tr><td>差异百分比</td><td>{result.difference_pct:.4f}%</td></tr>")
        html.append("</table>")

        html.append("</div>")
        return html

    def _get_css(self) -> str:
        """获取CSS样式"""
        return """
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        h1 { color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }
        h2 { color: #555; margin-top: 30px; }
        .timestamp { color: #666; font-size: 14px; }
        .summary { background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }
        .results { background: white; padding: 20px; border-radius: 8px; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        td { padding: 8px; border: 1px solid #ddd; }
        .pass { color: green; font-weight: bold; }
        .fail { color: red; font-weight: bold; }
        .result { margin: 15px 0; padding: 15px; border-radius: 5px; }
        .result.info { background: #d4edda; border-left: 4px solid #28a745; }
        .result.warning { background: #fff3cd; border-left: 4px solid #ffc107; }
        .result.error { background: #f8d7da; border-left: 4px solid #dc3545; }
        .result.critical { background: #f5c6cb; border-left: 4px solid #721c24; }
        .message { font-weight: bold; margin: 10px 0; }
        """
