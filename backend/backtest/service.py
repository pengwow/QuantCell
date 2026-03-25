"""
回测模块服务层

实现策略回测和回测结果分析功能。

主要功能:
    - 策略回测执行
    - 多货币对并行回测
    - 回测结果分析
    - 回测结果管理
    - 回放数据生成
    - 引擎选择和工厂方法

服务类:
    - BacktestService: 回测服务主类

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

import sys
import os
import json
import uuid
import concurrent.futures
from pathlib import Path
import pandas as pd
from datetime import datetime
from typing import Any, Dict, Optional

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

# 导入现有模块
from collector.services.data_service import DataService
from strategy.service import StrategyService
from i18n.utils import load_translations
from utils.config_manager import config_manager
from utils.timezone import format_datetime
from utils.data_utils import sanitize_for_json, DataSanitizer

# 导入回测引擎
from backtest.engines import Engine, LegacyEngine, BacktestEngineBase
from backtest.config import EngineType
from backtest.progress_tracker import get_progress_tracker, StageStatus


class BacktestService:
    """
    回测服务类，用于执行策略回测和分析回测结果
    """

    def _get_kline_data_from_db(self, symbol: str, interval: str, start_time: str, end_time: str, db) -> list:
        """
        从数据库K线表获取K线数据

        :param symbol: 货币对，如 "BTCUSDT" 或 "BTC/USDT"
        :param interval: 时间周期，如 "15m"
        :param start_time: 开始时间，ISO格式字符串
        :param end_time: 结束时间，ISO格式字符串
        :param db: 数据库会话
        :return: K线数据列表
        """
        logger.info(f"[_get_kline_data_from_db] 开始获取K线数据: symbol={symbol}, interval={interval}, start_time={start_time}, end_time={end_time}")

        try:
            from collector.db.models import CryptoSpotKline
            from datetime import datetime

            # 解析时间字符串
            logger.info(f"[_get_kline_data_from_db] 解析时间字符串: start_time={start_time}, end_time={end_time}")
            start_dt = datetime.fromisoformat(start_time.replace(' ', 'T'))
            end_dt = datetime.fromisoformat(end_time.replace(' ', 'T'))

            # 转换为微秒级时间戳（数据库中存储的是微秒时间戳）
            start_timestamp_us = int(start_dt.timestamp() * 1000000)
            end_timestamp_us = int(end_dt.timestamp() * 1000000)
            logger.info(f"[_get_kline_data_from_db] 时间解析结果: start_timestamp_us={start_timestamp_us}, end_timestamp_us={end_timestamp_us}")

            # 处理symbol格式，支持 BTCUSDT 和 BTC/USDT 两种格式
            symbol_variants = [symbol]
            if '/' in symbol:
                # BTC/USDT -> BTCUSDT
                symbol_variants.append(symbol.replace('/', ''))
            else:
                # BTCUSDT -> BTC/USDT
                symbol_variants.append(f"{symbol[:-4]}/{symbol[-4:]}" if len(symbol) > 4 else symbol)

            logger.info(f"[_get_kline_data_from_db] symbol变体: {symbol_variants}")

            # 查询K线数据 - 使用微秒时间戳作为字符串查询
            logger.info(f"[_get_kline_data_from_db] 执行数据库查询: interval={interval}")
            kline_records = db.query(CryptoSpotKline).filter(
                CryptoSpotKline.symbol.in_(symbol_variants),
                CryptoSpotKline.interval == interval,
                CryptoSpotKline.timestamp >= str(start_timestamp_us),
                CryptoSpotKline.timestamp <= str(end_timestamp_us)
            ).order_by(CryptoSpotKline.timestamp).all()

            logger.info(f"[_get_kline_data_from_db] 数据库查询完成，获取到 {len(kline_records)} 条原始记录")

            # 转换为字典列表
            kline_data = []
            for idx, record in enumerate(kline_records):
                try:
                    # 数据库中存储的是微秒级时间戳(16位)
                    ts_int = int(record.timestamp)
                    # 微秒转毫秒
                    timestamp_ms = ts_int // 1000
                    # 微秒转秒用于datetime
                    dt = datetime.fromtimestamp(ts_int / 1000000)
                    datetime_str = dt.isoformat()

                    kline_item = {
                        "timestamp": timestamp_ms,
                        "datetime": datetime_str,
                        "open": float(record.open),
                        "close": float(record.close),
                        "high": float(record.high),
                        "low": float(record.low),
                        "volume": float(record.volume),
                        "turnover": 0.0
                    }
                    kline_data.append(kline_item)

                    # 只记录前3条和后3条的解析情况
                    if idx < 3 or idx >= len(kline_records) - 3:
                        logger.info(f"[_get_kline_data_from_db] 解析记录[{idx}]: timestamp={record.timestamp} -> {timestamp_ms}ms, open={record.open}, close={record.close}")
                except Exception as e:
                    logger.warning(f"[_get_kline_data_from_db] 解析K线记录[{idx}]失败: {e}, timestamp={record.timestamp}")
                    continue

            logger.info(f"[_get_kline_data_from_db] 从数据库获取K线数据完成: {symbol} {interval}, 共 {len(kline_data)} 条")
            return kline_data
        except Exception as e:
            logger.error(f"[_get_kline_data_from_db] 从数据库获取K线数据失败: {e}")
            logger.exception(e)
            return []

    def _run_event_backtest(
        self,
        strategy_config,
        backtest_config,
        task_id,
        db,
        is_new_task,
        progress_tracker
    ):
        """
        使用事件驱动引擎执行回测（与CLI保持一致）
        
        :param strategy_config: 策略配置
        :param backtest_config: 回测配置
        :param task_id: 任务ID
        :param db: 数据库会话
        :param is_new_task: 是否新任务
        :param progress_tracker: 进度跟踪器
        :return: 回测结果
        """
        import sys
        from pathlib import Path
        from datetime import datetime, timezone
        import json
        
        # 添加后端目录到路径
        backend_path = Path(__file__).resolve().parent.parent
        if str(backend_path) not in sys.path:
            sys.path.insert(0, str(backend_path))
        
        # 延迟导入CLI核心模块
        try:
            from backtest.cli_core import CLICore, get_system_config
        except ImportError:
            from backend.backtest.cli_core import CLICore, get_system_config
        
        from utils.validation import parse_symbols, parse_timeframes
        from collector.db.models import BacktestTask, BacktestResult
        
        try:
            # 更新数据准备阶段进度
            progress_tracker.update_progress(
                task_id,
                "data_prep",
                {
                    "status": "running",
                    "current_step": "loading",
                    "message": "正在准备数据..."
                }
            )
            
            # 创建CLI核心 - 前端调用时不显示详细日志和进度条
            cli_core = CLICore(verbose=False, detail=False)
            
            # 获取参数
            strategy_name = strategy_config.get("strategy_name")
            strategy_params = strategy_config.get("params", {})
            symbols_list = backtest_config.get("symbols", ["BTCUSDT"])
            timeframes_list = [backtest_config.get("interval", "1h")]
            init_cash = backtest_config.get("initial_cash", 10000.0)
            fees = backtest_config.get("commission", 0.001)
            base_currency = backtest_config.get("base_currency", "USDT")
            leverage = backtest_config.get("leverage", 1.0)
            venue = backtest_config.get("venue", "SIM")
            
            # 获取数据处理和进度显示配置
            auto_download = backtest_config.get("auto_download", True)
            ignore_missing = backtest_config.get("ignore_missing", False)
            # 前端调用时默认不显示命令行进度条，只在CLI模式下显示
            show_progress = backtest_config.get("show_progress", False)
            logger.info(f"[DEBUG] show_progress value: {show_progress}, backtest_config show_progress: {backtest_config.get('show_progress', 'NOT_SET')}")
            
            # 解析时间范围
            start_time = backtest_config.get("start_time")
            end_time = backtest_config.get("end_time")
            
            # 如果有时间范围，格式化为CLI使用的格式
            time_range = None
            if start_time and end_time:
                try:
                    start_dt = datetime.strptime(start_time.split()[0], "%Y-%m-%d")
                    end_dt = datetime.strptime(end_time.split()[0], "%Y-%m-%d")
                    time_range = f"{start_dt.strftime('%Y%m%d')}-{end_dt.strftime('%Y%m%d')}"
                except Exception as e:
                    logger.warning(f"时间范围格式转换失败: {e}")
            
            # 更新任务状态为进行中
            task = db.query(BacktestTask).filter(BacktestTask.id == task_id).first()
            if task:
                task.status = "in_progress"
                db.commit()
            elif is_new_task:
                # 如果是新任务且不存在，创建任务记录
                task = BacktestTask(
                    id=task_id,
                    strategy_name=strategy_name,
                    backtest_config=json.dumps(backtest_config, default=str, ensure_ascii=False),
                    status="in_progress",
                    started_at=datetime.now(timezone.utc)
                )
                db.add(task)
                db.commit()
            
            logger.info(f"[事件驱动引擎] 准备数据...")
            
            # 更新进度：开始数据准备，让用户知道正在检查/下载数据
            progress_tracker.update_progress(
                task_id,
                "data_prep",
                {
                    "status": "running",
                    "current_step": "checking",
                    "progress": 10.0,
                    "checked_symbols": 0,
                    "total_symbols": len(symbols_list),
                    "message": f"正在检查 {symbols_list[0]} 数据完整性..."
                }
            )
            
            # 准备数据
            data_dict, download_results = cli_core.prepare_data(
                symbols=symbols_list,
                timeframes=timeframes_list,
                time_range=time_range,
                trading_mode='spot',
                auto_download=auto_download,
                ignore_missing=ignore_missing,
                show_progress=show_progress
            )
            
            if not data_dict:
                raise ValueError("没有成功加载任何数据，回测无法继续")
            
            # 更新执行阶段进度 - 数据准备完成
            progress_tracker.update_progress(
                task_id,
                "data_prep",
                {
                    "status": "completed",
                    "progress": 100.0,
                    "current_step": "loading",
                    "checked_symbols": len(symbols_list),
                    "total_symbols": len(symbols_list),
                    "message": f"数据准备完成，共加载 {len(data_dict)} 个数据文件"
                }
            )
            progress_tracker.update_progress(
                task_id,
                "execution",
                {
                    "status": "running",
                    "message": "正在执行回测..."
                }
            )
            
            logger.info(f"[事件驱动引擎] 初始化事件驱动引擎...")
            # 初始化事件驱动引擎
            try:
                from decimal import Decimal
                from backtest.engines.event_engine import EventDrivenBacktestEngine
                from nautilus_trader.model import Venue
                from nautilus_trader.model.enums import AccountType, OmsType
                from nautilus_trader.model.objects import Money
                from nautilus_trader.model.data import BarType
                from nautilus_trader.test_kit.providers import TestInstrumentProvider
                from nautilus_trader.persistence.wranglers import BarDataWrangler
                import pandas as pd
            except ImportError as e:
                logger.error(f"无法导入事件驱动引擎模块: {e}")
                raise RuntimeError(f"事件驱动引擎依赖缺失: {e}")
            
            # 创建引擎配置
            engine_config = {
                "trader_id": f"BACKTEST-{strategy_name.upper()}",
                "log_level": "INFO",
                "initial_capital": init_cash,
            }
            
            # 解析时间范围
            start_date = '2023-01-01'
            end_date = '2023-12-31'
            if time_range:
                from utils.validation import parse_time_range
                start_dt, end_dt = parse_time_range(time_range)
                start_date = start_dt.strftime('%Y-%m-%d') if start_dt else '2023-01-01'
                end_date = end_dt.strftime('%Y-%m-%d') if end_dt else '2023-12-31'
            elif data_dict:
                # 使用第一个数据的时间范围
                first_key = list(data_dict.keys())[0]
                first_df = data_dict[first_key]
                if len(first_df) > 0:
                    first_idx = first_df.index[0]
                    last_idx = first_df.index[-1]
                    start_date = str(first_idx)[:10] if first_idx is not None else '2023-01-01'
                    end_date = str(last_idx)[:10] if last_idx is not None else '2023-12-31'
            
            engine_config["start_date"] = start_date
            engine_config["end_date"] = end_date
            
            logger.info(f"[事件驱动引擎] 回测时间范围: {start_date} 至 {end_date}")
            
            # 创建引擎实例
            engine = EventDrivenBacktestEngine(engine_config)
            engine.initialize()
            
            # 为每个品种创建交易品种并加载数据
            instruments = {}
            bar_types = {}
            all_bars = []
            
            # 使用第一个品种的venue作为交易所
            first_symbol = symbols_list[0]
            first_timeframe = timeframes_list[0]
            first_key = f"{first_symbol}_{first_timeframe}"
            
            # 创建第一个品种以获取venue
            if first_symbol == 'BTCUSDT' or first_symbol == 'BTC/USDT':
                first_instrument = TestInstrumentProvider.btcusdt_binance()
            elif first_symbol == 'ETHUSDT' or first_symbol == 'ETH/USDT':
                first_instrument = TestInstrumentProvider.ethusdt_binance()
            else:
                first_instrument = TestInstrumentProvider.btcusdt_binance()
            instrument_venue = str(first_instrument.id.venue)
            
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
            for symbol in symbols_list:
                timeframe = timeframes_list[0]
                key = f"{symbol}_{timeframe}"
                
                if key not in data_dict:
                    logger.warning(f"跳过 {key}，数据未加载")
                    continue
                
                df = data_dict[key]
                
                # 创建交易品种
                if symbol == 'BTCUSDT' or symbol == 'BTC/USDT':
                    instrument = TestInstrumentProvider.btcusdt_binance()
                elif symbol == 'ETHUSDT' or symbol == 'ETH/USDT':
                    instrument = TestInstrumentProvider.ethusdt_binance()
                else:
                    instrument = TestInstrumentProvider.btcusdt_binance()
                
                engine.add_instrument(instrument)
                instruments[symbol] = instrument
                
                # 转换数据格式并加载
                df = df.copy()
                df.columns = [col.lower() for col in df.columns]
                
                # 确保索引是带时区的datetime类型
                if not isinstance(df.index, pd.DatetimeIndex):
                    if 'timestamp' in df.columns:
                        df = df.set_index('timestamp')
                    df.index = pd.to_datetime(df.index, utc=True)
                
                # 确保所有价格列都是float64类型
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in df.columns:
                        df[col] = df[col].astype('float64')
                
                # 创建BarType
                from backtest.cli import _convert_timeframe_to_event
                bar_type_str = f"{instrument.id}-{_convert_timeframe_to_event(timeframe)}-LAST-EXTERNAL"
                bar_type = BarType.from_str(bar_type_str)
                bar_types[symbol] = bar_type
                
                # 使用BarDataWrangler转换数据
                wrangler = BarDataWrangler(bar_type, instrument)
                bars = wrangler.process(df)
                
                # 添加数据到引擎
                if hasattr(engine, 'engine') and engine.engine is not None:
                    engine.engine.add_data(bars)
                engine._data.extend(bars)
                all_bars.extend(bars)
                
                logger.info(f"[事件驱动引擎] 成功加载 {symbol} 的 {len(bars)} 条K线数据")
            
            # 加载策略
            logger.info(f"[事件驱动引擎] 加载策略...")
            from backtest.cli import _load_event_strategy_multi
            strategy = _load_event_strategy_multi(
                strategy_name, strategy_params, bar_types, instruments
            )
            
            if strategy is None:
                raise ValueError(f"无法加载策略 {strategy_name}")
            
            engine.add_strategy(strategy)
            
            # 执行回测
            logger.info(f"[事件驱动引擎] 开始执行回测...")
            results = engine.run_backtest()
            
            # 格式化结果
            logger.info(f"[事件驱动引擎] 处理回测结果...")
            from backtest.cli import _format_event_results_multi
            formatted_results = _format_event_results_multi(
                results, symbols_list, timeframes_list[0], strategy_name, instruments
            )
            
            # 保存结果到文件
            output_file = str(cli_core.results_dir / f"{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_event_results.json")
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(formatted_results, f, ensure_ascii=False, indent=2, default=str)
                logger.info(f"[事件驱动引擎] 结果已保存到: {output_file}")
            except Exception as e:
                logger.error(f"[事件驱动引擎] 保存结果文件失败: {e}")
                # 尝试找出哪个字段包含 Timestamp
                import traceback
                logger.error(f"保存结果时的堆栈: {traceback.format_exc()}")
                # 继续执行，不因为保存文件失败而中断
            
            # 清理引擎资源
            engine.cleanup()
            
            # 更新执行阶段为完成
            progress_tracker.update_progress(
                task_id,
                "execution",
                {
                    "status": "completed",
                    "progress": 100.0,
                    "message": "回测执行完成"
                }
            )
            progress_tracker.update_progress(
                task_id,
                "analysis",
                {
                    "status": "running",
                    "progress": 50.0,
                    "message": "正在保存结果..."
                }
            )
            
            # 保存结果到数据库
            # 创建回测结果记录
            result_id = str(uuid.uuid4())
            
            # 从事件驱动结果中提取指标
            portfolio_metrics = formatted_results.get('portfolio', {}).get('metrics', {})
            trades = formatted_results.get('portfolio', {}).get('trades', [])
            equity_curve = formatted_results.get('portfolio', {}).get('equity_curve', [])
            
            # 转换指标格式
            metrics_list = []
            for key, value in portfolio_metrics.items():
                metrics_list.append({
                    'name': key,
                    'key': key,
                    'value': value,
                    'description': key,
                    'type': 'number'
                })
            
            # 从数据库获取K线数据作为strategy_data
            strategy_data_list = []
            for symbol in symbols_list:
                symbol_kline_data = self._get_kline_data_from_db(
                    symbol=symbol,
                    interval=timeframes_list[0],
                    start_time=start_time,
                    end_time=end_time,
                    db=db
                )
                strategy_data_list.extend(symbol_kline_data)

            backtest_result = BacktestResult(
                id=result_id,
                task_id=task_id,
                strategy_name=strategy_name,
                symbol=','.join(symbols_list),
                metrics=json.dumps(metrics_list, default=str, ensure_ascii=False),
                trades=json.dumps(trades, default=str, ensure_ascii=False),
                equity_curve=json.dumps(equity_curve, default=str, ensure_ascii=False),
                strategy_data=json.dumps(strategy_data_list, default=str, ensure_ascii=False)
            )
            db.add(backtest_result)
            
            # 更新回测任务状态
            task.status = "completed"
            task.result_id = result_id
            task.completed_at = datetime.now(timezone.utc)
            db.commit()
            
            # 保存合并后的回测结果
            self.save_backtest_result(task_id, formatted_results)
            
            # 更新进度为完成
            progress_tracker.update_progress(
                task_id,
                "analysis",
                {
                    "status": "completed",
                    "progress": 100.0,
                    "message": "回测完成"
                }
            )
            progress_tracker.complete_progress(task_id)
            
            logger.info(f"[事件驱动引擎] 回测任务 {task_id} 成功完成")
            
            # 构建响应结果
            return {
                "task_id": task_id,
                "status": "completed",
                "message": f"回测完成，共 {len(symbols_list)} 个货币对",
                "successful_currencies": symbols_list,
                "failed_currencies": [],
                "results": formatted_results
            }
            
        except Exception as e:
            logger.error(f"[事件驱动引擎] 回测失败: {e}")
            logger.exception(e)
            
            # 更新进度为失败
            progress_tracker.fail_progress(
                task_id,
                f"事件驱动回测失败: {str(e)}",
                "execution"
            )
            
            # 更新任务状态为失败
            task = db.query(BacktestTask).filter(BacktestTask.id == task_id).first()
            if task:
                task.status = "failed"
                task.completed_at = datetime.now(timezone.utc)
                db.commit()
            
            return {
                "status": "failed",
                "task_id": task_id,
                "message": f"事件驱动回测失败: {str(e)}"
            }
    
    def __init__(self):
        """初始化回测服务"""
        # 策略服务实例 - 使用独立的策略模块
        self.strategy_service = StrategyService()

        # 回测结果保存路径
        self.backtest_result_dir = Path(project_root) / "backend" / "backtest" / "results"
        self.backtest_result_dir.mkdir(parents=True, exist_ok=True)

        # 数据服务实例
        self.data_service = DataService()

        # 数据管理器实例，用于管理多时间周期数据
        from .data_manager import DataManager
        self.data_manager = DataManager(self.data_service)

        # 需要翻译的指标键列表
        self.metric_keys = [
            'Start', 'End', 'Duration', 'Exposure Time [%]', 'Equity Final [$]',
            'Equity Peak [$]', 'Commissions [$]', 'Return [%]', 'Return (Ann.) [%]',
            'Buy & Hold Return [%]', 'Volatility (Ann.) [%]', 'CAGR [%]', 'Sharpe Ratio',
            'Sortino Ratio', 'Calmar Ratio', 'Alpha [%]', 'Beta', 'Max. Drawdown [%]',
            'Avg. Drawdown [%]', 'Profit Factor', 'Win Rate [%]', 'Expectancy [%]',
            '# Trades', 'Best Trade [%]', 'Worst Trade [%]', 'Avg. Trade [%]',
            'Max. Trade Duration', 'Avg. Trade Duration', 'Max. Drawdown Duration',
            'Avg. Drawdown Duration', 'SQN', 'Kelly Criterion'
        ]

        # 当前使用的回测引擎实例
        self._engine: Optional[BacktestEngineBase] = None

    def create_engine(self, config: Optional[Dict[str, Any]] = None) -> Optional[BacktestEngineBase]:
        """
        引擎工厂方法，根据配置创建对应的回测引擎

        从配置中读取 engine_type 参数，创建对应的回测引擎实例。
        默认使用 default 引擎，支持回退到传统引擎。

        Args:
            config: 引擎配置字典，包含 engine_type 等参数
                   如果为 None，则使用默认配置

        Returns:
            Optional[BacktestEngineBase]: 回测引擎实例

        Example:
            >>> service = BacktestService()
            >>> engine = service.create_engine({"engine_type": "default"})
            >>> if engine:
            ...     engine.initialize()
            ...     results = engine.run_backtest()
        """
        # 获取配置，使用传入的配置或默认空配置
        engine_config = config or {}

        # 从配置中读取引擎类型，默认为 default
        engine_type_str = engine_config.get("engine_type", "default")

        logger.info(f"创建回测引擎，引擎类型: {engine_type_str}")

        # 根据引擎类型创建对应的引擎实例
        if engine_type_str == EngineType.DEFAULT.value:
            logger.info("使用高级回测引擎")
            self._engine = Engine(engine_config)
        elif engine_type_str == EngineType.LEGACY.value:
            logger.info("使用传统回测引擎 (Legacy)")
            # 延迟导入 LegacyEngine 以避免循环依赖
            from backtest.engines.legacy_engine import LegacyEngine
            self._engine = LegacyEngine(engine_config)
        else:
            # 未知的引擎类型，使用默认的默认引擎
            logger.warning(f"未知的引擎类型: {engine_type_str}，使用默认的默认引擎")
            self._engine = Engine(engine_config)

        return self._engine

    def get_engine(self) -> Optional[BacktestEngineBase]:
        """
        获取当前使用的回测引擎实例

        Returns:
            Optional[BacktestEngineBase]: 当前引擎实例，如果未创建则返回 None
        """
        return self._engine

    def get_strategy_list(self):
        """
        获取所有支持的策略类型列表
        
        :return: 策略类型列表
        """
        try:
            # 调用策略服务获取策略列表
            strategies = self.strategy_service.get_strategy_list()
            
            # 只返回策略名称列表，保持原有接口兼容性
            strategy_names = [strategy["name"] for strategy in strategies]
            
            logger.info(f"获取策略列表成功，共 {len(strategy_names)} 个策略")
            return strategy_names
        except Exception as e:
            logger.error(f"获取策略列表失败: {e}")
            logger.exception(e)
            return []
    
    def load_strategy_from_file(self, strategy_name):
        """
        从文件中加载策略类
        
        :param strategy_name: 策略名称
        :return: 策略类
        """
        try:
            # 调用策略服务加载策略
            strategy_class = self.strategy_service.load_strategy(strategy_name)
            
            if strategy_class:
                logger.info(f"成功加载策略: {strategy_name}")
                return strategy_class
            else:
                logger.error(f"加载策略失败: {strategy_name}")
                return None
        except Exception as e:
            logger.error(f"加载策略失败: {e}")
            logger.exception(e)
            return None
    
    def upload_strategy_file(self, strategy_name, file_content):
        """
        上传策略文件
        
        :param strategy_name: 策略名称
        :param file_content: 文件内容
        :return: 是否上传成功
        """
        try:
            # 调用策略服务上传策略文件
            success = self.strategy_service.upload_strategy_file(strategy_name, file_content)
            
            if success:
                logger.info(f"策略文件上传成功: {strategy_name}")
            else:
                logger.error(f"策略文件上传失败: {strategy_name}")
            
            return success
        except Exception as e:
            logger.error(f"策略文件上传失败: {e}")
            logger.exception(e)
            return False
    
    def run_single_backtest(self, strategy_config, backtest_config, task_id, symbol_index=0, total_symbols=1):
        """
        执行单个货币对的回测
        
        :param strategy_config: 策略配置
        :param backtest_config: 回测配置，包含单个货币对信息
        :param task_id: 回测任务ID，所有货币对共享同一个task_id
        :param symbol_index: 当前货币对索引（用于进度计算）
        :param total_symbols: 总货币对数量（用于进度计算）
        :return: 单个货币对的回测结果数据，不直接保存到数据库
        """
        # 获取进度跟踪器
        progress_tracker = get_progress_tracker()
        
        try:
            from collector.db.database import SessionLocal, init_database_config
            import json
            
            # 初始化数据库连接
            init_database_config()
            db = SessionLocal()
            
            # 创建带有数据库会话的DataService和DataManager
            # 注意：在多线程环境中，必须为每个线程创建独立的数据库会话
            local_data_service = DataService(db)
            from .data_manager import DataManager
            local_data_manager = DataManager(local_data_service)
            
            strategy_name = strategy_config.get("strategy_name")
            symbol = backtest_config.get("symbol", "BTCUSDT")
            interval = backtest_config.get("interval", "1d")
            start_time = backtest_config.get("start_time")
            end_time = backtest_config.get("end_time")
            
            logger.info(f"开始回测，策略名称: {strategy_name}, 货币对: {symbol}, task_id: {task_id}")
            
            # ========== 数据完整性检查 ==========
            logger.info(f"[{symbol}] 开始数据完整性检查...")
            
            # 更新进度：数据准备阶段 - 检查中
            progress_tracker.update_progress(
                task_id,
                "data_prep",
                {
                    "status": "running",
                    "current_step": "checking",
                    "checked_symbols": symbol_index,
                    "total_symbols": total_symbols,
                    "message": f"正在检查 {symbol} 数据完整性..."
                }
            )
            
            from .data_integrity import DataIntegrityChecker
            from .data_downloader import BacktestDataDownloader
            
            integrity_checker = DataIntegrityChecker()
            data_downloader = BacktestDataDownloader()
            
            # 检查数据完整性
            integrity_result = integrity_checker.check_data_completeness(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                market_type='crypto',
                crypto_type='spot'
            )
            
            if not integrity_result.is_complete:
                logger.warning(
                    f"[{symbol}] 数据不完整，覆盖率: {integrity_result.coverage_percent:.2f}%, "
                    f"缺失: {integrity_result.missing_count} 条"
                )
                
                # 更新进度：数据准备阶段 - 下载中
                progress_tracker.update_progress(
                    task_id,
                    "data_prep",
                    {
                        "status": "running",
                        "current_step": "downloading",
                        "checked_symbols": symbol_index + 1,
                        "total_symbols": total_symbols,
                        "downloading": {
                            "symbol": symbol,
                            "progress": 0
                        },
                        "message": f"正在下载 {symbol} 缺失数据..."
                    }
                )
                
                # 尝试下载缺失数据
                logger.info(f"[{symbol}] 开始下载缺失数据...")
                download_success, new_result = data_downloader.ensure_data_complete(
                    symbol=symbol,
                    interval=interval,
                    start_time=start_time,
                    end_time=end_time,
                    max_wait_time=300  # 最多等待5分钟
                )
                
                if not download_success:
                    # 检查覆盖率，如果达到可接受水平（如80%以上），则继续回测
                    min_coverage = 80.0  # 最小可接受覆盖率
                    if new_result.coverage_percent >= min_coverage:
                        logger.warning(
                            f"[{symbol}] 数据下载不完全，但覆盖率达到 {new_result.coverage_percent:.2f}%，继续回测"
                        )
                        integrity_result = new_result
                    else:
                        logger.error(f"[{symbol}] 数据下载失败且覆盖率不足，回测无法继续")
                        # 更新进度为失败状态
                        progress_tracker.update_progress(
                            task_id,
                            "data_prep",
                            {
                                "status": "failed",
                                "progress": new_result.coverage_percent,
                                "checked_symbols": symbol_index + 1,
                                "total_symbols": total_symbols,
                                "message": f"{symbol} 数据不完整: 覆盖率 {new_result.coverage_percent:.2f}%"
                            }
                        )
                        return {
                            "symbol": symbol,
                            "task_id": task_id,
                            "status": "failed",
                            "message": f"数据不完整且下载失败，覆盖率: {new_result.coverage_percent:.2f}%",
                            "data_integrity": new_result.to_dict()
                        }
                
                logger.info(f"[{symbol}] 数据下载完成，重新检查完整性...")
                integrity_result = new_result
            
            logger.info(f"[{symbol}] 数据完整性检查通过，覆盖率: {integrity_result.coverage_percent:.2f}%")
            # ========== 数据完整性检查结束 ==========
            
            # 更新进度：数据准备阶段完成
            progress_tracker.update_progress(
                task_id,
                "data_prep",
                {
                    "status": "completed" if symbol_index == total_symbols - 1 else "running",
                    "progress": 100.0,
                    "current_step": "loading",
                    "checked_symbols": symbol_index + 1,
                    "total_symbols": total_symbols,
                    "message": f"{symbol} 数据准备完成"
                }
            )
            
            # 加载策略类
            strategy_class = self.load_strategy_from_file(strategy_name)
            if not strategy_class:
                return {
                    "symbol": symbol,
                    "task_id": task_id,
                    "status": "failed",
                    "message": f"策略加载失败: {strategy_name}"
                }
            
            # 获取回测配置
            interval = backtest_config.get("interval", "1d")
            start_time = backtest_config.get("start_time")
            end_time = backtest_config.get("end_time")
            
            logger.info(f"回测配置: {symbol}, {interval}, {start_time} to {end_time}")
            
            # 预加载多种时间周期的数据
            local_data_manager.preload_data(
                symbol=symbol,
                base_interval=interval,
                start_time=start_time,
                end_time=end_time,
                preload_intervals=['1m', '5m', '15m', '30m', '1h', '4h', '1d']  # 预加载常用周期
            )
            
            # 获取主周期K线数据
            logger.info(f"获取主周期 {interval} 的K线数据")
            
            # 使用数据服务获取K线数据
            result = local_data_service.get_kline_data(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time
            )
            
            kline_data = result.get("kline_data", [])
            
            if not kline_data:
                logger.error(f"未获取到K线数据: {symbol}, {interval}, {start_time} to {end_time}")
                return {
                    "symbol": symbol,
                    "task_id": task_id,
                    "status": "failed",
                    "message": f"未获取到货币对 {symbol} 的K线数据"
                }
                
            # Convert to DataFrame
            candles = pd.DataFrame(kline_data)
            
            # 转换数据格式
            candles.rename(columns={
                'open': 'Open',
                'close': 'Close',
                'high': 'High',
                'low': 'Low',
                'volume': 'Volume'
            }, inplace=True)
            
            # 设置时间索引
            if 'timestamp' in candles.columns:
                candles['datetime'] = pd.to_datetime(candles['timestamp'], unit='ms')
                candles.set_index('datetime', inplace=True)
            elif 'datetime' in candles.columns:
                candles.set_index('datetime', inplace=True)
            elif 'open_time' in candles.columns:
                candles['open_time'] = pd.to_datetime(candles['open_time'])
                candles.set_index('open_time', inplace=True)
            
            # 初始化回测
            initial_cash = backtest_config.get("initial_cash", 10000)
            commission = backtest_config.get("commission", 0.001)
            
            # Check if initial cash is sufficient for the asset price
            max_price = candles['Close'].max()
            if max_price > initial_cash:
                logger.warning(f"Initial cash ({initial_cash}) is lower than max price ({max_price}). Increasing cash to avoid warnings.")
                initial_cash = max_price * 1.1 # Add 10% buffer
            
            # 为数据添加交易对符号属性
            candles.symbol = symbol
            
            # 自定义回测运行器，用于在策略实例化后设置数据管理器
            class CustomBacktest(Backtest):
                def run(self, **kwargs):
                    # 执行父类的run方法
                    result = super().run(**kwargs)
                    # 获取策略实例并设置数据管理器
                    if hasattr(result, '_strategy'):
                        strategy_instance = result['_strategy']
                        if hasattr(strategy_instance, 'set_data_manager'):
                            strategy_instance.set_data_manager(local_data_manager)
                    return result
            
            bt = CustomBacktest(
                candles, 
                strategy_class, 
                cash=initial_cash,
                commission=commission,
                exclusive_orders=True
            )
            
            # 执行回测
            stats = bt.run()
            
            # 获取策略数据
            strategy_data = []
            if '_strategy' in stats:
                strategy_instance = stats['_strategy']
                if hasattr(strategy_instance, 'data'):
                    # Try to access underlying DataFrame
                    try:
                        df = None
                        if hasattr(strategy_instance.data, 'df'):
                            df = strategy_instance.data.df
                        elif isinstance(strategy_instance.data, pd.DataFrame):
                            df = strategy_instance.data

                        if df is not None:
                            # 重要：保留时间索引作为一个字段
                            df_copy = df.copy()
                            df_copy.reset_index(inplace=True)

                            # 重命名索引列为datetime
                            if 'index' in df_copy.columns:
                                df_copy.rename(columns={'index': 'datetime'}, inplace=True)
                            elif df_copy.index.name and df_copy.index.name not in df_copy.columns:
                                # 如果索引有名称且不是datetime，重命名为datetime
                                first_col = df_copy.columns[0]
                                if first_col not in ['Open', 'High', 'Low', 'Close', 'Volume']:
                                    df_copy.rename(columns={first_col: 'datetime'}, inplace=True)

                            # 如果还是没有datetime列，假设第一列是时间
                            if 'datetime' not in df_copy.columns and len(df_copy.columns) > 0:
                                first_col = df_copy.columns[0]
                                df_copy.rename(columns={first_col: 'datetime'}, inplace=True)

                            strategy_data = df_copy.to_dict('records')
                    except Exception as e:
                        logger.warning(f"Failed to extract strategy data: {e}")
                        logger.exception(e)

            # 如果策略数据为空，从数据库获取K线数据
            logger.info(f"[run_single_backtest] 检查策略数据: len(strategy_data)={len(strategy_data)}, type={type(strategy_data)}")
            if not strategy_data:
                logger.info(f"[run_single_backtest] 策略数据为空，准备从数据库获取K线数据: symbol={symbol}, interval={interval}, start_time={start_time}, end_time={end_time}")
                logger.info(f"[run_single_backtest] 数据库会话状态: db={db}, type={type(db)}")
                strategy_data = self._get_kline_data_from_db(
                    symbol=symbol,
                    interval=interval,
                    start_time=start_time,
                    end_time=end_time,
                    db=db
                )
                logger.info(f"[run_single_backtest] 从数据库获取K线数据完成: len(strategy_data)={len(strategy_data)}")
            else:
                logger.info(f"[run_single_backtest] 策略数据不为空，跳过数据库查询: len(strategy_data)={len(strategy_data)}")

            # 获取交易记录
            trades = []
            if '_trades' in stats:
                trades = stats['_trades'].to_dict('records')
                for trade in trades:
                    for key, value in trade.items():
                        if isinstance(value, pd.Timestamp):
                            trade[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                        elif isinstance(value, pd.Timedelta):
                            trade[key] = str(value)
                    # 添加交易方向
                    if trade.get('Size', 0) > 0:
                        trade['Direction'] = '多单'
                    else:
                        trade['Direction'] = '空单'
            
            # 翻译回测结果
            translated_metrics = self.translate_backtest_results(stats)
            
            # 生成回测ID - 使用UUID替代原有格式，避免URL路径问题
            backtest_id = str(uuid.uuid4())
            
            # 准备资金曲线数据，保留时间索引
            equity_df = stats['_equity_curve'].copy()
            equity_df.reset_index(inplace=True)
            # 重命名索引列为datetime，以匹配前端期望
            if 'index' in equity_df.columns:
                equity_df.rename(columns={'index': 'datetime'}, inplace=True)
            elif 'time' in equity_df.columns:
                equity_df.rename(columns={'time': 'datetime'}, inplace=True)
            # 如果索引有名称但不是index或time，它会自动成为列名，我们确保它是datetime
            # 这里做一个通用处理：找到第一个列（原索引）并重命名为datetime
            if 'datetime' not in equity_df.columns and len(equity_df.columns) > 0:
                # 假设第一列是时间
                equity_df.rename(columns={equity_df.columns[0]: 'datetime'}, inplace=True)
            
            equity_curve_data = equity_df.to_dict('records')
            
            # 构建回测结果数据，不直接保存到数据库
            result_data = {
                "id": backtest_id,
                "symbol": symbol,
                "task_id": task_id,
                "status": "success",
                "message": "回测完成",
                "strategy_name": strategy_name,
                "backtest_config": backtest_config,
                "metrics": sanitize_for_json(translated_metrics),
                "trades": sanitize_for_json(trades),
                "equity_curve": sanitize_for_json(equity_curve_data),
                "strategy_data": sanitize_for_json(strategy_data)
            }
            
            logger.info(f"回测完成，策略: {strategy_name}, 货币对: {symbol}, 回测ID: {backtest_id}, task_id: {task_id}")
            return result_data
        except Exception as e:
            logger.error(f"回测失败: {e}")
            logger.exception(e)
            symbol = backtest_config.get("symbol", "BTCUSDT")
            return {
                "symbol": symbol,
                "task_id": task_id,
                "status": "failed",
                "message": str(e)
            }
    
    def merge_backtest_results(self, results):
        """
        合并多个货币对的回测结果
        
        :param results: 各货币对的回测结果字典，格式为 {symbol: result}
        :return: 合并后的回测结果
        """
        try:
            logger.info(f"开始合并回测结果，共 {len(results)} 个货币对")
            
            # 提取第一个成功的回测结果作为基础
            base_result = None
            for symbol, result in results.items():
                if result["status"] == "success":
                    base_result = result
                    break
            
            if not base_result:
                logger.error("所有货币对回测失败，无法合并结果")
                return {
                    "status": "failed",
                    "message": "所有货币对回测失败",
                    "currencies": results
                }
            
            # 计算整体统计指标
            total_trades = 0
            successful_currencies = []
            returns = []
            max_drawdowns = []
            sharpe_ratios = []
            sortino_ratios = []
            calmar_ratios = []
            win_rates = []
            profit_factors = []
            total_equity = 0
            total_initial_cash = 0
            
            # 收集所有成功回测的结果
            successful_results = {}
            for symbol, result in results.items():
                if result["status"] == "success":
                    successful_currencies.append(symbol)
                    successful_results[symbol] = result
                    
                    # 统计交易次数
                    trade_count = len(result["trades"])
                    total_trades += trade_count
                    logger.info(f"货币对 {symbol} 交易次数: {trade_count}")
                    
                    # 提取关键指标
                    # 首先获取初始资金
                    initial_cash = result.get("backtest_config", {}).get("initial_cash", 10000)
                    total_initial_cash += initial_cash
                    logger.info(f"货币对 {symbol} 初始资金: ${initial_cash}")
                    
                    logger.info(f"开始提取货币对 {symbol} 的指标")
                    
                    # 标记是否找到最终权益指标
                    found_equity_final = False
                    
                    for metric in result["metrics"]:
                        # 同时检查指标的key和name字段，确保在不同语言设置下都能找到正确的指标
                        metric_key = metric.get("key", metric.get("name", ""))
                        metric_name = metric.get("name", "")
                        metric_value = metric.get("value")
                        
                        logger.debug(f"检查指标: key={metric_key}, name={metric_name}, value={metric_value}, type={type(metric_value)}")
                        
                        if metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率":
                            if isinstance(metric_value, (int, float)):
                                returns.append(metric_value)
                                logger.debug(f"货币对 {symbol} 收益率: {metric_value}%")
                        elif metric_key == "Max. Drawdown [%]" or metric_name == "Max. Drawdown [%]" or metric_name == "最大回撤":
                            if isinstance(metric_value, (int, float)):
                                max_drawdowns.append(metric_value)
                                logger.debug(f"货币对 {symbol} 最大回撤: {metric_value}%")
                        elif metric_key == "Sharpe Ratio" or metric_name == "Sharpe Ratio" or metric_name == "夏普比率":
                            if isinstance(metric_value, (int, float)):
                                sharpe_ratios.append(metric_value)
                                logger.debug(f"货币对 {symbol} 夏普比率: {metric_value}")
                        elif metric_key == "Sortino Ratio" or metric_name == "Sortino Ratio" or metric_name == "索提诺比率":
                            if isinstance(metric_value, (int, float)):
                                sortino_ratios.append(metric_value)
                                logger.debug(f"货币对 {symbol} 索提诺比率: {metric_value}")
                        elif metric_key == "Calmar Ratio" or metric_name == "Calmar Ratio" or metric_name == "卡尔玛比率":
                            if isinstance(metric_value, (int, float)):
                                calmar_ratios.append(metric_value)
                                logger.debug(f"货币对 {symbol} 卡尔玛比率: {metric_value}")
                        elif metric_key == "Win Rate [%]" or metric_name == "Win Rate [%]" or metric_name == "胜率":
                            if isinstance(metric_value, (int, float)):
                                win_rates.append(metric_value)
                                logger.debug(f"货币对 {symbol} 胜率: {metric_value}%")
                        elif metric_key == "Profit Factor" or metric_name == "Profit Factor" or metric_name == "盈利因子":
                            if isinstance(metric_value, (int, float)):
                                profit_factors.append(metric_value)
                                logger.debug(f"货币对 {symbol} 盈利因子: {metric_value}")
                        elif metric_key == "Equity Final [$]" or metric_name == "最终权益":
                            if isinstance(metric_value, (int, float)):
                                total_equity += metric_value
                                found_equity_final = True
                                logger.info(f"货币对 {symbol} 最终权益: ${metric_value}")
                            else:
                                logger.warning(f"货币对 {symbol} 最终权益值不是数字: {metric_value}, 类型: {type(metric_value)}")
                    
                    # 如果没有找到最终权益指标，尝试使用收益率和初始资金计算
                    if not found_equity_final:
                        logger.warning(f"货币对 {symbol} 未找到最终权益指标，尝试使用收益率计算")
                        # 查找总收益率指标
                        for metric in result["metrics"]:
                            metric_key = metric.get("key", metric.get("name", ""))
                            metric_name = metric.get("name", "")
                            metric_value = metric.get("value")
                            
                            if (metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率") and isinstance(metric_value, (int, float)):
                                # 使用收益率和初始资金计算最终权益
                                calculated_equity = initial_cash * (1 + metric_value / 100)
                                total_equity += calculated_equity
                                logger.info(f"货币对 {symbol} 使用收益率计算最终权益: ${calculated_equity}")
                                break
                    
                    logger.info(f"货币对 {symbol} 处理完成，累计总权益: ${total_equity}")
                    logger.debug(f"货币对 {symbol} 初始资金: ${initial_cash}")
            
            logger.info(f"成功回测的货币对数量: {len(successful_currencies)}/{len(results)}")
            
            # 计算平均值
            avg_return = sum(returns) / len(returns) if returns else 0
            avg_max_drawdown = sum(max_drawdowns) / len(max_drawdowns) if max_drawdowns else 0
            avg_sharpe = sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else 0
            avg_sortino = sum(sortino_ratios) / len(sortino_ratios) if sortino_ratios else 0
            avg_calmar = sum(calmar_ratios) / len(calmar_ratios) if calmar_ratios else 0
            avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
            avg_profit_factor = sum(profit_factors) / len(profit_factors) if profit_factors else 0
            
            # 计算总收益率
            total_return = ((total_equity - total_initial_cash) / total_initial_cash) * 100 if total_initial_cash > 0 else 0
            
            # 生成合并后的回测ID
            merged_backtest_id = str(uuid.uuid4())
            
            # 合并资金曲线
            def merge_equity_curves(currency_results):
                """
                合并多个货币对的资金曲线
                
                :param currency_results: 成功货币对的回测结果字典
                :return: 合并后的资金曲线
                """
                try:
                    # 收集所有时间戳和对应权益值
                    time_equity_map = {}
                    
                    for symbol, result in currency_results.items():
                        if result.get("status") == "success" and "equity_curve" in result:
                            equity_curve = result["equity_curve"]
                            for equity_data in equity_curve:
                                # 提取时间戳
                                timestamp = equity_data.get("datetime") or equity_data.get("time") or equity_data.get("timestamp")
                                if timestamp:
                                    # 提取权益值
                                    equity = equity_data.get("Equity") or equity_data.get("equity") or 0
                                    if timestamp not in time_equity_map:
                                        time_equity_map[timestamp] = 0
                                    time_equity_map[timestamp] += equity
                    
                    # 按时间戳排序并构建合并后的资金曲线
                    merged_curve = []
                    for timestamp in sorted(time_equity_map.keys()):
                        merged_curve.append({
                            "datetime": timestamp,
                            "Equity": time_equity_map[timestamp]
                        })
                    
                    logger.info(f"资金曲线合并完成，共 {len(merged_curve)} 个时间点")
                    return merged_curve
                except Exception as e:
                    logger.error(f"合并资金曲线失败: {e}")
                    logger.exception(e)
                    return []
            
            # 执行资金曲线合并
            merged_equity_curve = merge_equity_curves(successful_results)
            
            # 构建合并后的回测结果
            merged_result = {
                "task_id": merged_backtest_id,
                "status": "success",
                "message": "多货币对回测完成",
                "strategy_name": base_result.get("strategy_name", "Unknown"),
                "backtest_config": base_result.get("backtest_config", {}),
                "summary": {
                    "total_currencies": len(results),
                    "successful_currencies": len(successful_currencies),
                    "failed_currencies": len(results) - len(successful_currencies),
                    "total_trades": total_trades,
                    "average_trades_per_currency": round(total_trades / len(successful_currencies), 2) if successful_currencies else 0,
                    "total_initial_cash": round(total_initial_cash, 2),
                    "total_equity": round(total_equity, 2),
                    "total_return": round(total_return, 2),
                    "average_return": round(avg_return, 2),
                    "average_max_drawdown": round(avg_max_drawdown, 2),
                    "average_sharpe_ratio": round(avg_sharpe, 2),
                    "average_sortino_ratio": round(avg_sortino, 2),
                    "average_calmar_ratio": round(avg_calmar, 2),
                    "average_win_rate": round(avg_win_rate, 2),
                    "average_profit_factor": round(avg_profit_factor, 2)
                },
                "currencies": results,
                "merged_equity_curve": merged_equity_curve,  # 合并后的资金曲线
                "successful_currencies": successful_currencies,
                "failed_currencies": [symbol for symbol, result in results.items() if result["status"] != "success"]
            }
            
            logger.info(f"回测结果合并完成，共 {len(successful_currencies)} 个货币对回测成功")
            logger.info(f"合并后总收益率: {round(total_return, 2)}%，总交易次数: {total_trades}")
            return merged_result
        except Exception as e:
            logger.error(f"合并回测结果失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": f"合并回测结果失败: {str(e)}",
                "currencies": results
            }
    
    def run_backtest(self, strategy_config, backtest_config, task_id=None):
        """
        执行回测，支持多货币对并行回测

        根据 backtest_config 中的 engine_type 参数选择回测引擎：
        - "default": 使用 trading engine 引擎（默认）
        - "legacy": 使用传统 backtesting.py 引擎
        - "event": 使用事件驱动引擎

        :param strategy_config: 策略配置
        :param backtest_config: 回测配置，包含symbols列表和可选的engine_type
        :param task_id: 可选的任务ID，如果提供则使用现有任务，否则创建新任务
        :return: 回测结果，单个货币对返回BacktestResult，多个货币对返回MultiBacktestResult
        """
        db = None
        # 获取进度跟踪器
        progress_tracker = get_progress_tracker()
        is_new_task = task_id is None

        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask, BacktestResult
            import json

            # 初始化数据库连接
            init_database_config()
            db = SessionLocal()

            # 从配置中获取货币对列表
            symbols = backtest_config.get("symbols", ["BTCUSDT"])
            strategy_name = strategy_config.get("strategy_name", "Unknown")

            # 获取引擎类型，默认为 default
            engine_type = backtest_config.get("engine_type", "default")

            logger.info(f"=== 开始回测任务 ===")
            logger.info(f"策略名称: {strategy_name}")
            logger.info(f"回测货币对: {symbols}")
            logger.info(f"回测周期: {backtest_config.get('interval', '1d')}")
            logger.info(f"回测时间范围: {backtest_config.get('start_time')} 至 {backtest_config.get('end_time')}")
            logger.info(f"初始资金: {backtest_config.get('initial_cash', 10000)}")
            logger.info(f"手续费率: {backtest_config.get('commission', 0.001)}")
            logger.info(f"回测引擎: {engine_type}")

            # 如果没有提供task_id，则生成新的
            if is_new_task:
                task_id = str(uuid.uuid4())
                # 创建进度记录
                progress_tracker.create_progress(task_id)
            else:
                logger.info(f"使用现有任务ID: {task_id}")
                # 确保进度记录存在
                if not progress_tracker.get_progress(task_id):
                    progress_tracker.create_progress(task_id)

            progress_tracker.update_progress(
                task_id,
                "overall",
                {
                    "status": "running"
                }
            )

            # ========== 事件驱动引擎分支 ==========
            if engine_type == "event":
                logger.info(f"使用事件驱动引擎执行回测")
                return self._run_event_backtest(
                    strategy_config=strategy_config,
                    backtest_config=backtest_config,
                    task_id=task_id,
                    db=db,
                    is_new_task=is_new_task,
                    progress_tracker=progress_tracker
                )
            # ========== 事件驱动引擎分支结束 ==========

            # ========== 启动阶段错误处理 ==========
            # 尝试创建回测引擎（可能失败的第三方 API 调用）
            try:
                # 创建引擎配置
                engine_config = {
                    "engine_type": engine_type,
                    "initial_capital": backtest_config.get("initial_cash", 10000),
                    "start_date": backtest_config.get("start_time"),
                    "end_date": backtest_config.get("end_time"),
                    "symbols": symbols,
                    "strategy_config": strategy_config,
                }

                # 创建回测引擎
                self.create_engine(engine_config)
            except Exception as e:
                error_msg = str(e)
                logger.error(f"创建回测引擎失败: {error_msg}")

                # 记录失败状态到进度跟踪器
                progress_tracker.fail_progress(
                    task_id,
                    f"启动失败: {error_msg}。请检查网络连接或代理配置。",
                    "initialization"
                )

                # 更新任务状态为失败
                from datetime import datetime, timezone
                task = db.query(BacktestTask).filter(BacktestTask.id == task_id).first()
                if task:
                    task.status = "failed"
                    task.completed_at = datetime.now(timezone.utc)
                    db.commit()
                elif is_new_task:
                    # 如果是新任务且不存在，创建失败记录
                    task = BacktestTask(
                        id=task_id,
                        strategy_name=strategy_name,
                        backtest_config=json.dumps(backtest_config, default=str, ensure_ascii=False),
                        status="failed",
                        started_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc)
                    )
                    db.add(task)
                    db.commit()

                return {
                    "status": "failed",
                    "task_id": task_id,
                    "message": f"启动失败: {error_msg}。请检查网络连接或代理配置。"
                }
            # ========== 启动阶段错误处理结束 ==========

            # 更新任务状态为进行中
            from datetime import datetime, timezone
            task = db.query(BacktestTask).filter(BacktestTask.id == task_id).first()
            if task:
                task.status = "in_progress"
                db.commit()
            elif is_new_task:
                # 如果是新任务且不存在，创建任务记录
                task = BacktestTask(
                    id=task_id,
                    strategy_name=strategy_name,
                    backtest_config=json.dumps(backtest_config, default=str, ensure_ascii=False),
                    status="in_progress",
                    started_at=datetime.now(timezone.utc)
                )
                db.add(task)
                db.commit()
            
            # 限制线程数量，避免系统过载
            cpu_count = os.cpu_count() or 1
            max_workers = min(len(symbols), cpu_count * 2)
            logger.info(f"使用线程池执行回测，最大线程数: {max_workers}")
            logger.info(f"CPU核心数: {cpu_count}")
            
            # 使用线程池并行执行回测
            results = {}
            completed_count = 0
            failed_count = 0
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有回测任务
                future_to_symbol = {}
                symbol_index_map = {symbol: idx for idx, symbol in enumerate(symbols)}
                for symbol in symbols:
                    # 复制配置，替换货币对
                    single_config = backtest_config.copy()
                    single_config["symbol"] = symbol
                    del single_config["symbols"]
                    
                    logger.info(f"提交回测任务: {symbol}, task_id: {task_id}")
                    future = executor.submit(
                        self.run_single_backtest,
                        strategy_config,
                        single_config,
                        task_id,  # 传递task_id
                        symbol_index_map[symbol],  # 传递货币对索引
                        len(symbols)  # 传递总货币对数
                    )
                    future_to_symbol[future] = symbol
                
                # 收集回测结果
                total_futures = len(future_to_symbol)
                for future in concurrent.futures.as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        result = future.result(timeout=3600)  # 1小时超时
                        results[symbol] = result
                        completed_count += 1
                        
                        # 更新执行阶段进度
                        progress_tracker.update_progress(
                            task_id,
                            "execution",
                            {
                                "status": "running",
                                "current_symbol": symbol,
                                "completed_symbols": completed_count,
                                "total_symbols": total_futures,
                                "progress": (completed_count / total_futures) * 100,
                                "message": f"已完成 {completed_count}/{total_futures} 个货币对"
                            }
                        )
                        
                        logger.info(f"回测完成 [{completed_count}/{total_futures}]: {symbol}, 状态: {result.get('status')}")
                        if result.get('status') == 'success':
                            # 记录关键指标
                            for metric in result.get('metrics', []):
                                if metric['name'] == 'Return [%]':
                                    logger.info(f"货币对 {symbol} 收益率: {metric['value']}%")
                                    break
                    except concurrent.futures.TimeoutError:
                        logger.error(f"回测超时 [{completed_count + failed_count + 1}/{total_futures}]: {symbol}")
                        results[symbol] = {
                            "symbol": symbol,
                            "task_id": task_id,
                            "status": "failed",
                            "message": "回测超时"
                        }
                        failed_count += 1
                    except Exception as e:
                        logger.error(f"回测失败 [{completed_count + failed_count + 1}/{total_futures}]: {symbol}, 错误: {e}")
                        logger.exception(e)
                        results[symbol] = {
                            "symbol": symbol,
                            "task_id": task_id,
                            "status": "failed",
                            "message": str(e)
                        }
                        failed_count += 1
            
            logger.info(f"=== 所有回测任务执行完毕 ===")
            logger.info(f"总货币对数量: {len(symbols)}")
            logger.info(f"成功数量: {completed_count - failed_count}")
            logger.info(f"失败数量: {failed_count}")
            logger.info(f"完成率: {(completed_count / len(symbols)) * 100:.2f}%")
            
            # 更新执行阶段为完成
            progress_tracker.update_progress(
                task_id,
                "execution",
                {
                    "status": "completed",
                    "progress": 100.0,
                    "completed_symbols": completed_count,
                    "total_symbols": total_futures,
                    "message": "回测执行完成"
                }
            )
            
            # 更新结果统计阶段
            progress_tracker.update_progress(
                task_id,
                "analysis",
                {
                    "status": "running",
                    "progress": 50.0,
                    "message": "正在合并回测结果..."
                }
            )
            
            # 保存每个货币对的回测结果到数据库
            successful_results = []
            failed_results = []
            for symbol, result in results.items():
                if result.get('status') == 'success':
                    successful_results.append(symbol)
                    # 记录 strategy_data 信息
                    strategy_data_len = len(result.get('strategy_data', [])) if isinstance(result.get('strategy_data'), list) else 0
                    logger.info(f"[run_backtest] 保存回测结果: symbol={symbol}, strategy_data长度={strategy_data_len}")
                    # 创建回测结果记录
                    backtest_result = BacktestResult(
                        id=result['id'],
                        task_id=task_id,
                        strategy_name=strategy_name,
                        symbol=symbol,
                        metrics=json.dumps(result['metrics'], default=str, ensure_ascii=False),
                        trades=json.dumps(result['trades'], default=str, ensure_ascii=False),
                        equity_curve=json.dumps(result['equity_curve'], default=str, ensure_ascii=False),
                        strategy_data=json.dumps(result['strategy_data'], default=str, ensure_ascii=False)
                    )
                    db.add(backtest_result)
                    # 保存回测结果到文件
                    self.save_backtest_result(result['id'], result)
                else:
                    failed_results.append(symbol)
            
            # 更新回测任务状态
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            # 设置结果ID为第一个成功的回测结果ID（兼容旧版本）
            if successful_results:
                first_success_result = results[successful_results[0]]
                task.result_id = first_success_result['id']
            db.commit()
            
            # 合并回测结果
            logger.info("=== 开始合并回测结果 ===")
            merged_result = self.merge_backtest_results(results)
            merged_result['task_id'] = task_id
            logger.info("=== 回测任务全部完成 ===")
            
            # 保存合并后的回测结果到文件系统
            self.save_backtest_result(task_id, merged_result)
            
            # 检查是否有成功的回测结果
            if not successful_results:
                # 所有货币对都失败
                logger.error(f"所有货币对回测失败，任务 {task_id} 标记为失败")
                progress_tracker.fail_progress(
                    task_id,
                    f"所有货币对回测失败: {', '.join(failed_results)}",
                    "execution"
                )
                
                # 更新任务状态为失败
                task.status = "failed"
                task.completed_at = datetime.now(timezone.utc)
                db.commit()
                
                return {
                    "task_id": task_id,
                    "status": "failed",
                    "message": f"所有货币对回测失败，共 {len(failed_results)} 个失败",
                    "failed_currencies": failed_results,
                    "results": merged_result
                }
            
            # 标记任务完成
            progress_tracker.complete_progress(task_id)
            
            # 构建响应结果
            response = {
                "task_id": task_id,
                "status": "completed",
                "message": f"回测完成，共 {len(symbols)} 个货币对，{len(successful_results)} 个成功，{len(failed_results)} 个失败",
                "successful_currencies": successful_results,
                "failed_currencies": failed_results,
                "results": merged_result
            }
            
            return response
        except Exception as e:
            if db:
                db.rollback()
            logger.error(f"回测任务执行失败: {e}")
            logger.exception(e)
            # 标记任务失败
            if task_id:
                progress_tracker.fail_progress(task_id, str(e), "execution")
            return {
                "status": "failed",
                "message": str(e)
            }
        finally:
            if db:
                db.close()
    
    def stop_backtest(self, task_id: str):
        """
        终止回测任务
        
        :param task_id: 回测任务ID
        :return: 终止结果
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask
            import json
            from datetime import datetime, timezone
            
            # 初始化数据库连接
            init_database_config()
            db = SessionLocal()
            
            # 查询任务
            task = db.query(BacktestTask).filter(BacktestTask.id == task_id).first()
            
            if not task:
                return {
                    "status": "error",
                    "message": f"回测任务不存在: {task_id}"
                }
            
            if task.status != "in_progress":
                return {
                    "status": "error",
                    "message": f"回测任务当前状态为 {task.status}，无法终止"
                }
            
            # 更新任务状态为已终止
            task.status = "stopped"
            task.finished_at = datetime.now(timezone.utc)
            db.commit()
            
            logger.info(f"回测任务已终止: {task_id}")
            
            return {
                "status": "success",
                "message": "回测已终止",
                "task_id": task_id
            }
            
        except Exception as e:
            if db:
                db.rollback()
            logger.error(f"终止回测失败: {e}")
            logger.exception(e)
            return {
                "status": "error",
                "message": f"终止回测失败: {str(e)}"
            }
        finally:
            if db:
                db.close()
    
    def translate_backtest_results(self, stats):
        """
        翻译回测结果为多语言
        
        :param stats: 回测结果
        :return: 翻译后的回测结果
        """
        # 获取当前语言设置
        language = config_manager.get_config_item("general", "language", "zh-CN")
        # 使用 DataSanitizer 进行指标翻译
        data_sanitizer = DataSanitizer()
        return data_sanitizer.translate_metrics(stats, language)
    
    def analyze_backtest(self, backtest_id):
        """
        分析回测结果
        
        :param backtest_id: 回测ID
        :return: 分析结果
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestResult
            import json
            
            logger.info(f"开始分析回测结果，回测ID: {backtest_id}")
            
            # 首先尝试从文件系统加载回测结果（优先获取合并后的多货币对结果）
            result = self.load_backtest_result(backtest_id)
            
            if result:
                logger.info(f"从文件系统加载回测结果成功，回测ID: {backtest_id}")
                return {
                    "status": "success",
                    "message": "回测结果分析完成",
                    **result
                }
            
            # 如果文件系统中没有找到，再尝试从数据库加载
            logger.warning(f"回测结果在文件系统中不存在，尝试从数据库加载，回测ID: {backtest_id}")
            
            # 初始化数据库配置
            init_database_config()
            db = SessionLocal()
            
            try:
                # 从数据库中获取回测结果
                result_record = db.query(BacktestResult).filter_by(id=backtest_id).first()
                
                if not result_record:
                    return {
                        "status": "failed",
                        "message": f"回测结果不存在: {backtest_id}"
                    }
                
                # 构建回测结果
                result = {
                    "task_id": result_record.id,
                    "status": "success",
                    "message": "回测完成",
                    "strategy_name": result_record.strategy_name,
                    "backtest_config": {},  # 从回测任务中获取，这里简化处理
                    "metrics": json.loads(result_record.metrics),
                    "trades": json.loads(result_record.trades),
                    "equity_curve": json.loads(result_record.equity_curve),
                    "strategy_data": json.loads(result_record.strategy_data)
                }
                
                # 获取回测配置
                from collector.db.models import BacktestTask
                task = db.query(BacktestTask).filter_by(id=result_record.task_id).first()
                if task:
                    result["backtest_config"] = json.loads(task.backtest_config)
                
                logger.info(f"回测结果分析完成，回测ID: {backtest_id}")
                return {
                    "status": "success",
                    "message": "回测结果分析完成",
                    **result
                }
            except Exception as db_e:
                logger.error(f"从数据库获取回测结果失败: {db_e}")
                logger.exception(db_e)
                return {
                    "status": "failed",
                    "message": f"从数据库获取回测结果失败: {str(db_e)}"
                }
            finally:
                db.close()
        except Exception as e:
            logger.error(f"回测结果分析失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }
    
    def save_backtest_result(self, backtest_id, result, save_to_file: bool = False):
        """
        保存回测结果

        :param backtest_id: 回测ID
        :param result: 回测结果
        :param save_to_file: 是否保存到本地文件系统，默认False（只保存到数据库）
        :return: 是否保存成功
        """
        try:
            # 默认只保存到数据库，不写入本地文件
            if save_to_file:
                # 保存回测结果文件
                result_path = self.backtest_result_dir / f"{backtest_id}.json"

                with open(result_path, "w") as f:
                    json.dump(result, f, indent=4, default=str, ensure_ascii=False)

                logger.info(f"回测结果保存成功，回测路径: {result_path}")
            else:
                logger.info(f"回测结果已保存到数据库，未写入本地文件，回测ID: {backtest_id}")

            return True
        except Exception as e:
            logger.error(f"回测结果保存失败: {e}")
            logger.exception(e)
            return False
    
    def load_backtest_result(self, backtest_id):
        """
        加载回测结果
        
        :param backtest_id: 回测ID
        :return: 回测结果
        """
        try:
            # 加载回测结果文件
            result_path = self.backtest_result_dir / f"{backtest_id}.json"
            if not result_path.exists():
                logger.warning(f"回测结果文件不存在: {result_path}")
                return None
            
            with open(result_path, "r", encoding="utf-8") as f:
                backtest_result = json.load(f)
            
            logger.info(f"回测结果加载成功，回测路径: {result_path}")
            return backtest_result
        except Exception as e:
            logger.error(f"回测结果加载失败: {e}")
            logger.exception(e)
            return None
    
    def delete_backtest_result(self, backtest_id):
        """
        删除回测结果
        
        :param backtest_id: 回测ID
        :return: 是否删除成功
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask, BacktestResult
            
            success = False
            
            # 先从数据库中删除回测结果
            try:
                # 初始化数据库配置
                init_database_config()
                db = SessionLocal()
                
                try:
                    # 删除回测结果记录
                    result_record = db.query(BacktestResult).filter_by(id=backtest_id).first()
                    if result_record:
                        db.delete(result_record)
                        logger.info(f"从数据库删除回测结果记录成功，回测ID: {backtest_id}")
                    
                    # 删除回测任务记录
                    task = db.query(BacktestTask).filter_by(id=backtest_id).first()
                    if task:
                        db.delete(task)
                        logger.info(f"从数据库删除回测任务记录成功，回测ID: {backtest_id}")
                        success = True
                    
                    db.commit()
                except Exception as db_e:
                    db.rollback()
                    logger.error(f"从数据库删除回测结果失败: {db_e}")
                    logger.exception(db_e)
                finally:
                    db.close()
            except Exception as db_init_e:
                logger.error(f"初始化数据库失败，无法从数据库删除回测结果: {db_init_e}")
                logger.exception(db_init_e)
            
            # 然后从文件系统中删除回测结果文件
            try:
                result_path = self.backtest_result_dir / f"{backtest_id}.json"
                if result_path.exists():
                    result_path.unlink()
                    logger.info(f"从文件系统删除回测结果文件成功，回测路径: {result_path}")
                    success = True
                else:
                    logger.warning(f"回测结果文件不存在，回测ID: {backtest_id}")
            except Exception as file_e:
                logger.error(f"从文件系统删除回测结果文件失败: {file_e}")
                logger.exception(file_e)
            
            return success
        except Exception as e:
            logger.error(f"删除回测结果失败: {e}")
            logger.exception(e)
            return False
    
    def list_backtest_results(self):
        """
        列出所有回测结果
        优先从数据库获取，数据库中不存在时才尝试从文件系统获取
        
        :return: 回测结果列表
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask, BacktestResult
            import json
            
            # 初始化数据库配置
            init_database_config()
            db = SessionLocal()
            
            try:
                # 从数据库中获取回测任务列表
                tasks = db.query(BacktestTask).order_by(BacktestTask.created_at.desc()).all()
                
                backtest_list = []
                for task in tasks:
                    try:
                        # 提取关键信息
                        backtest_info = {
                            "id": task.id,
                            "strategy_name": task.strategy_name,
                            "created_at": format_datetime(task.created_at),
                            "status": task.status
                        }

                        # 优先从数据库获取回测结果
                        db_result_found = False
                        if task.status == "completed" and task.result_id:
                            logger.info(f"尝试从数据库获取回测结果，任务ID: {task.id}, result_id: {task.result_id}")
                            result = db.query(BacktestResult).filter_by(id=task.result_id).first()
                            if result and result.metrics:
                                logger.info(f"数据库加载成功，任务ID: {task.id}")
                                db_result_found = True
                                try:
                                    metrics = json.loads(result.metrics)
                                    logger.info(f"解析到的metrics: {metrics}, 任务ID: {task.id}")
                                    
                                    # 处理数组格式的metrics
                                    if isinstance(metrics, list):
                                        for metric in metrics:
                                            # 同时检查指标的key和name字段，确保在不同语言设置下都能找到正确的指标
                                            metric_key = metric.get("key", "")
                                            metric_name = metric.get("name", "")
                                            metric_value = metric.get("value", 0)
                                            
                                            logger.debug(f"检查指标 - key: {metric_key}, name: {metric_name}, value: {metric_value}, 任务ID: {task.id}")
                                            
                                            if metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率":
                                                logger.info(f"找到Return [%]指标: {metric_value}, 任务ID: {task.id}")
                                                backtest_info["total_return"] = round(float(metric_value), 2)
                                            elif metric_key == "Max. Drawdown [%]" or metric_name == "Max. Drawdown [%]" or metric_name == "最大回撤":
                                                logger.info(f"找到Max. Drawdown [%]指标: {metric_value}, 任务ID: {task.id}")
                                                backtest_info["max_drawdown"] = round(float(metric_value), 2)
                                    # 处理对象格式的metrics（兼容旧数据）
                                    elif isinstance(metrics, dict):
                                        logger.info(f"metrics为对象格式，任务ID: {task.id}")
                                        if "total_return" in metrics:
                                            backtest_info["total_return"] = round(float(metrics["total_return"]), 2)
                                        if "max_drawdown" in metrics:
                                            backtest_info["max_drawdown"] = round(float(metrics["max_drawdown"]), 2)
                                    
                                    logger.info(f"从数据库提取的指标 - total_return: {backtest_info.get('total_return')}, max_drawdown: {backtest_info.get('max_drawdown')}, 任务ID: {task.id}")
                                except Exception as e:
                                    logger.warning(f"解析数据库回测结果指标失败: {task.id}, 错误: {e}")
                                    logger.exception(e)
                            else:
                                logger.info(f"数据库中未找到回测结果或metrics为空，任务ID: {task.id}, result: {result}, metrics: {result.metrics if result else None}")
                        
                        # 如果数据库中没有找到结果，才尝试从文件系统加载
                        if not db_result_found:
                            logger.debug(f"数据库中未找到回测结果，尝试从文件系统加载，任务ID: {task.id}")
                            file_result = self.load_backtest_result(task.id)
                            if file_result:
                                logger.debug(f"文件系统加载成功，任务ID: {task.id}")
                                # 从合并结果中提取指标
                                if "summary" in file_result:
                                    logger.debug(f"回测结果包含summary字段，任务ID: {task.id}")
                                    # 多货币对回测结果
                                    if "total_return" in file_result["summary"]:
                                        logger.debug(f"summary中包含total_return: {file_result['summary']['total_return']}, 任务ID: {task.id}")
                                        # 只有当total_return不是-100.0时才使用它
                                        if float(file_result["summary"]["total_return"]) != -100.0:
                                            backtest_info["total_return"] = round(float(file_result["summary"]["total_return"]), 2)
                                    if "average_max_drawdown" in file_result["summary"]:
                                        logger.debug(f"summary中包含average_max_drawdown: {file_result['summary']['average_max_drawdown']}, 任务ID: {task.id}")
                                        backtest_info["max_drawdown"] = round(float(file_result["summary"]["average_max_drawdown"]), 2)
                                
                                # 检查是否需要从metrics或currencies部分提取指标
                                if not backtest_info.get("total_return") or not backtest_info.get("max_drawdown"):
                                    if "metrics" in file_result:
                                        logger.debug(f"回测结果包含metrics字段，任务ID: {task.id}")
                                        # 单个货币对回测结果
                                        for metric in file_result["metrics"]:
                                            # 同时检查指标的key和name字段，确保在不同语言设置下都能找到正确的指标
                                            metric_key = metric.get("key", metric.get("name", ""))
                                            metric_name = metric.get("name", "")
                                            
                                            if not backtest_info.get("total_return") and (metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率"):
                                                logger.debug(f"找到Return [%]指标: {metric['value']}, 任务ID: {task.id}")
                                                backtest_info["total_return"] = round(float(metric["value"]), 2)
                                            elif not backtest_info.get("max_drawdown") and (metric_key == "Max. Drawdown [%]" or metric_name == "Max. Drawdown [%]" or metric_name == "最大回撤"):
                                                logger.debug(f"找到Max. Drawdown [%]指标: {metric['value']}, 任务ID: {task.id}")
                                                backtest_info["max_drawdown"] = round(float(metric["value"]), 2)
                                            
                                            # 如果已经找到total_return和max_drawdown，就跳出循环
                                            if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                                break
                                    elif "currencies" in file_result:
                                        logger.debug(f"回测结果包含currencies字段，任务ID: {task.id}")
                                        # 从currencies部分的回测结果中提取指标
                                        for symbol, currency_result in file_result["currencies"].items():
                                            if currency_result.get("status") == "success" and "metrics" in currency_result:
                                                logger.debug(f"尝试从货币对 {symbol} 的回测结果中提取指标，任务ID: {task.id}")
                                                for metric in currency_result["metrics"]:
                                                    # 同时检查指标的key和name字段，确保在不同语言设置下都能找到正确的指标
                                                    metric_key = metric.get("key", metric.get("name", ""))
                                                    metric_name = metric.get("name", "")
                                                    
                                                    if not backtest_info.get("total_return") and (metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率"):
                                                        logger.debug(f"找到Return [%]指标: {metric['value']}, 任务ID: {task.id}")
                                                        backtest_info["total_return"] = round(float(metric["value"]), 2)
                                                    elif not backtest_info.get("max_drawdown") and (metric_key == "Max. Drawdown [%]" or metric_name == "Max. Drawdown [%]" or metric_name == "最大回撤"):
                                                        logger.debug(f"找到Max. Drawdown [%]指标: {metric['value']}, 任务ID: {task.id}")
                                                        backtest_info["max_drawdown"] = round(float(metric["value"]), 2)
                                                    
                                                    # 如果已经找到total_return和max_drawdown，就跳出循环
                                                    if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                                        break
                                                
                                                # 如果已经找到total_return和max_drawdown，就跳出循环
                                                if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                                    break
                            else:
                                logger.debug(f"文件系统中也未找到回测结果，任务ID: {task.id}")

                        backtest_list.append(backtest_info)
                    except Exception as e:
                        logger.error(f"解析回测任务记录失败: {task.id}, 错误: {e}")
                
                logger.info(f"从数据库获取回测结果列表成功，共 {len(backtest_list)} 个回测结果")
                return backtest_list
            except Exception as db_e:
                logger.error(f"从数据库获取回测结果列表失败: {db_e}")
                logger.exception(db_e)
                # 如果数据库查询失败，回退到从文件系统读取
                return self._list_backtest_results_from_files()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"获取回测结果列表失败: {e}")
            logger.exception(e)
            # 如果初始化数据库失败，回退到从文件系统读取
            return self._list_backtest_results_from_files()
    
    def _list_backtest_results_from_files(self):
        """
        从文件系统中列出所有回测结果（回退方案）
        
        :return: 回测结果列表
        """
        try:
            # 获取所有回测结果文件
            result_files = list(self.backtest_result_dir.glob("*.json"))
            backtest_list = []
            
            for file in result_files:
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        result = json.load(f)
                    
                    # 提取关键信息
                    backtest_info = {
                        "id": file.stem,
                        "strategy_name": result.get("strategy_name", "未知策略"),
                        "created_at": file.stem.split("_")[-1] if "_" in file.stem else file.stem,
                        "status": result.get("status", "未知状态")
                    }

                    # 优先处理多货币对回测结果
                    if "summary" in result:
                        # 多货币对回测结果
                        if "total_return" in result["summary"]:
                            # 只有当total_return不是-100.0时才使用它
                            if float(result["summary"]["total_return"]) != -100.0:
                                backtest_info["total_return"] = round(float(result["summary"]["total_return"]), 2)
                        if "average_max_drawdown" in result["summary"]:
                            backtest_info["max_drawdown"] = round(float(result["summary"]["average_max_drawdown"]), 2)
                    
                    # 检查是否需要从metrics或currencies部分提取指标
                    if not backtest_info.get("total_return") or not backtest_info.get("max_drawdown"):
                        if "metrics" in result:
                            for metric in result["metrics"]:
                                if not backtest_info.get("total_return") and (metric.get("key") == "Return [%]" or metric.get("name") == "Return [%]" or metric.get("name") == "总收益率"):
                                    backtest_info["total_return"] = round(float(metric["value"]), 2) if isinstance(metric["value"], (int, float)) else metric["value"]
                                elif not backtest_info.get("max_drawdown") and (metric.get("key") == "Max. Drawdown [%]" or metric.get("name") == "Max. Drawdown [%]" or metric.get("name") == "最大回撤"):
                                    backtest_info["max_drawdown"] = round(float(metric["value"]), 2) if isinstance(metric["value"], (int, float)) else metric["value"]
                                
                                # 如果已经找到total_return和max_drawdown，就跳出循环
                                if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                    break
                        if "currencies" in result:
                            for symbol, currency_result in result["currencies"].items():
                                if currency_result.get("status") == "success" and "metrics" in currency_result:
                                    for metric in currency_result["metrics"]:
                                        if not backtest_info.get("total_return") and (metric.get("key") == "Return [%]" or metric.get("name") == "Return [%]" or metric.get("name") == "总收益率"):
                                            backtest_info["total_return"] = round(float(metric["value"]), 2) if isinstance(metric["value"], (int, float)) else metric["value"]
                                        elif not backtest_info.get("max_drawdown") and (metric.get("key") == "Max. Drawdown [%]" or metric.get("name") == "Max. Drawdown [%]" or metric.get("name") == "最大回撤"):
                                            backtest_info["max_drawdown"] = round(float(metric["value"]), 2) if isinstance(metric["value"], (int, float)) else metric["value"]
                                        
                                        # 如果已经找到total_return和max_drawdown，就跳出循环
                                        if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                            break
                                    
                                    # 如果已经找到total_return和max_drawdown，就跳出循环
                                    if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                        break

                    backtest_list.append(backtest_info)
                except Exception as e:
                    logger.error(f"解析回测结果文件失败: {file}, 错误: {e}")
            
            # 按创建时间排序
            backtest_list.sort(key=lambda x: x["created_at"], reverse=True)
            
            logger.info(f"从文件系统获取回测结果列表成功，共 {len(backtest_list)} 个回测结果")
            return backtest_list
        except Exception as e:
            logger.error(f"从文件系统获取回测结果列表失败: {e}")
            logger.exception(e)
            return []
    
    def get_replay_data(self, backtest_id, symbol=None):
        """
        获取回放数据
        新数据格式：与回测详情接口一致，返回 trades, backtest_config, equity_curve, metrics 等
        
        :param backtest_id: 回测ID
        :param symbol: 可选，指定货币对，用于多货币对回测结果
        :return: 回放数据
        """
        try:
            logger.info(f"开始获取回放数据，回测ID: {backtest_id}, 货币对: {symbol}")
            
            # 从数据库获取回测任务和结果（与回测详情接口一致）
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask, BacktestResult
            import json
            
            init_database_config()
            db = SessionLocal()
            
            try:
                # 获取回测任务
                task = db.query(BacktestTask).filter_by(id=backtest_id).first()
                
                if not task:
                    logger.error(f"回测任务不存在，回测ID: {backtest_id}")
                    return {
                        "status": "failed",
                        "message": f"回测任务不存在: {backtest_id}"
                    }
                
                # 解析回测配置
                backtest_config = {}
                try:
                    if task.backtest_config:
                        backtest_config = json.loads(task.backtest_config)
                except Exception as e:
                    logger.warning(f"解析回测配置失败: {e}")
                
                # 获取回测结果
                result_record = db.query(BacktestResult).filter_by(task_id=backtest_id).first()
                
                metrics = []
                trades = []
                equity_curve = []
                strategy_data = []
                
                if result_record:
                    try:
                        if result_record.metrics:
                            metrics = json.loads(result_record.metrics)
                        if result_record.trades:
                            trades = json.loads(result_record.trades)
                        if result_record.equity_curve:
                            equity_curve = json.loads(result_record.equity_curve)
                        if result_record.strategy_data:
                            strategy_data = json.loads(result_record.strategy_data)
                    except Exception as e:
                        logger.warning(f"解析结果数据失败: {e}")
                
                # 构建K线数据（从strategy_data中提取）
                kline_data = []
                if strategy_data:
                    logger.info(f"从strategy_data构建K线数据，数据条数: {len(strategy_data)}")
                    for data in strategy_data:
                        # 尝试多种时间字段名
                        time_value = None
                        for time_field in ["datetime", "Open_time", "open_time", "timestamp", "time", "date"]:
                            if time_field in data and data[time_field]:
                                time_value = data[time_field]
                                break
                        
                        if not time_value:
                            continue
                        
                        # 转换为毫秒级时间戳
                        timestamp = None
                        if isinstance(time_value, (int, float)):
                            if time_value > 10000000000:
                                timestamp = int(time_value)
                            else:
                                timestamp = int(time_value * 1000)
                        else:
                            from datetime import datetime
                            try:
                                if isinstance(time_value, str):
                                    dt = datetime.fromisoformat(time_value.replace(' ', 'T'))
                                else:
                                    dt = time_value
                                timestamp = int(dt.timestamp() * 1000)
                            except Exception:
                                continue
                        
                        # 支持大小写字段名
                        open_price = float(data.get("open", data.get("Open", 0)))
                        close_price = float(data.get("close", data.get("Close", 0)))
                        high_price = float(data.get("high", data.get("High", 0)))
                        low_price = float(data.get("low", data.get("Low", 0)))
                        volume = float(data.get("volume", data.get("Volume", 0)))

                        kline_item = {
                            "timestamp": timestamp,
                            "open": open_price,
                            "close": close_price,
                            "high": high_price,
                            "low": low_price,
                            "volume": volume,
                            "turnover": 0.0
                        }
                        kline_data.append(kline_item)
                    logger.info(f"构建K线数据完成，共 {len(kline_data)} 条")
                else:
                    logger.warning(f"strategy_data 为空，尝试从数据库K线表获取数据，回测ID: {backtest_id}")
                    # 尝试从数据库K线表获取数据
                    try:
                        from collector.db.models import CryptoSpotKline
                        from datetime import datetime
                        
                        symbol = backtest_config.get("symbol", "BTCUSDT")
                        interval = backtest_config.get("interval", "15m")
                        start_time_str = backtest_config.get("start_time")
                        end_time_str = backtest_config.get("end_time")
                        
                        if start_time_str and end_time_str:
                            # 解析时间字符串
                            try:
                                start_dt = datetime.fromisoformat(start_time_str.replace(' ', 'T'))
                                end_dt = datetime.fromisoformat(end_time_str.replace(' ', 'T'))
                                
                                # 从数据库查询K线数据
                                kline_records = db.query(CryptoSpotKline).filter(
                                    CryptoSpotKline.symbol == symbol,
                                    CryptoSpotKline.interval == interval,
                                    CryptoSpotKline.timestamp >= start_dt.isoformat(),
                                    CryptoSpotKline.timestamp <= end_dt.isoformat()
                                ).order_by(CryptoSpotKline.timestamp).all()
                                
                                logger.info(f"从数据库获取到 {len(kline_records)} 条K线数据")
                                
                                for record in kline_records:
                                    try:
                                        # 解析时间戳
                                        dt = datetime.fromisoformat(record.timestamp)
                                        timestamp_ms = int(dt.timestamp() * 1000)
                                        
                                        kline_item = {
                                            "timestamp": timestamp_ms,
                                            "open": float(record.open),
                                            "close": float(record.close),
                                            "high": float(record.high),
                                            "low": float(record.low),
                                            "volume": float(record.volume),
                                            "turnover": 0.0
                                        }
                                        kline_data.append(kline_item)
                                    except Exception as e:
                                        logger.warning(f"解析K线记录失败: {e}")
                                        continue
                                
                                logger.info(f"从数据库K线表构建完成，共 {len(kline_data)} 条")
                            except Exception as e:
                                logger.warning(f"解析时间范围失败: {e}")
                    except Exception as e:
                        logger.warning(f"从数据库获取K线数据失败: {e}")
                
                
                # 构建权益数据（从equity_curve中提取）
                equity_data = []
                for equity in equity_curve:
                    equity_item = {
                        "time": equity.get("datetime", equity.get("formatted_time", "")),
                        "equity": equity.get("Equity", equity.get("equity", 0)),
                        "balance": equity.get("Balance", equity.get("balance", 0))
                    }
                    equity_data.append(equity_item)
                
                # 构建前端期望的新格式响应（与回测详情接口一致）
                replay_data = {
                    "id": task.id,
                    "strategy_name": task.strategy_name,
                    "backtest_config": backtest_config,
                    "metrics": metrics,
                    "equity_curve": equity_curve,
                    "trades": trades,
                    "kline_data": kline_data,
                    "equity_data": equity_data,
                    "status": task.status,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "metadata": {
                        "symbol": backtest_config.get("symbol", symbol or "BTCUSDT"),
                        "interval": backtest_config.get("interval", "15m"),
                        "strategy_name": task.strategy_name
                    }
                }
                
                logger.info(f"获取回放数据成功，回测ID: {backtest_id}, K线数量: {len(kline_data)}, 交易数量: {len(trades)}")
                return {
                    "status": "success",
                    "message": "获取回放数据成功",
                    "data": replay_data
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"获取回放数据失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }
    
    def get_backtest_symbols(self, backtest_id):
        """
        获取回测包含的所有货币对信息
        
        :param backtest_id: 回测ID
        :return: 货币对列表及相关元数据
        """
        try:
            logger.info(f"开始获取回测货币对列表，回测ID: {backtest_id}")
            
            # 优先从数据库查询回测结果
            try:
                from collector.db.database import SessionLocal, init_database_config
                from collector.db.models import BacktestResult
                
                # 初始化数据库配置
                init_database_config()
                db = SessionLocal()
                
                try:
                    # 首先通过 task_id 查询回测结果
                    result_record = db.query(BacktestResult).filter_by(task_id=backtest_id).first()
                    
                    # 如果通过 task_id 没找到，再尝试通过 id 查询
                    if not result_record:
                        result_record = db.query(BacktestResult).filter_by(id=backtest_id).first()
                    
                    if result_record:
                        logger.info(f"从数据库找到回测结果，回测ID: {backtest_id}, 货币对: {result_record.symbol}")
                        
                        # 将逗号分隔的货币对字符串拆分成数组
                        symbol_list = [s.strip() for s in result_record.symbol.split(',') if s.strip()]
                        
                        return {
                            "status": "success",
                            "message": "获取回测货币对列表成功",
                            "data": {
                                "symbols": symbol_list,
                                "total": len(symbol_list)
                            }
                        }
                    else:
                        logger.warning(f"数据库中未找到回测结果，回测ID: {backtest_id}")
                finally:
                    db.close()
                    
            except Exception as db_e:
                logger.warning(f"从数据库获取回测结果失败: {db_e}")
            
            # 如果数据库中没有找到，尝试从文件系统加载
            logger.info(f"尝试从文件系统加载回测结果，回测ID: {backtest_id}")
            result = self.load_backtest_result(backtest_id)
            
            if not result:
                logger.error(f"回测结果不存在（数据库和文件系统都未找到），回测ID: {backtest_id}")
                return {
                    "status": "failed",
                    "message": f"回测结果不存在: {backtest_id}"
                }
            
            symbols = []
            
            # 处理多货币对回测结果
            if "currencies" in result:
                # 多货币对回测结果，返回所有货币对
                for symbol, currency_result in result["currencies"].items():
                    symbols.append({
                        "symbol": symbol,
                        "status": currency_result.get("status", "success"),
                        "message": currency_result.get("message", "回测成功")
                    })
            else:
                # 单货币对回测结果，返回单一货币对
                symbol = result.get("backtest_config", {}).get("symbol", "BTCUSDT")
                symbols.append({
                    "symbol": symbol,
                    "status": result.get("status", "success"),
                    "message": result.get("message", "回测成功")
                })
            
            logger.info(f"获取回测货币对列表成功，回测ID: {backtest_id}, 货币对数量: {len(symbols)}")
            return {
                "status": "success",
                "message": "获取回测货币对列表成功",
                "data": {
                    "symbols": symbols,
                    "total": len(symbols)
                }
            }
        except Exception as e:
            logger.error(f"获取回测货币对列表失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }
    
    def create_executor_config(self, executor_type, params):
        """
        创建执行器配置
        
        :param executor_type: 执行器类型
        :param params: 执行器参数
        :return: 执行器配置
        """
        try:
            # 执行器类型映射
            executor_classes = {
                "simulator": "qlib.backtest.executor.SimulatorExecutor",
                "nested": "qlib.backtest.executor.NestedExecutor"
            }
            
            # 获取执行器类路径
            executor_class = executor_classes.get(executor_type)
            if not executor_class:
                logger.error(f"不支持的执行器类型: {executor_type}")
                return None
            
            # 创建执行器配置
            executor_config = {
                "class": executor_class,
                "module_path": None,
                "kwargs": params
            }
            
            logger.info(f"执行器配置创建成功，执行器类型: {executor_type}")
            return executor_config
        except Exception as e:
            logger.error(f"执行器配置创建失败: {e}")
            logger.exception(e)
            return None
