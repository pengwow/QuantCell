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
from backend.collector.db.models import Kline


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
    
    def get_kline_data(self, symbol: str, interval: str, start: Optional[datetime] = None, end: Optional[datetime] = None) -> pd.DataFrame:
        """
        从数据库获取kline数据
        
        Args:
            symbol: 货币对，如BTCUSDT
            interval: 时间周期，如1m, 5m, 1h, 1d
            start: 开始时间
            end: 结束时间
            
        Returns:
            pandas DataFrame: kline数据
        """
        query = self.db.query(Kline)
        
        # 添加过滤条件
        query = query.filter(
            and_(
                Kline.symbol == symbol,
                Kline.interval == interval
            )
        )
        
        if start:
            query = query.filter(Kline.date >= start)
        
        if end:
            query = query.filter(Kline.date <= end)
        
        # 执行查询并转换为DataFrame
        kline_list = query.all()
        df = pd.DataFrame([{
            'date': k.date,
            'open': k.open,
            'high': k.high,
            'low': k.low,
            'close': k.close,
            'volume': k.volume
        } for k in kline_list])
        
        if not df.empty:
            # 设置日期为索引
            df.set_index('date', inplace=True)
            # 按日期排序
            df.sort_index(inplace=True)
        
        return df
    
    def check_integrity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查数据完整性
        
        Args:
            df: kline数据DataFrame
            
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
                result["status"] = "fail"
                result["missing_values"] = missing_values
        
        return result
    
    def check_continuity(self, df: pd.DataFrame, interval: str) -> Dict[str, Any]:
        """
        检查数据连续性
        
        Args:
            df: kline数据DataFrame
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
        
        # 生成完整的时间序列
        expected_index = pd.date_range(start=df.index.min(), end=df.index.max(), freq=delta)
        result["expected_records"] = len(expected_index)
        result["actual_records"] = len(df)
        
        # 计算覆盖率
        if len(expected_index) > 0:
            result["coverage_ratio"] = len(df) / len(expected_index)
        
        # 找出缺失的时间点
        missing_periods = expected_index.difference(df.index)
        if len(missing_periods) > 0:
            result["status"] = "fail"
            result["missing_records"] = len(missing_periods)
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
            df: kline数据DataFrame
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
        data_start = df.index.min()
        data_end = df.index.max()
        result["data_start_date"] = str(data_start)
        result["data_end_date"] = str(data_end)
        
        # 计算预期的起始时间（假设应该从2023年1月1日开始）
        expected_start = datetime(2023, 1, 1, tzinfo=data_start.tzinfo)
        result["expected_start_date"] = str(expected_start)
        
        # 计算预期的结束时间（假设应该到当前时间）
        expected_end = datetime.now(data_start.tzinfo)
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
            df: kline数据DataFrame
            
        Returns:
            Dict[str, Any]: 有效性检查结果
        """
        result = {
            "status": "pass",
            "negative_prices": [],
            "negative_volumes": [],
            "invalid_high_low": [],
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
        
        result["total_invalid_records"] = invalid_records
        
        return result
    
    def check_uniqueness(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查数据唯一性
        
        Args:
            df: kline数据DataFrame
            
        Returns:
            Dict[str, Any]: 唯一性检查结果
        """
        result = {
            "status": "pass",
            "duplicate_records": 0,
            "duplicate_periods": []
        }
        
        if df.empty:
            return result
        
        # 检查重复的索引（日期）
        duplicate_index = df.index.duplicated()
        if duplicate_index.any():
            result["status"] = "fail"
            result["duplicate_records"] = duplicate_index.sum()
            result["duplicate_periods"] = [str(idx) for idx in df.index[duplicate_index]]
        
        return result
    
    def check_all(self, symbol: str, interval: str, start: Optional[datetime] = None, end: Optional[datetime] = None) -> Dict[str, Any]:
        """
        执行所有健康检查
        
        Args:
            symbol: 货币对，如BTCUSDT
            interval: 时间周期，如1m, 5m, 1h, 1d
            start: 开始时间
            end: 结束时间
            
        Returns:
            Dict[str, Any]: 所有检查结果
        """
        logger.info(f"开始检查 {symbol} {interval} 的K线数据健康状况")
        
        # 获取数据
        df = self.get_kline_data(symbol, interval, start, end)
        
        # 执行各项检查
        integrity_result = self.check_integrity(df)
        continuity_result = self.check_continuity(df, interval)
        validity_result = self.check_validity(df)
        uniqueness_result = self.check_uniqueness(df)
        coverage_result = self.check_coverage(df, interval, symbol)
        
        # 汇总结果
        all_checks = [integrity_result, continuity_result, validity_result, uniqueness_result, coverage_result]
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
                "uniqueness": uniqueness_result,
                "coverage": coverage_result
            },
            "total_records": len(df)
        }
        
        logger.info(f"检查完成，总体状态: {overall_status}")
        return result


# 命令行调用支持
import fire


def cli_check(symbol: str, interval: str, start: Optional[str] = None, end: Optional[str] = None):
    """
    命令行调用的健康检查函数
    
    Args:
        symbol: 货币对，如BTCUSDT
        interval: 时间周期，如1m, 5m, 1h, 1d
        start: 开始时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD
        end: 结束时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD
        
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
    return checker.check_all(symbol, interval, start_dt, end_dt)


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
