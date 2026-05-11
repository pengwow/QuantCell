#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 数据下载脚本，用于从命令行下载各种资产的数据

# 支持 Parquet 格式本地存储，提供更高的压缩率和查询性能。

import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from pathlib import Path

import typer
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from exchange import BinanceCollector, OKXCollector
from collector.db.models import SystemConfigBusiness as SystemConfig
from utils.parquet_utils import load_from_parquet, load_kline_data_auto, list_parquet_files


# 创建 typer 应用实例
app = typer.Typer(help="数据下载工具，用于从各种交易所下载资产数据")

# 默认保存目录
default_save_dir = Path.home() / ".qlib" / "crypto_data" / "source"


def _convert_to_qlib(data_dir: Path, qlib_dir: Path, interval: str):
    """
    将数据转换为QLib格式
    
    :param data_dir: 原始数据目录
    :param qlib_dir: QLib数据保存目录
    :param interval: 时间间隔
    """
    try:
        logger.info(f"开始将数据转换为QLib格式，数据目录: {data_dir}, QLib目录: {qlib_dir}, 时间间隔: {interval}")
        
        # 导入转换函数
        from collector.scripts.convert_to_qlib import \
            convert_crypto_to_qlib

        # 调用转换函数
        success = convert_crypto_to_qlib(
            csv_dir=str(data_dir),
            qlib_dir=str(qlib_dir),
            freq=interval,
            date_field_name="timestamp",
            file_suffix=".csv",
            symbol_field_name="symbol",
            include_fields="timestamp,open,high,low,close,volume",
            max_workers=16
        )
        
        if success:
            logger.info(f"数据转换为QLib格式成功")
        else:
            logger.error(f"数据转换为QLib格式失败")
    except Exception as e:
        logger.error(f"处理QLib转换时发生异常: {e}")
        logger.exception(e)


def _write_to_database(save_dir, interval, symbols, candle_type):
    """
    将数据写入数据库（从Parquet文件读取）

    :param save_dir: 数据保存目录
    :param interval: 时间间隔
    :param symbols: 交易对列表
    :param candle_type: 蜡烛图类型
    """
    try:
        logger.info(f"开始将 {interval} 数据写入数据库")
        # 获取当前项目根目录
        project_root = Path(__file__).parent.parent.parent
        logger.info(f"当前项目根目录: {project_root}")

        # 构建数据目录路径
        data_dir = Path(save_dir) / interval
        data_dir = project_root / data_dir
        logger.info(f"数据目录: {data_dir}")
        
        # 导入数据库相关模块
        from sqlalchemy import func

        from collector.db.database import (
            SessionLocal, init_database_config)
        from collector.db.models import CryptoSpotKline, CryptoFutureKline

        # 初始化数据库配置
        init_database_config()
        
        # 优先查找 Parquet 文件，兼容旧版 CSV 文件
        parquet_files = list_parquet_files(data_dir)
        if not parquet_files:
            # 如果没有 Parquet 文件，尝试查找 CSV 文件（向后兼容）
            csv_files = list(data_dir.glob("*.csv"))
            logger.info(f"未找到 Parquet 文件，找到 {len(csv_files)} 个 CSV 文件（旧格式）")
            
            for csv_file in csv_files:
                symbol = csv_file.stem
                logger.info(f"开始处理CSV文件: {csv_file}")
                
                df = pd.read_csv(csv_file)
                if df is None or df.empty:
                    logger.warning(f"{symbol} 数据为空，跳过写入数据库")
                    continue
                
                _process_dataframe_for_db(df, symbol, interval, candle_type)
        else:
            logger.info(f"找到 {len(parquet_files)} 个 Parquet 文件")
            
            # 过滤文件（只处理当前下载的交易对）
            if symbols:
                symbol_set = set(symbol.replace("/", "") for symbol in symbols)
                parquet_files = [f for f in parquet_files if f.stem in symbol_set]
                logger.info(f"过滤后找到 {len(parquet_files)} 个 Parquet 文件")
            
            # 处理每个 Parquet 文件
            for parquet_file in parquet_files:
                symbol = parquet_file.stem
                logger.info(f"开始处理Parquet文件: {parquet_file}")
                
                # 使用 load_from_parquet 读取数据
                df = load_from_parquet(parquet_file)
                
                if df is None or df.empty:
                    logger.warning(f"{symbol} 数据为空，跳过写入数据库")
                    continue
                
                _process_dataframe_for_db(df, symbol, interval, candle_type)
                
    except Exception as e:
        logger.error(f"处理数据库写入时发生异常: {e}")
        logger.exception(e)


def _process_dataframe_for_db(df, symbol, interval, candle_type):
    """
    处理 DataFrame 并写入数据库

    :param df: K线数据DataFrame
    :param symbol: 交易对符号
    :param interval: 时间间隔
    :param candle_type: 蜡烛图类型
    """
    try:
        from sqlalchemy import func
        from collector.db.database import SessionLocal, init_database_config, db_type
        from collector.db.models import CryptoSpotKline, CryptoFutureKline
        
        # 准备数据，确保只包含需要的列
        kline_list = []
        for _, row in df.iterrows():
            # 跳过无效行 - 使用pandas Series的isna()方法检查相关字段
            if row[['timestamp', 'open', 'high', 'low', 'close', 'volume']].isna().any(axis=None):
                continue
            
            # 将timestamp转换为整数，去除小数点
            try:
                timestamp = int(float(row['timestamp']))
            except (ValueError, TypeError):
                logger.warning(f"无效的timestamp值: {row['timestamp']}，跳过该行")
                continue
            
            # 使用整数timestamp生成unique_kline值
            unique_kline = f"{symbol}_{interval}_{timestamp}"
            
            kline_list.append({
                'symbol': symbol,
                'interval': interval,
                'timestamp': str(timestamp),  # 转换为字符串存储
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'],
                'unique_kline': unique_kline
            })
        
        if not kline_list:
            logger.warning(f"没有有效数据可以写入数据库: {symbol}")
            return
        
        # 根据candle_type选择对应的K线模型
        kline_model = CryptoSpotKline if candle_type == "spot" else CryptoFutureKline
        logger.info(f"使用K线模型: {kline_model.__tablename__}, candle_type: {candle_type}")
        
        # 创建数据库会话
        db = SessionLocal()
        try:
            # 实现跨数据库兼容的UPSERT逻辑
            
            if db_type == "sqlite":
                # SQLite使用更简单的冲突处理方式
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                
                # 分批插入数据，避免SQL变量限制
                batch_size = 100
                total_rows = len(kline_list)
                for i in range(0, total_rows, batch_size):
                    batch = kline_list[i:i+batch_size]
                    stmt = sqlite_insert(kline_model).values(batch)
                    db.execute(stmt)
                    if i % 500 == 0:
                        logger.info(f"{symbol}: 已插入 {i}/{total_rows} 条新记录")
                        
            elif db_type == "duckdb":
                # DuckDB使用PostgreSQL兼容的ON CONFLICT语法
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                stmt = pg_insert(kline_model).values(kline_list)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['unique_kline'],
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume,
                        'updated_at': func.now()
                    }
                )
                db.execute(stmt)
            else:
                # 其他数据库类型，使用BULK INSERT + 错误处理
                raise ValueError(f"不支持的数据库类型: {db_type}")
            
            db.commit()
            logger.info(f"成功将 {len(kline_list)} 条 {symbol} 数据写入 {kline_model.__tablename__} 表")
        except Exception as e:
            logger.error(f"写入数据库失败: {e}")
            logger.exception(e)
            db.rollback()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"处理DataFrame失败: {e}")
        logger.exception(e)


@app.command("crypto_binance")
def crypto_binance(
    save_dir: Path = typer.Option(None, help="数据保存目录"),
    start: str = typer.Option(None, help="开始时间 (YYYY-MM-DD)"),
    end: str = typer.Option(None, help="结束时间 (YYYY-MM-DD)"),
    interval: str = typer.Option("1d", help="时间间隔"),
    max_workers: int = typer.Option(1, help="最大工作线程数"),
    max_collector_count: int = typer.Option(2, help="最大收集次数"),
    delay: float = typer.Option(0.0, help="请求延迟时间（秒）"),
    check_data_length: int = typer.Option(None, help="数据长度检查阈值"),
    limit_nums: int = typer.Option(None, help="限制收集的标的数量"),
    candle_type: str = typer.Option('spot', help="蜡烛图类型 (spot/futures/option)"),
    symbols: str = typer.Option(None, help="交易对列表，逗号分隔"),
    exists_skip: bool = typer.Option(False, help="是否跳过已存在的文件"),
    mode: str = typer.Option('inc', help="下载模式 (inc/full)"),
    write_to_db: bool = typer.Option(False, help="是否将数据写入数据库"),
):
    """从币安交易所下载加密货币数据"""
    
    if save_dir is None:
        try:
            data_download_dir = SystemConfig.get("data_download_dir")
            if data_download_dir:
                save_dir = Path(data_download_dir)
                logger.info(f"从数据库获取下载目录: {save_dir}")
            else:
                save_dir = default_save_dir
                logger.info(f"数据库中未找到下载目录配置，使用默认值: {save_dir}")
        except Exception as e:
            save_dir = default_save_dir
            logger.warning(f"从数据库读取下载目录失败: {e}，使用默认值: {save_dir}")
    
    save_dir = save_dir / interval
    
    # 处理交易对列表
    if symbols is not None:
        symbols = symbols.split(',')
    
    # 如果exists_skip为True，过滤掉已经存在的文件对应的交易对
    original_symbols_count = len(symbols) if symbols is not None else "全量"
    if exists_skip:
        all_symbols = symbols
        if all_symbols is None:
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
        
        symbols_to_download = []
        collector = BinanceCollector(save_dir=save_dir, interval=interval)
        for symbol in all_symbols:
            normalized_symbol = collector.normalize_symbol(symbol)
            file_path = save_dir / f"{normalized_symbol}.csv"
            if not file_path.exists():
                symbols_to_download.append(symbol)
        
        symbols = symbols_to_download
        logger.info(f"存在跳过模式，原始交易对数量: {original_symbols_count}，过滤后剩余 {len(symbols)} 个交易对需要下载")
    
    logger.info(f"开始下载币安{interval}数据，保存目录: {save_dir}")
    logger.info(f"交易类型: {candle_type}")
    logger.info(f"交易对数量: {'全量' if symbols is None else len(symbols)}")
    
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
        mode=mode,
    )
    
    collector.collect_data()
    
    if write_to_db:
        _write_to_database(save_dir, interval, symbols, candle_type)
    
    logger.info("数据下载完成！")


@app.command("crypto_okx")
def crypto_okx(
    save_dir: Path = typer.Option(None, help="数据保存目录"),
    start: str = typer.Option(None, help="开始时间 (YYYY-MM-DD)"),
    end: str = typer.Option(None, help="结束时间 (YYYY-MM-DD)"),
    interval: str = typer.Option("1d", help="时间间隔"),
    max_workers: int = typer.Option(1, help="最大工作线程数"),
    max_collector_count: int = typer.Option(2, help="最大收集次数"),
    delay: float = typer.Option(0.0, help="请求延迟时间（秒）"),
    check_data_length: int = typer.Option(None, help="数据长度检查阈值"),
    limit_nums: int = typer.Option(None, help="限制收集的标的数量"),
    candle_type: str = typer.Option('spot', help="蜡烛图类型 (spot/futures/option)"),
    symbols: str = typer.Option(None, help="交易对列表，逗号分隔"),
    exists_skip: bool = typer.Option(False, help="是否跳过已存在的文件"),
    mode: str = typer.Option('inc', help="下载模式 (inc/full)"),
    write_to_db: bool = typer.Option(False, help="是否将数据写入数据库"),
):
    """从OKX交易所下载加密货币数据"""
    
    if save_dir is None:
        try:
            data_download_dir = SystemConfig.get("data_download_dir")
            if data_download_dir:
                save_dir = Path(data_download_dir)
                logger.info(f"从数据库获取下载目录: {save_dir}")
            else:
                save_dir = default_save_dir
                logger.info(f"数据库中未找到下载目录配置，使用默认值: {save_dir}")
        except Exception as e:
            save_dir = default_save_dir
            logger.warning(f"从数据库读取下载目录失败: {e}，使用默认值: {save_dir}")
    
    save_dir = save_dir / interval
    
    # 处理交易对列表
    if symbols is not None:
        symbols = symbols.split(',')
    
    # 如果exists_skip为True，过滤掉已经存在的文件对应的交易对
    original_symbols_count = len(symbols) if symbols is not None else "全量"
    if exists_skip:
        all_symbols = symbols
        if all_symbols is None:
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
        
        symbols_to_download = []
        for symbol in all_symbols:
            normalized_symbol = symbol.replace('/', '') if '/' in symbol else symbol.replace('-', '') if '-' in symbol else symbol
            file_path = save_dir / f"{normalized_symbol}.csv"
            if not file_path.exists():
                symbols_to_download.append(symbol)
        
        symbols = symbols_to_download
        logger.info(f"存在跳过模式，原始交易对数量: {original_symbols_count}，过滤后剩余 {len(symbols)} 个交易对需要下载")
    
    logger.info(f"开始下载OKX {interval}数据，保存目录: {save_dir}")
    logger.info(f"交易类型: {candle_type}")
    logger.info(f"交易对数量: {'全量' if symbols is None else len(symbols)}")
    
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
        mode=mode,
    )
    
    collector.collect_data()
    
    if write_to_db:
        _write_to_database(save_dir, interval, symbols, candle_type)
    
    logger.info("数据下载完成！")


@app.command("crypto")
def crypto(
    exchange: str = typer.Option("binance", help="交易所名称 (binance/okx)"),
    save_dir: Path = typer.Option(None, help="数据保存目录"),
    start: str = typer.Option(None, help="开始时间 (YYYY-MM-DD)"),
    end: str = typer.Option(None, help="结束时间 (YYYY-MM-DD)"),
    interval: str = typer.Option("1d", help="时间间隔"),
    max_workers: int = typer.Option(1, help="最大工作线程数"),
    max_collector_count: int = typer.Option(2, help="最大收集次数"),
    delay: float = typer.Option(0.0, help="请求延迟时间（秒）"),
    check_data_length: int = typer.Option(None, help="数据长度检查阈值"),
    limit_nums: int = typer.Option(None, help="限制收集的标的数量"),
    candle_type: str = typer.Option('spot', help="蜡烛图类型 (spot/futures/option)"),
    symbols: str = typer.Option(None, help="交易对列表，逗号分隔"),
    exists_skip: bool = typer.Option(False, help="是否跳过已存在的文件"),
    mode: str = typer.Option('inc', help="下载模式 (inc/full)"),
    write_to_db: bool = typer.Option(False, help="是否将数据写入数据库"),
):
    """从指定交易所下载加密货币数据"""
    
    if exchange == "binance":
        ctx = typer.Context(app)
        ctx.invoke(crypto_binance, save_dir=save_dir, start=start, end=end, interval=interval,
                   max_workers=max_workers, max_collector_count=max_collector_count, delay=delay,
                   check_data_length=check_data_length, limit_nums=limit_nums, candle_type=candle_type,
                   symbols=symbols, exists_skip=exists_skip, mode=mode, write_to_db=write_to_db)
    elif exchange == "okx":
        ctx = typer.Context(app)
        ctx.invoke(crypto_okx, save_dir=save_dir, start=start, end=end, interval=interval,
                   max_workers=max_workers, max_collector_count=max_collector_count, delay=delay,
                   check_data_length=check_data_length, limit_nums=limit_nums, candle_type=candle_type,
                   symbols=symbols, exists_skip=exists_skip, mode=mode, write_to_db=write_to_db)
    else:
        logger.error(f"不支持的交易所: {exchange}")


@app.command("stock")
def stock(
    exchange: str = typer.Option("", help="交易所名称"),
    save_dir: Path = typer.Option(None, help="数据保存目录"),
    start: str = typer.Option(None, help="开始时间 (YYYY-MM-DD)"),
    end: str = typer.Option(None, help="结束时间 (YYYY-MM-DD)"),
    interval: str = typer.Option("1d", help="时间间隔"),
    max_workers: int = typer.Option(1, help="最大工作线程数"),
    max_collector_count: int = typer.Option(2, help="最大收集次数"),
    delay: float = typer.Option(0.0, help="请求延迟时间（秒）"),
    check_data_length: int = typer.Option(None, help="数据长度检查阈值"),
    limit_nums: int = typer.Option(None, help="限制收集的标的数量"),
):
    """从指定交易所下载股票数据（暂未实现）"""
    
    if save_dir is None:
        try:
            data_download_dir = SystemConfig.get("data_download_dir")
            if data_download_dir:
                save_dir = Path(data_download_dir) / interval
                logger.info(f"从数据库获取下载目录: {save_dir}")
            else:
                save_dir = default_save_dir / interval
                logger.info(f"数据库中未找到下载目录配置，使用默认值: {save_dir}")
        except Exception as e:
            save_dir = default_save_dir / interval
            logger.warning(f"从数据库读取下载目录失败: {e}，使用默认值: {save_dir}")
    
    logger.warning("股票数据下载功能暂未实现")


# ==================== 兼容层：保留旧的 GetData 类接口 ====================
# 为了向后兼容，保留 GetData 类供其他模块（如 scheduled_task_manager, export_data）使用

class GetData:
    """
    数据下载工具类（兼容旧接口）
    
    注意：此类已迁移到 typer 命令行工具，此处的类仅作为兼容层存在。
    新代码建议直接调用命令行函数或使用 typer 接口。
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
            start: 开始时间
            end: 结束时间
            interval: 时间间隔
            max_workers: 最大工作线程数
            max_collector_count: 最大收集次数
            delay: 请求延迟时间
            check_data_length: 数据长度检查阈值
            limit_nums: 限制标的数量
            exists_skip: 是否跳过已存在的文件
            mode: 下载模式 (inc/full)
            write_to_db: 是否写入数据库
        """
        self.symbols = symbols
        self.exchange = exchange
        self.candle_type = candle_type
        self.save_dir = save_dir or default_save_dir
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
        执行数据下载
        
        Args:
            start_date: 开始日期（用于增量下载），如果为None则使用初始化时的start参数
        """
        # 使用提供的 start_date 或默认值
        actual_start = start_date or self.start
        
        # 处理 symbols 参数格式
        if isinstance(self.symbols, list):
            symbols_str = ','.join(self.symbols)
        else:
            symbols_str = self.symbols
        
        # 根据交易所类型调用对应的下载函数
        if self.exchange.lower() in ["binance", "binance_spot", "binance_futures"]:
            crypto_binance(
                save_dir=self.save_dir,
                start=actual_start,
                end=self.end,
                interval=self.interval,
                max_workers=self.max_workers,
                max_collector_count=self.max_collector_count,
                delay=self.delay,
                check_data_length=self.check_data_length,
                limit_nums=self.limit_nums,
                candle_type=self.candle_type,
                symbols=symbols_str,
                exists_skip=self.exists_skip,
                mode=self.mode,
                write_to_db=self.write_to_db,
            )
        elif self.exchange.lower() in ["okx"]:
            crypto_okx(
                save_dir=self.save_dir,
                start=actual_start,
                end=self.end,
                interval=self.interval,
                max_workers=self.max_workers,
                max_collector_count=self.max_collector_count,
                delay=self.delay,
                check_data_length=self.check_data_length,
                limit_nums=self.limit_nums,
                candle_type=self.candle_type,
                symbols=symbols_str,
                exists_skip=self.exists_skip,
                mode=self.mode,
                write_to_db=self.write_to_db,
            )
        else:
            # 使用通用的 crypto 函数
            crypto(
                exchange=self.exchange,
                save_dir=self.save_dir,
                start=actual_start,
                end=self.end,
                interval=self.interval,
                max_workers=self.max_workers,
                max_collector_count=self.max_collector_count,
                delay=self.delay,
                check_data_length=self.check_data_length,
                limit_nums=self.limit_nums,
                candle_type=self.candle_type,
                symbols=symbols_str,
                exists_skip=self.exists_skip,
                mode=self.mode,
                write_to_db=self.write_to_db,
            )


if __name__ == "__main__":
    # 配置日志格式
    logger.add(
        "data_download.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level="INFO",
        rotation="1 week",
        retention="1 month",
    )
    
    # 使用typer运行应用
    app()
