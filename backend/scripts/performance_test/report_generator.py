#!/usr/bin/env python3
"""
性能测试报告生成器

生成详细的性能对比报告，包括表格和图表
"""

import json
from datetime import datetime
from typing import Dict, List
import pandas as pd
import numpy as np


class ReportGenerator:
    """性能测试报告生成器"""

    def __init__(self, runner, output_dir: str = "performance_reports"):
        self.runner = runner
        self.output_dir = output_dir

    def _df_to_markdown(self, df: pd.DataFrame) -> str:
        """将DataFrame转换为Markdown表格"""
        if df.empty:
            return ""

        # 获取列名
        columns = df.columns.tolist()

        # 创建表头
        header = "| " + " | ".join(columns) + " |"
        separator = "|" + "|".join(["---" for _ in columns]) + "|"

        # 创建数据行
        rows = []
        for _, row in df.iterrows():
            row_values = [str(val) for val in row.values]
            rows.append("| " + " | ".join(row_values) + " |")

        return "\n".join([header, separator] + rows)

    def generate_markdown_report(self, filename: str = None) -> str:
        """生成Markdown格式的报告"""
        if filename is None:
            filename = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        report_path = f"{self.output_dir}/{filename}"

        # 确保输出目录存在
        import os
        os.makedirs(self.output_dir, exist_ok=True)

        lines = []

        # 报告标题
        lines.append("# 量化交易框架性能测试报告")
        lines.append("")
        lines.append(f"**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 系统信息
        lines.append("## 1. 测试环境")
        lines.append("")
        lines.append("### 1.1 系统配置")
        lines.append("")
        lines.append("| 配置项 | 值 |")
        lines.append("|--------|-----|")
        for key, value in self.runner.system_info.items():
            lines.append(f"| {key} | {value} |")
        lines.append("")

        # 测试配置
        lines.append("### 1.2 测试配置")
        lines.append("")
        lines.append(f"- **数据文件:** {self.runner.data_file}")
        lines.append(f"- **策略参数:** {self.runner.strategy_params}")
        lines.append(f"- **迭代次数:** {len(list(self.runner.results.values())[0]) if self.runner.results else 0}")
        lines.append("")

        # 性能摘要
        lines.append("## 2. 性能摘要")
        lines.append("")

        summary_df = self.runner.get_summary()
        if not summary_df.empty:
            lines.append(self._df_to_markdown(summary_df))
        lines.append("")

        # 详细对比
        lines.append("## 3. 框架对比")
        lines.append("")

        comparison = self.runner.compare_frameworks()
        if comparison:
            lines.append("### 3.1 相对性能对比（以QuantCell为基准）")
            lines.append("")
            lines.append("| 框架 | 时间比 | 时间差(ms) | 内存比 | 内存差(MB) | 更快 | 更省内存 |")
            lines.append("|------|--------|------------|--------|------------|------|----------|")

            # 添加 QuantCell 基准行
            lines.append("| QuantCell | 1.00x | 0.00 | 1.00x | 0.00 | - | - |")

            for framework, metrics in comparison.items():
                faster = "✓" if metrics['faster'] else "✗"
                less_memory = "✓" if metrics['less_memory'] else "✗"
                lines.append(
                    f"| {framework} | "
                    f"{metrics['time_ratio']:.2f}x | "
                    f"{metrics['time_diff_ms']:+.2f} | "
                    f"{metrics['memory_ratio']:.2f}x | "
                    f"{metrics['memory_diff_mb']:+.2f} | "
                    f"{faster} | "
                    f"{less_memory} |"
                )
            lines.append("")

        # 每次运行的详细结果
        lines.append("## 4. 每次运行详细结果")
        lines.append("")

        for framework_name, metrics_list in self.runner.results.items():
            lines.append(f"### 4.{list(self.runner.results.keys()).index(framework_name) + 1} {framework_name}")
            lines.append("")
            lines.append("| 运行次数 | 总耗时(ms) | 数据加载(ms) | 策略执行(ms) | 内存峰值(MB) | 内存平均(MB) | CPU平均(%) | CPU峰值(%) | 交易次数 | 信号数量 |")
            lines.append("|----------|------------|--------------|--------------|--------------|--------------|------------|------------|----------|----------|")

            for i, metrics in enumerate(metrics_list):
                lines.append(
                    f"| 第{i+1}次 | "
                    f"{metrics.total_time_ms:.2f} | "
                    f"{metrics.data_load_time_ms:.2f} | "
                    f"{metrics.strategy_execution_time_ms:.2f} | "
                    f"{metrics.memory_peak_mb:.2f} | "
                    f"{metrics.memory_avg_mb:.2f} | "
                    f"{metrics.cpu_avg_percent:.2f} | "
                    f"{metrics.cpu_peak_percent:.2f} | "
                    f"{metrics.total_trades} | "
                    f"{metrics.signals_generated} |"
                )

            # 计算统计值
            times = [m.total_time_ms for m in metrics_list]
            lines.append(f"| **平均** | **{np.mean(times):.2f}** | - | - | - | - | - | - | - | - |")
            lines.append(f"| **标准差** | **{np.std(times):.2f}** | - | - | - | - | - | - | - | - |")
            lines.append(f"| **最小值** | **{np.min(times):.2f}** | - | - | - | - | - | - | - | - |")
            lines.append(f"| **最大值** | **{np.max(times):.2f}** | - | - | - | - | - | - | - | - |")
            lines.append("")

        # 详细结果（原始数据）
        lines.append("## 5. 原始详细数据")
        lines.append("")

        detailed_df = self.runner.get_detailed_results()
        if not detailed_df.empty:
            lines.append(self._df_to_markdown(detailed_df))
        lines.append("")

        # 分析结论
        lines.append("## 6. 分析结论")
        lines.append("")

        if comparison:
            fastest_framework = min(
                comparison.items(),
                key=lambda x: x[1]['time_ratio']
            )
            lines.append(f"### 6.1 性能最快的框架")
            lines.append("")
            lines.append(f"**{fastest_framework[0]}** 相对于 QuantCell 的性能比为 {fastest_framework[1]['time_ratio']:.2f}x")
            lines.append("")

            most_memory_efficient = min(
                comparison.items(),
                key=lambda x: x[1]['memory_ratio']
            )
            lines.append(f"### 6.2 内存效率最高的框架")
            lines.append("")
            lines.append(f"**{most_memory_efficient[0]}** 相对于 QuantCell 的内存使用比为 {most_memory_efficient[1]['memory_ratio']:.2f}x")
            lines.append("")

        lines.append("### 6.3 适用场景建议")
        lines.append("")
        lines.append("- **QuantCell**: 适合需要灵活策略开发和快速迭代的场景")
        lines.append("- **Backtrader**: 适合需要丰富内置指标和事件驱动架构的场景")
        lines.append("- **Freqtrade**: 适合需要实盘交易和完整生态系统的场景")
        lines.append("")

        # 写入文件
        content = "\n".join(lines)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"\n报告已生成: {report_path}")
        return report_path

    def generate_json_report(self, filename: str = None) -> str:
        """生成JSON格式的报告"""
        if filename is None:
            filename = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        report_path = f"{self.output_dir}/{filename}"

        # 确保输出目录存在
        import os
        os.makedirs(self.output_dir, exist_ok=True)

        report_data = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'system_info': self.runner.system_info,
                'test_config': {
                    'data_file': self.runner.data_file,
                    'strategy_params': self.runner.strategy_params,
                }
            },
            'summary': self.runner.get_summary().to_dict('records'),
            'detailed_results': self.runner.get_detailed_results().to_dict('records'),
            'comparison': self.runner.compare_frameworks(),
        }

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, default=str)

        print(f"JSON报告已生成: {report_path}")
        return report_path

    def generate_csv_reports(self) -> List[str]:
        """生成CSV格式的详细报告"""
        import os
        os.makedirs(self.output_dir, exist_ok=True)

        generated_files = []

        # 摘要报告
        summary_df = self.runner.get_summary()
        if not summary_df.empty:
            summary_path = f"{self.output_dir}/summary.csv"
            summary_df.to_csv(summary_path, index=False)
            generated_files.append(summary_path)

        # 详细结果
        detailed_df = self.runner.get_detailed_results()
        if not detailed_df.empty:
            detailed_path = f"{self.output_dir}/detailed_results.csv"
            detailed_df.to_csv(detailed_path, index=False)
            generated_files.append(detailed_path)

        print(f"\nCSV报告已生成:")
        for f in generated_files:
            print(f"  - {f}")

        return generated_files

    def print_console_summary(self):
        """在控制台打印摘要"""
        print("\n" + "=" * 80)
        print("性能测试摘要")
        print("=" * 80)

        summary_df = self.runner.get_summary()
        if not summary_df.empty:
            print("\n", summary_df.to_string(index=False))

        # 打印每次运行的详细结果
        print("\n" + "-" * 80)
        print("每次运行详细结果")
        print("-" * 80)

        for framework_name, metrics_list in self.runner.results.items():
            print(f"\n{framework_name}:")
            print(f"{'运行次数':<10} {'总耗时(ms)':<15} {'数据加载(ms)':<15} {'策略执行(ms)':<15} {'内存峰值(MB)':<15}")
            print("-" * 70)

            for i, metrics in enumerate(metrics_list):
                print(f"第{i+1}次     {metrics.total_time_ms:<15.2f} {metrics.data_load_time_ms:<15.2f} "
                      f"{metrics.strategy_execution_time_ms:<15.2f} {metrics.memory_peak_mb:<15.2f}")

            # 计算统计值
            times = [m.total_time_ms for m in metrics_list]
            print(f"{'平均':<10} {np.mean(times):<15.2f} {'-':<15} {'-':<15} {'-':<15}")
            print(f"{'标准差':<10} {np.std(times):<15.2f} {'-':<15} {'-':<15} {'-':<15}")
            print(f"{'最小值':<10} {np.min(times):<15.2f} {'-':<15} {'-':<15} {'-':<15}")
            print(f"{'最大值':<10} {np.max(times):<15.2f} {'-':<15} {'-':<15} {'-':<15}")

        comparison = self.runner.compare_frameworks()
        if comparison:
            print("\n" + "-" * 80)
            print("框架对比（相对于QuantCell）")
            print("-" * 80)

            # 添加 QuantCell 基准
            print("\nQuantCell:")
            print("  时间性能: 1.00x (基准)")
            print("  内存使用: 1.00x (基准)")
            print("  更快: -")
            print("  更省内存: -")

            for framework, metrics in comparison.items():
                print(f"\n{framework}:")
                print(f"  时间性能: {metrics['time_ratio']:.2f}x ({metrics['time_diff_ms']:+.2f} ms)")
                print(f"  内存使用: {metrics['memory_ratio']:.2f}x ({metrics['memory_diff_mb']:+.2f} MB)")
                print(f"  更快: {'是' if metrics['faster'] else '否'}")
                print(f"  更省内存: {'是' if metrics['less_memory'] else '否'}")

        print("\n" + "=" * 80)
