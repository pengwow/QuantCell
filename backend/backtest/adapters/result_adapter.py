"""
trading engine 回测结果适配器

将 trading engine 的回测结果转换为内部格式，与 backtest/service.py 兼容。

主要功能:
    - 转换资金曲线格式
    - 转换交易记录格式
    - 转换回测指标格式

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-15
"""

import pandas as pd
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from loguru import logger


def convert_default_results(advanced_result: Any) -> Dict[str, Any]:
    """
    将 trading engine 回测结果转换为内部格式

    :param advanced_result: trading engine 回测结果对象
    :return: 内部格式的回测结果字典
    """
    try:
        logger.info("开始转换 trading engine 回测结果")

        # 初始化结果字典
        result = {
            "status": "success",
            "message": "回测完成",
            "metrics": [],
            "trades": [],
            "equity_curve": [],
            "strategy_data": []
        }

        # 转换资金曲线
        result["equity_curve"] = _convert_equity_curve(advanced_result)

        # 转换交易记录
        result["trades"] = _convert_trades(advanced_result)

        # 转换回测指标
        result["metrics"] = _convert_metrics(advanced_result)

        # 转换策略数据
        result["strategy_data"] = _convert_strategy_data(advanced_result)

        logger.info("trading engine 回测结果转换完成")
        return result

    except Exception as e:
        logger.error(f"转换 trading engine 回测结果失败: {e}")
        logger.exception(e)
        return {
            "status": "failed",
            "message": f"转换回测结果失败: {str(e)}",
            "metrics": [],
            "trades": [],
            "equity_curve": [],
            "strategy_data": []
        }


def _convert_equity_curve(advanced_result: Any) -> List[Dict[str, Any]]:
    """
    转换资金曲线格式

    advanced 格式: DataFrame with timestamp and equity columns
    内部格式: List of dicts with datetime and Equity keys

    :param advanced_result: trading engine 回测结果对象
    :return: 内部格式的资金曲线列表
    """
    equity_curve = []

    try:
        # 尝试从 advanced 结果中获取资金曲线 DataFrame
        equity_df = None

        # 尝试不同的属性名获取资金曲线
        if hasattr(advanced_result, '_equity_curve'):
            equity_df = advanced_result._equity_curve
        elif hasattr(advanced_result, 'equity_curve'):
            equity_df = advanced_result.equity_curve
        elif isinstance(advanced_result, dict) and '_equity_curve' in advanced_result:
            equity_df = advanced_result['_equity_curve']
        elif isinstance(advanced_result, dict) and 'equity_curve' in advanced_result:
            equity_df = advanced_result['equity_curve']

        if equity_df is None:
            logger.warning("未找到资金曲线数据")
            return equity_curve

        # 确保是 DataFrame
        if not isinstance(equity_df, pd.DataFrame):
            logger.warning(f"资金曲线数据类型不正确: {type(equity_df)}")
            return equity_curve

        # 转换 DataFrame 为列表格式
        # 保留时间索引作为一个字段
        df_copy = equity_df.copy()
        df_copy.reset_index(inplace=True)

        # 重命名时间列
        time_columns = ['index', 'timestamp', 'time', 'datetime', 'date']
        for col in df_copy.columns:
            if col.lower() in time_columns or isinstance(df_copy[col].iloc[0], (datetime, pd.Timestamp)):
                df_copy.rename(columns={col: 'datetime'}, inplace=True)
                break

        # 重命名权益列
        equity_columns = ['equity', 'Equity', 'balance', 'Balance', 'value', 'Value']
        for col in df_copy.columns:
            if col in equity_columns:
                if col != 'Equity':
                    df_copy.rename(columns={col: 'Equity'}, inplace=True)
                break

        # 转换为字典列表
        for _, row in df_copy.iterrows():
            record = {}

            # 处理时间字段
            if 'datetime' in row:
                time_val = row['datetime']
                if isinstance(time_val, (datetime, pd.Timestamp)):
                    record['datetime'] = time_val.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    record['datetime'] = str(time_val)

            # 处理权益字段
            if 'Equity' in row:
                record['Equity'] = float(row['Equity']) if pd.notna(row['Equity']) else 0.0
            elif 'equity' in row:
                record['Equity'] = float(row['equity']) if pd.notna(row['equity']) else 0.0

            # 添加其他可能的字段
            for col in df_copy.columns:
                if col not in record and col not in ['datetime', 'Equity', 'equity']:
                    val = row[col]
                    if isinstance(val, (datetime, pd.Timestamp)):
                        record[col] = val.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(val, pd.Timedelta):
                        record[col] = str(val)
                    elif pd.notna(val):
                        record[col] = val

            if record:
                equity_curve.append(record)

        logger.info(f"资金曲线转换完成，共 {len(equity_curve)} 条记录")

    except Exception as e:
        logger.error(f"转换资金曲线失败: {e}")
        logger.exception(e)

    return equity_curve


def _convert_trades(advanced_result: Any) -> List[Dict[str, Any]]:
    """
    转换交易记录格式

    从 advanced 结果中提取交易记录并映射到内部格式
    内部格式包含: EntryTime, ExitTime, EntryPrice, ExitPrice, Size, PnL, Direction 等

    :param advanced_result: trading engine 回测结果对象
    :return: 内部格式的交易记录列表
    """
    trades = []

    try:
        # 尝试从 advanced 结果中获取交易记录
        trades_df = None

        # 尝试不同的属性名获取交易记录
        if hasattr(advanced_result, '_trades'):
            trades_df = advanced_result._trades
        elif hasattr(advanced_result, 'trades'):
            trades_df = advanced_result.trades
        elif hasattr(advanced_result, 'trade_list'):
            trades_df = advanced_result.trade_list
        elif isinstance(advanced_result, dict) and '_trades' in advanced_result:
            trades_df = advanced_result['_trades']
        elif isinstance(advanced_result, dict) and 'trades' in advanced_result:
            trades_df = advanced_result['trades']

        if trades_df is None:
            logger.warning("未找到交易记录数据")
            return trades

        # 处理 DataFrame 格式
        if isinstance(trades_df, pd.DataFrame):
            for _, row in trades_df.iterrows():
                trade = _convert_single_trade(row)
                if trade:
                    trades.append(trade)
        # 处理列表格式
        elif isinstance(trades_df, list):
            for trade_item in trades_df:
                if isinstance(trade_item, dict):
                    trade = _convert_single_trade(trade_item)
                    if trade:
                        trades.append(trade)
                elif hasattr(trade_item, '__dict__'):
                    trade = _convert_single_trade(trade_item.__dict__)
                    if trade:
                        trades.append(trade)

        logger.info(f"交易记录转换完成，共 {len(trades)} 条记录")

    except Exception as e:
        logger.error(f"转换交易记录失败: {e}")
        logger.exception(e)

    return trades


def _convert_single_trade(trade_data: Union[pd.Series, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    转换单条交易记录

    :param trade_data: 单条交易数据 (Series 或 dict)
    :return: 内部格式的交易记录
    """
    try:
        # 统一转换为字典
        if isinstance(trade_data, pd.Series):
            trade_dict = trade_data.to_dict()
        else:
            trade_dict = dict(trade_data)

        # 字段映射表 (advanced -> 内部格式)
        field_mapping = {
            # 时间字段
            'entry_time': 'EntryTime',
            'EntryTime': 'EntryTime',
            'entry_timestamp': 'EntryTime',
            'open_time': 'EntryTime',
            'exit_time': 'ExitTime',
            'ExitTime': 'ExitTime',
            'exit_timestamp': 'ExitTime',
            'close_time': 'ExitTime',

            # 价格字段
            'entry_price': 'EntryPrice',
            'EntryPrice': 'EntryPrice',
            'entry_px': 'EntryPrice',
            'avg_entry_price': 'EntryPrice',
            'exit_price': 'ExitPrice',
            'ExitPrice': 'ExitPrice',
            'exit_px': 'ExitPrice',
            'avg_exit_price': 'ExitPrice',

            # 数量字段
            'size': 'Size',
            'Size': 'Size',
            'quantity': 'Size',
            'qty': 'Size',
            'position_size': 'Size',

            # 盈亏字段
            'pnl': 'PnL',
            'PnL': 'PnL',
            'realized_pnl': 'PnL',
            'realized_pnl_usd': 'PnL',
            'profit': 'PnL',
            'return': 'ReturnPct',
            'return_pct': 'ReturnPct',

            # 手续费字段
            'commission': 'Commission',
            'Commission': 'Commission',
            'fees': 'Commission',
            'fee': 'Commission',

            # 交易ID
            'trade_id': 'ID',
            'id': 'ID',
            'ID': 'ID',
            'order_id': 'ID',

            # 交易方向
            'side': 'Side',
            'Side': 'Side',
            'direction': 'Direction',
            'Direction': 'Direction',
        }

        # 构建内部格式的交易记录
        trade = {}

        for source_key, target_key in field_mapping.items():
            if source_key in trade_dict:
                value = trade_dict[source_key]

                # 处理时间类型
                if isinstance(value, (datetime, pd.Timestamp)):
                    value = value.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(value, pd.Timedelta):
                    value = str(value)
                elif isinstance(value, float) and pd.isna(value):
                    value = None

                # 只设置第一个匹配的值
                if target_key not in trade:
                    trade[target_key] = value

        # 如果没有 ID，生成一个
        if 'ID' not in trade:
            import uuid
            trade['ID'] = str(uuid.uuid4())

        # 推断交易方向
        if 'Direction' not in trade:
            size = trade.get('Size', 0)
            if isinstance(size, (int, float)):
                if size > 0:
                    trade['Direction'] = '多单'
                elif size < 0:
                    trade['Direction'] = '空单'
                else:
                    trade['Direction'] = '未知'

        # 如果 Side 存在但 Direction 不存在，根据 Side 推断
        if 'Direction' not in trade and 'Side' in trade:
            side = trade['Side']
            if isinstance(side, str):
                if side.upper() in ['BUY', 'LONG']:
                    trade['Direction'] = '多单'
                elif side.upper() in ['SELL', 'SHORT']:
                    trade['Direction'] = '空单'

        return trade if trade else None

    except Exception as e:
        logger.warning(f"转换单条交易记录失败: {e}")
        return None


def _convert_metrics(advanced_result: Any) -> List[Dict[str, Any]]:
    """
    转换回测指标格式

    将 advanced 指标映射到内部格式，包含 Return [%], Sharpe Ratio, Max Drawdown 等

    :param advanced_result: trading engine 回测结果对象
    :return: 内部格式的指标列表
    """
    metrics = []

    try:
        # 指标映射表 (advanced -> 内部格式)
        metric_mapping = {
            # 收益率指标
            'total_return': 'Return [%]',
            'return': 'Return [%]',
            'total_return_pct': 'Return [%]',
            'cagr': 'CAGR [%]',
            'annual_return': 'Return (Ann.) [%]',

            # 风险指标
            'sharpe_ratio': 'Sharpe Ratio',
            'sharpe': 'Sharpe Ratio',
            'sortino_ratio': 'Sortino Ratio',
            'sortino': 'Sortino Ratio',
            'calmar_ratio': 'Calmar Ratio',
            'calmar': 'Calmar Ratio',
            'max_drawdown': 'Max. Drawdown [%]',
            'max_drawdown_pct': 'Max. Drawdown [%]',
            'avg_drawdown': 'Avg. Drawdown [%]',
            'volatility': 'Volatility (Ann.) [%]',

            # 交易统计
            'total_trades': '# Trades',
            'trade_count': '# Trades',
            'num_trades': '# Trades',
            'win_rate': 'Win Rate [%]',
            'win_rate_pct': 'Win Rate [%]',
            'winning_rate': 'Win Rate [%]',
            'profit_factor': 'Profit Factor',
            'expectancy': 'Expectancy [%]',
            'avg_trade': 'Avg. Trade [%]',
            'avg_trade_return': 'Avg. Trade [%]',
            'best_trade': 'Best Trade [%]',
            'worst_trade': 'Worst Trade [%]',

            # 资金指标
            'initial_cash': 'Initial Cash',
            'equity_final': 'Equity Final [$]',
            'final_equity': 'Equity Final [$]',
            'equity_peak': 'Equity Peak [$]',
            'peak_equity': 'Equity Peak [$]',
            'total_commission': 'Commissions [$]',
            'total_fees': 'Commissions [$]',

            # 时间指标
            'start_time': 'Start',
            'end_time': 'End',
            'duration': 'Duration',
            'avg_trade_duration': 'Avg. Trade Duration',
            'max_trade_duration': 'Max. Trade Duration',

            # 其他指标
            'alpha': 'Alpha [%]',
            'beta': 'Beta',
            'sqn': 'SQN',
            'kelly_criterion': 'Kelly Criterion',
            'exposure_time': 'Exposure Time [%]',
        }

        # 从 advanced 结果中提取指标
        source_metrics = {}

        if isinstance(advanced_result, dict):
            source_metrics = advanced_result
        elif hasattr(advanced_result, '__dict__'):
            source_metrics = advanced_result.__dict__
        elif hasattr(advanced_result, '_asdict'):
            source_metrics = advanced_result._asdict()

        # 遍历源指标并进行转换
        for source_key, value in source_metrics.items():
            # 跳过内部字段和复杂数据结构
            if source_key.startswith('_') or isinstance(value, (pd.DataFrame, pd.Series)):
                continue

            # 查找映射
            target_key = metric_mapping.get(source_key, source_key)

            # 处理值类型
            metric_type = 'string'
            processed_value = value

            if isinstance(value, (datetime, pd.Timestamp)):
                processed_value = value.strftime('%Y-%m-%d %H:%M:%S')
                metric_type = 'datetime'
            elif isinstance(value, pd.Timedelta):
                processed_value = str(value)
                metric_type = 'duration'
            elif isinstance(value, (int, float)):
                if pd.isna(value):
                    processed_value = None
                else:
                    # 根据指标名称判断类型
                    if '[%]' in target_key:
                        metric_type = 'percentage'
                    elif '[$]' in target_key:
                        metric_type = 'currency'
                    else:
                        metric_type = 'number'

            # 构建指标记录
            metric = {
                'name': target_key,
                'key': target_key,
                'value': processed_value,
                'description': target_key,
                'type': metric_type
            }

            metrics.append(metric)

        # 如果没有找到标准指标，尝试计算一些基本指标
        if not metrics:
            metrics = _calculate_basic_metrics(advanced_result)

        logger.info(f"指标转换完成，共 {len(metrics)} 个指标")

    except Exception as e:
        logger.error(f"转换指标失败: {e}")
        logger.exception(e)

    return metrics


def _calculate_basic_metrics(advanced_result: Any) -> List[Dict[str, Any]]:
    """
    计算基本回测指标

    当无法从 advanced 结果中提取指标时，尝试计算一些基本指标

    :param advanced_result: trading engine 回测结果对象
    :return: 基本指标列表
    """
    metrics = []

    try:
        # 尝试获取资金曲线计算收益率
        equity_curve = _convert_equity_curve(advanced_result)
        if equity_curve:
            first_equity = equity_curve[0].get('Equity', 0)
            last_equity = equity_curve[-1].get('Equity', 0)

            if first_equity and first_equity > 0:
                total_return = ((last_equity - first_equity) / first_equity) * 100
                metrics.append({
                    'name': 'Return [%]',
                    'key': 'Return [%]',
                    'value': round(total_return, 2),
                    'description': '总收益率',
                    'type': 'percentage'
                })

        # 尝试获取交易记录计算胜率
        trades = _convert_trades(advanced_result)
        if trades:
            winning_trades = [t for t in trades if t.get('PnL', 0) > 0]
            win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0

            metrics.append({
                'name': '# Trades',
                'key': '# Trades',
                'value': len(trades),
                'description': '交易次数',
                'type': 'number'
            })

            metrics.append({
                'name': 'Win Rate [%]',
                'key': 'Win Rate [%]',
                'value': round(win_rate, 2),
                'description': '胜率',
                'type': 'percentage'
            })

    except Exception as e:
        logger.warning(f"计算基本指标失败: {e}")

    return metrics


def _convert_strategy_data(advanced_result: Any) -> List[Dict[str, Any]]:
    """
    转换策略数据

    从 advanced 结果中提取策略相关的数据（如 K 线数据、指标数据等）

    :param advanced_result: trading engine 回测结果对象
    :return: 策略数据列表
    """
    strategy_data = []

    try:
        # 尝试从 advanced 结果中获取策略数据
        data = None

        if hasattr(advanced_result, '_strategy'):
            strategy = advanced_result._strategy
            if hasattr(strategy, 'data'):
                data = strategy.data
        elif hasattr(advanced_result, 'strategy_data'):
            data = advanced_result.strategy_data
        elif isinstance(advanced_result, dict) and 'strategy_data' in advanced_result:
            data = advanced_result['strategy_data']

        if data is None:
            return strategy_data

        # 处理 DataFrame 格式
        if isinstance(data, pd.DataFrame):
            df_copy = data.copy()
            df_copy.reset_index(inplace=True)

            # 重命名时间列
            for col in df_copy.columns:
                if col.lower() in ['index', 'timestamp', 'time', 'datetime', 'date']:
                    if col != 'datetime':
                        df_copy.rename(columns={col: 'datetime'}, inplace=True)
                    break

            # 标准化 OHLCV 列名
            column_mapping = {
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume',
                'Open': 'Open',
                'High': 'High',
                'Low': 'Low',
                'Close': 'Close',
                'Volume': 'Volume',
            }

            for old_col, new_col in column_mapping.items():
                if old_col in df_copy.columns and old_col != new_col:
                    df_copy.rename(columns={old_col: new_col}, inplace=True)

            # 转换为字典列表
            for _, row in df_copy.iterrows():
                record = {}
                for col in df_copy.columns:
                    value = row[col]
                    if isinstance(value, (datetime, pd.Timestamp)):
                        record[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(value, pd.Timedelta):
                        record[col] = str(value)
                    elif pd.notna(value):
                        record[col] = value
                    else:
                        record[col] = None

                if record:
                    strategy_data.append(record)

        # 处理列表格式
        elif isinstance(data, list):
            strategy_data = data

        logger.info(f"策略数据转换完成，共 {len(strategy_data)} 条记录")

    except Exception as e:
        logger.error(f"转换策略数据失败: {e}")
        logger.exception(e)

    return strategy_data


def sanitize_for_json(data: Any) -> Any:
    """
    递归清理数据，使其可以被 JSON 序列化

    处理 NaT, NaN, Infinity, Timestamp 等

    :param data: 需要清理的数据
    :return: 清理后的数据
    """
    import numpy as np

    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_for_json(item) for item in data]
    elif isinstance(data, (pd.Timestamp, datetime)):
        if pd.isna(data):
            return None
        return data.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(data, pd.Timedelta):
        if pd.isna(data):
            return None
        return str(data)
    elif pd.isna(data):
        return None
    elif isinstance(data, float):
        if np.isinf(data):
            return None
        return data
    elif isinstance(data, (np.integer, np.int64, np.int32)):
        return int(data)
    elif isinstance(data, (np.floating, np.float64, np.float32)):
        if np.isnan(data) or np.isinf(data):
            return None
        return float(data)

    return data
