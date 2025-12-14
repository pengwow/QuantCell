#!/usr/bin/env python3
# 数据下载脚本，用于从命令行下载各种资产类型的数据

import sys
import os
# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import fire
from pathlib import Path
from loguru import logger

from backend.collector.crypto.binance.collector import BinanceCollector
from backend.collector.crypto.okx.collector import OKXCollector
from backend.collector.db.models import SystemConfigBusiness as SystemConfig


class GetData:
    """数据下载工具，用于从各种交易所下载资产数据"""
    
    def __init__(self):
        """初始化数据下载工具"""
        self.default_save_dir = Path.home() / ".qlib" / "crypto_data" / "source"
    
    
    def _convert_to_qlib(self, data_dir: Path, qlib_dir: Path, interval: str):
        """
        将数据转换为QLib格式
        
        :param data_dir: 原始数据目录
        :param qlib_dir: QLib数据保存目录
        :param interval: 时间间隔
        """
        try:
            logger.info(f"开始将数据转换为QLib格式，数据目录: {data_dir}, QLib目录: {qlib_dir}, 时间间隔: {interval}")
            
            # 导入转换函数
            from backend.collector.scripts.convert_to_qlib import convert_crypto_to_qlib
            
            # 调用转换函数
            success = convert_crypto_to_qlib(
                csv_dir=str(data_dir),
                qlib_dir=str(qlib_dir),
                freq=interval,
                date_field_name="date",
                file_suffix=".csv",
                symbol_field_name="symbol",
                include_fields="date,open,high,low,close,volume",
                max_workers=16
            )
            
            if success:
                logger.info(f"数据转换为QLib格式成功")
            else:
                logger.error(f"数据转换为QLib格式失败")
        except Exception as e:
            logger.error(f"处理QLib转换时发生异常: {e}")
            logger.exception(e)
    
    def crypto_binance(
        self,
        save_dir=None,
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length=None,
        limit_nums=None,
        candle_type='spot',
        symbols=None,
        convert_to_qlib=False,
        qlib_dir=None,
        progress_callback=None,
        exists_skip=False,
    ):
        """
        从币安交易所下载加密货币数据
        
        :param save_dir: 数据保存目录，默认 ~/.qlib/crypto_data/source
        :param start: 开始时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'
        :param end: 结束时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'
        :param interval: 时间间隔，如'1m', '5m', '15m', '30m', '1h', '4h', '1d'等
        :param max_workers: 最大工作线程数，默认1
        :param max_collector_count: 最大收集次数，默认2
        :param delay: 请求延迟时间（秒），默认0
        :param check_data_length: 数据长度检查阈值，默认None
        :param limit_nums: 限制收集的标的数量，用于调试，默认None
        :param candle_type: 蜡烛图类型，可选'spot'（现货）、'futures'（期货）或'option'（期权），默认'spot'
        :param symbols: 交易对列表，如'BTCUSDT,ETHUSDT'，如果为None则获取全量交易对
        :param convert_to_qlib: 是否将数据转换为QLib格式，默认False
        :param qlib_dir: QLib数据保存目录，如果为None则自动生成
        :param progress_callback: 进度回调函数，格式为 callback(current, completed, total, failed)
        :param exists_skip: 是否跳过已存在的文件，默认False
        """
        if save_dir is None:
            # 从数据库中读取下载目录配置
            try:
                data_download_dir = SystemConfig.get("data_download_dir")
                if data_download_dir:
                    save_dir = Path(data_download_dir)
                    logger.info(f"从数据库获取下载目录: {save_dir}")
                else:
                    # 数据库中没有配置，使用默认值
                    save_dir = self.default_save_dir
                    logger.info(f"数据库中未找到下载目录配置，使用默认值: {save_dir}")
            except Exception as e:
                # 数据库读取失败，使用默认值
                save_dir = self.default_save_dir
                logger.warning(f"从数据库读取下载目录失败: {e}，使用默认值: {save_dir}")
        
        # 确保在save_dir后面添加interval作为子目录
        save_dir = Path(save_dir) / interval
        logger.info(f"最终保存目录: {save_dir}")
        
        # 处理交易对列表
        if symbols is not None:
            if isinstance(symbols, str):
                symbols = symbols.split(',')
            # 如果是元组或列表，直接使用
            elif isinstance(symbols, (tuple, list)):
                pass
            else:
                symbols = [str(symbols)]
        
        # 如果exists_skip为True，过滤掉已经存在的文件对应的交易对
        original_symbols_count = len(symbols) if symbols is not None else "全量"
        if exists_skip:
            # 先获取所有需要处理的交易对列表
            all_symbols = symbols
            if all_symbols is None:
                # 如果是全量交易对，先创建收集器实例获取全量交易对列表
                temp_collector = BinanceCollector(
                    save_dir=save_dir,
                    start=start,
                    end=end,
                    interval=interval,
                    max_workers=max_workers,
                    max_collector_count=max_collector_count,
                    delay=delay,
                    check_data_length=check_data_length,
                    limit_nums=limit_nums,
                    candle_type=candle_type,
                    symbols=symbols,
                )
                all_symbols = temp_collector.instrument_list
            
            # 过滤掉已经存在的文件对应的交易对
            symbols_to_download = []
            # 创建一个临时收集器实例，用于标准化交易对名称
            collector = BinanceCollector(save_dir=save_dir, interval=interval)
            for symbol in all_symbols:
                # 使用收集器的normalize_symbol方法标准化交易对名称，确保与实际保存的文件名一致
                normalized_symbol = collector.normalize_symbol(symbol)
                file_path = save_dir / f"{normalized_symbol}.csv"
                if not file_path.exists():
                    symbols_to_download.append(symbol)
            
            symbols = symbols_to_download
            logger.info(f"存在跳过模式，原始交易对数量: {original_symbols_count}，过滤后剩余 {len(symbols)} 个交易对需要下载")
        
        logger.info(f"开始下载币安{interval}数据，保存目录: {save_dir}")
        logger.info(f"交易类型: {candle_type}")
        logger.info(f"交易对数量: {'全量' if symbols is None else len(symbols)}")
        
        # 创建收集器实例
        collector = BinanceCollector(
            save_dir=save_dir,
            start=start,
            end=end,
            interval=interval,
            max_workers=max_workers,
            max_collector_count=max_collector_count,
            delay=delay,
            check_data_length=check_data_length,
            limit_nums=limit_nums,
            candle_type=candle_type,
            symbols=symbols,
        )
        
        # 执行数据收集
        collector.collect_data(progress_callback=progress_callback)
        
        # 数据写入数据库的逻辑已移至API层，此处不再处理
        
        # 处理QLib转换
        if convert_to_qlib:
            if qlib_dir is None:
                # 自动生成QLib数据目录
                qlib_dir = self.default_save_dir.parent.parent / "qlib_data"
            self._convert_to_qlib(save_dir, qlib_dir, interval)
        
        logger.info("数据下载完成！")
    
    def crypto_okx(
        self,
        save_dir=None,
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length=None,
        limit_nums=None,
        candle_type='spot',
        symbols=None,
        convert_to_qlib=False,
        qlib_dir=None,
        progress_callback=None,
        exists_skip=False,
    ):
        """
        从OKX交易所下载加密货币数据
        
        :param save_dir: 数据保存目录，默认 ~/.qlib/crypto_data/source
        :param start: 开始时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'
        :param end: 结束时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'
        :param interval: 时间间隔，如'1m', '5m', '15m', '30m', '1h', '4h', '1d'等
        :param max_workers: 最大工作线程数，默认1
        :param max_collector_count: 最大收集次数，默认2
        :param delay: 请求延迟时间（秒），默认0
        :param check_data_length: 数据长度检查阈值，默认None
        :param limit_nums: 限制收集的标的数量，用于调试，默认None
        :param candle_type: 蜡烛图类型，可选'spot'（现货）、'futures'（期货）或'option'（期权），默认'spot'
        :param symbols: 交易对列表，如'BTC-USDT,ETH-USDT'，如果为None则获取全量交易对
        :param convert_to_qlib: 是否将数据转换为QLib格式，默认False
        :param qlib_dir: QLib数据保存目录，如果为None则自动生成
        :param progress_callback: 进度回调函数，格式为 callback(current, completed, total, failed)
        :param exists_skip: 是否跳过已存在的文件，默认False
        """
        if save_dir is None:
            # 从数据库中读取下载目录配置
            try:
                data_download_dir = SystemConfig.get("data_download_dir")
                if data_download_dir:
                    save_dir = Path(data_download_dir)
                    logger.info(f"从数据库获取下载目录: {save_dir}")
                else:
                    # 数据库中没有配置，使用默认值
                    save_dir = self.default_save_dir
                    logger.info(f"数据库中未找到下载目录配置，使用默认值: {save_dir}")
            except Exception as e:
                # 数据库读取失败，使用默认值
                save_dir = self.default_save_dir
                logger.warning(f"从数据库读取下载目录失败: {e}，使用默认值: {save_dir}")
        
        # 确保在save_dir后面添加interval作为子目录
        save_dir = Path(save_dir) / interval
        logger.info(f"最终保存目录: {save_dir}")
        
        # 处理交易对列表
        if symbols is not None:
            if isinstance(symbols, str):
                symbols = symbols.split(',')
            # 如果是元组或列表，直接使用
            elif isinstance(symbols, (tuple, list)):
                pass
            else:
                symbols = [str(symbols)]
        
        # 如果exists_skip为True，过滤掉已经存在的文件对应的交易对
        original_symbols_count = len(symbols) if symbols is not None else "全量"
        if exists_skip:
            # 先获取所有需要处理的交易对列表
            all_symbols = symbols
            if all_symbols is None:
                # 如果是全量交易对，先创建收集器实例获取全量交易对列表
                temp_collector = OKXCollector(
                    save_dir=save_dir,
                    start=start,
                    end=end,
                    interval=interval,
                    max_workers=max_workers,
                    max_collector_count=max_collector_count,
                    delay=delay,
                    check_data_length=check_data_length,
                    limit_nums=limit_nums,
                    candle_type=candle_type,
                    symbols=symbols,
                )
                all_symbols = temp_collector.instrument_list
            
            # 过滤掉已经存在的文件对应的交易对
            symbols_to_download = []
            for symbol in all_symbols:
                # 标准化交易对名称，去除可能的分隔符
                normalized_symbol = symbol.replace('/', '') if '/' in symbol else symbol.replace('-', '') if '-' in symbol else symbol
                file_path = save_dir / f"{normalized_symbol}.csv"
                if not file_path.exists():
                    symbols_to_download.append(symbol)
            
            symbols = symbols_to_download
            logger.info(f"存在跳过模式，原始交易对数量: {original_symbols_count}，过滤后剩余 {len(symbols)} 个交易对需要下载")
        
        logger.info(f"开始下载OKX {interval}数据，保存目录: {save_dir}")
        logger.info(f"交易类型: {candle_type}")
        logger.info(f"交易对数量: {'全量' if symbols is None else len(symbols)}")
        
        # 创建收集器实例
        collector = OKXCollector(
            save_dir=save_dir,
            start=start,
            end=end,
            interval=interval,
            max_workers=max_workers,
            max_collector_count=max_collector_count,
            delay=delay,
            check_data_length=check_data_length,
            limit_nums=limit_nums,
            candle_type=candle_type,
            symbols=symbols,
        )
        
        # 执行数据收集
        collector.collect_data(progress_callback=progress_callback)
        
        # 数据写入数据库的逻辑已移至API层，此处不再处理
        
        # 处理QLib转换
        if convert_to_qlib:
            if qlib_dir is None:
                # 自动生成QLib数据目录
                qlib_dir = self.default_save_dir.parent.parent / "qlib_data"
            self._convert_to_qlib(save_dir, qlib_dir, interval)
        
        logger.info("数据下载完成！")
    
    def crypto(
        self,
        exchange="binance",
        save_dir=None,
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length=None,
        limit_nums=None,
        candle_type='spot',
        symbols=None,
        convert_to_qlib=False,
        qlib_dir=None,
        progress_callback=None,
        exists_skip=False,
    ):
        """
        从指定交易所下载加密货币数据
        
        :param exchange: 交易所名称，目前支持'binance'和'okx'，默认'binance'
        :param save_dir: 数据保存目录，默认 ~/.qlib/crypto_data/source
        :param start: 开始时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'
        :param end: 结束时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'
        :param interval: 时间间隔，如'1m', '5m', '15m', '30m', '1h', '4h', '1d'等
        :param max_workers: 最大工作线程数，默认1
        :param max_collector_count: 最大收集次数，默认2
        :param delay: 请求延迟时间（秒），默认0
        :param check_data_length: 数据长度检查阈值，默认None
        :param limit_nums: 限制收集的标的数量，用于调试，默认None
        :param candle_type: 蜡烛图类型，可选'spot'（现货）、'futures'（期货）或'option'（期权），默认'spot'
        :param symbols: 交易对列表，如'BTCUSDT,ETHUSDT'（Binance）或'BTC-USDT,ETH-USDT'（OKX），如果为None则获取全量交易对
        :param convert_to_qlib: 是否将数据转换为QLib格式，默认False
        :param qlib_dir: QLib数据保存目录，如果为None则自动生成
        :param progress_callback: 进度回调函数，格式为 callback(current, completed, total, failed)
        :param exists_skip: 是否跳过已存在的文件，默认False
        """
        if exchange == "binance":
            self.crypto_binance(
                save_dir=save_dir,
                start=start,
                end=end,
                interval=interval,
                max_workers=max_workers,
                max_collector_count=max_collector_count,
                delay=delay,
                check_data_length=check_data_length,
                limit_nums=limit_nums,
                candle_type=candle_type,
                symbols=symbols,
                convert_to_qlib=convert_to_qlib,
                qlib_dir=qlib_dir,
                progress_callback=progress_callback,
                exists_skip=exists_skip,
            )
        elif exchange == "okx":
            self.crypto_okx(
                save_dir=save_dir,
                start=start,
                end=end,
                interval=interval,
                max_workers=max_workers,
                max_collector_count=max_collector_count,
                delay=delay,
                check_data_length=check_data_length,
                limit_nums=limit_nums,
                candle_type=candle_type,
                symbols=symbols,
                convert_to_qlib=convert_to_qlib,
                qlib_dir=qlib_dir,
                progress_callback=progress_callback,
                exists_skip=exists_skip,
            )
        else:
            logger.error(f"不支持的交易所: {exchange}")
    
    def stock(
        self,
        exchange="",
        save_dir=None,
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length=None,
        limit_nums=None,
    ):
        """
        从指定交易所下载股票数据（暂未实现）
        
        :param exchange: 交易所名称
        :param save_dir: 数据保存目录
        :param start: 开始时间
        :param end: 结束时间
        :param interval: 时间间隔
        :param max_workers: 最大工作线程数
        :param max_collector_count: 最大收集次数
        :param delay: 请求延迟时间
        :param check_data_length: 数据长度检查阈值
        :param limit_nums: 限制收集的标的数量
        """
        if save_dir is None:
            # 从数据库中读取下载目录配置
            try:
                data_download_dir = SystemConfig.get("data_download_dir")
                if data_download_dir:
                    save_dir = Path(data_download_dir) / interval
                    logger.info(f"从数据库获取下载目录: {save_dir}")
                else:
                    # 数据库中没有配置，使用默认值
                    save_dir = self.default_save_dir / interval
                    logger.info(f"数据库中未找到下载目录配置，使用默认值: {save_dir}")
            except Exception as e:
                # 数据库读取失败，使用默认值
                save_dir = self.default_save_dir / interval
                logger.warning(f"从数据库读取下载目录失败: {e}，使用默认值: {save_dir}")
        
        logger.warning("股票数据下载功能暂未实现")
    
    def help(self):
        """显示帮助信息"""
        print("数据下载工具使用说明：")
        print("\n1. 下载加密货币数据：")
        print("   python get_data.py crypto --exchange binance --start 2024-01-01 --end 2024-10-31 --interval 1d")
        print("\n2. 下载指定交易对数据：")
        print("   python get_data.py crypto_binance --start 2024-01-01 --end 2024-10-31 --interval 1h --symbols BTCUSDT,ETHUSDT")
        print("\n3. 下载全量交易对数据：")
        print("   python get_data.py crypto_binance --start 2024-01-01 --end 2024-10-31 --interval 1d --limit_nums 10")
        print("\n4. 下载币安现货数据并转换为QLib格式：")
        print("   python get_data.py crypto_binance --start 2024-01-01 --end 2024-10-31 --interval 1h --candle_type spot --convert_to_qlib")
        print("\n5. 下载币安期货数据：")
        print("   python get_data.py crypto_binance --start 2024-01-01 --end 2024-10-31 --interval 4h --candle_type futures")
        print("\n6. 查看详细帮助：")
        print("   python get_data.py crypto_binance --help")


if __name__ == "__main__":
    # 配置日志格式
    logger.add(
        "data_download.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level="INFO",
        rotation="1 week",
        retention="1 month",
    )
    
    # 使用fire库创建命令行界面
    fire.Fire(GetData)
