# -*- coding: utf-8 -*-
"""
回测数据下载协调模块

提供回测数据下载协调功能，包括：
- 缺失数据下载
- 下载进度跟踪
- 下载结果验证
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Callable
from loguru import logger

from collector.services.data_service import DataService
from collector.schemas.data import DownloadCryptoRequest
from collector.utils.task_manager import task_manager
from backtest.data_integrity import DataIntegrityChecker, DataIntegrityResult


class DownloadProgress:
    """下载进度信息"""
    
    def __init__(self, task_id: str, symbol: str, interval: str):
        self.task_id = task_id
        self.symbol = symbol
        self.interval = interval
        self.status: str = "pending"  # pending, downloading, completed, failed
        self.progress: float = 0.0
        self.message: str = "等待下载"
        self.created_at: datetime = datetime.now()
        self.updated_at: datetime = datetime.now()
        self.error: Optional[str] = None
        
    def update(self, status: str = None, progress: float = None, message: str = None, error: str = None):
        """更新进度信息"""
        if status:
            self.status = status
        if progress is not None:
            self.progress = progress
        if message:
            self.message = message
        if error:
            self.error = error
        self.updated_at = datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "symbol": self.symbol,
            "interval": self.interval,
            "status": self.status,
            "progress": round(self.progress, 2),
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error": self.error
        }


class BacktestDataDownloader:
    """回测数据下载协调器"""
    
    def __init__(self, standalone_mode: bool = True):
        """
        初始化下载协调器
        
        参数：
            standalone_mode: 是否使用独立模式（不依赖FastAPI服务）
        """
        self.data_service = DataService()
        self.integrity_checker = DataIntegrityChecker()
        self.progress_callbacks: List[Callable[[DownloadProgress], None]] = []
        
        # 独立模式
        self.standalone_mode = standalone_mode
        if standalone_mode:
            from .standalone_downloader import StandaloneDataDownloader
            self.standalone_downloader = StandaloneDataDownloader()
        
    def register_progress_callback(self, callback: Callable[[DownloadProgress], None]):
        """注册进度回调函数"""
        self.progress_callbacks.append(callback)
        
    def _notify_progress(self, progress: DownloadProgress):
        """通知所有回调函数"""
        for callback in self.progress_callbacks:
            try:
                callback(progress)
            except Exception as e:
                logger.error(f"进度回调执行失败: {e}")
    
    def ensure_data_complete(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        market_type: str = 'crypto',
        crypto_type: str = 'spot',
        max_wait_time: int = 300,
        progress_callback: Callable[[DownloadProgress], None] = None
    ) -> Tuple[bool, DataIntegrityResult]:
        """
        确保数据完整，如果不完整则触发下载
        
        Args:
            symbol: 交易对符号
            interval: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            market_type: 市场类型
            crypto_type: 加密货币类型
            max_wait_time: 最大等待时间（秒）
            progress_callback: 进度回调函数
            
        Returns:
            Tuple[bool, DataIntegrityResult]: (是否成功, 检查结果)
        """
        # 注册回调
        if progress_callback:
            self.register_progress_callback(progress_callback)
            
        # 1. 检查数据完整性
        logger.info(f"检查数据完整性: {symbol} {interval}")
        result = self.integrity_checker.check_data_completeness(
            symbol, interval, start_time, end_time, market_type, crypto_type
        )
        
        # 2. 如果数据完整，直接返回
        if result.is_complete:
            logger.info(f"数据已完整，无需下载: {symbol}")
            return True, result
            
        # 3. 如果有缺失，触发下载
        if result.missing_ranges:
            logger.info(f"发现数据缺失，开始下载: {symbol}, 缺失 {result.missing_count} 条")
            
            # 下载缺失数据
            download_success = self._download_missing_data(
                symbol=symbol,
                interval=interval,
                missing_ranges=result.missing_ranges,
                market_type=market_type,
                crypto_type=crypto_type,
                max_wait_time=max_wait_time
            )
            
            if not download_success:
                logger.error(f"数据下载失败: {symbol}")
                return False, result
                
            # 4. 重新检查数据完整性
            logger.info(f"下载完成，重新检查数据完整性: {symbol}")
            result = self.integrity_checker.check_data_completeness(
                symbol, interval, start_time, end_time, market_type, crypto_type
            )
            
            if result.is_complete:
                logger.info(f"数据完整性验证通过: {symbol}")
                return True, result
            else:
                logger.warning(f"数据仍不完整: {symbol}, 覆盖率: {result.coverage_percent:.2f}%")
                return False, result
        
        return False, result
    
    def _download_missing_data(
        self,
        symbol: str,
        interval: str,
        missing_ranges: List[Tuple[datetime, datetime]],
        market_type: str,
        crypto_type: str,
        max_wait_time: int
    ) -> bool:
        """
        下载缺失数据
        
        Args:
            symbol: 交易对符号
            interval: 时间周期
            missing_ranges: 缺失时间段列表
            market_type: 市场类型
            crypto_type: 加密货币类型
            max_wait_time: 最大等待时间
            
        Returns:
            bool: 是否下载成功
        """
        # 合并所有缺失时间段
        earliest_start = min(r[0] for r in missing_ranges)
        latest_end = max(r[1] for r in missing_ranges)
        
        # 添加缓冲时间
        earliest_start = earliest_start - timedelta(days=1)
        latest_end = latest_end + timedelta(days=1)
        
        if self.standalone_mode:
            # 使用独立下载器
            return self._download_with_standalone(
                symbol=symbol,
                interval=interval,
                earliest_start=earliest_start,
                latest_end=latest_end,
                crypto_type=crypto_type
            )
        else:
            # 使用任务管理器方式（需要FastAPI服务）
            return self._download_with_task_manager(
                symbol=symbol,
                interval=interval,
                earliest_start=earliest_start,
                latest_end=latest_end,
                crypto_type=crypto_type,
                max_wait_time=max_wait_time
            )
    
    def _download_with_standalone(
        self,
        symbol: str,
        interval: str,
        earliest_start: datetime,
        latest_end: datetime,
        crypto_type: str
    ) -> bool:
        """
        使用独立下载器下载数据
        
        Args:
            symbol: 交易对符号
            interval: 时间周期
            earliest_start: 最早开始时间
            latest_end: 最晚结束时间
            crypto_type: 加密货币类型
            
        Returns:
            bool: 是否下载成功
        """
        try:
            logger.info(f"使用独立下载器下载: {symbol} {interval}")
            
            # 创建进度追踪
            progress = DownloadProgress(
                task_id=f"standalone_{symbol}_{interval}",
                symbol=symbol,
                interval=interval
            )
            progress.update(status="downloading", message="开始下载数据")
            self._notify_progress(progress)
            
            # 定义进度回调
            def standalone_progress_callback(standalone_progress):
                progress.update(
                    status=standalone_progress.status,
                    progress=standalone_progress.progress,
                    message=standalone_progress.message
                )
                self._notify_progress(progress)
            
            # 使用独立下载器下载
            success = self.standalone_downloader.download_sync(
                symbol=symbol,
                interval=interval,
                start_time=earliest_start,
                end_time=latest_end,
                crypto_type=crypto_type,
                progress_callback=standalone_progress_callback
            )
            
            if success:
                progress.update(
                    status="completed",
                    progress=100.0,
                    message="下载完成"
                )
                self._notify_progress(progress)
                logger.info(f"独立下载完成: {symbol} {interval}")
            else:
                progress.update(
                    status="failed",
                    message="下载失败"
                )
                self._notify_progress(progress)
                logger.error(f"独立下载失败: {symbol} {interval}")
            
            return success
            
        except Exception as e:
            logger.error(f"独立下载异常: {e}")
            return False
    
    def _download_with_task_manager(
        self,
        symbol: str,
        interval: str,
        earliest_start: datetime,
        latest_end: datetime,
        crypto_type: str,
        max_wait_time: int
    ) -> bool:
        """
        使用任务管理器下载数据（需要FastAPI服务）
        
        Args:
            symbol: 交易对符号
            interval: 时间周期
            earliest_start: 最早开始时间
            latest_end: 最晚结束时间
            crypto_type: 加密货币类型
            max_wait_time: 最大等待时间
            
        Returns:
            bool: 是否下载成功
        """
        try:
            # 标准化symbol格式（去除/）
            normalized_symbol = symbol.replace('/', '')
            
            logger.info(f"创建下载任务: {normalized_symbol} {interval}, 范围: {earliest_start} ~ {latest_end}")
            
            # 创建下载请求
            download_request = DownloadCryptoRequest(
                exchange='binance',
                symbols=[normalized_symbol],
                interval=[interval],
                start=earliest_start.isoformat() if earliest_start else None,
                end=latest_end.isoformat() if latest_end else None,
                candle_type=crypto_type if crypto_type in ['spot', 'futures'] else 'spot'
            )
            
            # 创建下载任务
            task_result = self.data_service.create_download_task(download_request)
            
            if not task_result.get("success"):
                logger.error(f"创建下载任务失败: {task_result.get('error')}")
                return False
                
            task_id = task_result.get("task_id")
            logger.info(f"下载任务创建成功: {task_id}")
            
            # 等待下载完成
            return self._wait_for_download(
                task_id=task_id,
                symbol=symbol,
                interval=interval,
                max_wait_time=max_wait_time
            )
            
        except Exception as e:
            logger.error(f"任务管理器下载失败: {e}")
            return False
    
    def _wait_for_download(
        self,
        task_id: str,
        symbol: str,
        interval: str,
        max_wait_time: int
    ) -> bool:
        """
        等待下载完成
        
        Args:
            task_id: 任务ID
            symbol: 交易对符号
            interval: 时间周期
            max_wait_time: 最大等待时间（秒）
            
        Returns:
            bool: 是否下载成功
        """
        progress = DownloadProgress(task_id, symbol, interval)
        progress.update(status="downloading", message="开始下载数据")
        self._notify_progress(progress)
        
        start_time = time.time()
        check_interval = 2  # 每2秒检查一次
        
        while time.time() - start_time < max_wait_time:
            try:
                # 查询任务状态
                task_status = self.data_service.get_task_status(task_id)
                
                if not task_status:
                    logger.warning(f"无法获取任务状态: {task_id}")
                    time.sleep(check_interval)
                    continue
                
                status = task_status.get("status")
                progress_percent = task_status.get("progress", 0)
                
                # 更新进度
                if status == "completed":
                    progress.update(
                        status="completed",
                        progress=100.0,
                        message="下载完成"
                    )
                    self._notify_progress(progress)
                    logger.info(f"下载任务完成: {task_id}")
                    return True
                    
                elif status == "failed":
                    error_msg = task_status.get("error", "未知错误")
                    progress.update(
                        status="failed",
                        message="下载失败",
                        error=error_msg
                    )
                    self._notify_progress(progress)
                    logger.error(f"下载任务失败: {task_id}, 错误: {error_msg}")
                    return False
                    
                elif status == "running":
                    progress.update(
                        status="downloading",
                        progress=progress_percent,
                        message=f"正在下载... {progress_percent:.1f}%"
                    )
                    self._notify_progress(progress)
                    
                # 等待下次检查
                time.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"检查下载状态失败: {e}")
                time.sleep(check_interval)
        
        # 超时
        progress.update(
            status="failed",
            message="下载超时",
            error=f"超过最大等待时间 {max_wait_time} 秒"
        )
        self._notify_progress(progress)
        logger.error(f"下载任务超时: {task_id}")
        return False
    
    async def async_ensure_data_complete(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        market_type: str = 'crypto',
        crypto_type: str = 'spot',
        max_wait_time: int = 300,
        progress_callback: Callable[[DownloadProgress], None] = None
    ) -> Tuple[bool, DataIntegrityResult]:
        """
        异步确保数据完整
        
        Args:
            symbol: 交易对符号
            interval: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            market_type: 市场类型
            crypto_type: 加密货币类型
            max_wait_time: 最大等待时间（秒）
            progress_callback: 进度回调函数
            
        Returns:
            Tuple[bool, DataIntegrityResult]: (是否成功, 检查结果)
        """
        return await asyncio.to_thread(
            self.ensure_data_complete,
            symbol, interval, start_time, end_time,
            market_type, crypto_type, max_wait_time, progress_callback
        )
    
    def ensure_multi_symbol_data_complete(
        self,
        symbols: List[str],
        interval: str,
        start_time: datetime,
        end_time: datetime,
        market_type: str = 'crypto',
        crypto_type: str = 'spot',
        max_wait_time: int = 300,
        progress_callback: Callable[[str, DownloadProgress], None] = None
    ) -> Dict[str, Tuple[bool, DataIntegrityResult]]:
        """
        确保多个交易对的数据完整
        
        Args:
            symbols: 交易对列表
            interval: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            market_type: 市场类型
            crypto_type: 加密货币类型
            max_wait_time: 每个交易对的最大等待时间
            progress_callback: 进度回调函数，接收symbol和progress
            
        Returns:
            Dict[str, Tuple[bool, DataIntegrityResult]]: 各交易对的结果
        """
        results = {}
        
        for symbol in symbols:
            logger.info(f"确保数据完整: {symbol}")
            
            # 创建针对该交易对的回调
            symbol_callback = None
            if progress_callback:
                symbol_callback = lambda p, s=symbol: progress_callback(s, p)
            
            success, result = self.ensure_data_complete(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                market_type=market_type,
                crypto_type=crypto_type,
                max_wait_time=max_wait_time,
                progress_callback=symbol_callback
            )
            
            results[symbol] = (success, result)
            
        return results
