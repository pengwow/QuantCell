"""
验证模块命令行接口
提供便捷的命令行工具来执行验证
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

# 在导入任何其他模块之前，先配置日志以抑制模块导入时的调试输出
from loguru import logger

# 移除默认的日志处理器并设置日志级别为 INFO
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

# 现在可以安全地导入其他模块
from .runner import BacktestValidator, quick_validate


def setup_logging(verbose: bool = False):
    """设置日志（根据用户参数调整日志级别）"""
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")


def run_case(case_name: str, output_dir: Optional[str] = None) -> bool:
    """
    运行验证案例

    Args:
        case_name: 案例名称
        output_dir: 输出目录

    Returns:
        bool: 是否通过
    """
    # 延迟导入验证案例，避免在模块加载时输出日志
    from .cases.sma_cross_case import SmaCrossValidationCase, SmaCrossEngineComparisonCase
    from .cases.buy_hold_case import BuyHoldValidationCase

    cases = {
        "sma_cross": SmaCrossValidationCase,
        "sma_cross_comparison": SmaCrossEngineComparisonCase,
        "buy_hold": BuyHoldValidationCase,
    }

    if case_name not in cases:
        logger.error(f"未知案例: {case_name}")
        logger.info(f"可用案例: {', '.join(cases.keys())}")
        return False

    case_class = cases[case_name]
    case = case_class()

    logger.info(f"运行验证案例: {case_name}")
    result = case.run_validation()

    passed = result.get("passed", False)
    summary = result.get("summary", {})

    logger.info(f"案例执行完成: {case_name}")
    logger.info(f"通过状态: {'✅ 通过' if passed else '❌ 失败'}")
    logger.info(f"总验证项: {summary.get('total', 0)}")
    logger.info(f"通过: {summary.get('passed', 0)}")
    logger.info(f"失败: {summary.get('failed', 0)}")

    # 保存报告
    if output_dir:
        from .reports.report_generator import ReportGenerator
        from .core.base import ValidationSuite

        suite = ValidationSuite(name=case_name)
        # 这里简化处理，实际应该传递完整的验证结果
        generator = ReportGenerator()
        output_path = Path(output_dir) / f"{case_name}_report.md"
        generator.save([], summary, str(output_path), "markdown")
        logger.info(f"报告已保存: {output_path}")

    return passed


def run_all_cases(output_dir: Optional[str] = None) -> bool:
    """
    运行所有验证案例

    Args:
        output_dir: 输出目录

    Returns:
        bool: 是否全部通过
    """
    cases = ["sma_cross", "sma_cross_comparison", "buy_hold"]
    all_passed = True

    logger.info("=" * 60)
    logger.info("运行所有验证案例")
    logger.info("=" * 60)

    for case_name in cases:
        passed = run_case(case_name, output_dir)
        if not passed:
            all_passed = False
        logger.info("-" * 60)

    logger.info("=" * 60)
    logger.info(f"所有案例执行完成: {'✅ 全部通过' if all_passed else '❌ 存在失败'}")
    logger.info("=" * 60)

    return all_passed


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="回测引擎验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行所有验证案例
  python -m strategy.validation.cli --all

  # 运行特定案例
  python -m strategy.validation.cli --case sma_cross

  # 运行并保存报告
  python -m strategy.validation.cli --all --output ./reports

  # 详细输出
  python -m strategy.validation.cli --all --verbose
        """
    )

    parser.add_argument(
        "--case",
        type=str,
        help="运行特定验证案例 (sma_cross, sma_cross_comparison, buy_hold)",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="运行所有验证案例",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="报告输出目录",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="详细输出",
    )

    args = parser.parse_args()

    # 如果没有指定任何操作，直接显示帮助信息
    if not args.all and not args.case:
        parser.print_help()
        return 0

    # 根据用户参数重新设置日志级别
    setup_logging(args.verbose)

    # 执行验证
    if args.all:
        passed = run_all_cases(args.output)
    elif args.case:
        passed = run_case(args.case, args.output)
    else:
        return 0

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
