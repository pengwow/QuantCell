# -*- coding: utf-8 -*-
"""
回测数据完整性检查模块

提供回测数据完整性检查功能，包括：
- 时间范围完整性检查
- 数据质量验证（缺失值、异常值）
- 缺失时间段计算
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np
from loguru import logger

from collector.db.database import SessionLocal
from collector.db.models import CryptoSpotKline, CryptoFutureKline


class DataIntegrityResult:
    """数据完整性检查结果"""
    
    def __init__(self):
        self.is_complete: bool = False
        self.total_expected: int = 0
        self.total_actual: int = 0
        self.missing_count: int = 0
        self.missing_ranges: List[Tuple[datetime, datetime]] = []
        self.quality_issues: List[Dict[str, Any]] = []
        self.coverage_percent: float = 0.0
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "is_complete": self.is_complete,
            "total_expected": self.total_expected,
            "total_actual": self.total_actual,
            "missing_count": self.missing_count,
            "missing_ranges": [
                (start.isoformat(), end.isoformat()) 
                for start, end in self.missing_ranges
            ],
            "quality_issues": self.quality_issues,
            "coverage_percent": round(self.coverage_percent, 2)
        }


class DataIntegrityChecker:
    """数据完整性检查器"""
    
    # 时间周期到分钟的映射
    INTERVAL_MINUTES = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '4h': 240,
        '1d': 1440,
        '1w': 10080,
    }
    
    def __init__(self):
        self._db = None
    
    @property
    def db(self):
        """懒加载数据库会话"""
        if self._db is None:
            from collector.db.database import init_database_config, SessionLocal
            import collector.db.database as db_module
            init_database_config()
            # 通过模块访问引擎，确保获取最新值
            if db_module.engine is not None:
                self._db = SessionLocal(bind=db_module.engine)
        return self._db
    
    def __del__(self):
        """析构时关闭数据库连接"""
        if self._db is not None:
            self._db.close()
    
    def check_data_completeness(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        market_type: str = 'crypto',
        crypto_type: str = 'spot'
    ) -> DataIntegrityResult:
        """
        检查数据完整性
        
        Args:
            symbol: 交易对符号
            interval: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            market_type: 市场类型
            crypto_type: 加密货币类型
            
        Returns:
            DataIntegrityResult: 检查结果
        """
        result = DataIntegrityResult()
        
        try:
            # 1. 获取现有数据
            existing_data = self._get_existing_data(
                symbol, interval, start_time, end_time, market_type, crypto_type
            )
            
            # 2. 计算期望的数据点数量
            result.total_expected = self._calculate_expected_count(
                start_time, end_time, interval
            )
            result.total_actual = len(existing_data)
            
            # 3. 计算缺失时间段
            if existing_data.empty:
                result.missing_ranges = [(start_time, end_time)]
                result.missing_count = result.total_expected
            else:
                result.missing_ranges = self._calculate_missing_ranges(
                    existing_data, start_time, end_time, interval
                )
                result.missing_count = result.total_expected - result.total_actual
            
            # 4. 计算覆盖率
            if result.total_expected > 0:
                result.coverage_percent = (result.total_actual / result.total_expected) * 100
            
            # 5. 检查数据质量
            if not existing_data.empty:
                result.quality_issues = self._check_data_quality(existing_data)
            
            # 6. 判断是否完整
            result.is_complete = (
                result.missing_count == 0 and 
                len(result.quality_issues) == 0
            )
            
            logger.info(
                f"数据完整性检查完成: {symbol} {interval}, "
                f"覆盖率: {result.coverage_percent:.2f}%, "
                f"缺失: {result.missing_count} 条"
            )
            
        except Exception as e:
            logger.error(f"数据完整性检查失败: {e}")
            result.quality_issues.append({
                "type": "check_error",
                "message": str(e)
            })
        
        return result
    
    def _get_existing_data(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        market_type: str,
        crypto_type: str
    ) -> pd.DataFrame:
        """获取现有数据"""
        try:
            # 确保数据库会话已初始化
            if self.db is None:
                logger.error("数据库会话未初始化")
                return pd.DataFrame()
            
            # 标准化symbol格式（去除/）
            normalized_symbol = symbol.replace('/', '')
            
            # 转换时间戳为毫秒字符串（与数据库格式一致）
            start_timestamp = int(start_time.timestamp() * 1000)
            end_timestamp = int(end_time.timestamp() * 1000)
            
            if market_type == 'crypto':
                if crypto_type == 'spot':
                    model = CryptoSpotKline
                else:
                    model = CryptoFutureKline
                
                # 使用字符串比较（因为数据库中timestamp是String类型）
                query = self.db.query(model).filter(
                    model.symbol == normalized_symbol,
                    model.interval == interval,
                    model.timestamp >= str(start_timestamp),
                    model.timestamp <= str(end_timestamp)
                ).order_by(model.timestamp.asc())
                
                records = query.all()
                
                if records:
                    data = {
                        'timestamp': [int(r.timestamp) for r in records],
                        'open': [float(r.open) for r in records],
                        'high': [float(r.high) for r in records],
                        'low': [float(r.low) for r in records],
                        'close': [float(r.close) for r in records],
                        'volume': [float(r.volume) for r in records],
                    }
                    return pd.DataFrame(data)
                
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"获取现有数据失败: {e}")
            import traceback
            logger.debug(f"错误详情: {traceback.format_exc()}")
            return pd.DataFrame()
    
    def _calculate_expected_count(
        self,
        start_time: datetime,
        end_time: datetime,
        interval: str
    ) -> int:
        """计算期望的数据点数量"""
        minutes = self.INTERVAL_MINUTES.get(interval, 1)
        time_diff = end_time - start_time
        total_minutes = time_diff.total_seconds() / 60
        return int(total_minutes / minutes) + 1
    
    def _calculate_missing_ranges(
        self,
        existing_data: pd.DataFrame,
        start_time: datetime,
        end_time: datetime,
        interval: str
    ) -> List[Tuple[datetime, datetime]]:
        """计算缺失时间段"""
        missing_ranges = []
        
        if existing_data.empty:
            return [(start_time, end_time)]
        
        # 生成完整的时间序列
        minutes = self.INTERVAL_MINUTES.get(interval, 1)
        freq = f'{minutes}min'
        
        full_range = pd.date_range(
            start=start_time,
            end=end_time,
            freq=freq
        )
        
        # 获取现有数据的时间戳
        existing_timestamps = set(existing_data['timestamp'])
        
        # 找出缺失的时间点
        missing_timestamps = [
            ts for ts in full_range 
            if ts not in existing_timestamps
        ]
        
        if not missing_timestamps:
            return []
        
        # 合并连续的缺失时间点为时间段
        missing_ranges = self._merge_continuous_timestamps(
            missing_timestamps, interval
        )
        
        return missing_ranges
    
    def _merge_continuous_timestamps(
        self,
        timestamps: List[datetime],
        interval: str
    ) -> List[Tuple[datetime, datetime]]:
        """合并连续的时间戳为时间段"""
        if not timestamps:
            return []
        
        minutes = self.INTERVAL_MINUTES.get(interval, 1)
        delta = timedelta(minutes=minutes)
        
        ranges = []
        range_start = timestamps[0]
        range_end = timestamps[0]
        
        for i in range(1, len(timestamps)):
            # 检查是否连续
            if timestamps[i] - range_end <= delta * 1.5:  # 允许一点误差
                range_end = timestamps[i]
            else:
                ranges.append((range_start, range_end))
                range_start = timestamps[i]
                range_end = timestamps[i]
        
        # 添加最后一个范围
        ranges.append((range_start, range_end))
        
        return ranges
    
    def _check_data_quality(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """检查数据质量"""
        issues = []
        
        # 检查必需列
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in data.columns:
                issues.append({
                    "type": "missing_column",
                    "column": col,
                    "message": f"缺少必需列: {col}"
                })
        
        if issues:
            return issues
        
        # 检查缺失值
        for col in required_columns:
            null_count = data[col].isnull().sum()
            if null_count > 0:
                issues.append({
                    "type": "null_values",
                    "column": col,
                    "count": int(null_count),
                    "message": f"{col} 列有 {null_count} 个缺失值"
                })
        
        # 检查负数价格
        price_columns = ['open', 'high', 'low', 'close']
        for col in price_columns:
            negative_count = (data[col] < 0).sum()
            if negative_count > 0:
                issues.append({
                    "type": "negative_price",
                    "column": col,
                    "count": int(negative_count),
                    "message": f"{col} 列有 {negative_count} 个负数值"
                })
        
        # 检查价格逻辑 (high >= low, high >= open, high >= close)
        logic_errors = (
            (data['high'] < data['low']) |
            (data['high'] < data['open']) |
            (data['high'] < data['close']) |
            (data['low'] > data['open']) |
            (data['low'] > data['close'])
        )
        logic_error_count = logic_errors.sum()
        if logic_error_count > 0:
            issues.append({
                "type": "price_logic_error",
                "count": int(logic_error_count),
                "message": f"有 {logic_error_count} 条记录价格逻辑错误"
            })
        
        # 检查零成交量
        zero_volume_count = (data['volume'] == 0).sum()
        if zero_volume_count > 0:
            issues.append({
                "type": "zero_volume",
                "count": int(zero_volume_count),
                "message": f"有 {zero_volume_count} 条记录成交量为0"
            })
        
        # 检查异常涨跌幅 (>20%)
        if len(data) > 1:
            data['price_change'] = data['close'].pct_change().abs()
            abnormal_changes = (data['price_change'] > 0.2).sum()
            if abnormal_changes > 0:
                issues.append({
                    "type": "abnormal_change",
                    "count": int(abnormal_changes),
                    "message": f"有 {abnormal_changes} 条记录涨跌幅超过20%"
                })
        
        return issues
    
    def check_multi_symbol_completeness(
        self,
        symbols: List[str],
        interval: str,
        start_time: datetime,
        end_time: datetime,
        market_type: str = 'crypto',
        crypto_type: str = 'spot'
    ) -> Dict[str, DataIntegrityResult]:
        """
        检查多个交易对的数据完整性
        
        Args:
            symbols: 交易对列表
            interval: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            market_type: 市场类型
            crypto_type: 加密货币类型
            
        Returns:
            Dict[str, DataIntegrityResult]: 各交易对的检查结果
        """
        results = {}
        
        for symbol in symbols:
            logger.info(f"检查数据完整性: {symbol}")
            result = self.check_data_completeness(
                symbol, interval, start_time, end_time, 
                market_type, crypto_type
            )
            results[symbol] = result
        
        return results
