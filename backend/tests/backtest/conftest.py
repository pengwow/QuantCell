# -*- coding: utf-8 -*-
"""
回测测试模块配置

提供回测测试专用的夹具和配置
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytest

# 确保能够导入后端模块
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class PerformanceReportCollector:
    """
    性能测试报告收集器

    收集并生成性能测试对比报告
    """

    def __init__(self):
        self.results: Dict[str, Any] = {}
        self.report_dir = project_root / "performance_reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def add_result(self, test_name: str, engine_type: str, metrics: Dict[str, Any]):
        """
        添加测试结果

        Args:
            test_name: 测试名称
            engine_type: 引擎类型 (default/legacy)
            metrics: 性能指标字典
        """
        if test_name not in self.results:
            self.results[test_name] = {}
        self.results[test_name][engine_type] = metrics

    def generate_comparison_report(self) -> Path:
        """
        生成性能对比报告

        Returns:
            Path: 报告文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.report_dir / f"engine_comparison_{timestamp}.json"

        # 计算对比指标
        comparison = self._calculate_comparison()

        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": comparison,
            "detailed_results": self.results,
            "system_info": {
                "python_version": sys.version,
                "platform": sys.platform,
            },
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return report_path

    def _calculate_comparison(self) -> Dict[str, Any]:
        """
        计算引擎对比指标

        Returns:
            Dict: 对比结果
        """
        comparison = {}

        for test_name, engines in self.results.items():
            if "default" in engines and "legacy" in engines:
                default_time = engines["default"].get("elapsed_time", 0)
                legacy_time = engines["legacy"].get("elapsed_time", 0)

                if legacy_time > 0:
                    speedup = legacy_time / default_time if default_time > 0 else 0
                else:
                    speedup = 0

                default_memory = engines["default"].get("peak_memory_mb", 0)
                legacy_memory = engines["legacy"].get("peak_memory_mb", 0)

                comparison[test_name] = {
                    "default_time": default_time,
                    "legacy_time": legacy_time,
                    "speedup": round(speedup, 2),
                    "default_memory_mb": default_memory,
                    "legacy_memory_mb": legacy_memory,
                    "memory_ratio": round(default_memory / legacy_memory, 2) if legacy_memory > 0 else 0,
                }

        return comparison


@pytest.fixture(scope="session")
def performance_collector():
    """
    性能测试收集器夹具

    用于收集和生成性能对比报告
    """
    collector = PerformanceReportCollector()
    yield collector

    # 测试会话结束时生成报告
    if collector.results:
        report_path = collector.generate_comparison_report()
        print(f"\n性能对比报告已生成: {report_path}")
