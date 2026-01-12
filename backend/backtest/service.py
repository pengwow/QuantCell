# 回测服务
# 实现策略回测和回测结果分析功能

import sys
import os
import json
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
        
        # 指标翻译映射
        self.translations = {
            # 基础指标
            'Start': {'cn': '起始时间', 'en': 'Start', 'desc': '回测开始时间'}, 
            'End': {'cn': '结束时间', 'en': 'End', 'desc': '回测结束时间'}, 
            'Duration': {'cn': '策略运行时间', 'en': 'Duration', 'desc': '反映策略回测的时间跨度'}, 
            'Exposure Time [%]': {'cn': '持仓时间百分比', 'en': 'Exposure Time [%]', 'desc': '策略在回测期间平均持仓时间占比'}, 
            'Equity Final [$]': {'cn': '最终权益', 'en': 'Equity Final [$]', 'desc': '策略最终资产价值'}, 
            'Equity Peak [$]': {'cn': '权益峰值', 'en': 'Equity Peak [$]', 'desc': '策略历史最高资产值'}, 
            'Commissions [$]': {'cn': '手续费', 'en': 'Commissions [$]', 'desc': '策略交易中的手续费成本'}, 
            # 收益与风险指标
            'Return [%]': {'cn': '总收益率', 'en': 'Return [%]', 'desc': '策略总收益率'}, 
            'Return (Ann.) [%]': {'cn': '年化收益率', 'en': 'Return (Ann.) [%]', 'desc': '扣除时间后的年均收益'}, 
            'Buy & Hold Return [%]': {'cn': '买入持有收益率', 'en': 'Buy & Hold Return [%]', 'desc': '不进行交易的基准收益率'}, 
            'Volatility (Ann.) [%]': {'cn': '年化波动率', 'en': 'Volatility (Ann.) [%]', 'desc': '衡量收益的波动程度'}, 
            'CAGR [%]': {'cn': '复合年化增长率', 'en': 'CAGR [%]', 'desc': '剔除波动后的平滑收益'}, 
            'Sharpe Ratio': {'cn': '夏普比率', 'en': 'Sharpe Ratio', 'desc': '衡量单位风险下的超额收益'}, 
            'Sortino Ratio': {'cn': '索提诺比率', 'en': 'Sortino Ratio', 'desc': '仅考虑下行风险后的收益比'}, 
            'Calmar Ratio': {'cn': '卡尔马比率', 'en': 'Calmar Ratio', 'desc': '收益与最大回撤的比值'}, 
            # 策略性能指标
            'Alpha [%]': {'cn': '阿尔法系数', 'en': 'Alpha [%]', 'desc': '策略相对于基准的超额收益'}, 
            'Beta': {'cn': '贝塔系数', 'en': 'Beta', 'desc': '衡量策略收益与市场收益的相关性'}, 
            'Max. Drawdown [%]': {'cn': '最大回撤', 'en': 'Max. Drawdown [%]', 'desc': '策略从峰值到谷底的跌幅'}, 
            'Avg. Drawdown [%]': {'cn': '平均回撤', 'en': 'Avg. Drawdown [%]', 'desc': '策略历史最大回撤的平均值'}, 
            'Profit Factor': {'cn': '利润因子', 'en': 'Profit Factor', 'desc': '盈利交易总收益与亏损交易总损失的比值'}, 
            'Win Rate [%]': {'cn': '胜率', 'en': 'Win Rate [%]', 'desc': '盈利交易占比'}, 
            'Expectancy [%]': {'cn': '期望值', 'en': 'Expectancy [%]', 'desc': '单次交易的平均收益'}, 
            # 交易行为指标
            '# Trades': {'cn': '交易次数', 'en': '# Trades', 'desc': '策略交易的总次数'}, 
            'Best Trade [%]': {'cn': '最佳交易', 'en': 'Best Trade [%]', 'desc': '单笔交易的最大盈利百分比'}, 
            'Worst Trade [%]': {'cn': '最差交易', 'en': 'Worst Trade [%]', 'desc': '单笔交易的最大亏损百分比'}, 
            'Avg. Trade [%]': {'cn': '平均交易收益率', 'en': 'Avg. Trade [%]', 'desc': '所有交易的平均盈利百分比'}, 
            'Max. Trade Duration': {'cn': '最大持仓时间', 'en': 'Max. Trade Duration', 'desc': '单笔交易的最长持仓时间'}, 
            'Avg. Trade Duration': {'cn': '平均持仓时间', 'en': 'Avg. Trade Duration', 'desc': '所有交易的平均持仓时间'}, 
            'Max. Drawdown Duration': {'cn': '最大回撤时长', 'en': 'Max. Drawdown Duration', 'desc': '最大回撤持续的时间'}, 
            'Avg. Drawdown Duration': {'cn': '平均回撤时长', 'en': 'Avg. Drawdown Duration', 'desc': '平均回撤持续的时间'}, 
            'SQN': {'cn': '系统质量数', 'en': 'SQN', 'desc': '衡量交易系统质量的综合指标'}, 
            'Kelly Criterion': {'cn': '凯利准则', 'en': 'Kelly Criterion', 'desc': '优化资金分配比例的指标'}
        }
    
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
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask, BacktestResult
            import json
            
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
            self.data_manager.preload_data(
                symbol=symbol,
                base_interval=interval,
                start_time=start_time,
                end_time=end_time,
                preload_intervals=['1m', '5m', '15m', '30m', '1h', '4h', '1d']  # 预加载常用周期
            )
            
            # 获取主周期K线数据
            logger.info(f"获取主周期 {interval} 的K线数据")
            
            # 使用数据服务获取K线数据
            candles = self.data_service.get_kline_data(
                exchange="binance",
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time
            )
            
            if candles.empty:
                logger.error(f"未获取到K线数据: {symbol}, {interval}, {start_time} to {end_time}")
                return {
                    "status": "failed",
                    "message": f"未获取到货币对 {symbol} 的K线数据"
                }
            
            # 转换数据格式为backtesting.py所需格式
            candles.rename(columns={
                'open': 'Open',
                'close': 'Close',
                'high': 'High',
                'low': 'Low',
                'volume': 'Volume'
            }, inplace=True)
            
            # 设置时间索引
            if 'datetime' in candles.columns:
                candles.set_index('datetime', inplace=True)
            elif 'open_time' in candles.columns:
                candles['open_time'] = pd.to_datetime(candles['open_time'])
                candles.set_index('open_time', inplace=True)
            
            # 初始化回测
            initial_cash = backtest_config.get("initial_cash", 10000)
            commission = backtest_config.get("commission", 0.001)
            
            # 设置全局数据管理器，供策略访问
            from .strategies.base import set_data_manager
            set_data_manager(self.data_manager)
            
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
            if hasattr(bt, '_strategy') and hasattr(bt._strategy, 'data'):
                strategy_data = bt._strategy.data.df.to_dict('records')
            
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
            
            # 生成回测ID
            backtest_id = f"{strategy_name}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 初始化数据库配置
            init_database_config()
            db = SessionLocal()
            
            try:
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
                
                # 创建回测结果记录
                result_record = BacktestResult(
                    id=backtest_id,
                    task_id=backtest_id,
                    strategy_name=strategy_name,
                    metrics=json.dumps(translated_metrics),
                    trades=json.dumps(trades),
                    equity_curve=json.dumps(stats['_equity_curve'].to_dict('records')),
                    strategy_data=json.dumps(strategy_data)
                )
                db.add(result_record)
                db.commit()
                
                # 更新任务的结果ID
                task.result_id = backtest_id
                db.commit()
                
                logger.info(f"回测结果已保存到数据库，回测ID: {backtest_id}")
            except Exception as db_e:
                db.rollback()
                logger.error(f"保存回测结果到数据库失败: {db_e}")
                logger.exception(db_e)
            finally:
                db.close()
            
            result = {
                "task_id": backtest_id,
                "status": "success",
                "message": "回测完成",
                "strategy_name": strategy_name,
                "backtest_config": backtest_config,
                "metrics": translated_metrics,
                "trades": trades,
                "equity_curve": stats['_equity_curve'].to_dict('records'),
                "strategy_data": strategy_data
            }
            
            # 保存回测结果到文件（兼容旧版本）
            self.save_backtest_result(backtest_id, result)
            
            logger.info(f"回测完成，策略: {strategy_name}, 货币对: {symbol}, 回测ID: {backtest_id}")
            return result
        except Exception as e:
            logger.error(f"回测失败: {e}")
            logger.exception(e)
            return {
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
            merged_backtest_id = f"{base_result['strategy_name']}_multi_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
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
            max_workers = min(len(symbols), os.cpu_count() * 2)
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
        translated_metrics = []
        for key, value in stats.items():
            if key in ['_strategy', '_equity_curve', '_trade_list', '_trades']:
                continue
            
            # 翻译指标
            translation = self.translations.get(key, {'cn': key, 'en': key, 'desc': ''})
            
            # 处理特殊类型的值
            if isinstance(value, pd.Timestamp):
                value = value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, pd.Timedelta):
                value = str(value)
            elif isinstance(value, (pd.Series, pd.DataFrame)):
                continue  # 跳过复杂数据结构
            
            translated_metrics.append({
                'name': key,
                'cn_name': translation['cn'],
                'en_name': translation['en'],
                'value': value,
                'description': translation['desc']
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
