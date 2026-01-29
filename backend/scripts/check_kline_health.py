#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据健康检查脚本

用于检查数据库中kline表数据的健康状况，包括完整性、连续性、有效性和唯一性检查
支持命令行调用和FastAPI调用
"""

import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/qbot')

from sqlalchemy import and_
from sqlalchemy.orm import Session

from backend.collector.db.database import SessionLocal
# 数据库连接和模型
from backend.collector.db.models import CryptoSpotKline, CryptoFutureKline, StockKline


class KlineHealthChecker:
    """K线数据健康检查类
    
    用于检查kline表数据的健康状况，包括完整性、连续性、有效性和唯一性检查
    """
    
    def __init__(self):
        """初始化健康检查器"""
        # 确保数据库配置已初始化
        from backend.collector.db.database import init_database_config
        init_database_config()
        # 初始化数据库会话
        self.db: Session = SessionLocal()
        self.results: Dict[str, Any] = {
            "summary": {},
            "details": {
                "integrity": {},
                "continuity": {},
                "validity": {},
                "uniqueness": {}
            }
        }
    
    def __del__(self):
        """关闭数据库连接"""
        if hasattr(self, 'db'):
            self.db.close()
    
    def get_kline_data(self, symbol: str, interval: str, start: Optional[datetime] = None, end: Optional[datetime] = None, market_type: str = "crypto", crypto_type: str = "spot") -> pd.DataFrame:
        """
        从数据库获取kline数据
        
        Args:
            symbol: 货币对，如BTCUSDT
            interval: 时间周期，如1m, 5m, 1h, 1d
            start: 开始时间
            end: 结束时间
            market_type: 市场类型，如crypto（加密货币）、stock（股票）、futures（期货）
            crypto_type: 加密货币类型，如spot（现货）、future（合约）
            
        Returns:
            pandas DataFrame: k线数据
        """
        # 根据市场类型和加密货币类型选择相应的模型
        KlineModel = None
        
        if market_type == "crypto":
            if crypto_type == "spot":
                KlineModel = CryptoSpotKline
            elif crypto_type == "future":
                KlineModel = CryptoFutureKline
            else:
                logger.warning(f"不支持的加密货币类型: {crypto_type}")
                return pd.DataFrame()
        elif market_type == "stock":
            KlineModel = StockKline
        else:
            logger.warning(f"不支持的市场类型: {market_type}")
            return pd.DataFrame()
        
        query = self.db.query(KlineModel)
        
        # 添加过滤条件
        query = query.filter(
            and_(
                KlineModel.symbol == symbol,
                KlineModel.interval == interval
            )
        )
        
        if start:
            query = query.filter(KlineModel.date >= start)
        
        if end:
            query = query.filter(KlineModel.date <= end)
        
        # 执行查询并转换为DataFrame
        kline_list = query.all()
        df = pd.DataFrame([{
            'id': k.id,
            'timestamp': k.timestamp,
            'open': float(k.open),
            'high': float(k.high),
            'low': float(k.low),
            'close': float(k.close),
            'volume': float(k.volume)
        } for k in kline_list])
        
        if not df.empty:
            # 按时间戳排序
            df.sort_values('timestamp', inplace=True)
        
        return df
    
    def check_integrity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查数据完整性
        
        Args:
            df: k线数据DataFrame
            
        Returns:
            Dict[str, Any]: 完整性检查结果
        """
        result = {
            "status": "pass",
            "missing_columns": [],
            "missing_values": [],
            "total_records": len(df)
        }
        
        # 检查必需列是否存在
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            result["status"] = "fail"
            result["missing_columns"] = missing_columns
        
        # 检查缺失值
        if not df.empty:
            missing_values = df.isnull().sum()
            missing_values = missing_values[missing_values > 0].to_dict()
            if missing_values:
                # 将numpy.int64转换为Python int
                missing_values = {k: int(v) for k, v in missing_values.items()}
                result["status"] = "fail"
                result["missing_values"] = missing_values
        
        return result
    
    def check_continuity(self, df: pd.DataFrame, interval: str) -> Dict[str, Any]:
        """
        检查数据连续性
        
        Args:
            df: k线数据DataFrame
            interval: 时间周期，如1m, 5m, 1h, 1d
            
        Returns:
            Dict[str, Any]: 连续性检查结果
        """
        result = {
            "status": "pass",
            "expected_records": 0,
            "actual_records": len(df),
            "missing_records": 0,
            "missing_periods": [],
            "coverage_ratio": 1.0,
            "missing_time_ranges": []
        }
        
        if df.empty:
            return result
        
        # 计算预期的时间间隔
        interval_mapping = {
            '1m': timedelta(minutes=1),
            '5m': timedelta(minutes=5),
            '15m': timedelta(minutes=15),
            '30m': timedelta(minutes=30),
            '1h': timedelta(hours=1),
            '4h': timedelta(hours=4),
            '1d': timedelta(days=1)
        }
        
        if interval not in interval_mapping:
            logger.warning(f"不支持的时间周期: {interval}")
            return result
        
        delta = interval_mapping[interval]
        
        # 生成完整的时间序列（使用timestamp字符串的数值排序）
        df_sorted = df.sort_values('timestamp')
        timestamp_numeric = pd.to_numeric(df_sorted['timestamp'], errors='coerce')
        
        if timestamp_numeric.empty:
            return result
        
        # 生成完整的时间序列
        expected_index = pd.date_range(start=timestamp_numeric.min(), end=timestamp_numeric.max(), freq=delta)
        # 将numpy.int64转换为Python int
        result["expected_records"] = int(len(expected_index))
        result["actual_records"] = int(len(df))
        
        # 计算覆盖率，转换为Python float
        if len(expected_index) > 0:
            result["coverage_ratio"] = float(len(df) / len(expected_index))
        
        # 找出缺失的时间点
        missing_periods = expected_index.difference(timestamp_numeric)
        if len(missing_periods) > 0:
            result["status"] = "fail"
            # 将numpy.int64转换为Python int
            result["missing_records"] = int(len(missing_periods))
            result["missing_periods"] = [str(period) for period in missing_periods]
            
            # 分析缺失时间段
            if len(missing_periods) > 0:
                # 排序缺失的时间点
                missing_sorted = sorted(missing_periods)
                
                # 找出连续缺失的时间段
                ranges = []
                start_range = missing_sorted[0]
                
                prev = missing_sorted[0]
                
                for period in missing_sorted[1:]:
                    # 如果当前时间与前一个时间间隔超过预期，则视为新的缺失时间段
                    if (period - prev) > delta:
                        ranges.append({
                            "start": str(start_range),
                            "end": str(prev),
                            "duration": str(prev - start_range),
                            "count": int((prev - start_range) / delta) + 1
                        })
                        start_range = period
                    prev = period
                
                # 添加最后一个时间段
                ranges.append({
                    "start": str(start_range),
                    "end": str(missing_sorted[-1]),
                    "duration": str(missing_sorted[-1] - start_range),
                    "count": int((missing_sorted[-1] - start_range) / delta) + 1
                })
                
                result["missing_time_ranges"] = ranges
        
        return result
    
    def check_coverage(self, df: pd.DataFrame, interval: str, symbol: str) -> Dict[str, Any]:
        """
        检查数据覆盖率，包括历史数据和未来数据
        
        Args:
            df: k线数据DataFrame
            interval: 时间周期，如1m, 5m, 1h, 1d
            symbol: 货币对名称
            
        Returns:
            Dict[str, Any]: 覆盖率检查结果
        """
        result = {
            "status": "pass",
            "data_start_date": None,
            "data_end_date": None,
            "expected_start_date": None,
            "expected_end_date": None,
            "missing_historical_data": False,
            "missing_future_data": False,
            "historical_gap_days": 0,
            "future_gap_days": 0
        }
        
        if df.empty:
            result["status"] = "fail"
            return result
        
        # 数据的实际起止时间
        data_start = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce').min()
        data_end = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce').max()
        result["data_start_date"] = str(data_start)
        result["data_end_date"] = str(data_end)
        
        # 计算预期的起始时间（假设应该从2023年1月1日开始）
        expected_start = datetime(2023, 1, 1)
        result["expected_start_date"] = str(expected_start)
        
        # 计算预期的结束时间（假设应该到当前时间）
        expected_end = datetime.now()
        result["expected_end_date"] = str(expected_end)
        
        # 检查是否缺少历史数据
        if data_start > expected_start:
            result["missing_historical_data"] = True
            result["historical_gap_days"] = (data_start - expected_start).days
            result["status"] = "fail"
        
        # 检查是否缺少未来数据（允许有1天的延迟）
        if expected_end - data_end > timedelta(days=1):
            result["missing_future_data"] = True
            result["future_gap_days"] = (expected_end - data_end).days
            result["status"] = "fail"
        
        return result
    
    def check_validity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查数据有效性
        
        Args:
            df: k线数据DataFrame
            
        Returns:
            Dict[str, Any]: 有效性检查结果
        """
        result = {
            "status": "pass",
            "negative_prices": [],
            "negative_volumes": [],
            "invalid_high_low": [],
            "invalid_price_logic": [],
            "abnormal_price_changes": [],
            "abnormal_volumes": [],
            "price_gaps": [],
            "total_invalid_records": 0
        }
        
        if df.empty:
            return result
        
        invalid_records = 0
        
        # 检查价格是否为负数
        negative_prices = df[(df['open'] < 0) | (df['high'] < 0) | (df['low'] < 0) | (df['close'] < 0)]
        if not negative_prices.empty:
            result["status"] = "fail"
            result["negative_prices"] = [str(idx) for idx in negative_prices.index]
            invalid_records += len(negative_prices)
        
        # 检查成交量是否为负数
        negative_volumes = df[df['volume'] < 0]
        if not negative_volumes.empty:
            result["status"] = "fail"
            result["negative_volumes"] = [str(idx) for idx in negative_volumes.index]
            invalid_records += len(negative_volumes)
        
        # 检查high是否大于等于low
        invalid_high_low = df[df['high'] < df['low']]
        if not invalid_high_low.empty:
            result["status"] = "fail"
            result["invalid_high_low"] = [str(idx) for idx in invalid_high_low.index]
            invalid_records += len(invalid_high_low)
        
        # 检查价格逻辑：high >= max(open, close) 且 low <= min(open, close)
        invalid_price_logic = df[
            (df['high'] < df[['open', 'close']].max(axis=1)) | 
            (df['low'] > df[['open', 'close']].min(axis=1))
        ]
        if not invalid_price_logic.empty:
            result["status"] = "fail"
            result["invalid_price_logic"] = [str(idx) for idx in invalid_price_logic.index]
            invalid_records += len(invalid_price_logic)
        
        # 计算涨跌幅
        df['price_change_pct'] = (df['close'] - df['close'].shift(1)) / df['close'].shift(1) * 100
        
        # 检查单日涨跌幅超过±20%
        abnormal_price_changes = df[abs(df['price_change_pct']) > 20]
        if not abnormal_price_changes.empty:
            result["status"] = "fail"
            result["abnormal_price_changes"] = [
                {
                    "timestamp": str(idx),
                    "change_pct": round(row['price_change_pct'], 2)
                }
                for idx, row in abnormal_price_changes.iterrows()
            ]
            invalid_records += len(abnormal_price_changes)
        
        # 检查成交量异常（超过过去1年平均成交量的10倍，此处简化为过去30天）
        df['volume_ma30'] = df['volume'].rolling(window=30).mean()
        abnormal_volumes = df[df['volume'] > df['volume_ma30'] * 10]
        if not abnormal_volumes.empty:
            result["status"] = "fail"
            result["abnormal_volumes"] = [
                {
                    "timestamp": str(idx),
                    "volume": row['volume'],
                    "avg_30d_volume": round(row['volume_ma30'], 2)
                }
                for idx, row in abnormal_volumes.iterrows()
                if not pd.isna(row['volume_ma30'])  # 排除ma30计算结果为NaN的情况
            ]
            invalid_records += len(result["abnormal_volumes"])
        
        # 检查非除权除息日的价格跳空异常（此处简化为跳空超过5%）
        df['open_gap_pct'] = (df['open'] - df['close'].shift(1)) / df['close'].shift(1) * 100
        price_gaps = df[abs(df['open_gap_pct']) > 5]
        if not price_gaps.empty:
            result["status"] = "fail"
            result["price_gaps"] = [
                {
                    "timestamp": str(idx),
                    "gap_pct": round(row['open_gap_pct'], 2)
                }
                for idx, row in price_gaps.iterrows()
            ]
            invalid_records += len(price_gaps)
        
        # 将numpy.int64转换为Python int
        result["total_invalid_records"] = int(invalid_records)
        
        return result
    
    def check_consistency(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查数据一致性
        
        Args:
            df: k线数据DataFrame
            
        Returns:
            Dict[str, Any]: 一致性检查结果
        """
        result = {
            "status": "pass",
            "time_format_issues": [],
            "duplicate_codes": [],
            "code_name_mismatches": [],
            "inconsistent_adj_factors": []
        }
        
        if df.empty:
            return result
        
        # 检查时间格式一致性
        try:
            # 检查timestamp列的时间格式一致性
            if 'timestamp' in df.columns:
                # 直接使用timestamp字段，不进行转换
                pass
        except Exception as e:
            result["status"] = "fail"
            result["time_format_issues"].append(f"时间格式错误: {str(e)}")
        
        # 检查标的代码一致性（如果数据包含code字段）
        if 'code' in df.columns:
            duplicate_codes = df['code'].duplicated()
            if duplicate_codes.any():
                # 将numpy.int64转换为Python int
                duplicate_count = int(duplicate_codes.sum())
                result["status"] = "fail"
                result["duplicate_codes"].append(f"存在重复代码: {duplicate_count} 条记录")
        
        # 检查复权因子一致性（如果数据包含复权因子字段）
        if 'adj_factor' in df.columns:
            # 检查复权因子是否单调变化（前复权因子应递减，后复权因子应递增）
            adj_factor_diff = df['adj_factor'].diff()
            
            # 检查是否有非单调变化
            if len(adj_factor_diff.dropna()) > 0:
                # 计算递增和递减的数量，转换为Python int
                increasing = int((adj_factor_diff > 0).sum())
                decreasing = int((adj_factor_diff < 0).sum())
                
                # 如果大部分是递增的，检查是否有递减的情况
                if increasing > decreasing * 2 and decreasing > 0:
                    result["status"] = "fail"
                    result["inconsistent_adj_factors"].append(f"复权因子存在非递增情况: {decreasing} 条记录")
                # 如果大部分是递减的，检查是否有递增的情况
                elif decreasing > increasing * 2 and increasing > 0:
                    result["status"] = "fail"
                    result["inconsistent_adj_factors"].append(f"复权因子存在非递增情况: {increasing} 条记录")
                # 如果混合情况较多，说明复权方式可能不一致
                elif increasing > 0 and decreasing > 0:
                    result["status"] = "fail"
                    result["inconsistent_adj_factors"].append(f"复权因子变化不一致: 递增 {increasing} 条，递减 {decreasing} 条")
        
        return result
    
    def check_uniqueness(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查数据唯一性
        
        Args:
            df: k线数据DataFrame
            
        Returns:
            Dict[str, Any]: 唯一性检查结果，包含重复记录的详细信息
        """
        result = {
            "status": "pass",
            "duplicate_records": 0,
            "duplicate_periods": [],
            "duplicate_code_timestamp": [],
            "duplicate_details": []
        }
        
        if df.empty:
            return result
        
        # 检查时间戳字段的重复（而不是索引的重复）
        if 'timestamp' in df.columns:
            duplicate_timestamps = df.duplicated(subset=['timestamp'], keep=False)
        else:
            return result
        
        if duplicate_timestamps.any():
            result["status"] = "fail"
            duplicate_count = int(duplicate_timestamps.sum())
            result["duplicate_records"] = duplicate_count
            
            # 获取所有重复的时间戳值
            if 'timestamp' in df.columns:
                duplicate_dates = df[duplicate_timestamps]['timestamp'].unique()
            else:
                duplicate_dates = []
            
            result["duplicate_periods"] = [str(dt) for dt in duplicate_dates]
            
            # 为每个重复的时间戳获取详细信息
            for duplicate_date in duplicate_dates:
                # 获取该时间戳下的所有记录
                if 'timestamp' in df.columns:
                    duplicate_rows = df[df['timestamp'] == duplicate_date]
                else:
                    continue
                
                # 转换为可序列化的格式
                duplicate_records = []
                for i, row in duplicate_rows.iterrows():
                    record = {
                        "id": row['id'],
                        "timestamp": str(i),
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "close": float(row['close']),
                        "volume": float(row['volume']),
                        "row_number": len(duplicate_records) + 1
                    }
                    duplicate_records.append(record)
                
                # 添加到重复详情
                result["duplicate_details"].append({
                    "group_type": "timestamp_duplicate",
                    "key": str(duplicate_date),
                    "records": duplicate_records,
                    "count": len(duplicate_records)
                })
        
        # 检查"标的代码+时间戳"唯一性（如果数据包含code字段）
        if 'code' in df.columns:
            # 找出所有重复的(code, date)组合
            duplicate_code_timestamp = df.duplicated(subset=['code', 'timestamp'], keep=False)
            if duplicate_code_timestamp.any():
                result["status"] = "fail"
                code_dup_count = int(duplicate_code_timestamp.sum())
                result["duplicate_records"] += code_dup_count
                result["duplicate_code_timestamp"].append(f"存在 {code_dup_count} 条重复的(代码+时间戳)记录")
                
                # 对于code+timestamp重复，我们已经在上面的timestamp_duplicate中处理了，这里不再重复
        
        return result
    
    def check_logic(self, df: pd.DataFrame, interval: str) -> Dict[str, Any]:
        """
        检查数据逻辑性
        
        Args:
            df: k线数据DataFrame
            interval: 时间周期，如1m, 5m, 1h, 1d
            
        Returns:
            Dict[str, Any]: 逻辑性检查结果
        """
        result = {
            "status": "pass",
            "trading_time_issues": [],
            "suspension_issues": [],
            "price_limit_issues": []
        }
        
        if df.empty:
            return result
        
        # 检查交易时间匹配（仅对日内K线）
        if interval in ['1m', '5m', '15m', '30m', '1h', '4h']:
            # 检查timestamp列是否存在
            if 'timestamp' in df.columns:
                # 直接使用timestamp字段，不进行转换
                pass
        
        # 检查停牌数据处理
        # 假设成交量为0且价格不变表示停牌
        df['price_change'] = df['close'] - df['close'].shift(1)
        potential_suspension = df[(df['volume'] == 0) & (df['price_change'] == 0)]
        
        if not potential_suspension.empty:
            # 检查停牌期间的价格字段是否完整
            suspension_missing_prices = potential_suspension[(potential_suspension['open'].isnull()) | \
                                                           (potential_suspension['high'].isnull()) | \
                                                           (potential_suspension['low'].isnull()) | \
                                                           (potential_suspension['close'].isnull())]
            
            if not suspension_missing_prices.empty:
                result["status"] = "fail"
                result["suspension_issues"].append(f"停牌期间价格字段缺失: {int(len(suspension_missing_prices))} 条记录")
        
        # 检查涨跌停规则
        # 计算涨跌幅
        df['price_change_pct'] = (df['close'] - df['close'].shift(1)) / df['close'].shift(1) * 100
        
        # 假设A股涨跌停限制为±10%
        # 注意：实际情况可能更复杂，如ST股票±5%，新股上市首日无限制等
        price_limit_issues = df[(df['price_change_pct'] > 10.1) | (df['price_change_pct'] < -10.1)]
        
        if not price_limit_issues.empty:
            result["status"] = "fail"
            result["price_limit_issues"].append(f"发现 {int(len(price_limit_issues))} 条记录超出涨跌停限制")
        
        return result
    
    def check_all(self, symbol: str, interval: str, start: Optional[datetime] = None, end: Optional[datetime] = None, market_type: str = "crypto", crypto_type: str = "spot") -> Dict[str, Any]:
        """
        执行所有健康检查
        
        Args:
            symbol: 货币对，如BTCUSDT
            interval: 时间周期，如1m, 5m, 1h, 1d
            start: 开始时间
            end: 结束时间
            market_type: 市场类型，如crypto（加密货币）、stock（股票）、futures（期货）
            crypto_type: 加密货币类型，如spot（现货）、future（合约）
            
        Returns:
            Dict[str, Any]: 所有检查结果
        """
        logger.info(f"开始检查 {symbol} {interval} 的K线数据健康状况")
        
        # 获取数据
        df = self.get_kline_data(symbol, interval, start, end, market_type, crypto_type)
        
        # 执行各项检查
        # 检查完整性
        integrity_result = self.check_integrity(df)
        # 检查连续性
        continuity_result = self.check_continuity(df, interval)
        # 检查有效性
        validity_result = self.check_validity(df)
        # 检查一致性
        consistency_result = self.check_consistency(df)
        # 检查逻辑性    
        logic_result = self.check_logic(df, interval)
        # 检查唯一性
        uniqueness_result = self.check_uniqueness(df)
        # 检查数据覆盖率
        coverage_result = self.check_coverage(df, interval, symbol)
        
        # 汇总结果
        all_checks = [integrity_result, continuity_result, validity_result, consistency_result, logic_result, uniqueness_result, coverage_result]
        overall_status = "pass" if all(check["status"] == "pass" for check in all_checks) else "fail"
        
        result = {
            "symbol": symbol,
            "interval": interval,
            "start_time": start.isoformat() if start else None,
            "end_time": end.isoformat() if end else None,
            "overall_status": overall_status,
            "checks": {
                "integrity": integrity_result,
                "continuity": continuity_result,
                "validity": validity_result,
                "consistency": consistency_result,
                "logic": logic_result,
                "uniqueness": uniqueness_result,
                "coverage": coverage_result
            },
            "total_records": len(df)
        }
        
        logger.info(f"检查完成，总体状态: {overall_status}")
        return result


# 命令行调用支持
import fire


def cli_check(symbol: str, interval: str, start: Optional[str] = None, end: Optional[str] = None, market_type: str = "crypto", crypto_type: str = "spot"):
    """
    命令行调用的健康检查函数
    
    Args:
        symbol: 货币对，如BTCUSDT
        interval: 时间周期，如1m, 5m, 1h, 1d
        start: 开始时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD
        end: 结束时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD
        market_type: 市场类型，如crypto（加密货币）、stock（股票）、futures（期货）
        crypto_type: 加密货币类型，如spot（现货）、future（合约）
        
    Returns:
        Dict[str, Any]: 健康检查结果
    """
    # 解析时间参数
    start_dt = None
    end_dt = None
    
    if start:
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError:
            try:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
            except ValueError:
                logger.error(f"无效的开始时间格式: {start}")
                return
    
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            try:
                end_dt = datetime.strptime(end, "%Y-%m-%d")
            except ValueError:
                logger.error(f"无效的结束时间格式: {end}")
                return
    
    checker = KlineHealthChecker()
    return checker.check_all(symbol, interval, start_dt, end_dt, market_type, crypto_type)


# FastAPI路由支持
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router_health = APIRouter(prefix="/api/health", tags=["health"])


class HealthCheckRequest(BaseModel):
    """健康检查请求模型"""
    symbol: str
    interval: str
    start: Optional[str] = None
    end: Optional[str] = None


@router_health.get("/check")
async def check_health_api(
    symbol: str = Query(..., description="货币对，如BTCUSDT"),
    interval: str = Query(..., description="时间周期，如1m, 5m, 1h, 1d"),
    start: Optional[str] = Query(None, description="开始时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD")
):
    """
    K线数据健康检查API
    
    用于检查数据库中kline表数据的健康状况
    """
    # 解析时间参数
    start_dt = None
    end_dt = None
    
    if start:
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError:
            try:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的开始时间格式: {start}")
    
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            try:
                end_dt = datetime.strptime(end, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的结束时间格式: {end}")
    
    checker = KlineHealthChecker()
    return checker.check_all(symbol, interval, start_dt, end_dt)


if __name__ == "__main__":
    # 命令行调用
    fire.Fire(cli_check)