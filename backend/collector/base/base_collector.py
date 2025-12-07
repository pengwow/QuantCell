# 基础收集器类
import abc
import time
import datetime
from pathlib import Path
from typing import Type, Iterable, Union, Optional

import pandas as pd
from loguru import logger
from tqdm import tqdm
from joblib import Parallel, delayed


class BaseCollector(abc.ABC):
    """基础收集器类，定义数据收集的通用接口和功能"""
    
    CACHE_FLAG = "CACHED"
    NORMAL_FLAG = "NORMAL"
    
    DEFAULT_START_DATETIME_1D = pd.Timestamp("2000-01-01")
    DEFAULT_START_DATETIME_1MIN = pd.Timestamp(datetime.datetime.now() - pd.Timedelta(days=30))
    DEFAULT_END_DATETIME_1D = pd.Timestamp(datetime.datetime.now() + pd.Timedelta(days=1))
    DEFAULT_END_DATETIME_1MIN = DEFAULT_END_DATETIME_1D
    
    INTERVAL_1min = "1min"
    INTERVAL_5min = "5min"
    INTERVAL_15min = "15min"
    INTERVAL_30min = "30min"
    INTERVAL_1h = "1h"
    INTERVAL_4h = "4h"
    INTERVAL_1d = "1d"
    
    def __init__(
        self,
        save_dir: Union[str, Path],
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length: Optional[int] = None,
        limit_nums: Optional[int] = None,
    ):
        """
        初始化收集器
        
        :param save_dir: 数据保存目录
        :param start: 开始时间
        :param end: 结束时间
        :param interval: 时间间隔，如'1m', '1h', '1d'等
        :param max_workers: 最大工作线程数
        :param max_collector_count: 最大收集次数
        :param delay: 请求延迟时间（秒）
        :param check_data_length: 数据长度检查阈值
        :param limit_nums: 限制收集的标的数量，用于调试
        """
        self.save_dir = Path(save_dir).expanduser().resolve()
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        self.delay = delay
        self.max_workers = max_workers
        self.max_collector_count = max_collector_count
        self.mini_symbol_map: dict = {}
        self.interval = interval
        self.check_data_length = max(int(check_data_length) if check_data_length is not None else 0, 0)
        
        self.start_datetime = self.normalize_start_datetime(start)
        self.end_datetime = self.normalize_end_datetime(end)
        
        self.instrument_list = sorted(set(self.get_instrument_list()))
        
        if limit_nums is not None:
            try:
                self.instrument_list = self.instrument_list[: int(limit_nums)]
            except Exception as e:
                logger.warning(f"无法使用limit_nums={limit_nums}，该参数将被忽略")
    
    def normalize_start_datetime(self, start_datetime: Optional[Union[str, pd.Timestamp]] = None):
        """标准化开始时间"""
        return (
            pd.Timestamp(str(start_datetime))
            if start_datetime
            else getattr(self, f"DEFAULT_START_DATETIME_{self.interval.upper()}")
        )
    
    def normalize_end_datetime(self, end_datetime: Optional[Union[str, pd.Timestamp]] = None):
        """标准化结束时间"""
        return (
            pd.Timestamp(str(end_datetime))
            if end_datetime
            else getattr(self, f"DEFAULT_END_DATETIME_{self.interval.upper()}")
        )
    
    @abc.abstractmethod
    def get_instrument_list(self):
        """获取标的列表"""
        raise NotImplementedError("请重写get_instrument_list方法")
    
    @abc.abstractmethod
    def normalize_symbol(self, symbol: str):
        """标准化标的代码"""
        raise NotImplementedError("请重写normalize_symbol方法")
    
    @abc.abstractmethod
    def get_data(
        self, symbol: str, interval: str, start_datetime: pd.Timestamp, end_datetime: pd.Timestamp, progress_callback=None
    ) -> pd.DataFrame:
        """获取标的数据
        
        :param symbol: 标的代码
        :param interval: 时间间隔
        :param start_datetime: 开始时间
        :param end_datetime: 结束时间
        :param progress_callback: 进度回调函数，格式为 callback(symbol, current, total, status)
        :return: 标的数据DataFrame
        """
        raise NotImplementedError("请重写get_data方法")
    
    def sleep(self):
        """休眠指定时间，用于控制请求频率"""
        time.sleep(self.delay)
    
    def _simple_collector(self, symbol: str, progress_callback=None):
        """简单收集器，用于单个标的的数据收集
        
        :param symbol: 标的代码
        :param progress_callback: 进度回调函数，格式为 callback(symbol, current, total, status)
        :return: 收集结果标志
        """
        self.sleep()
        df = self.get_data(symbol, self.interval, self.start_datetime, self.end_datetime, progress_callback)
        _result = self.NORMAL_FLAG
        if self.check_data_length > 0:
            _result = self.cache_small_data(symbol, df)
        if _result == self.NORMAL_FLAG:
            self.save_instrument(symbol, df)
        return _result
    
    def save_instrument(self, symbol, df: pd.DataFrame):
        """保存标的数据到文件
        
        :param symbol: 标的代码
        :param df: 标的数据DataFrame
        """
        if df is None or df.empty:
            logger.warning(f"{symbol} 数据为空")
            return
        
        symbol = self.normalize_symbol(symbol)
        instrument_path = self.save_dir.joinpath(f"{symbol}.csv")
        df["symbol"] = symbol
        if instrument_path.exists():
            _old_df = pd.read_csv(instrument_path)
            df = pd.concat([_old_df, df], sort=False)
        df.to_csv(instrument_path, index=False)
        logger.info(f"成功将 {symbol} 数据保存到文件: {instrument_path}")
    
    def cache_small_data(self, symbol, df):
        """缓存数据量较小的标的数据
        
        :param symbol: 标的代码
        :param df: 标的数据DataFrame
        :return: 缓存标志或正常标志
        """
        if len(df) < self.check_data_length:
            logger.warning(f"{symbol} 的数据长度小于 {self.check_data_length}！")
            _temp = self.mini_symbol_map.setdefault(symbol, [])
            _temp.append(df.copy())
            return self.CACHE_FLAG
        else:
            if symbol in self.mini_symbol_map:
                self.mini_symbol_map.pop(symbol)
            return self.NORMAL_FLAG
    
    def _collector(self, instrument_list, progress_callback=None, completed=0, total=0):
        """批量收集标的数据
        
        :param instrument_list: 标的列表
        :param progress_callback: 进度回调函数，格式为 callback(current, completed, total, failed)
        :param completed: 已完成的标的数量
        :param total: 总标的数量
        :return: 收集失败的标的列表
        """
        error_symbol = []
        failed = 0
        
        # 定义带进度回调的收集函数
        def collect_with_progress(_inst, index):
            nonlocal completed, failed
            
            # 创建一个适配器函数，将底层下载进度转换为上层进度格式
            def download_progress_callback(symbol, current, total, status):
                if progress_callback:
                    # 传递完整的进度信息，包括status参数
                    progress_callback(_inst, current, total, failed, status)
            
            # 调用回调函数更新进度
            if progress_callback:
                progress_callback(_inst, completed, total, failed)
            
            result = self._simple_collector(_inst, download_progress_callback)
            completed += 1
            
            if result != self.NORMAL_FLAG:
                error_symbol.append(_inst)
                failed += 1
            
            # 再次调用回调函数更新进度
            if progress_callback:
                progress_callback(_inst, completed, total, failed)
            
            return result
        
        # 执行并行收集
        res = Parallel(n_jobs=self.max_workers)(
            delayed(collect_with_progress)(_inst, idx) for idx, _inst in enumerate(instrument_list)
        )
        
        logger.info(f"收集失败的标的数量: {len(error_symbol)}")
        logger.info(f"当前收集的标的数量: {len(instrument_list)}")
        error_symbol.extend(self.mini_symbol_map.keys())
        return sorted(set(error_symbol))
    
    def collect_data(self, progress_callback=None):
        """执行数据收集
        
        :param progress_callback: 进度回调函数，格式为 callback(current, completed, total, failed)
        """
        logger.info("开始收集数据......")
        instrument_list = self.instrument_list
        total_instruments = len(instrument_list)
        completed = 0
        failed = 0
        
        for i in range(self.max_collector_count):
            if not instrument_list:
                break
            logger.info(f"第 {i+1} 次获取数据")
            instrument_list = self._collector(instrument_list, progress_callback, completed, total_instruments)
            logger.info(f"第 {i+1} 次收集完成")
        
        # 处理缓存的小数据量标的
        for _symbol, _df_list in self.mini_symbol_map.items():
            _df = pd.concat(_df_list, sort=False)
            if not _df.empty:
                self.save_instrument(_symbol, _df.drop_duplicates(["date"]).sort_values(["date"]))
        
        if self.mini_symbol_map:
            logger.warning(f"数据长度小于 {self.check_data_length} 的标的列表: {list(self.mini_symbol_map.keys())}")
        
        logger.info(f"总标的数量: {len(self.instrument_list)}, 收集失败: {len(set(instrument_list))}")
