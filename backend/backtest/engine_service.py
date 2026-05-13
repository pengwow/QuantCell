"""
回测引擎服务模块

封装事件驱动回测引擎的初始化、数据加载、策略加载和执行流程。
将原本分散在 cli.py 和 service.py 中的引擎操作逻辑统一到此模块。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
from utils.logger import get_logger, LogType


# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class EventDrivenBacktestService:
    """
    事件驱动回测引擎服务
    
    封装事件驱动引擎的完整生命周期管理：
    1. 数据加载（通过BacktestDataProvider）
    2. 引擎初始化
    3. Instrument和BarType创建
    4. 数据转换和加载到引擎
    5. 策略加载和实例化
    6. 回测执行
    7. 结果格式化
    
    使用示例：
        from backtest.data_provider import BacktestDataProvider
        from backtest.engine_service import EventDrivenBacktestService
        
        provider = BacktestDataProvider()
        service = EventDrivenBacktestService(provider)
        
        results = service.run_backtest(
            strategy_name="sma_cross_nautilus",
            strategy_params={"fast_period": 10},
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            engine_config={"initial_capital": 100000}
        )
    """
    
    def __init__(self, data_provider):
        """
        初始化引擎服务
        
        Args:
            data_provider: BacktestDataProvider实例
        """
        self.provider = data_provider
    
    def run_backtest(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        symbols: List[str],
        timeframes: List[str],
        engine_config: Optional[Dict] = None,
        show_progress: bool = False
    ) -> Dict:
        """
        执行完整的事件驱动回测流程
        
        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            symbols: 品种列表
            timeframes: 时间周期列表
            engine_config: 引擎配置（可选）
            show_progress: 是否显示进度
            
        Returns:
            dict: 格式化的回测结果
        """
        logger.info(f"[EventDrivenBacktestService] 开始执行回测: {strategy_name}")
        
        # 解析默认配置
        init_cash = (engine_config or {}).get("initial_capital", 10000)
        base_currency = (engine_config or {}).get("base_currency", "USDT")
        leverage = (engine_config or {}).get("leverage", 1.0)
        time_range = (engine_config or {}).get("time_range")
        
        # 1. 加载数据
        if show_progress:
            print("\n[1/5] 正在加载数据...")
        
        data_dict, _ = self.provider.load_multiple(
            symbols=symbols,
            timeframes=timeframes,
            candle_type="spot",
            time_range=time_range,
            auto_download=False,
            show_progress=show_progress
        )
        
        if not data_dict:
            raise ValueError("没有成功加载任何数据，回测无法继续")
        
        # 2. 初始化引擎
        if show_progress:
            print("[2/5] 正在初始化引擎...")
        
        engine = self._initialize_engine(
            engine_config=engine_config,
            strategy_name=strategy_name,
            symbols=symbols,
            timeframes=timeframes,
            data_dict=data_dict,
            init_cash=init_cash
        )
        
        # 3. 加载数据到引擎
        if show_progress:
            print("[3/5] 正在加载数据到引擎...")
        
        instruments, bar_types = self._load_data_to_engine(
            engine=engine,
            data_dict=data_dict,
            symbols=symbols,
            timeframes=timeframes,
            base_currency=base_currency,
            leverage=leverage,
            init_cash=init_cash
        )
        
        # 4. 加载策略
        if show_progress:
            print(f"[4/5] 正在加载策略: {strategy_name}...")
        
        from backtest.strategy_loader_service import StrategyLoaderService
        
        strategy = StrategyLoaderService.load_event_strategy_multi(
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            bar_types=bar_types,
            instruments=instruments
        )
        
        if strategy is None:
            raise ValueError(f"无法加载策略: {strategy_name}")
        
        engine.add_strategy(strategy)
        
        # 5. 执行回测
        if show_progress:
            print("[5/5] 正在执行回测...")
        
        results = engine.run_backtest()
        
        # 6. 格式化结果
        formatted_results = self._format_results(
            results=results,
            symbols=symbols,
            timeframe=timeframes[0] if timeframes else "1h",
            strategy_name=strategy_name,
            instruments=instruments
        )
        
        # 清理资源
        engine.cleanup()
        
        logger.info(f"[EventDrivenBacktestService] 回测完成")
        
        return formatted_results
    
    def _initialize_engine(
        self,
        engine_config: Optional[Dict],
        strategy_name: str,
        symbols: List[str],
        timeframes: List[str],
        data_dict: Dict[str, pd.DataFrame],
        init_cash: float
    ):
        """
        初始化事件驱动引擎
        
        Args:
            engine_config: 引擎配置字典
            strategy_name: 策略名称
            symbols: 品种列表
            timeframes: 时间周期列表
            data_dict: 已加载的数据字典
            init_cash: 初始资金
            
        Returns:
            EventDrivenBacktestEngine: 已初始化的引擎实例
        """
        try:
            from backtest.engines.event_engine import EventDrivenBacktestEngine
            
            config = engine_config or {}
            time_range = config.get("time_range")
            
            # 解析时间范围
            if time_range:
                from utils.validation import parse_time_range
                start_dt, end_dt = parse_time_range(time_range)
                start_date = start_dt.strftime('%Y-%m-%d') if start_dt else '2023-01-01'
                end_date = end_dt.strftime('%Y-%m-%d') if end_dt else '2023-12-31'
            else:
                first_key = list(data_dict.keys())[0]
                first_df = data_dict[first_key]
                if len(first_df) > 0:
                    first_idx = first_df.index[0]
                    last_idx = first_df.index[-1]
                    start_date = str(first_idx)[:10] if first_idx is not None else '2023-01-01'
                    end_date = str(last_idx)[:10] if last_idx is not None else '2023-12-31'
                else:
                    start_date = '2023-01-01'
                    end_date = '2023-12-31'
            
            full_config = {
                "trader_id": f"BACKTEST-{strategy_name.upper()}",
                "log_level": config.get("log_level", "INFO"),
                "initial_capital": init_cash,
                "start_date": start_date,
                "end_date": end_date,
            }
            
            engine = EventDrivenBacktestEngine(full_config)
            engine.initialize()
            
            logger.info(f"[EventDrivenBacktestService] 引擎初始化完成")
            return engine
            
        except Exception as e:
            logger.error(f"[EventDrivenBacktestService] 引擎初始化失败: {e}")
            raise
    
    def _load_data_to_engine(
        self,
        engine,
        data_dict: Dict[str, pd.DataFrame],
        symbols: List[str],
        timeframes: List[str],
        base_currency: str,
        leverage: float,
        init_cash: float
    ):
        """
        加载数据到引擎并创建Instrument和BarType
        
        Args:
            engine: 已初始化的引擎实例
            data_dict: 数据字典
            symbols: 品种列表
            timeframes: 时间周期列表
            base_currency: 基础货币
            leverage: 杠杆倍数
            init_cash: 初始资金
            
        Returns:
            tuple: (instruments字典, bar_types字典)
        """
        from decimal import Decimal
        from nautilus_trader.model.enums import AccountType, OmsType
        from nautilus_trader.test_kit.providers import TestInstrumentProvider
        from nautilus_trader.model.data import BarType
        from nautilus_trader.persistence.wranglers import BarDataWrangler
        from backtest.result_formatter_service import ResultFormatterService
        
        instruments = {}
        bar_types = {}
        all_bars = []
        
        first_symbol = symbols[0]
        first_timeframe = timeframes[0]
        
        # 创建第一个品种以获取venue
        try:
            if first_symbol == 'BTCUSDT' or first_symbol == 'BTC/USDT':
                first_instrument = TestInstrumentProvider.btcusdt_binance()
            elif first_symbol == 'ETHUSDT' or first_symbol == 'ETH/USDT':
                first_instrument = TestInstrumentProvider.ethusdt_binance()
            else:
                first_instrument = TestInstrumentProvider.btcusdt_binance()
            instrument_venue = str(first_instrument.id.venue)
        except Exception as e:
            logger.error(f"创建交易品种失败: {e}")
            first_instrument = TestInstrumentProvider.btcusdt_binance()
            instrument_venue = "BINANCE"
        
        # 添加交易所
        engine.add_venue(
            venue_name=instrument_venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            starting_capital=init_cash,
            base_currency=base_currency,
            default_leverage=Decimal(str(leverage)),
        )
        
        # 为每个品种创建instrument并加载数据
        for symbol in symbols:
            timeframe = timeframes[0]
            key = f"{symbol}_{timeframe}"
            
            if key not in data_dict:
                logger.warning(f"跳过 {key}，数据未加载")
                continue
            
            df = data_dict[key]
            
            # 创建交易品种
            try:
                if symbol == 'BTCUSDT' or symbol == 'BTC/USDT':
                    instrument = TestInstrumentProvider.btcusdt_binance()
                elif symbol == 'ETHUSDT' or symbol == 'ETH/USDT':
                    instrument = TestInstrumentProvider.ethusdt_binance()
                else:
                    instrument = TestInstrumentProvider.btcusdt_binance()
            except Exception as e:
                logger.error(f"创建交易品种失败: {e}，使用默认品种")
                instrument = TestInstrumentProvider.btcusdt_binance()
            
            engine.add_instrument(instrument)
            instruments[symbol] = instrument
            
            # 转换数据格式
            df = df.copy()
            df.columns = [col.lower() for col in df.columns]
            
            if not isinstance(df.index, pd.DatetimeIndex):
                if 'timestamp' in df.columns:
                    df = df.set_index('timestamp')
                df.index = pd.to_datetime(df.index, utc=True)
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = df[col].astype('float64')
            
            # 创建BarType
            event_timeframe = ResultFormatterService.convert_timeframe_to_event(timeframe)
            bar_type_str = f"{instrument.id}-{event_timeframe}-LAST-EXTERNAL"
            bar_type = BarType.from_str(bar_type_str)
            bar_types[symbol] = bar_type
            
            # 转换并加载数据
            wrangler = BarDataWrangler(bar_type, instrument)
            bars = wrangler.process(df)
            
            if hasattr(engine, 'engine') and engine.engine is not None:
                engine.engine.add_data(bars)
            engine._data.extend(bars)
            all_bars.extend(bars)
            
            logger.info(f"成功加载 {symbol} 的 {len(bars)} 条K线数据")
        
        logger.info(f"共加载 {len(instruments)} 个品种，{len(all_bars)} 条K线数据")
        
        return instruments, bar_types
    
    def _format_results(
        self,
        results: dict,
        symbols: List[str],
        timeframe: str,
        strategy_name: str,
        instruments: dict
    ) -> dict:
        """
        格式化回测结果
        
        Args:
            results: 原始回测结果
            symbols: 品种列表
            timeframe: 时间周期
            strategy_name: 策略名称
            instruments: 品种映射
            
        Returns:
            dict: 格式化后的结果
        """
        from backtest.result_formatter_service import ResultFormatterService
        
        if len(symbols) == 1:
            return ResultFormatterService.format_event_results(
                results=results,
                symbol=symbols[0],
                timeframe=timeframe,
                strategy_name=strategy_name
            )
        else:
            return ResultFormatterService.format_event_results_multi(
                results=results,
                symbols=symbols,
                timeframe=timeframe,
                strategy_name=strategy_name,
                instruments=instruments
            )


class DefaultBacktestService:
    """
    默认引擎回测服务（使用backtesting.py库）
    
    用于非事件驱动的传统回测场景。
    """
    
    def __init__(self, data_provider):
        """
        初始化默认引擎服务
        
        Args:
            data_provider: BacktestDataProvider实例
        """
        self.provider = data_provider
    
    def run_backtest(
        self,
        strategy,
        data_dict: Dict[str, pd.DataFrame],
        config: Dict,
        show_progress: bool = True
    ) -> Dict:
        """
        执行默认引擎回测
        
        Args:
            strategy: 策略实例
            data_dict: 数据字典
            config: 回测配置
            show_progress: 是否显示进度
            
        Returns:
            dict: 回测结果
        """
        from backtesting import Backtest
        import pandas as pd
        
        if show_progress:
            print("正在执行默认引擎回测...")
        
        # 从data_dict获取第一个品种的数据
        first_key = list(data_dict.keys())[0]
        candles = data_dict[first_key]
        
        initial_cash = config.get("initial_cash", 10000)
        commission = config.get("commission", 0.001)
        
        bt = Backtest(
            candles,
            strategy,
            cash=initial_cash,
            commission=commission,
            exclusive_orders=True
        )
        
        stats = bt.run()
        
        return stats
