#!/usr/bin/env python3
# 数据导出模块，用于将数据库中的K线数据导出到CSV文件

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from backend.collector.db.database import SessionLocal, init_database_config
from backend.collector.db.models import CryptoSpotKline, CryptoFutureKline
from backend.collector.scripts.get_data import GetData


class ExportData:
    """数据导出工具，用于将数据库中的K线数据导出到CSV文件"""
    
    def __init__(self):
        """初始化数据导出工具"""
        self.default_save_dir = Path.home() / ".qlib" / "crypto_data" / "export"
        self.get_data = GetData()
    
    def _get_db_session(self):
        """获取数据库会话
        
        Returns:
            Session: 数据库会话对象
        """
        init_database_config()
        return SessionLocal()
    
    def _get_kline_model(self, candle_type: str):
        """根据蜡烛图类型获取对应的数据库模型
        
        Args:
            candle_type: 蜡烛图类型，spot或futures
            
        Returns:
            Model: 对应的数据库模型类
        """
        if candle_type == "spot":
            return CryptoSpotKline
        elif candle_type == "futures":
            return CryptoFutureKline
        else:
            raise ValueError(f"不支持的蜡烛图类型: {candle_type}")
    
    def _query_kline_data(self, session, model, symbol: str, interval: str, start: datetime, end: datetime):
        """查询数据库中的K线数据
        
        Args:
            session: 数据库会话
            model: 数据库模型类
            symbol: 交易对
            interval: 时间间隔
            start: 开始时间
            end: 结束时间
            
        Returns:
            pd.DataFrame: 查询结果DataFrame
        """
        try:
            # 查询数据库
            query = session.query(model).filter(
                model.symbol == symbol,
                model.interval == interval,
                model.timestamp >= start,
                model.timestamp <= end
            )
            
            # 执行查询并转换为DataFrame
            df = pd.read_sql(query.statement, session.bind)
            
            if not df.empty:
                # 转换时间戳格式
                df['timestamp'] = df['timestamp']
                # 排序
                df = df.sort_values('timestamp')
                # 选择需要的列
                df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'symbol']]
            
            return df
        except Exception as e:
            logger.error(f"查询K线数据失败: {e}")
            return pd.DataFrame()
    
    def _calculate_missing_ranges(self, df: pd.DataFrame, symbol: str, interval: str, start: datetime, end: datetime):
        """计算缺失的数据范围
        
        Args:
            df: 现有数据DataFrame
            symbol: 交易对
            interval: 时间间隔
            start: 开始时间
            end: 结束时间
            
        Returns:
            List[Tuple[datetime, datetime]]: 缺失的数据范围列表
        """
        if df.empty:
            return [(start, end)]
        
        # 生成完整的日期范围
        if interval == "1d":
            freq = "D"
        elif interval == "1h":
            freq = "H"
        elif interval == "15m":
            freq = "15min"
        elif interval == "30m":
            freq = "30min"
        elif interval == "4h":
            freq = "4h"
        elif interval == "1m":
            freq = "T"
        elif interval == "5m":
            freq = "5T"
        else:
            logger.warning(f"不支持的时间间隔: {interval}，使用1天作为默认值")
            freq = "D"
        
        # 生成完整的日期索引
        full_index = pd.date_range(start=start, end=end, freq=freq)
        
        # 获取现有数据的日期索引
        existing_index = pd.DatetimeIndex(df['date'])
        
        # 找出缺失的日期
        missing_dates = full_index.difference(existing_index)
        
        if missing_dates.empty:
            return []
        
        # 将缺失的日期转换为连续的范围
        missing_ranges = []
        current_start = missing_dates[0]
        
        for i in range(1, len(missing_dates)):
            # 检查是否连续
            if (missing_dates[i] - missing_dates[i-1]).total_seconds() > pd.Timedelta(freq).total_seconds():
                # 不连续，保存当前范围
                missing_ranges.append((current_start, missing_dates[i-1]))
                current_start = missing_dates[i]
        
        # 保存最后一个范围
        missing_ranges.append((current_start, missing_dates[-1]))
        
        return missing_ranges
    
    def _download_missing_data(self, symbol: str, interval: str, missing_ranges: List[Tuple[datetime, datetime]], 
                             exchange: str = "binance", candle_type: str = "spot", max_workers: int = 1, 
                             save_dir: Optional[Path] = None):
        """下载缺失的数据
        
        Args:
            symbol: 交易对
            interval: 时间间隔
            missing_ranges: 缺失的数据范围列表
            exchange: 交易所
            candle_type: 蜡烛图类型
            max_workers: 最大工作线程数
            save_dir: 保存目录
            
        Returns:
            bool: 是否成功下载所有缺失数据
            List[Tuple[datetime, datetime]]: 下载失败的数据范围列表
        """
        failed_ranges = []
        
        for start, end in missing_ranges:
            try:
                logger.info(f"开始下载 {symbol} {interval} 缺失数据: {start} 至 {end}")
                
                # 使用现有下载功能下载缺失数据
                self.get_data.crypto(
                    exchange=exchange,
                    save_dir=str(save_dir) if save_dir else None,  # 使用指定的保存目录
                    start=start.strftime("%Y-%m-%d %H:%M:%S"),
                    end=end.strftime("%Y-%m-%d %H:%M:%S"),
                    interval=interval,
                    max_workers=max_workers,
                    candle_type=candle_type,
                    symbols=symbol,
                    # convert_to_qlib=False,  # 移除convert_to_qlib参数，该功能已移除
                    # qlib_dir=None,  # 移除qlib_dir参数，该功能已移除
                    exists_skip=False,
                    mode="full"
                )
                
                logger.info(f"成功下载 {symbol} {interval} 缺失数据: {start} 至 {end}")
            except Exception as e:
                logger.error(f"下载 {symbol} {interval} 缺失数据失败: {e}")
                failed_ranges.append((start, end))
        
        return len(failed_ranges) == 0, failed_ranges
    
    def _export_to_csv(self, df: pd.DataFrame, save_dir: Path, symbol: str, interval: str):
        """将数据导出到CSV文件
        
        Args:
            df: 要导出的数据DataFrame
            save_dir: 保存目录
            symbol: 交易对
            interval: 时间间隔
            
        Returns:
            Path: 导出的CSV文件路径
        """
        # 确保保存目录存在
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        filename = f"{symbol}_{interval}.csv"
        file_path = save_dir / filename
        
        # 导出到CSV
        df.to_csv(file_path, index=False)
        logger.info(f"成功将 {symbol} {interval} 数据导出到: {file_path}")
        
        return file_path
    
    def export_kline_data(self, symbols: List[str], interval: str, start: str, end: str, 
                         exchange: str = "binance", candle_type: str = "spot", 
                         save_dir: Optional[str] = None, max_workers: int = 1, 
                         auto_download: bool = True):
        """导出K线数据到CSV文件
        
        Args:
            symbols: 交易对列表
            interval: 时间间隔
            start: 开始时间，格式为YYYY-MM-DD或YYYY-MM-DD HH:MM:SS
            end: 结束时间，格式为YYYY-MM-DD或YYYY-MM-DD HH:MM:SS
            exchange: 交易所
            candle_type: 蜡烛图类型
            save_dir: 保存目录
            max_workers: 最大工作线程数
            auto_download: 是否自动下载缺失数据
            
        Returns:
            Dict: 导出结果，包含成功导出的文件和缺失的数据范围
        """
        # 处理保存目录
        if save_dir is None:
            save_dir = self.default_save_dir
        else:
            save_dir = Path(save_dir)
        
        # 解析时间
        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)
        
        # 结果字典
        result = {
            "success": True,
            "exported_files": [],
            "missing_ranges": {}
        }
        
        # 遍历所有交易对
        for symbol in symbols:
            logger.info(f"开始导出 {symbol} {interval} 数据")
            
            # 获取数据库会话
            session = self._get_db_session()
            try:
                # 获取对应的数据库模型
                kline_model = self._get_kline_model(candle_type)
                
                # 查询现有数据
                existing_df = self._query_kline_data(session, kline_model, symbol, interval, start_dt, end_dt)
                
                # 计算缺失的数据范围
                missing_ranges = self._calculate_missing_ranges(existing_df, symbol, interval, start_dt, end_dt)
                
                failed_ranges = []
                if missing_ranges:
                    logger.info(f"{symbol} {interval} 缺少 {len(missing_ranges)} 个数据范围")
                    
                    if auto_download:
                        # 下载缺失数据
                        success, failed_ranges = self._download_missing_data(
                            symbol=symbol, interval=interval, missing_ranges=missing_ranges,
                            exchange=exchange, candle_type=candle_type, max_workers=max_workers,
                            save_dir=save_dir  # 传递保存目录参数
                        )
                        
                        if failed_ranges:
                            logger.warning(f"{symbol} {interval} 有 {len(failed_ranges)} 个数据范围下载失败")
                    else:
                        failed_ranges = missing_ranges
                
                # 如果有下载失败的数据范围，记录下来
                if failed_ranges:
                    result["missing_ranges"][symbol] = [
                        {"start": start.strftime("%Y-%m-%d %H:%M:%S"), "end": end.strftime("%Y-%m-%d %H:%M:%S")}
                        for start, end in failed_ranges
                    ]
                
                # 重新查询数据（包括可能刚下载的数据）
                final_df = self._query_kline_data(session, kline_model, symbol, interval, start_dt, end_dt)
                
                if not final_df.empty:
                    # 导出到CSV
                    file_path = self._export_to_csv(final_df, save_dir, symbol, interval)
                    result["exported_files"].append(str(file_path))
                else:
                    logger.warning(f"{symbol} {interval} 没有数据可以导出")
                    result["success"] = False
                    
            except Exception as e:
                logger.error(f"导出 {symbol} {interval} 数据失败: {e}")
                result["success"] = False
                result["missing_ranges"][symbol] = [{"start": start, "end": end, "error": str(e)}]
            finally:
                session.close()
        
        return result


if __name__ == "__main__":
    # 配置日志格式
    logger.add(
        "data_export.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level="INFO",
        rotation="1 week",
        retention="1 month",
    )
    
    # 使用示例
    export_data = ExportData()
    result = export_data.export_kline_data(
        symbols=["BTCUSDT", "ETHUSDT"],
        interval="1d",
        start="2024-01-01",
        end="2024-12-31",
        exchange="binance",
        candle_type="spot",
        auto_download=True
    )
    
    logger.info(f"导出结果: {result}")
