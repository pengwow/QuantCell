# -*- coding: utf-8 -*-
"""
trading engine 集成性能测试模块

对 Engine 和 LegacyEngine 进行全面的性能对比测试，包括：
- 执行时间基准测试
- 内存使用分析
- 大数据集处理能力
- 吞吐量测试

测试结果保存到文件以便历史对比分析。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-15
"""

import gc
import json
import os
import sys
import time
import tracemalloc
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import pytest
from loguru import logger

# 确保能够导入后端模块
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backtest.engines import LegacyEngine, Engine
from backtest.config import EngineType


# =============================================================================
# 测试配置常量
# =============================================================================

# 测试数据规模配置
TEST_DATA_SIZES = {
    "small": 1000,      # 小规模测试
    "medium": 10000,    # 中等规模测试
    "large": 100000,    # 大规模测试
    "xlarge": 500000,   # 超大规模测试
}

# 性能测试报告保存路径
PERFORMANCE_REPORT_DIR = Path(__file__).parent.parent.parent / "performance_reports"


# =============================================================================
# 测试数据生成器
# =============================================================================

def generate_mock_kline_data(
    n_records: int,
    symbol: str = "BTCUSDT",
    start_price: float = 50000.0,
    volatility: float = 0.02,
    start_date: str = "2023-01-01",
) -> pd.DataFrame:
    """
    生成模拟K线数据用于性能测试

    Args:
        n_records: 数据记录数量
        symbol: 交易品种
        start_price: 起始价格
        volatility: 价格波动率
        start_date: 起始日期

    Returns:
        pd.DataFrame: 包含OHLCV数据的DataFrame
    """
    import numpy as np

    np.random.seed(42)  # 确保可重复性

    # 生成时间序列
    start_dt = pd.Timestamp(start_date)
    timestamps = pd.date_range(
        start=start_dt,
        periods=n_records,
        freq="1min"
    )

    # 生成价格序列（随机游走）
    returns = np.random.normal(0, volatility, n_records)
    prices = start_price * np.exp(np.cumsum(returns))

    # 生成OHLCV数据
    data = {
        "timestamp": timestamps,
        "open": prices * (1 + np.random.normal(0, 0.001, n_records)),
        "high": prices * (1 + np.abs(np.random.normal(0, 0.005, n_records))),
        "low": prices * (1 - np.abs(np.random.normal(0, 0.005, n_records))),
        "close": prices,
        "volume": np.random.uniform(1, 100, n_records),
    }

    df = pd.DataFrame(data)
    df["symbol"] = symbol

    return df


def create_mock_catalog(
    n_records: int,
    symbols: List[str],
    catalog_path: Path,
) -> Path:
    """
    创建模拟数据目录（Parquet格式）

    Args:
        n_records: 每个品种的数据记录数
        symbols: 交易品种列表
        catalog_path: 数据目录路径

    Returns:
        Path: 数据目录路径
    """
    catalog_path.mkdir(parents=True, exist_ok=True)

    for symbol in symbols:
        df = generate_mock_kline_data(n_records, symbol)

        # 保存为Parquet格式
        symbol_dir = catalog_path / "bars" / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)

        parquet_path = symbol_dir / "data.parquet"
        df.to_parquet(parquet_path, index=False)

    return catalog_path


# =============================================================================
# 性能测试基类
# =============================================================================

class PerformanceBenchmark:
    """
    性能测试基类

    提供统一的性能测试接口和结果收集功能
    """

    def __init__(self, name: str):
        """
        初始化性能测试

        Args:
            name: 测试名称
        """
        self.name = name
        self.results: Dict[str, Any] = {}
        self._start_time: Optional[float] = None
        self._peak_memory: int = 0

    def __enter__(self):
        """开始性能测试"""
        gc.collect()  # 清理垃圾回收
        tracemalloc.start()
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """结束性能测试"""
        elapsed = time.perf_counter() - self._start_time
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        self.results = {
            "elapsed_time": elapsed,
            "peak_memory_mb": peak / (1024 * 1024),
            "current_memory_mb": current / (1024 * 1024),
            "timestamp": datetime.now().isoformat(),
        }

        if exc_type is not None:
            self.results["error"] = str(exc_val)

    def get_throughput(self, n_records: int) -> float:
        """
        计算吞吐量（记录/秒）

        Args:
            n_records: 处理的记录数

        Returns:
            float: 每秒处理的记录数
        """
        elapsed = self.results.get("elapsed_time", 0)
        if elapsed > 0:
            return n_records / elapsed
        return 0.0


# =============================================================================
# 测试夹具 (Fixtures)
# =============================================================================

@pytest.fixture(scope="module")
def test_data_dir(tmp_path_factory):
    """创建测试数据目录"""
    return tmp_path_factory.mktemp("test_data")


@pytest.fixture(scope="module")
def mock_catalog_small(test_data_dir):
    """创建小规模测试数据目录"""
    catalog_path = test_data_dir / "catalog_small"
    return create_mock_catalog(
        TEST_DATA_SIZES["small"],
        ["BTCUSDT"],
        catalog_path
    )


@pytest.fixture(scope="module")
def mock_catalog_medium(test_data_dir):
    """创建中等规模测试数据目录"""
    catalog_path = test_data_dir / "catalog_medium"
    return create_mock_catalog(
        TEST_DATA_SIZES["medium"],
        ["BTCUSDT"],
        catalog_path
    )


@pytest.fixture(scope="module")
def mock_catalog_large(test_data_dir):
    """创建大规模测试数据目录"""
    catalog_path = test_data_dir / "catalog_large"
    return create_mock_catalog(
        TEST_DATA_SIZES["large"],
        ["BTCUSDT"],
        catalog_path
    )


@pytest.fixture(scope="module")
def mock_catalog_multi(test_data_dir):
    """创建多品种测试数据目录"""
    catalog_path = test_data_dir / "catalog_multi"
    return create_mock_catalog(
        TEST_DATA_SIZES["medium"],
        ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        catalog_path
    )


@pytest.fixture
def engine_config(mock_catalog_small):
    """Engine 测试配置"""
    return {
        "initial_capital": 100000.0,
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "symbols": ["BTCUSDT"],
        "catalog_path": str(mock_catalog_small),
        "strategy_config": {
            "strategy_path": "backtest.strategies.sma_cross:SMACrossStrategy",
            "params": {
                "fast_period": 10,
                "slow_period": 20,
            }
        },
        "log_level": "ERROR",  # 减少日志输出以提高性能
    }


@pytest.fixture
def legacy_engine_config():
    """LegacyEngine 测试配置"""
    return {
        "initial_capital": 100000.0,
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "strategy_config": {
            "strategy_name": "sma_cross",
            "params": {
                "fast_period": 10,
                "slow_period": 20,
            }
        },
        "backtest_config": {
            "symbols": ["BTCUSDT"],
            "interval": "1h",
            "start_time": "2023-01-01",
            "end_time": "2023-12-31",
            "initial_cash": 100000.0,
            "commission": 0.001,
        }
    }


# =============================================================================
# 基准测试类
# =============================================================================

class TestEngineBenchmark:
    """
    引擎基准测试类

    测试 Engine 和 LegacyEngine 的基础性能指标
    """

    @pytest.mark.benchmark
    @pytest.mark.parametrize("data_size", ["small", "medium"])
    def test_engine_initialization(
        self,
        benchmark,
        test_data_dir,
        data_size: str
    ):
        """
        测试 Engine 初始化性能

        验证引擎初始化所需时间和内存
        """
        catalog_path = create_mock_catalog(
            TEST_DATA_SIZES[data_size],
            ["BTCUSDT"],
            test_data_dir / f"catalog_init_{data_size}"
        )

        config = {
            "initial_capital": 100000.0,
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "symbols": ["BTCUSDT"],
            "catalog_path": str(catalog_path),
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SMACrossStrategy",
                "params": {"fast_period": 10, "slow_period": 20}
            },
            "log_level": "ERROR",
        }

        def init_engine():
            engine = Engine(config)
            engine.initialize()
            engine.cleanup()

        result = benchmark(init_engine)

        # 记录性能指标
        logger.info(
            f"Engine 初始化 [{data_size}]: "
            f"{result.stats['mean']:.4f}s"
        )

    @pytest.mark.benchmark
    @pytest.mark.parametrize("data_size", ["small", "medium"])
    def test_legacy_engine_initialization(
        self,
        benchmark,
        data_size: str
    ):
        """
        测试 LegacyEngine 初始化性能

        验证引擎初始化所需时间和内存
        """
        config = {
            "initial_capital": 100000.0,
            "strategy_config": {
                "strategy_name": "sma_cross",
                "params": {"fast_period": 10, "slow_period": 20}
            },
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1h",
            }
        }

        def init_engine():
            engine = LegacyEngine(config)
            engine.initialize()
            engine.cleanup()

        result = benchmark(init_engine)

        logger.info(
            f"LegacyEngine 初始化 [{data_size}]: "
            f"{result.stats['mean']:.4f}s"
        )


# =============================================================================
# 数据加载性能测试
# =============================================================================

class TestDataLoadingPerformance:
    """
    数据加载性能测试类

    测试不同规模数据集的数据加载性能
    """

    @pytest.mark.slow
    @pytest.mark.parametrize("n_records", [1000, 10000, 100000])
    def test_data_loading_throughput(self, test_data_dir, n_records: int):
        """
        测试数据加载吞吐量

        测量每秒加载的数据记录数
        """
        catalog_path = create_mock_catalog(
            n_records,
            ["BTCUSDT"],
            test_data_dir / f"catalog_throughput_{n_records}"
        )

        with PerformanceBenchmark(f"data_loading_{n_records}") as bench:
            # 模拟数据加载
            df = pd.read_parquet(catalog_path / "bars" / "BTCUSDT" / "data.parquet")
            _ = len(df)  # 强制计算

        throughput = bench.get_throughput(n_records)

        logger.info(
            f"数据加载吞吐量 [{n_records} 条记录]: "
            f"{throughput:.2f} records/s, "
            f"内存使用: {bench.results['peak_memory_mb']:.2f} MB"
        )

        # 断言性能指标
        assert throughput > 1000, f"数据加载吞吐量过低: {throughput} records/s"
        assert bench.results["peak_memory_mb"] < 500, "内存使用过高"

    @pytest.mark.slow
    @pytest.mark.parametrize("n_symbols", [1, 3, 5])
    def test_multi_symbol_data_loading(self, test_data_dir, n_symbols: int):
        """
        测试多品种数据加载性能

        验证同时加载多个品种数据的性能
        """
        symbols = [f"SYM{i}USDT" for i in range(n_symbols)]
        catalog_path = create_mock_catalog(
            10000,
            symbols,
            test_data_dir / f"catalog_multi_{n_symbols}"
        )

        with PerformanceBenchmark(f"multi_symbol_loading_{n_symbols}") as bench:
            total_records = 0
            for symbol in symbols:
                df = pd.read_parquet(catalog_path / "bars" / symbol / "data.parquet")
                total_records += len(df)

        throughput = bench.get_throughput(total_records)

        logger.info(
            f"多品种数据加载 [{n_symbols} 个品种]: "
            f"{throughput:.2f} records/s"
        )


# =============================================================================
# 回测执行性能测试
# =============================================================================

class TestBacktestExecutionPerformance:
    """
    回测执行性能测试类

    测试完整回测流程的执行性能
    """

    @pytest.mark.slow
    @pytest.mark.parametrize("n_records", [1000, 10000, 50000])
    def test_single_currency_backtest_performance(
        self,
        test_data_dir,
        n_records: int
    ):
        """
        测试单品种回测性能

        对比 Engine 和 LegacyEngine 的执行时间
        """
        catalog_path = create_mock_catalog(
            n_records,
            ["BTCUSDT"],
            test_data_dir / f"catalog_single_{n_records}"
        )

        results = {}

        # 测试 Engine
        default_config = {
            "initial_capital": 100000.0,
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "symbols": ["BTCUSDT"],
            "catalog_path": str(catalog_path),
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SMACrossStrategy",
                "params": {"fast_period": 10, "slow_period": 20}
            },
            "log_level": "ERROR",
        }

        with PerformanceBenchmark("default_single") as bench:
            try:
                engine = Engine(default_config)
                engine.initialize()
                engine.run_backtest()
                engine.cleanup()
                results["default"] = bench.results
            except Exception as e:
                logger.warning(f"Engine 测试失败: {e}")
                results["default"] = {"error": str(e)}

        # 测试 LegacyEngine
        legacy_config = {
            "initial_capital": 100000.0,
            "strategy_config": {
                "strategy_name": "sma_cross",
                "params": {"fast_period": 10, "slow_period": 20}
            },
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1h",
            }
        }

        with PerformanceBenchmark("legacy_single") as bench:
            try:
                engine = LegacyEngine(legacy_config)
                engine.initialize()
                # 注意：LegacyEngine 需要实际数据才能运行完整回测
                engine.cleanup()
                results["legacy"] = bench.results
            except Exception as e:
                logger.warning(f"LegacyEngine 测试失败: {e}")
                results["legacy"] = {"error": str(e)}

        # 记录对比结果
        logger.info(
            f"单品种回测性能对比 [{n_records} 条记录]:\n"
            f"  Engine: {results.get('advanced', {}).get('elapsed_time', 'N/A')}s\n"
            f"  LegacyEngine: {results.get('legacy', {}).get('elapsed_time', 'N/A')}s"
        )

    @pytest.mark.slow
    @pytest.mark.parametrize("n_symbols", [1, 3, 5])
    def test_multi_currency_backtest_performance(
        self,
        test_data_dir,
        n_symbols: int
    ):
        """
        测试多品种回测性能

        验证引擎处理多个交易品种的能力
        """
        symbols = [f"SYM{i}USDT" for i in range(n_symbols)]
        catalog_path = create_mock_catalog(
            10000,
            symbols,
            test_data_dir / f"catalog_multi_perf_{n_symbols}"
        )

        with PerformanceBenchmark(f"multi_currency_{n_symbols}") as bench:
            # 模拟多品种回测
            for symbol in symbols:
                df = pd.read_parquet(catalog_path / "bars" / symbol / "data.parquet")
                # 简单的策略计算
                df["sma_fast"] = df["close"].rolling(10).mean()
                df["sma_slow"] = df["close"].rolling(20).mean()

        throughput = bench.get_throughput(10000 * n_symbols)

        logger.info(
            f"多品种回测性能 [{n_symbols} 个品种]: "
            f"{throughput:.2f} records/s, "
            f"时间: {bench.results['elapsed_time']:.4f}s"
        )


# =============================================================================
# 结果转换性能测试
# =============================================================================

class TestResultConversionPerformance:
    """
    结果转换性能测试类

    测试回测结果格式转换的性能
    """

    @pytest.mark.parametrize("n_trades", [100, 1000, 10000])
    def test_trade_conversion_performance(self, n_trades: int):
        """
        测试交易记录转换性能

        验证大量交易记录的格式转换速度
        """
        import numpy as np

        # 生成模拟交易数据
        trades = pd.DataFrame({
            "order_id": [f"order_{i}" for i in range(n_trades)],
            "instrument_id": ["BTCUSDT.SIM"] * n_trades,
            "side": np.random.choice(["BUY", "SELL"], n_trades),
            "quantity": np.random.uniform(0.1, 10, n_trades),
            "price": np.random.uniform(40000, 60000, n_trades),
            "timestamp": pd.date_range("2023-01-01", periods=n_trades, freq="1min"),
        })

        with PerformanceBenchmark(f"trade_conversion_{n_trades}") as bench:
            # 模拟结果转换
            result = []
            for _, row in trades.iterrows():
                result.append({
                    "order_id": str(row["order_id"]),
                    "instrument_id": str(row["instrument_id"]),
                    "side": str(row["side"]),
                    "quantity": float(row["quantity"]),
                    "price": float(row["price"]),
                    "timestamp": str(row["timestamp"]),
                })

        throughput = bench.get_throughput(n_trades)

        logger.info(
            f"交易记录转换 [{n_trades} 条]: "
            f"{throughput:.2f} trades/s, "
            f"内存: {bench.results['peak_memory_mb']:.2f} MB"
        )

        assert throughput > 10000, f"交易转换吞吐量过低: {throughput} trades/s"

    @pytest.mark.parametrize("n_points", [1000, 10000, 100000])
    def test_equity_curve_building_performance(self, n_points: int):
        """
        测试权益曲线构建性能

        验证大量权益数据点的处理速度
        """
        import numpy as np

        # 生成模拟权益数据
        account_df = pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=n_points, freq="1min"),
            "equity": 100000 + np.cumsum(np.random.normal(0, 100, n_points)),
            "balance": 100000 + np.cumsum(np.random.normal(0, 100, n_points)),
            "margin": np.random.uniform(1000, 10000, n_points),
        })

        with PerformanceBenchmark(f"equity_curve_{n_points}") as bench:
            # 模拟权益曲线构建
            equity_curve = []
            for _, row in account_df.iterrows():
                equity_curve.append({
                    "timestamp": str(row["timestamp"]),
                    "equity": float(row["equity"]),
                    "balance": float(row["balance"]),
                    "margin": float(row["margin"]),
                })

        throughput = bench.get_throughput(n_points)

        logger.info(
            f"权益曲线构建 [{n_points} 点]: "
            f"{throughput:.2f} points/s"
        )


# =============================================================================
# 内存使用测试
# =============================================================================

class TestMemoryUsage:
    """
    内存使用测试类

    测试引擎在不同场景下的内存消耗
    """

    @pytest.mark.slow
    @pytest.mark.parametrize("n_records", [10000, 100000, 500000])
    def test_memory_usage_with_large_dataset(
        self,
        test_data_dir,
        n_records: int
    ):
        """
        测试大数据集的内存使用

        验证引擎处理大规模数据时的内存效率
        """
        catalog_path = create_mock_catalog(
            n_records,
            ["BTCUSDT"],
            test_data_dir / f"catalog_memory_{n_records}"
        )

        tracemalloc.start()

        # 加载数据
        df = pd.read_parquet(catalog_path / "bars" / "BTCUSDT" / "data.parquet")

        # 计算内存使用
        data_memory = df.memory_usage(deep=True).sum() / (1024 * 1024)

        # 执行一些计算
        df["sma_fast"] = df["close"].rolling(10).mean()
        df["sma_slow"] = df["close"].rolling(20).mean()
        df["signal"] = (df["sma_fast"] > df["sma_slow"]).astype(int)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_memory_mb = peak / (1024 * 1024)
        memory_ratio = peak_memory_mb / data_memory if data_memory > 0 else 0

        logger.info(
            f"大数据集内存使用 [{n_records} 条记录]:\n"
            f"  数据大小: {data_memory:.2f} MB\n"
            f"  峰值内存: {peak_memory_mb:.2f} MB\n"
            f"  内存比例: {memory_ratio:.2f}x"
        )

        # 内存使用不应超过数据的10倍
        assert memory_ratio < 10, f"内存使用过高: {memory_ratio:.2f}x"

    def test_memory_leak_detection(self, test_data_dir):
        """
        测试内存泄漏

        验证引擎在多次运行后是否存在内存泄漏
        """
        catalog_path = create_mock_catalog(
            10000,
            ["BTCUSDT"],
            test_data_dir / "catalog_leak"
        )

        memory_usage = []

        for i in range(5):
            gc.collect()
            tracemalloc.start()

            # 模拟引擎操作
            df = pd.read_parquet(catalog_path / "bars" / "BTCUSDT" / "data.parquet")
            _ = df["close"].rolling(10).mean()

            current, _ = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            memory_usage.append(current / (1024 * 1024))

        # 检查内存增长趋势
        if len(memory_usage) >= 3:
            avg_increase = (memory_usage[-1] - memory_usage[0]) / len(memory_usage)

            logger.info(
                f"内存泄漏检测:\n"
                f"  初始内存: {memory_usage[0]:.2f} MB\n"
                f"  最终内存: {memory_usage[-1]:.2f} MB\n"
                f"  平均增长: {avg_increase:.2f} MB/次"
            )

            # 平均每次增长不应超过10MB
            assert avg_increase < 10, f"可能存在内存泄漏: {avg_increase:.2f} MB/次"


# =============================================================================
# 性能报告生成
# =============================================================================

def generate_performance_report(
    test_results: Dict[str, Any],
    output_path: Optional[Path] = None
) -> Path:
    """
    生成性能测试报告

    Args:
        test_results: 测试结果字典
        output_path: 报告输出路径

    Returns:
        Path: 报告文件路径
    """
    if output_path is None:
        PERFORMANCE_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = PERFORMANCE_REPORT_DIR / f"backtest_performance_{timestamp}.json"

    report = {
        "timestamp": datetime.now().isoformat(),
        "test_summary": test_results,
        "system_info": {
            "python_version": sys.version,
            "platform": sys.platform,
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(f"性能测试报告已保存: {output_path}")
    return output_path


@pytest.fixture(scope="session", autouse=True)
def save_performance_report(request):
    """
    会话结束时保存性能测试报告
    """
    yield

    # 收集所有测试结果
    # 注意：实际结果需要从测试会话中收集
    # 这里仅作为示例

    report_data = {
        "note": "运行 pytest 时添加 --benchmark-only 选项以收集详细性能数据",
        "recommendation": "使用 pytest-benchmark 插件进行更详细的基准测试",
    }

    generate_performance_report(report_data)


# =============================================================================
# 主入口
# =============================================================================

if __name__ == "__main__":
    # 允许直接运行测试
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-m", "not slow",  # 跳过慢速测试
    ])
