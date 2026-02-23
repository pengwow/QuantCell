# -*- coding: utf-8 -*-
"""
NautilusTrader 回测引擎单元测试

测试 NautilusBacktestEngine 的核心功能，包括:
- 引擎初始化
- 添加交易所
- 添加交易品种
- 数据加载
- 策略添加
- 回测执行
- 资源清理

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-23
"""

import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from nautilus_trader.model import Venue
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.trading.strategy import Strategy

from backend.backtest.engines.nautilus_engine import NautilusBacktestEngine
from backend.backtest.engines.base import EngineType


# =============================================================================
# 测试固件 (Fixtures)
# =============================================================================

@pytest.fixture
def engine_config():
    """返回测试用的引擎配置"""
    return {
        "trader_id": "TEST-001",
        "log_level": "DEBUG",
        "initial_capital": 50000.0,
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
    }


@pytest.fixture
def mock_engine(engine_config):
    """返回一个已初始化的模拟引擎实例"""
    with patch("backend.backtest.engines.nautilus_engine.BacktestEngine") as mock_bt_engine:
        # 创建引擎实例
        engine = NautilusBacktestEngine(engine_config)
        # 模拟引擎配置
        engine._engine_config = MagicMock()
        # 模拟底层引擎
        engine._engine = mock_bt_engine.return_value
        engine._is_initialized = True
        yield engine


@pytest.fixture
def sample_instrument():
    """返回一个模拟的交易品种"""
    instrument = MagicMock(spec=CurrencyPair)
    instrument.id = "BTCUSDT.BINANCE"
    return instrument


@pytest.fixture
def sample_bar_type():
    """返回一个模拟的 BarType"""
    bar_type = MagicMock(spec=BarType)
    bar_type.__str__ = Mock(return_value="BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL")
    return bar_type


@pytest.fixture
def sample_strategy():
    """返回一个模拟的策略"""
    strategy = MagicMock(spec=Strategy)
    strategy.id = "TEST-STRATEGY-001"
    return strategy


@pytest.fixture
def sample_csv_data():
    """返回示例 CSV 数据"""
    return pd.DataFrame({
        "timestamp": pd.date_range("2023-01-01", periods=100, freq="1min"),
        "open": [50000 + i * 10 for i in range(100)],
        "high": [50100 + i * 10 for i in range(100)],
        "low": [49900 + i * 10 for i in range(100)],
        "close": [50050 + i * 10 for i in range(100)],
        "volume": [100 + i for i in range(100)],
    })


# =============================================================================
# 引擎初始化测试
# =============================================================================

class TestNautilusEngineInitialization:
    """测试 NautilusBacktestEngine 初始化相关功能"""

    def test_engine_creation(self, engine_config):
        """测试引擎实例创建"""
        engine = NautilusBacktestEngine(engine_config)

        assert engine is not None
        assert engine._config == engine_config
        assert engine._engine is None
        assert engine._is_initialized is False

    def test_engine_type_property(self, engine_config):
        """测试引擎类型属性"""
        engine = NautilusBacktestEngine(engine_config)

        assert engine.engine_type == EngineType.EVENT_DRIVEN

    def test_engine_property_uninitialized(self, engine_config):
        """测试未初始化时 engine 属性返回 None"""
        engine = NautilusBacktestEngine(engine_config)

        assert engine.engine is None

    def test_initialize_success(self, engine_config):
        """测试引擎初始化成功"""
        with patch("backend.backtest.engines.nautilus_engine.BacktestEngine") as mock_bt_engine:
            engine = NautilusBacktestEngine(engine_config)
            engine.initialize()

            assert engine._is_initialized is True
            assert engine._engine is not None
            mock_bt_engine.assert_called_once()

    def test_initialize_with_invalid_config(self):
        """测试无效配置时的初始化行为"""
        # 使用缺少必需参数的配置
        invalid_config = {"trader_id": "TEST"}  # 缺少 initial_capital, start_date, end_date
        engine = NautilusBacktestEngine(invalid_config)

        # 无效配置应该抛出异常
        with patch("backend.backtest.engines.nautilus_engine.BacktestEngine"):
            with pytest.raises(RuntimeError, match="引擎初始化失败"):
                engine.initialize()

    def test_initialize_raises_on_error(self, engine_config):
        """测试初始化失败时抛出异常"""
        with patch("backend.backtest.engines.nautilus_engine.BacktestEngine") as mock_bt_engine:
            mock_bt_engine.side_effect = Exception("初始化失败")

            engine = NautilusBacktestEngine(engine_config)

            with pytest.raises(RuntimeError, match="引擎初始化失败"):
                engine.initialize()


# =============================================================================
# 添加交易所测试
# =============================================================================

class TestNautilusEngineAddVenue:
    """测试添加交易所功能"""

    def test_add_venue_success(self, mock_engine):
        """测试成功添加交易所"""
        venue = mock_engine.add_venue(
            venue_name="TEST",
            starting_capital=100000.0,
            base_currency="USD",
        )

        assert venue is not None
        assert "TEST" in mock_engine._venues
        mock_engine._engine.add_venue.assert_called_once()

    def test_add_venue_without_initialization(self, engine_config):
        """测试未初始化时添加交易所抛出异常"""
        engine = NautilusBacktestEngine(engine_config)

        with pytest.raises(RuntimeError, match="引擎未初始化"):
            engine.add_venue("TEST")

    def test_add_venue_with_empty_name(self, mock_engine):
        """测试添加空名称交易所抛出异常"""
        with pytest.raises(ValueError, match="交易所名称不能为空"):
            mock_engine.add_venue("")

    def test_add_venue_with_custom_params(self, mock_engine):
        """测试使用自定义参数添加交易所"""
        venue = mock_engine.add_venue(
            venue_name="BINANCE",
            oms_type=OmsType.HEDGING,
            account_type=AccountType.CASH,
            starting_capital=50000.0,
            base_currency="USDT",
            default_leverage=Decimal("2"),
        )

        assert venue is not None
        call_kwargs = mock_engine._engine.add_venue.call_args.kwargs
        assert call_kwargs["oms_type"] == OmsType.HEDGING
        assert call_kwargs["account_type"] == AccountType.CASH

    def test_add_venue_error_handling(self, mock_engine):
        """测试添加交易所错误处理"""
        mock_engine._engine.add_venue.side_effect = Exception("添加失败")

        with pytest.raises(RuntimeError, match="添加交易所失败"):
            mock_engine.add_venue("TEST")

    def test_get_venue(self, mock_engine):
        """测试获取已添加的交易所"""
        mock_engine.add_venue("TEST")

        venue = mock_engine.get_venue("TEST")
        assert venue is not None

    def test_get_nonexistent_venue(self, mock_engine):
        """测试获取不存在的交易所"""
        venue = mock_engine.get_venue("NONEXISTENT")
        assert venue is None


# =============================================================================
# 添加交易品种测试
# =============================================================================

class TestNautilusEngineAddInstrument:
    """测试添加交易品种功能"""

    def test_add_instrument_success(self, mock_engine, sample_instrument):
        """测试成功添加交易品种"""
        mock_engine.add_instrument(sample_instrument)

        assert str(sample_instrument.id) in mock_engine._instruments
        mock_engine._engine.add_instrument.assert_called_once_with(sample_instrument)

    def test_add_instrument_without_initialization(self, engine_config, sample_instrument):
        """测试未初始化时添加交易品种抛出异常"""
        engine = NautilusBacktestEngine(engine_config)

        with pytest.raises(RuntimeError, match="引擎未初始化"):
            engine.add_instrument(sample_instrument)

    def test_add_instrument_with_none(self, mock_engine):
        """测试添加 None 交易品种抛出异常"""
        with pytest.raises(ValueError, match="交易品种不能为空"):
            mock_engine.add_instrument(None)

    def test_add_instrument_error_handling(self, mock_engine, sample_instrument):
        """测试添加交易品种错误处理"""
        mock_engine._engine.add_instrument.side_effect = Exception("添加失败")

        with pytest.raises(RuntimeError, match="添加交易品种失败"):
            mock_engine.add_instrument(sample_instrument)

    def test_get_instrument(self, mock_engine, sample_instrument):
        """测试获取已添加的交易品种"""
        mock_engine.add_instrument(sample_instrument)

        instrument = mock_engine.get_instrument(str(sample_instrument.id))
        assert instrument == sample_instrument

    def test_get_nonexistent_instrument(self, mock_engine):
        """测试获取不存在的交易品种"""
        instrument = mock_engine.get_instrument("NONEXISTENT")
        assert instrument is None


# =============================================================================
# 数据加载测试
# =============================================================================

class TestNautilusEngineLoadData:
    """测试数据加载功能"""

    @patch("backend.backtest.engines.nautilus_engine.BarDataWrangler")
    @patch("backend.backtest.engines.nautilus_engine.pd.read_csv")
    @patch("backend.backtest.engines.nautilus_engine.Path.exists")
    def test_load_data_from_csv_success(
        self, mock_exists, mock_read_csv, mock_wrangler_class, mock_engine, sample_csv_data, sample_bar_type, sample_instrument
    ):
        """测试从 CSV 成功加载数据"""
        mock_exists.return_value = True
        mock_read_csv.return_value = sample_csv_data

        mock_bar = MagicMock(spec=Bar)
        mock_wrangler = MagicMock()
        mock_wrangler.process.return_value = [mock_bar] * 100
        mock_wrangler_class.return_value = mock_wrangler

        bars = mock_engine.load_data_from_csv(
            csv_path="/fake/path/data.csv",
            bar_type=sample_bar_type,
            instrument=sample_instrument,
        )

        assert len(bars) == 100
        mock_engine._engine.add_data.assert_called_once()
        assert mock_engine.get_data_count() == 100

    def test_load_data_from_csv_file_not_found(self, mock_engine, sample_bar_type, sample_instrument):
        """测试加载不存在的 CSV 文件抛出异常"""
        with pytest.raises(FileNotFoundError):
            mock_engine.load_data_from_csv(
                csv_path="/nonexistent/path/data.csv",
                bar_type=sample_bar_type,
                instrument=sample_instrument,
            )

    @patch("backend.backtest.engines.nautilus_engine.BarDataWrangler")
    @patch("backend.backtest.engines.nautilus_engine.pd.read_csv")
    @patch("backend.backtest.engines.nautilus_engine.Path.exists")
    def test_load_data_from_csv_with_column_mapping(
        self, mock_exists, mock_read_csv, mock_wrangler_class, mock_engine, sample_bar_type, sample_instrument
    ):
        """测试使用列名映射加载 CSV"""
        mock_exists.return_value = True
        # 创建带有不同列名的数据
        df = pd.DataFrame({
            "ts": pd.date_range("2023-01-01", periods=10, freq="1min"),
            "o": [50000 + i * 10 for i in range(10)],
            "h": [50100 + i * 10 for i in range(10)],
            "l": [49900 + i * 10 for i in range(10)],
            "c": [50050 + i * 10 for i in range(10)],
            "v": [100 + i for i in range(10)],
        })
        mock_read_csv.return_value = df

        mock_wrangler = MagicMock()
        mock_wrangler.process.return_value = [MagicMock(spec=Bar)] * 10
        mock_wrangler_class.return_value = mock_wrangler

        bars = mock_engine.load_data_from_csv(
            csv_path="/fake/path/data.csv",
            bar_type=sample_bar_type,
            instrument=sample_instrument,
            timestamp_column="ts",
            columns_mapping={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"},
        )

        assert len(bars) == 10

    @patch("backend.backtest.engines.nautilus_engine.BarDataWrangler")
    @patch("backend.backtest.engines.nautilus_engine.pd.read_parquet")
    @patch("backend.backtest.engines.nautilus_engine.Path.exists")
    def test_load_data_from_parquet_success(
        self, mock_exists, mock_read_parquet, mock_wrangler_class, mock_engine, sample_csv_data, sample_bar_type, sample_instrument
    ):
        """测试从 Parquet 成功加载数据"""
        mock_exists.return_value = True
        mock_read_parquet.return_value = sample_csv_data

        mock_wrangler = MagicMock()
        mock_wrangler.process.return_value = [MagicMock(spec=Bar)] * 100
        mock_wrangler_class.return_value = mock_wrangler

        bars = mock_engine.load_data_from_parquet(
            parquet_path="/fake/path/data.parquet",
            bar_type=sample_bar_type,
            instrument=sample_instrument,
        )

        assert len(bars) == 100
        mock_engine._engine.add_data.assert_called_once()

    def test_load_data_without_initialization(self, engine_config, sample_bar_type, sample_instrument):
        """测试未初始化时加载数据抛出异常"""
        engine = NautilusBacktestEngine(engine_config)

        with pytest.raises(RuntimeError, match="引擎未初始化"):
            engine.load_data_from_csv("/fake/path.csv", sample_bar_type, sample_instrument)

    def test_get_bar_type(self, mock_engine, sample_bar_type):
        """测试获取 BarType"""
        bar_type_str = "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL"
        mock_engine._bar_types[bar_type_str] = sample_bar_type

        result = mock_engine.get_bar_type(bar_type_str)
        assert result == sample_bar_type

    def test_get_nonexistent_bar_type(self, mock_engine):
        """测试获取不存在的 BarType"""
        result = mock_engine.get_bar_type("NONEXISTENT")
        assert result is None


# =============================================================================
# 策略添加测试
# =============================================================================

class TestNautilusEngineAddStrategy:
    """测试策略添加功能"""

    def test_add_strategy_success(self, mock_engine, sample_strategy):
        """测试成功添加策略"""
        mock_engine.add_strategy(sample_strategy)

        assert sample_strategy in mock_engine._strategies
        mock_engine._engine.add_strategy.assert_called_once_with(sample_strategy)

    def test_add_strategy_without_initialization(self, engine_config, sample_strategy):
        """测试未初始化时添加策略抛出异常"""
        engine = NautilusBacktestEngine(engine_config)

        with pytest.raises(RuntimeError, match="引擎未初始化"):
            engine.add_strategy(sample_strategy)

    def test_add_strategy_with_none(self, mock_engine):
        """测试添加 None 策略抛出异常"""
        with pytest.raises(ValueError, match="策略不能为空"):
            mock_engine.add_strategy(None)

    def test_add_invalid_strategy_type(self, mock_engine):
        """测试添加无效策略类型抛出异常"""
        with pytest.raises(ValueError, match="策略必须是 Strategy 类的实例"):
            mock_engine.add_strategy("not a strategy")

    def test_add_strategy_error_handling(self, mock_engine, sample_strategy):
        """测试添加策略错误处理"""
        mock_engine._engine.add_strategy.side_effect = Exception("添加失败")

        with pytest.raises(RuntimeError, match="添加策略失败"):
            mock_engine.add_strategy(sample_strategy)

    def test_get_strategies(self, mock_engine, sample_strategy):
        """测试获取策略列表"""
        mock_engine.add_strategy(sample_strategy)

        strategies = mock_engine.get_strategies()
        assert len(strategies) == 1
        assert strategies[0] == sample_strategy

    def test_get_strategies_returns_copy(self, mock_engine, sample_strategy):
        """测试获取策略列表返回副本"""
        mock_engine.add_strategy(sample_strategy)

        strategies = mock_engine.get_strategies()
        strategies.clear()

        # 原始列表不应被修改
        assert len(mock_engine._strategies) == 1


# =============================================================================
# 回测执行测试
# =============================================================================

class TestNautilusEngineRunBacktest:
    """测试回测执行功能"""

    def test_run_backtest_success(self, mock_engine, sample_strategy):
        """测试成功执行回测"""
        # 添加必要的组件
        mock_engine._venues["TEST"] = MagicMock(spec=Venue)
        mock_engine._strategies.append(sample_strategy)
        mock_engine._data.extend([MagicMock(spec=Bar)] * 10)

        # 模拟回测结果
        mock_engine._engine.trader.generate_order_fills_report.return_value = pd.DataFrame({
            "order_id": ["1", "2"],
            "instrument_id": ["BTCUSDT.BINANCE", "BTCUSDT.BINANCE"],
            "side": ["BUY", "SELL"],
            "quantity": [0.1, 0.1],
            "price": [50000, 51000],
            "timestamp": pd.to_datetime(["2023-01-01", "2023-01-02"]),
        })
        mock_engine._engine.trader.generate_positions_report.return_value = pd.DataFrame({
            "position_id": ["1"],
            "instrument_id": ["BTCUSDT.BINANCE"],
            "side": ["LONG"],
            "quantity": [0.1],
            "avg_px_open": [50000],
            "avg_px_close": [51000],
            "realized_pnl": ["100 USD"],
        })
        mock_engine._engine.trader.generate_account_report.return_value = pd.DataFrame({
            "timestamp": pd.to_datetime(["2023-01-01", "2023-01-02"]),
            "balance": [100000, 100100],
            "margin": [0, 0],
            "equity": [100000, 100100],
        })

        results = mock_engine.run_backtest()

        assert results is not None
        assert "trades" in results
        assert "positions" in results
        assert "account" in results
        assert "metrics" in results
        mock_engine._engine.run.assert_called_once()

    def test_run_backtest_without_initialization(self, engine_config):
        """测试未初始化时执行回测抛出异常"""
        engine = NautilusBacktestEngine(engine_config)

        with pytest.raises(RuntimeError, match="引擎未初始化"):
            engine.run_backtest()

    def test_run_backtest_without_strategy(self, mock_engine):
        """测试未添加策略时执行回测抛出异常"""
        with pytest.raises(RuntimeError, match="未添加策略"):
            mock_engine.run_backtest()

    def test_run_backtest_without_data(self, mock_engine, sample_strategy):
        """测试未加载数据时执行回测抛出异常"""
        mock_engine._strategies.append(sample_strategy)

        with pytest.raises(RuntimeError, match="未加载数据"):
            mock_engine.run_backtest()

    def test_run_backtest_error_handling(self, mock_engine, sample_strategy):
        """测试回测执行错误处理"""
        mock_engine._strategies.append(sample_strategy)
        mock_engine._data.extend([MagicMock(spec=Bar)] * 10)
        mock_engine._engine.run.side_effect = Exception("回测失败")

        with pytest.raises(RuntimeError, match="回测执行失败"):
            mock_engine.run_backtest()

    def test_get_results_before_run(self, mock_engine):
        """测试在回测前获取结果抛出异常"""
        with pytest.raises(RuntimeError, match="尚未执行回测"):
            mock_engine.get_results()

    def test_get_results_after_run(self, mock_engine, sample_strategy):
        """测试回测后获取结果"""
        mock_engine._strategies.append(sample_strategy)
        mock_engine._data.extend([MagicMock(spec=Bar)] * 10)

        mock_engine._engine.trader.generate_order_fills_report.return_value = pd.DataFrame()
        mock_engine._engine.trader.generate_positions_report.return_value = pd.DataFrame()

        mock_engine.run_backtest()
        results = mock_engine.get_results()

        assert results is not None


# =============================================================================
# 资源清理测试
# =============================================================================

class TestNautilusEngineCleanup:
    """测试资源清理功能"""

    def test_cleanup_success(self, mock_engine, sample_strategy, sample_instrument):
        """测试成功清理资源"""
        # 添加一些数据
        mock_engine._venues["TEST"] = MagicMock(spec=Venue)
        mock_engine._instruments["BTCUSDT.BINANCE"] = sample_instrument
        mock_engine._strategies.append(sample_strategy)
        mock_engine._data.extend([MagicMock(spec=Bar)] * 10)

        # 保存 engine 引用以便验证 dispose 被调用
        engine_mock = mock_engine._engine

        mock_engine.cleanup()

        assert mock_engine._engine is None
        assert len(mock_engine._venues) == 0
        assert len(mock_engine._instruments) == 0
        assert len(mock_engine._strategies) == 0
        assert len(mock_engine._data) == 0
        engine_mock.dispose.assert_called_once()

    def test_cleanup_with_error(self, mock_engine):
        """测试清理时出错的情况"""
        mock_engine._engine.dispose.side_effect = Exception("清理失败")

        # 不应抛出异常
        mock_engine.cleanup()

        assert mock_engine._engine is None

    def test_cleanup_without_engine(self, mock_engine):
        """测试没有引擎时的清理"""
        mock_engine._engine = None

        # 不应抛出异常
        mock_engine.cleanup()

        assert mock_engine._is_initialized is False


# =============================================================================
# 结果处理测试
# =============================================================================

class TestNautilusEngineResultsProcessing:
    """测试回测结果处理功能"""

    def test_process_results_with_empty_data(self, mock_engine):
        """测试处理空结果"""
        # 模拟空 DataFrame 而不是 None
        empty_df = pd.DataFrame()
        mock_engine._engine.trader.generate_order_fills_report.return_value = empty_df
        mock_engine._engine.trader.generate_positions_report.return_value = empty_df
        mock_engine._venues["TEST"] = MagicMock(spec=Venue)
        mock_engine._engine.trader.generate_account_report.return_value = empty_df

        results = mock_engine._process_results()

        # 空数据应该返回包含空列表的结果
        assert "trades" in results
        assert "positions" in results
        assert "account" in results
        assert "metrics" in results
        assert "equity_curve" in results

    def test_convert_orders_to_trades(self, mock_engine):
        """测试订单到交易的转换"""
        orders_df = pd.DataFrame({
            "order_id": ["1", "2"],
            "instrument_id": ["BTCUSDT.BINANCE", "ETHUSDT.BINANCE"],
            "side": ["BUY", "SELL"],
            "quantity": [0.1, 0.2],
            "price": [50000, 3000],
            "timestamp": pd.to_datetime(["2023-01-01", "2023-01-02"]),
        })

        trades = mock_engine._convert_orders_to_trades(orders_df)

        assert len(trades) == 2
        assert trades[0]["order_id"] == "1"
        assert trades[0]["side"] == "BUY"

    def test_convert_orders_to_trades_with_none(self, mock_engine):
        """测试转换 None 订单数据"""
        trades = mock_engine._convert_orders_to_trades(None)
        assert trades == []

    def test_convert_positions(self, mock_engine):
        """测试持仓数据转换"""
        positions_df = pd.DataFrame({
            "position_id": ["1", "2"],
            "instrument_id": ["BTCUSDT.BINANCE", "ETHUSDT.BINANCE"],
            "side": ["LONG", "SHORT"],
            "quantity": [0.1, 0.2],
            "avg_px_open": [50000, 3000],
            "avg_px_close": [51000, 2900],
            "realized_pnl": ["100 USD", "-20 USD"],
        })

        positions = mock_engine._convert_positions(positions_df)

        assert len(positions) == 2
        assert positions[0]["realized_pnl"] == 100.0
        assert positions[1]["realized_pnl"] == -20.0

    def test_convert_positions_with_numeric_pnl(self, mock_engine):
        """测试数值类型 PnL 的转换"""
        positions_df = pd.DataFrame({
            "position_id": ["1"],
            "instrument_id": ["BTCUSDT.BINANCE"],
            "side": ["LONG"],
            "quantity": [0.1],
            "avg_px_open": [50000],
            "avg_px_close": [51000],
            "realized_pnl": [150.0],
        })

        positions = mock_engine._convert_positions(positions_df)

        assert positions[0]["realized_pnl"] == 150.0

    def test_convert_account(self, mock_engine):
        """测试账户数据转换"""
        account_df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2023-01-01", "2023-01-02"]),
            "balance": [100000, 100100],
            "margin": [0, 100],
            "equity": [100000, 100000],
        })

        account = mock_engine._convert_account(account_df)

        assert account["balance"] == 100100.0
        assert account["equity"] == 100000.0

    def test_convert_account_with_none(self, mock_engine):
        """测试转换 None 账户数据"""
        account = mock_engine._convert_account(None)
        assert account == {}

    def test_calculate_metrics(self, mock_engine):
        """测试绩效指标计算"""
        positions_df = pd.DataFrame({
            "realized_pnl": ["100 USD", "-50 USD", "200 USD"],
        })

        metrics = mock_engine._calculate_metrics(positions_df, None)

        assert metrics["total_trades"] == 3
        assert metrics["winning_trades"] == 2
        assert metrics["losing_trades"] == 1
        assert metrics["win_rate"] > 0

    def test_calculate_metrics_with_empty_data(self, mock_engine):
        """测试空数据的绩效指标"""
        metrics = mock_engine._calculate_metrics(None, None)

        assert metrics["total_trades"] == 0
        assert metrics["total_return"] == 0.0

    def test_build_equity_curve(self, mock_engine):
        """测试权益曲线构建"""
        account_df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"]),
            "balance": [100000, 100050, 100100],
            "margin": [0, 0, 0],
            "equity": [100000, 100050, 100100],
        })

        curve = mock_engine._build_equity_curve(account_df)

        assert len(curve) == 3
        assert curve[0]["equity"] == 100000.0

    def test_build_equity_curve_with_none(self, mock_engine):
        """测试构建空权益曲线"""
        curve = mock_engine._build_equity_curve(None)
        assert curve == []


# =============================================================================
# 数据计数测试
# =============================================================================

class TestNautilusEngineDataCount:
    """测试数据计数功能"""

    def test_get_data_count_empty(self, mock_engine):
        """测试空数据计数"""
        assert mock_engine.get_data_count() == 0

    def test_get_data_count_with_data(self, mock_engine):
        """测试有数据时的计数"""
        mock_engine._data.extend([MagicMock(spec=Bar)] * 50)
        assert mock_engine.get_data_count() == 50
