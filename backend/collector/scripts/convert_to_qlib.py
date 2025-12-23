#!/usr/bin/env python3
# 加密货币数据转换为QLib格式脚本

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd
from loguru import logger

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent  # /Users/liupeng/workspace/qbot
sys.path.append(str(project_root))

# 添加qlib目录到Python路径，以便导入scripts模块
qlib_dir = project_root / "qlib"
sys.path.append(str(qlib_dir))

# 导入QLib的dump_bin模块
from scripts.dump_bin import DumpDataAll


def convert_crypto_to_qlib(
    csv_dir,
    qlib_dir,
    freq="day",
    date_field_name="date",
    file_suffix=".csv",
    symbol_field_name="symbol",
    include_fields="date,open,high,low,close,volume",
    max_workers=16,
    limit_nums=None,
    backup_dir=None
):
    """
    将加密货币CSV数据转换为QLib格式
    
    :param csv_dir: CSV数据目录
    :param qlib_dir: QLib数据保存目录
    :param freq: 交易频率，如"day"、"1min"等
    :param date_field_name: CSV中的日期字段名称
    :param file_suffix: CSV文件后缀
    :param symbol_field_name: CSV中的交易对字段名称
    :param include_fields: 要转换的字段列表，逗号分隔
    :param max_workers: 最大工作线程数
    :param limit_nums: 限制转换的文件数量，用于调试
    :param backup_dir: 备份目录，如果提供则在转换前备份QLib数据
    :return: 转换结果
    """
    try:
        # 检查CSV目录是否存在
        csv_dir = Path(csv_dir).expanduser().resolve()
        if not csv_dir.exists():
            logger.error(f"CSV目录不存在: {csv_dir}")
            return False
        
        # 检查QLib目录是否存在，不存在则创建
        qlib_dir = Path(qlib_dir).expanduser().resolve()
        qlib_dir.mkdir(parents=True, exist_ok=True)
        
        # 处理include_fields参数，确保它是逗号分隔的字符串
        if isinstance(include_fields, (list, tuple)):
            include_fields = ",".join(include_fields)
        elif not isinstance(include_fields, str):
            include_fields = str(include_fields)
        
        # 创建临时目录，用于处理CSV文件
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # 复制CSV文件到临时目录，并确保文件名只包含交易对名称
            logger.info(f"正在处理CSV文件，源目录: {csv_dir}")
            csv_files = sorted(csv_dir.glob(f"*{file_suffix}"))
            
            if limit_nums is not None:
                csv_files = csv_files[:int(limit_nums)]
            
            for csv_file in csv_files:
                # 提取交易对名称（文件名去掉后缀）
                symbol = csv_file.stem
                # 复制文件到临时目录，确保文件名只包含交易对名称
                dest_file = temp_dir / f"{symbol}{file_suffix}"
                
                # 读取CSV文件，预处理日期字段
                df = pd.read_csv(csv_file)
                if date_field_name in df.columns:
                    # 尝试多种日期解析方式，处理包含时间的日期格式
                    df[date_field_name] = pd.to_datetime(df[date_field_name], errors='coerce')
                    # 过滤掉无法解析的日期（NaT值）
                    df = df.dropna(subset=[date_field_name])
                    # 如果是日线数据，只保留日期部分
                if (freq == 'day' or freq == '1d') and not df.empty:
                    df[date_field_name] = df[date_field_name].dt.strftime('%Y-%m-%d')
                
                # 将预处理后的数据保存到临时目录
                df.to_csv(dest_file, index=False)
                logger.debug(f"预处理并保存文件: {csv_file} -> {dest_file}")
            
            # 直接调用QLib的DumpDataAll类进行转换
            logger.info(f"开始转换数据为QLib格式，目标目录: {qlib_dir}")
            
            # 创建DumpDataAll实例
            dump_data = DumpDataAll(
                data_path=str(temp_dir),
                qlib_dir=str(qlib_dir),
                backup_dir=backup_dir,
                freq=freq,
                max_workers=max_workers,
                date_field_name=date_field_name,
                file_suffix=file_suffix,
                symbol_field_name=symbol_field_name,
                include_fields=include_fields,
                limit_nums=limit_nums
            )
            
            # 执行转换
            dump_data.dump()
            
            logger.info(f"数据转换成功！")
            return True
    
    except Exception as e:
        logger.error(f"转换过程中发生错误: {e}")
        logger.exception(e)
        return False


def convert_stock_to_qlib(
    csv_dir,
    qlib_dir,
    freq="day",
    date_field_name="date",
    file_suffix=".csv",
    symbol_field_name="symbol",
    include_fields="date,open,high,low,close,volume",
    max_workers=16,
    limit_nums=None,
    backup_dir=None
):
    """
    将股票CSV数据转换为QLib格式
    
    :param csv_dir: CSV数据目录
    :param qlib_dir: QLib数据保存目录
    :param freq: 交易频率，如"day"、"1min"等
    :param date_field_name: CSV中的日期字段名称
    :param file_suffix: CSV文件后缀
    :param symbol_field_name: CSV中的股票代码字段名称
    :param include_fields: 要转换的字段列表，逗号分隔
    :param max_workers: 最大工作线程数
    :param limit_nums: 限制转换的文件数量，用于调试
    :param backup_dir: 备份目录，如果提供则在转换前备份QLib数据
    :return: 转换结果
    """
    # 股票数据转换与加密货币数据转换逻辑基本相同，直接调用convert_crypto_to_qlib函数
    return convert_crypto_to_qlib(
        csv_dir=csv_dir,
        qlib_dir=qlib_dir,
        freq=freq,
        date_field_name=date_field_name,
        file_suffix=file_suffix,
        symbol_field_name=symbol_field_name,
        include_fields=include_fields,
        max_workers=max_workers,
        limit_nums=limit_nums,
        backup_dir=backup_dir
    )


def convert_data_to_qlib(
    data_type,
    csv_dir,
    qlib_dir,
    freq="day",
    date_field_name="date",
    file_suffix=".csv",
    symbol_field_name="symbol",
    include_fields="date,open,high,low,close,volume",
    max_workers=16,
    limit_nums=None,
    backup_dir=None
):
    """
    将数据转换为QLib格式的通用函数
    
    :param data_type: 数据类型，如"crypto"、"stock"等
    :param csv_dir: CSV数据目录
    :param qlib_dir: QLib数据保存目录
    :param freq: 交易频率，如"day"、"1min"等
    :param date_field_name: CSV中的日期字段名称
    :param file_suffix: CSV文件后缀
    :param symbol_field_name: CSV中的交易对/股票代码字段名称
    :param include_fields: 要转换的字段列表，逗号分隔
    :param max_workers: 最大工作线程数
    :param limit_nums: 限制转换的文件数量，用于调试
    :param backup_dir: 备份目录，如果提供则在转换前备份QLib数据
    :return: 转换结果
    """
    logger.info(f"开始转换{data_type}数据为QLib格式")
    
    if data_type == "crypto":
        return convert_crypto_to_qlib(
            csv_dir=csv_dir,
            qlib_dir=qlib_dir,
            freq=freq,
            date_field_name=date_field_name,
            file_suffix=file_suffix,
            symbol_field_name=symbol_field_name,
            include_fields=include_fields,
            max_workers=max_workers,
            limit_nums=limit_nums,
            backup_dir=backup_dir
        )
    elif data_type == "stock":
        return convert_stock_to_qlib(
            csv_dir=csv_dir,
            qlib_dir=qlib_dir,
            freq=freq,
            date_field_name=date_field_name,
            file_suffix=file_suffix,
            symbol_field_name=symbol_field_name,
            include_fields=include_fields,
            max_workers=max_workers,
            limit_nums=limit_nums,
            backup_dir=backup_dir
        )
    else:
        logger.error(f"不支持的数据类型: {data_type}")
        return False


if __name__ == "__main__":
    import fire

    # 配置日志
    logger.add(
        "convert_to_qlib.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level="INFO",
        rotation="1 week",
        retention="1 month",
    )
    
    # 使用fire库创建命令行界面
    fire.Fire({
        "convert": convert_data_to_qlib,
        "convert_crypto": convert_crypto_to_qlib,
        "convert_stock": convert_stock_to_qlib
    })
