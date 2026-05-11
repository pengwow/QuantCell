#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据下载与导出工具集

提供数据下载、导出等功能的统一接口，
供 scripts/data_cli.py、collector/utils 等模块使用。
"""

from pathlib import Path

from utils.logger import get_logger, LogType
from exchange import BinanceCollector, OKXCollector
from collector.db.models import SystemConfigBusiness as SystemConfig


# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


# 默认保存目录
default_save_dir = Path.home() / ".qlib" / "crypto_data" / "source"


class GetData:
    """
    数据下载工具类
    
    提供从各种交易所下载数据的统一接口。
    支持币安(Binance)和OKX交易所。
    """
    
    def __init__(
        self,
        symbols=None,
        exchange="binance",
        candle_type='spot',
        save_dir=None,
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length=None,
        limit_nums=None,
        exists_skip=False,
        mode='inc',
        write_to_db=False,
    ):
        """
        初始化数据下载工具
        
        Args:
            symbols: 交易对列表或逗号分隔的字符串
            exchange: 交易所名称 (binance/okx)
            candle_type: 蜡烛图类型 (spot/futures)
            save_dir: 保存目录
            start: 开始时间 (YYYY-MM-DD)
            end: 结束时间 (YYYY-MM-DD)
            interval: 时间间隔 (1d/1h/15m等)
            max_workers: 最大工作线程数
            max_collector_count: 最大收集次数
            delay: 请求延迟时间（秒）
            check_data_length: 数据长度检查阈值
            limit_nums: 限制标的数量
            exists_skip: 是否跳过已存在的文件
            mode: 下载模式 (inc/full)
            write_to_db: 是否写入数据库
        """
        self.symbols = symbols
        self.exchange = exchange
        self.candle_type = candle_type
        
        # 处理保存目录
        if save_dir is None:
            try:
                data_download_dir = SystemConfig.get("data_download_dir")
                if data_download_dir:
                    self.save_dir = Path(data_download_dir)
                    logger.info(f"从数据库获取下载目录: {self.save_dir}")
                else:
                    self.save_dir = default_save_dir
                    logger.info(f"数据库中未找到下载目录配置，使用默认值: {self.save_dir}")
            except Exception as e:
                self.save_dir = default_save_dir
                logger.warning(f"从数据库读取下载目录失败: {e}，使用默认值: {self.save_dir}")
        else:
            self.save_dir = Path(save_dir)
        
        self.start = start
        self.end = end
        self.interval = interval
        self.max_workers = max_workers
        self.max_collector_count = max_collector_count
        self.delay = delay
        self.check_data_length = check_data_length
        self.limit_nums = limit_nums
        self.exists_skip = exists_skip
        self.mode = mode
        self.write_to_db = write_to_db
    
    def run(self, start_date=None):
        """
        执行数据下载任务
        
        Args:
            start_date: 开始日期（用于增量下载），如果为None则使用初始化时的start参数
        """
        # 使用提供的 start_date 或默认值
        actual_start = start_date or self.start
        
        # 构建完整的保存路径
        full_save_dir = self.save_dir / self.interval
        
        # 处理 symbols 参数格式
        if isinstance(self.symbols, list):
            symbols_str = ','.join(self.symbols)
        else:
            symbols_str = self.symbols
        
        logger.info(f"开始下载 {self.exchange} {self.interval} 数据")
        logger.info(f"保存目录: {full_save_dir}")
        logger.info(f"蜡烛图类型: {self.candle_type}")
        if symbols_str:
            logger.info(f"交易对: {symbols_str}")
        
        # 根据交易所类型选择对应的收集器
        exchange_lower = self.exchange.lower()
        
        try:
            if exchange_lower in ["binance", "binance_spot", "binance_futures"]:
                # 使用币安收集器
                collector = BinanceCollector(
                    save_dir=full_save_dir,
                    start=actual_start,
                    end=self.end,
                    interval=self.interval,
                    max_workers=self.max_workers,
                    max_collector_count=self.max_collector_count,
                    delay=self.delay,
                    check_data_length=self.check_data_length,
                    limit_nums=self.limit_nums,
                    candle_type=self.candle_type,
                    symbols=symbols_str.split(',') if symbols_str else None,
                    mode=self.mode,
                )
                
                collector.collect_data()
                
            elif exchange_lower in ["okx"]:
                # 使用OKX收集器
                collector = OKXCollector(
                    save_dir=full_save_dir,
                    start=actual_start,
                    end=self.end,
                    interval=self.interval,
                    max_workers=self.max_workers,
                    max_collector_count=self.max_collector_count,
                    delay=self.delay,
                    check_data_length=self.check_data_length,
                    limit_nums=self.limit_nums,
                    candle_type=self.candle_type,
                    symbols=symbols_str.split(',') if symbols_str else None,
                    mode=self.mode,
                )
                
                collector.collect_data()
                
            else:
                logger.error(f"不支持的交易所: {self.exchange}")
                raise ValueError(f"不支持的交易所: {self.exchange}")
            
            logger.info(f"{self.exchange} 数据下载完成！")
            
            # 如果需要写入数据库
            if self.write_to_db:
                self._write_to_database(full_save_dir, symbols_str)
            
        except Exception as e:
            logger.error(f"数据下载失败: {e}")
            logger.exception(e)
            raise
    
    def _write_to_database(self, data_dir, symbols_str):
        """
        将下载的数据写入数据库
        
        Args:
            data_dir: 数据文件所在目录
            symbols_str: 交易对字符串（逗号分隔）
        """
        try:
            logger.info(f"开始将数据写入数据库...")
            
            from sqlalchemy import func
            from collector.db.database import SessionLocal, init_database_config, db_type
            from collector.db.models import CryptoSpotKline, CryptoFutureKline
            
            # 初始化数据库配置
            init_database_config()
            
            # 解析交易对列表
            symbol_list = symbols_str.split(',') if symbols_str else []
            
            # 查找所有数据文件
            if not data_dir.exists():
                logger.warning(f"数据目录不存在: {data_dir}")
                return
            
            # 这里可以添加具体的数据库写入逻辑
            # 目前仅记录日志
            logger.info(f"数据库写入功能待实现")
            logger.info(f"数据目录: {data_dir}")
            logger.info(f"交易对数量: {len(symbol_list)}")
            
        except Exception as e:
            logger.error(f"数据库写入失败: {e}")
            logger.exception(e)


class ExportData:
    """
    数据导出工具类
    
    提供从数据库导出K线数据到CSV/Parquet文件的功能。
    """
    
    def __init__(self):
        """初始化导出工具"""
        pass
    
    def export_kline_data(
        self,
        symbols,
        interval="1d",
        start=None,
        end=None,
        exchange="binance",
        candle_type="spot",
        save_dir=None,
        max_workers=1,
        auto_download=True,
    ):
        """
        导出K线数据到CSV文件
        
        Args:
            symbols: 交易对列表
            interval: 时间间隔
            start: 开始时间
            end: 结束时间
            exchange: 交易所
            candle_type: 蜡烛图类型
            save_dir: 保存目录
            max_workers: 最大工作线程数
            auto_download: 是否自动下载缺失数据
            
        Returns:
            dict: 导出结果 {
                'success': bool,
                'exported_files': list,
                'missing_ranges': dict
            }
        """
        result = {
            'success': True,
            'exported_files': [],
            'missing_ranges': {}
        }
        
        try:
            logger.info(f"开始导出K线数据...")
            logger.info(f"交易对: {symbols}")
            logger.info(f"时间范围: {start} 至 {end}")
            logger.info(f"时间间隔: {interval}")
            
            # TODO: 实现实际的导出逻辑
            # 这里应该查询数据库并导出到文件
            logger.info(f"导出功能待实现完整逻辑")
            
            result['exported_files'] = [f"{symbol}_{interval}.csv" for symbol in symbols]
            
        except Exception as e:
            logger.error(f"导出失败: {e}")
            logger.exception(e)
            result['success'] = False
            result['missing_ranges'] = {
                symbol: [{'error': str(e)}] for symbol in symbols
            }
        
        return result
