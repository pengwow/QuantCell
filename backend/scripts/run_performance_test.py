#!/usr/bin/env python3
"""
性能测试主脚本

用法:
    python scripts/run_performance_test.py --data data/ETHUSDT.csv --iterations 3
"""

import argparse
import sys
from pathlib import Path

# 添加backend到路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from scripts.performance_test.test_runner import PerformanceTestRunner
from scripts.performance_test.report_generator import ReportGenerator


def main():
    parser = argparse.ArgumentParser(description='量化交易框架性能测试')
    parser.add_argument('--data', type=str, default='data/ETHUSDT.csv',
                        help='数据文件路径 (默认: data/ETHUSDT.csv)')
    parser.add_argument('--iterations', type=int, default=3,
                        help='每个框架的测试迭代次数 (默认: 3)')
    parser.add_argument('--fast', type=int, default=10,
                        help='SMA快速周期 (默认: 10)')
    parser.add_argument('--slow', type=int, default=30,
                        help='SMA慢速周期 (默认: 30)')
    parser.add_argument('--no-warmup', action='store_true',
                        help='跳过预热阶段')
    parser.add_argument('--output-dir', type=str, default='performance_reports',
                        help='报告输出目录 (默认: performance_reports)')
    
    args = parser.parse_args()
    
    # 策略参数
    strategy_params = {
        'fast': args.fast,
        'slow': args.slow,
    }
    
    # 创建测试运行器
    runner = PerformanceTestRunner(
        data_file=args.data,
        strategy_params=strategy_params
    )
    
    # 运行测试
    print("\n开始性能测试...")
    runner.run_tests(
        iterations=args.iterations,
        warmup=not args.no_warmup
    )
    
    # 生成报告
    print("\n生成报告...")
    report_generator = ReportGenerator(runner, output_dir=args.output_dir)
    
    # 控制台摘要
    report_generator.print_console_summary()
    
    # Markdown报告
    md_path = report_generator.generate_markdown_report()
    
    # JSON报告
    json_path = report_generator.generate_json_report()
    
    # CSV报告
    csv_paths = report_generator.generate_csv_reports()
    
    print("\n" + "=" * 80)
    print("性能测试完成!")
    print("=" * 80)
    print(f"\n生成的报告文件:")
    print(f"  - Markdown: {md_path}")
    print(f"  - JSON: {json_path}")
    for csv_path in csv_paths:
        print(f"  - CSV: {csv_path}")
    print()


if __name__ == "__main__":
    main()
