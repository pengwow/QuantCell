# 回测服务
# 实现策略回测和回测结果分析功能

import sys
import os
import json
import uuid
import concurrent.futures
from pathlib import Path
import pandas as pd
from datetime import datetime

from loguru import logger
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

# 导入现有模块
from collector.services.data_service import DataService
from strategy.service import StrategyService
from i18n.utils import load_translations


class BacktestService:
    """
    回测服务类，用于执行策略回测和分析回测结果
    """
    
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

    def _sanitize_for_json(self, data):
        """
        递归清理数据，使其可以被JSON序列化
        处理 NaT, NaN, Infinity, Timestamp 等
        """
        import numpy as np
        if isinstance(data, dict):
            return {k: self._sanitize_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._sanitize_for_json(item) for item in data]
        elif isinstance(data, (pd.Timestamp, datetime)):
            if pd.isna(data):
                return None
            return data.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(data, pd.Timedelta):
            if pd.isna(data):
                return None
            return str(data)
        elif pd.isna(data):  # Checks for NaN, NaT, None
            return None
        elif isinstance(data, float):
            if np.isinf(data):
                return None
            return data
        # Handle numpy types if necessary
        if isinstance(data, (np.integer, np.int64, np.int32)):
            return int(data)
        if isinstance(data, (np.floating, np.float64, np.float32)):
            if np.isnan(data) or np.isinf(data):
                return None
            return float(data)
            
        return data
    
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
    
    def run_single_backtest(self, strategy_config, backtest_config):
        """
        执行单个货币对的回测
        
        :param strategy_config: 策略配置
        :param backtest_config: 回测配置，包含单个货币对信息
        :return: 单个货币对的回测结果
        """
        db = None
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask, BacktestResult
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
            logger.info(f"开始回测，策略名称: {strategy_name}, 货币对: {symbol}")
            
            # 加载策略类
            strategy_class = self.load_strategy_from_file(strategy_name)
            if not strategy_class:
                return {
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
                    "status": "failed",
                    "message": f"未获取到货币对 {symbol} 的K线数据"
                }
                
            # Convert to DataFrame
            candles = pd.DataFrame(kline_data)
            
            # 转换数据格式为backtesting.py所需格式
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
            # Find max close price to ensure we can cover at least one unit if needed, 
            # though backtesting.py handles this, explicit check avoids warning.
            max_price = candles['Close'].max()
            if max_price > initial_cash:
                logger.warning(f"Initial cash ({initial_cash}) is lower than max price ({max_price}). Increasing cash to avoid warnings.")
                initial_cash = max_price * 1.1 # Add 10% buffer
            
            # 设置全局数据管理器，供策略访问
            from .strategies.base import set_data_manager
            set_data_manager(local_data_manager)
            
            # 为数据添加交易对符号属性
            candles.symbol = symbol
            
            bt = Backtest(
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
                    # In some versions of backtesting.py, it might be .df or accessible via converting to dataframe
                    try:
                        if hasattr(strategy_instance.data, 'df'):
                            strategy_data = strategy_instance.data.df.to_dict('records')
                        elif isinstance(strategy_instance.data, pd.DataFrame):
                            strategy_data = strategy_instance.data.to_dict('records')
                    except Exception as e:
                        logger.warning(f"Failed to extract strategy data: {e}")

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
            
            # 创建回测任务记录
            task = BacktestTask(
                id=backtest_id,
                strategy_name=strategy_name,
                backtest_config=json.dumps(backtest_config),
                status="completed",
                started_at=datetime.now(),
                completed_at=datetime.now()
            )
            db.add(task)
            db.commit()
            
            # 准备资金曲线数据，保留时间索引
            equity_df = stats['_equity_curve'].copy()
            equity_df.reset_index(inplace=True)
            # 重命名索引列为datetime，以匹配前端期望
            if 'index' in equity_df.columns:
                equity_df.rename(columns={'index': 'datetime'}, inplace=True)
            elif 'time' in equity_df.columns:
                equity_df.rename(columns={'time': 'datetime'}, inplace=True)
            # 如果索引有名称但不是index或time，它会自动成为列名，我们确保它是datetime
            # backtesting.py通常使用datetime索引，所以reset_index后通常是index或原名
            # 这里做一个通用处理：找到第一个列（原索引）并重命名为datetime
            if 'datetime' not in equity_df.columns and len(equity_df.columns) > 0:
                # 假设第一列是时间
                equity_df.rename(columns={equity_df.columns[0]: 'datetime'}, inplace=True)
            
            equity_curve_data = equity_df.to_dict('records')

            # 创建回测结果记录
            # 使用_sanitize_for_json处理数据，避免JSON序列化错误
            result_record = BacktestResult(
                id=backtest_id,
                task_id=backtest_id,
                strategy_name=strategy_name,
                metrics=json.dumps(self._sanitize_for_json(translated_metrics)),
                trades=json.dumps(self._sanitize_for_json(trades)),
                equity_curve=json.dumps(self._sanitize_for_json(equity_curve_data)),
                strategy_data=json.dumps(self._sanitize_for_json(strategy_data))
            )
            db.add(result_record)
            db.commit()
            
            # 更新任务的结果ID
            task.result_id = backtest_id
            db.commit()
            
            logger.info(f"回测结果已保存到数据库，回测ID: {backtest_id}")
            
            result = {
                "task_id": backtest_id,
                "status": "success",
                "message": "回测完成",
                "strategy_name": strategy_name,
                "backtest_config": backtest_config,
                "metrics": self._sanitize_for_json(translated_metrics),
                "trades": self._sanitize_for_json(trades),
                "equity_curve": self._sanitize_for_json(equity_curve_data),
                "strategy_data": self._sanitize_for_json(strategy_data)
            }
            
            # 保存回测结果到文件（兼容旧版本）
            self.save_backtest_result(backtest_id, result)
            
            logger.info(f"回测完成，策略: {strategy_name}, 货币对: {symbol}, 回测ID: {backtest_id}")
            return result
        except Exception as e:
            if db:
                db.rollback()
            logger.error(f"回测失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }
        finally:
            if db:
                db.close()
    
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
            win_rates = []
            
            for symbol, result in results.items():
                if result["status"] == "success":
                    successful_currencies.append(symbol)
                    
                    # 统计交易次数
                    total_trades += len(result["trades"])
                    
                    # 提取关键指标
                    for metric in result["metrics"]:
                        if metric["name"] == "Return [%]":
                            returns.append(metric["value"])
                        elif metric["name"] == "Max. Drawdown [%]":
                            max_drawdowns.append(metric["value"])
                        elif metric["name"] == "Sharpe Ratio":
                            sharpe_ratios.append(metric["value"])
                        elif metric["name"] == "Win Rate [%]":
                            win_rates.append(metric["value"])
            
            # 计算平均值
            average_return = sum(returns) / len(returns) if returns else 0
            average_max_drawdown = sum(max_drawdowns) / len(max_drawdowns) if max_drawdowns else 0
            average_sharpe_ratio = sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else 0
            overall_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
            
            # 生成合并后的回测ID
            merged_backtest_id = str(uuid.uuid4())
            
            # 构建合并后的回测结果
            merged_result = {
                "task_id": merged_backtest_id,
                "status": "success",
                "message": "多货币对回测完成",
                "strategy_name": base_result["strategy_name"],
                "backtest_config": base_result["backtest_config"],
                "summary": {
                    "total_currencies": len(results),
                    "successful_currencies": len(successful_currencies),
                    "average_return": round(average_return, 2),
                    "average_max_drawdown": round(average_max_drawdown, 2),
                    "average_sharpe_ratio": round(average_sharpe_ratio, 2),
                    "total_trades": total_trades,
                    "overall_win_rate": round(overall_win_rate, 2)
                },
                "currencies": results,
                "merged_equity_curve": []  # 合并后的资金曲线，后续可以实现
            }
            
            logger.info(f"回测结果合并完成，共 {len(successful_currencies)} 个货币对回测成功")
            return merged_result
        except Exception as e:
            logger.error(f"合并回测结果失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": f"合并回测结果失败: {str(e)}",
                "currencies": results
            }
    
    def run_backtest(self, strategy_config, backtest_config):
        """
        执行回测，支持多货币对并行回测
        
        :param strategy_config: 策略配置
        :param backtest_config: 回测配置，包含symbols列表
        :return: 回测结果，单个货币对返回BacktestResult，多个货币对返回MultiBacktestResult
        """
        try:
            # 从配置中获取货币对列表
            symbols = backtest_config.get("symbols", ["BTCUSDT"])
            
            logger.info(f"开始回测，策略名称: {strategy_config.get('strategy_name')}, 货币对: {symbols}")
            
            # 如果只有一个货币对，直接执行回测
            if len(symbols) == 1:
                # 复制配置，使用单个货币对
                single_config = backtest_config.copy()
                single_config["symbol"] = symbols[0]
                del single_config["symbols"]
                
                return self.run_single_backtest(strategy_config, single_config)
            
            # 多个货币对，使用并行回测
            logger.info(f"开始多货币对并行回测，共 {len(symbols)} 个货币对")
            
            # 限制线程数量，避免系统过载
            cpu_count = os.cpu_count() or 1
            max_workers = min(len(symbols), cpu_count * 2)
            logger.info(f"使用线程池执行回测，最大线程数: {max_workers}")
            
            # 使用线程池并行执行回测
            results = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有回测任务
                future_to_symbol = {}
                for symbol in symbols:
                    # 复制配置，替换货币对
                    single_config = backtest_config.copy()
                    single_config["symbol"] = symbol
                    del single_config["symbols"]
                    
                    future = executor.submit(
                        self.run_single_backtest,
                        strategy_config,
                        single_config
                    )
                    future_to_symbol[future] = symbol
                
                # 收集回测结果
                for future in concurrent.futures.as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        result = future.result(timeout=3600)  # 1小时超时
                        results[symbol] = result
                    except concurrent.futures.TimeoutError:
                        logger.error(f"货币对 {symbol} 回测超时")
                        results[symbol] = {
                            "status": "failed",
                            "message": "回测超时"
                        }
                    except Exception as e:
                        logger.error(f"货币对 {symbol} 回测失败: {e}")
                        results[symbol] = {
                            "status": "failed",
                            "message": str(e)
                        }
            
            # 合并回测结果
            merged_result = self.merge_backtest_results(results)
            return merged_result
        except Exception as e:
            logger.error(f"回测失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }
    
    def translate_backtest_results(self, stats):
        """
        翻译回测结果为多语言
        
        :param stats: 回测结果
        :return: 翻译后的回测结果
        """
        # 加载翻译
        cn_trans = load_translations('zh-CN')
        en_trans = load_translations('en-US')
        
        translated_metrics = []
        for key, value in stats.items():
            if key in ['_strategy', '_equity_curve', '_trade_list', '_trades']:
                continue
            
            # 获取翻译
            cn_name = cn_trans.get(key, key)
            en_name = en_trans.get(key, key)
            desc = cn_trans.get(f"{key}.desc", "")
            
            # 处理特殊类型的值
            if isinstance(value, pd.Timestamp):
                value = value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, pd.Timedelta):
                value = str(value)
            elif isinstance(value, (pd.Series, pd.DataFrame)):
                continue  # 跳过复杂数据结构
            
            translated_metrics.append({
                'name': key,
                'cn_name': cn_name,
                'en_name': en_name,
                'value': value,
                'description': desc
            })
        
        return translated_metrics
    
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
            
            # 初始化数据库配置
            init_database_config()
            db = SessionLocal()
            
            try:
                # 从数据库中获取回测结果
                result_record = db.query(BacktestResult).filter_by(id=backtest_id).first()
                
                if not result_record:
                    # 如果数据库中没有找到，回退到从文件系统加载
                    logger.warning(f"回测结果在数据库中不存在，尝试从文件系统加载，回测ID: {backtest_id}")
                    result = self.load_backtest_result(backtest_id)
                    if not result:
                        return {
                            "status": "failed",
                            "message": f"回测结果不存在: {backtest_id}"
                        }
                    return {
                        "status": "success",
                        "message": "回测结果分析完成",
                        **result
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
                # 如果数据库查询失败，回退到从文件系统加载
                result = self.load_backtest_result(backtest_id)
                if not result:
                    return {
                        "status": "failed",
                        "message": f"回测结果不存在: {backtest_id}"
                    }
                return {
                    "status": "success",
                    "message": "回测结果分析完成",
                    **result
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
    
    def save_backtest_result(self, backtest_id, result):
        """
        保存回测结果
        
        :param backtest_id: 回测ID
        :param result: 回测结果
        :return: 是否保存成功
        """
        try:
            # 保存回测结果文件
            result_path = self.backtest_result_dir / f"{backtest_id}.json"
            
            with open(result_path, "w") as f:
                json.dump(result, f, indent=4, default=str, ensure_ascii=False)
            
            logger.info(f"回测结果保存成功，回测路径: {result_path}")
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
                logger.error(f"回测结果文件不存在: {result_path}")
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
        
        :return: 回测结果列表
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask
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
                            "created_at": task.created_at.strftime("%Y%m%d_%H%M%S"),
                            "status": task.status
                        }

                        # 如果任务已完成，尝试获取结果指标
                        if task.status == "completed" and task.result_id:
                            from collector.db.models import BacktestResult
                            result = db.query(BacktestResult).filter_by(id=task.result_id).first()
                            if result and result.metrics:
                                try:
                                    metrics = json.loads(result.metrics)
                                    for metric in metrics:
                                        if metric["name"] == "Return [%]":
                                            backtest_info["total_return"] = round(float(metric["value"]), 2)
                                        elif metric["name"] == "Max. Drawdown [%]":
                                            backtest_info["max_drawdown"] = round(float(metric["value"]), 2)
                                except Exception as e:
                                    logger.warning(f"解析回测结果指标失败: {task.id}, 错误: {e}")

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

                    # 提取指标
                    if "metrics" in result:
                        for metric in result["metrics"]:
                            if metric.get("name") == "Return [%]":
                                backtest_info["total_return"] = round(float(metric["value"]), 2) if isinstance(metric["value"], (int, float)) else metric["value"]
                            elif metric.get("name") == "Max. Drawdown [%]":
                                backtest_info["max_drawdown"] = round(float(metric["value"]), 2) if isinstance(metric["value"], (int, float)) else metric["value"]

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
    
    def get_replay_data(self, backtest_id):
        """
        获取回放数据
        
        :param backtest_id: 回测ID
        :return: 回放数据
        """
        try:
            # 加载回测结果
            result = self.load_backtest_result(backtest_id)
            if not result:
                return {
                    "status": "failed",
                    "message": f"回测结果不存在: {backtest_id}"
                }
            
            # 准备回放数据
            replay_data = {
                "kline_data": [],
                "trade_signals": [],
                "equity_data": []
            }
            
            # 从策略数据中提取K线数据
            if "strategy_data" in result:
                for data in result["strategy_data"]:
                    kline_item = {
                        "time": data.get("datetime", data.get("Open_time", "")),
                        "open": data.get("Open", 0),
                        "high": data.get("High", 0),
                        "low": data.get("Low", 0),
                        "close": data.get("Close", 0),
                        "volume": data.get("Volume", 0)
                    }
                    replay_data["kline_data"].append(kline_item)
            
            # 从交易记录中提取交易信号
            if "trades" in result:
                for trade in result["trades"]:
                    signal_item = {
                        "time": trade.get("EntryTime", ""),
                        "type": "buy" if trade.get("Direction") == "多单" else "sell",
                        "price": trade.get("EntryPrice", 0),
                        "size": abs(trade.get("Size", 0)),
                        "trade_id": trade.get("ID", "")
                    }
                    replay_data["trade_signals"].append(signal_item)
            
            # 从资金曲线中提取权益数据
            if "equity_curve" in result:
                for equity in result["equity_curve"]:
                    equity_item = {
                        "time": equity.get("datetime", ""),
                        "equity": equity.get("Equity", 0)
                    }
                    replay_data["equity_data"].append(equity_item)
            
            logger.info(f"获取回放数据成功，回测ID: {backtest_id}")
            return {
                "status": "success",
                "message": "获取回放数据成功",
                "data": replay_data
            }
        except Exception as e:
            logger.error(f"获取回放数据失败: {e}")
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
