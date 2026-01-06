# 基础收集器类
import abc
import datetime
import time
from pathlib import Path
from typing import Iterable, Optional, Type, Union

import pandas as pd
from joblib import Parallel, delayed
from loguru import logger
from tqdm import tqdm


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
        mode='inc',  # 添加模式参数，支持inc（增量）和full（全量），默认inc
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
        :param mode: 下载模式，可选'inc'（增量）或'full'（全量），默认'inc'
        """
        self.save_dir = Path(save_dir).expanduser().resolve()
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        self.delay = delay
        self.max_workers = max_workers
        self.max_collector_count = max_collector_count
        self.mini_symbol_map: dict = {}
        self.interval = interval
        self.check_data_length = max(int(check_data_length) if check_data_length is not None else 0, 0)
        self.mode = mode  # 保存模式参数
        
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
        
        # 获取当前标的的保存路径
        normalized_symbol = self.normalize_symbol(symbol)
        instrument_path = self.save_dir.joinpath(f"{normalized_symbol}.csv")
        
        # 断点续传逻辑：如果是增量模式且文件存在，获取最新日期作为新的开始日期
        actual_start_datetime = self.start_datetime
        if self.mode == 'inc' and instrument_path.exists():
            try:
                _old_df = pd.read_csv(instrument_path)
                if not _old_df.empty:
                    _old_df['date'] = pd.to_datetime(_old_df['date'], format='mixed')
                    latest_date = _old_df['date'].max()
                    if latest_date > self.start_datetime:
                        actual_start_datetime = latest_date
                        logger.info(f"[断点续传] {symbol} 最新数据日期: {latest_date}, 将从该日期开始增量下载")
            except Exception as e:
                logger.error(f"[断点续传] 读取 {symbol} 历史数据失败: {e}")
        
        # 如果计算出的开始日期已经大于等于结束日期，说明不需要下载新数据
        if actual_start_datetime >= self.end_datetime:
            logger.info(f"[增量模式] {symbol} 数据已是最新，无需下载")
            return self.NORMAL_FLAG
        
        # 记录下载状态
        download_status = {
            'symbol': symbol,
            'start_datetime': actual_start_datetime,
            'end_datetime': self.end_datetime,
            'status': 'downloading',
            'progress': 0
        }
        
        try:
            # 下载数据
            df = self.get_data(symbol, self.interval, actual_start_datetime, self.end_datetime, progress_callback)
            download_status['status'] = 'completed'
            download_status['progress'] = 100
            
            _result = self.NORMAL_FLAG
            if self.check_data_length > 0:
                _result = self.cache_small_data(symbol, df)
            if _result == self.NORMAL_FLAG:
                self.save_instrument(symbol, df)
            return _result
        except Exception as e:
            download_status['status'] = 'failed'
            logger.error(f"[下载失败] {symbol} 数据下载失败: {e}")
            # 即使下载失败，也尝试保存已下载的数据
            if 'df' in locals() and df is not None and not df.empty:
                logger.info(f"[断点续传] 尝试保存 {symbol} 已下载的数据")
                self.save_instrument(symbol, df)
            return self.CACHE_FLAG
    
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
        
        # 处理日期列，确保格式统一为Timestamp类型
        df['date'] = pd.to_datetime(df['date'], format='mixed')
        
        # 去重，基于date列，保留最新数据
        df = df.drop_duplicates(subset=['date'], keep='last')
        
        # 按date排序
        df = df.sort_values('date')
        
        # 处理增量模式
        if self.mode != 'full' and instrument_path.exists():
            _old_df = pd.read_csv(instrument_path)
            # 处理旧数据的日期列，确保为Timestamp类型
            _old_df['date'] = pd.to_datetime(_old_df['date'], format='mixed')
            # 合并新旧数据
            df = pd.concat([_old_df, df], sort=False)
            # 去重，基于date列，保留最新数据
            df = df.drop_duplicates(subset=['date'], keep='last')
            # 按date排序
            df = df.sort_values('date')
        
        # 只在最终保存到文件之前，将日期列转换为ISO格式的字符串
        df_for_save = df.copy()
        df_for_save['date'] = df_for_save['date'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # 保存数据
        df_for_save.to_csv(instrument_path, index=False)
        
        # 记录日志
        mode_label = "[全量模式]" if self.mode == 'full' else "[增量模式]"
        logger.info(f"{mode_label} 成功将 {symbol} 数据保存到文件: {instrument_path}")
    
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
        logger.info(f"[收集开始] 模式: {self.mode}, 标的数量: {len(self.instrument_list)}, 时间范围: {self.start_datetime} 至 {self.end_datetime}")
        instrument_list = self.instrument_list
        total_instruments = len(instrument_list)
        completed = 0
        failed = 0
        
        # 记录开始时间
        start_time = datetime.datetime.now()
        
        # 添加详细进度反馈的内部回调函数
        def detailed_progress_callback(symbol, current, total, failed_count, status="downloading"):
            if progress_callback:
                progress_callback(symbol, current, total, failed_count, status)
            
            # 计算整体进度
            overall_progress = (completed + (current / total if total > 0 else 0)) / total_instruments * 100
            logger.info(f"[进度] {symbol} - 当前进度: {current/total*100:.1f}%, 整体进度: {overall_progress:.1f}%, 状态: {status}")
        
        for i in range(self.max_collector_count):
            if not instrument_list:
                break
            logger.info(f"[收集轮次] 第 {i+1}/{self.max_collector_count} 次获取数据，当前待收集标的数量: {len(instrument_list)}")
            instrument_list = self._collector(instrument_list, detailed_progress_callback, completed, total_instruments)
            logger.info(f"[收集轮次] 第 {i+1} 次收集完成，剩余待收集标的数量: {len(instrument_list)}")
        
        # 处理缓存的小数据量标的
        if self.mini_symbol_map:
            logger.info(f"[缓存处理] 开始处理 {len(self.mini_symbol_map)} 个缓存的小数据量标的")
            for _symbol, _df_list in self.mini_symbol_map.items():
                _df = pd.concat(_df_list, sort=False)
                if not _df.empty:
                    self.save_instrument(_symbol, _df.drop_duplicates(["date"]).sort_values(["date"]))
            
            logger.warning(f"[缓存处理] 数据长度小于 {self.check_data_length} 的标的列表: {list(self.mini_symbol_map.keys())}")
        
        # 计算收集耗时
        elapsed_time = datetime.datetime.now() - start_time
        
        logger.info(f"[收集完成] 总标的数量: {len(self.instrument_list)}, 收集失败: {len(set(instrument_list))}, 耗时: {elapsed_time.total_seconds():.2f} 秒")
        logger.info(f"[收集结果] 模式: {self.mode}, 成功: {len(self.instrument_list) - len(set(instrument_list))}, 失败: {len(set(instrument_list))}")
