"""
回测引擎服务模块

封装事件驱动回测引擎的初始化、数据加载、策略加载和执行流程。
将原本分散在 cli.py 和 service.py 中的引擎操作逻辑统一到此模块。

所有与 axon-quant 的交互都通过 axon_bridge 适配层进行。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-08-14
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
from utils.logger import get_logger, LogType


# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


def _get_axon_bridge():
    """延迟导入 axon_bridge"""
    import axon_bridge
    return axon_bridge


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
            strategy_name="sma_crossover",
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
            engine_config: 引擎配置（可选），支持 trading_mode: "spot"/"futures"
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
        # 交易模式: spot(现货) / futures(永续合约)
        trading_mode = (engine_config or {}).get("trading_mode", "spot")
        candle_type = "future" if trading_mode == "futures" else "spot"
        
        # 1. 加载数据
        if show_progress:
            print("\n[1/5] 正在加载数据...")
        
        data_dict, _ = self.provider.load_multiple(
            symbols=symbols,
            timeframes=timeframes,
            candle_type=candle_type,
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
            init_cash=init_cash,
            trading_mode=trading_mode,
            time_range=time_range
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
    
    @staticmethod
    def _parse_symbol(symbol: str) -> tuple:
        """
        解析交易对符号，提取基础货币和计价货币

        Args:
            symbol: 交易对符号（如 "BTCUSDT", "BTC/USDT", "BTC-USDT"）

        Returns:
            tuple: (base, quote) 如 ("BTC", "USDT")
        """
        for sep in ['/', '-', '_']:
            if sep in symbol:
                parts = symbol.split(sep)
                return parts[0].upper(), parts[1].upper()
        return symbol[:3].upper(), symbol[3:].upper() if len(symbol) > 3 else (symbol.upper(), "USDT")

    def _load_data_to_engine(
        self,
        engine,
        data_dict: Dict[str, pd.DataFrame],
        symbols: List[str],
        timeframes: List[str],
        base_currency: str,
        leverage: float,
        init_cash: float,
        trading_mode: str = "spot",
        time_range: Optional[str] = None
    ):
        """
        加载数据到引擎并创建交易品种

        根据 trading_mode 使用 axon_bridge 创建现货或永续合约品种，
        合约模式下同时加载资金费率数据用于资金费用结算。

        Args:
            engine: 已初始化的引擎实例
            data_dict: 数据字典
            symbols: 品种列表
            timeframes: 时间周期列表
            base_currency: 基础货币
            leverage: 杠杆倍数
            init_cash: 初始资金
            trading_mode: 交易模式 ("spot" / "futures")
            time_range: 时间范围字符串（用于资金费率筛选）

        Returns:
            tuple: (instruments字典, bar_types字典)
        """
        from decimal import Decimal

        bridge = _get_axon_bridge()

        instruments = {}
        bar_types = {}
        is_futures = trading_mode == "futures"

        # 创建交易所（简单配置）
        engine.add_venue(
            venue_name="BINANCE",
            starting_capital=init_cash,
            base_currency=base_currency,
            default_leverage=Decimal(str(leverage)),
        )

        # 解析资金费率筛选的时间范围
        funding_start = funding_end = None
        if is_futures and time_range:
            try:
                from utils.validation import parse_time_range
                start_dt, end_dt = parse_time_range(time_range)
                funding_start = start_dt.strftime('%Y-%m-%d') if start_dt else None
                funding_end = end_dt.strftime('%Y-%m-%d') if end_dt else None
            except Exception as e:
                logger.warning(f"解析资金费率时间范围失败: {e}")

        # 为每个品种创建 instrument 并加载数据
        for symbol in symbols:
            timeframe = timeframes[0]
            key = f"{symbol}_{timeframe}"

            if key not in data_dict:
                logger.warning(f"跳过 {key}，数据未加载")
                continue

            df = data_dict[key]

            # 根据交易模式创建品种：现货 / 永续合约
            base, quote = self._parse_symbol(symbol)
            if is_futures:
                # 永续合约：U本位结算，合约乘数默认 1（1张=1个base币）
                instrument = bridge.create_swap_instrument(
                    base, quote, settle="usd_margin", contract_size=1.0
                )
            else:
                instrument = bridge.create_spot_instrument(base, quote)
            engine.add_instrument(instrument)
            instruments[symbol] = instrument

            # 合约模式：加载资金费率数据用于资金费用结算
            if is_futures:
                try:
                    funding_df = self.provider.load_funding_rate(
                        symbol, start=funding_start, end=funding_end
                    )
                    if not funding_df.empty:
                        engine.add_funding_data(instrument, funding_df)
                    else:
                        logger.warning(f"{symbol} 无资金费率数据，将不进行资金费用结算")
                except Exception as e:
                    logger.warning(f"{symbol} 资金费率加载失败，跳过: {e}")

            # 处理 DataFrame
            df = df.copy()
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            df.columns = [col.lower() for col in df.columns]

            cols_to_keep = [c for c in required_cols if c in df.columns]
            if 'timestamp' in df.columns:
                cols_to_keep.insert(0, 'timestamp')

            df = df[cols_to_keep]

            if not isinstance(df.index, pd.DatetimeIndex):
                if 'timestamp' in df.columns:
                    df = df.set_index('timestamp')
                    df.drop(columns=['timestamp'], errors='ignore', inplace=True)

            if len(df) > 0:
                try:
                    df.index = pd.to_datetime(df.index, utc=True)
                except Exception as e:
                    logger.warning(f"时间戳转换警告: {e}")
                    df.index = pd.to_datetime(df.index.astype(str), utc=True)

            for col in required_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    df[col] = df[col].astype('float64')
                    nan_count = df[col].isna().sum()
                    if nan_count > 0:
                        logger.warning(f"{symbol} 的 {col} 列有 {nan_count} 个 NaN 值，将填充为 0.0")
                        df[col] = df[col].fillna(0.0)

            non_numeric_cols = df.select_dtypes(exclude=['number']).columns.tolist()
            if non_numeric_cols:
                logger.error(f"发现非数值列: {non_numeric_cols}，将删除这些列")
                df = df.drop(columns=non_numeric_cols)

            bar_type_str = f"{symbol}-{timeframe}"
            bar_types[symbol] = bar_type_str

            # 通过引擎的 load_data_from_parquet 方法加载数据
            # 先保存为临时 parquet 文件再加载
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
                tmp_path = tmp.name

            try:
                df.to_parquet(tmp_path, index=True)
                engine.load_data_from_parquet(tmp_path, instrument)
                logger.info(f"成功加载 {symbol} 的 {len(df)} 条K线数据")
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        logger.info(f"共加载 {len(instruments)} 个品种")

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


# 注：DefaultBacktestService 已移除
# 根据项目规则，所有回测必须使用 axon-quant 事件驱动引擎
