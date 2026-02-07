# -*- coding: utf-8 -*-
"""
独立数据下载器模块

提供不依赖 FastAPI 服务的数据下载功能，包括：
- 直接从币安/OKX 下载数据
- 直接保存到数据库
- 实时进度更新
- 失败重试机制
"""

import asyncio
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Tuple

import pandas as pd
from loguru import logger

from collector.crypto.binance.downloader import BinanceDownloader
from collector.base.utils import get_date_range


class StandaloneDownloadProgress:
    """独立下载进度信息"""
    
    def __init__(self, symbol: str, interval: str):
        self.symbol = symbol
        self.interval = interval
        self.status: str = "pending"  # pending, downloading, completed, failed
        self.progress: float = 0.0
        self.message: str = "等待下载"
        self.current_date: Optional[str] = None
        self.total_dates: int = 0
        self.completed_dates: int = 0
        
    def update(self, status: str = None, progress: float = None, 
               message: str = None, current_date: str = None):
        """更新进度信息"""
        if status:
            self.status = status
        if progress is not None:
            self.progress = progress
        if message:
            self.message = message
        if current_date:
            self.current_date = current_date
            self.completed_dates += 1


class StandaloneDataDownloader:
    """独立数据下载器，不依赖 FastAPI 服务"""
    
    def __init__(self):
        """初始化独立下载器"""
        self.spot_downloader = BinanceDownloader(candle_type='spot')
        self.futures_downloader = BinanceDownloader(candle_type='futures')
        
    async def download_data(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        crypto_type: str = 'spot',
        progress_callback: Optional[Callable[[StandaloneDownloadProgress], None]] = None
    ) -> bool:
        """
        直接下载数据到数据库
        
        参数：
            symbol: 交易对（如 BTCUSDT）
            interval: 时间周期（如 15m, 1h）
            start_time: 开始时间
            end_time: 结束时间
            crypto_type: 交易类型（spot/futures）
            progress_callback: 进度回调函数
            
        返回：
            bool: 是否下载成功
        """
        # 标准化symbol格式
        normalized_symbol = symbol.replace('/', '')
        
        # 选择下载器
        downloader = self.spot_downloader if crypto_type == 'spot' else self.futures_downloader
        
        # 创建进度追踪
        progress = StandaloneDownloadProgress(normalized_symbol, interval)
        progress.update(status="downloading", message="开始下载数据")
        if progress_callback:
            progress_callback(progress)
        
        try:
            # 获取日期范围
            start_date = start_time.strftime('%Y-%m-%d')
            end_date = end_time.strftime('%Y-%m-%d')
            date_range = get_date_range(start_date, end_date)
            progress.total_dates = len(date_range)
            
            logger.info(f"开始下载 {normalized_symbol} {interval} 数据，"
                       f"日期范围: {start_date} ~ {end_date}，共 {len(date_range)} 天")
            
            # 逐日下载
            success_count = 0
            for idx, date in enumerate(date_range):
                try:
                    progress.current_date = date
                    progress.update(
                        status="downloading",
                        message=f"正在下载 {date} 的数据...",
                        current_date=date
                    )
                    if progress_callback:
                        progress.progress = (idx / len(date_range)) * 100
                        progress_callback(progress)
                    
                    # 下载单日数据
                    df = await downloader.get_daily_klines(normalized_symbol, interval, date)
                    
                    if df is not None and not df.empty:
                        # 直接保存到数据库
                        self._save_to_database(df, normalized_symbol, interval, crypto_type)
                        success_count += 1
                        logger.info(f"✓ {date} 数据下载成功: {len(df)} 条")
                    else:
                        logger.warning(f"⚠ {date} 无数据")
                    
                except Exception as e:
                    logger.error(f"✗ {date} 下载失败: {e}")
                    continue
            
            # 更新最终进度
            progress.update(
                status="completed" if success_count > 0 else "failed",
                progress=100.0,
                message=f"下载完成，成功 {success_count}/{len(date_range)} 天"
            )
            if progress_callback:
                progress_callback(progress)
            
            logger.info(f"下载完成: {normalized_symbol} {interval}，"
                       f"成功 {success_count}/{len(date_range)} 天")
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"下载过程发生错误: {e}")
            progress.update(
                status="failed",
                message=f"下载失败: {e}"
            )
            if progress_callback:
                progress_callback(progress)
            return False
    
    def _save_to_database(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
        crypto_type: str
    ) -> bool:
        """
        保存数据到数据库
        
        参数：
            df: K线数据DataFrame
            symbol: 交易对
            interval: 时间周期
            crypto_type: 交易类型
            
        返回：
            bool: 是否保存成功
        """
        from collector.db.database import SessionLocal, init_database_config, engine
        from collector.db.models import CryptoSpotKline, CryptoFutureKline
        
        try:
            # 初始化数据库配置
            init_database_config()
            
            # 重新导入引擎（确保获取最新值）
            from collector.db.database import engine as db_engine
            
            # 确保引擎已创建
            if db_engine is None:
                logger.error("数据库引擎未初始化")
                return False
            
            # 创建会话（显式绑定引擎）
            db = SessionLocal(bind=db_engine)
            
            try:
                # 选择模型
                Model = CryptoSpotKline if crypto_type == 'spot' else CryptoFutureKline
                
                # 准备记录
                records = []
                for _, row in df.iterrows():
                    # 转换时间戳（毫秒）
                    timestamp_ms = int(row['open_time'])
                    
                    # 生成唯一标识符
                    unique_kline = f"{symbol}_{interval}_{timestamp_ms}"
                    
                    records.append({
                        'symbol': symbol,
                        'interval': interval,
                        'timestamp': str(timestamp_ms),
                        'open': str(row['open']),
                        'high': str(row['high']),
                        'low': str(row['low']),
                        'close': str(row['close']),
                        'volume': str(row['volume']),
                        'unique_kline': unique_kline,
                        'data_source': 'binance'
                    })
                
                # 批量保存（使用INSERT OR IGNORE避免重复）
                if records:
                    from sqlalchemy.dialects.sqlite import insert
                    
                    # 构建INSERT语句
                    stmt = insert(Model).values(records)
                    # 添加ON CONFLICT DO NOTHING子句
                    stmt = stmt.on_conflict_do_nothing(index_elements=['unique_kline'])
                    
                    db.execute(stmt)
                    db.commit()
                    logger.debug(f"保存 {len(records)} 条记录到数据库")
                    return True
                
                return False
                
            except Exception as e:
                db.rollback()
                logger.error(f"保存到数据库失败: {e}")
                return False
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"数据库操作失败: {e}")
            return False
    
    def download_sync(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        crypto_type: str = 'spot',
        progress_callback: Optional[Callable[[StandaloneDownloadProgress], None]] = None
    ) -> bool:
        """
        同步接口下载数据
        
        参数：
            symbol: 交易对
            interval: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            crypto_type: 交易类型
            progress_callback: 进度回调函数
            
        返回：
            bool: 是否下载成功
        """
        return asyncio.run(self.download_data(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            crypto_type=crypto_type,
            progress_callback=progress_callback
        ))
