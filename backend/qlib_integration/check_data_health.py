import os
from pathlib import Path
from typing import Any, Dict, Optional

import fire
import pandas as pd
import qlib
from loguru import logger
from qlib.data import D
from tqdm import tqdm


class DataHealthChecker:
    """
    数据健康检查器，用于检查OHLCV数据的质量，支持加密货币格式和多种频率
    """

    def __init__(
        self,
        csv_path=None,
        qlib_dir=None,
        freq="day",
        large_step_threshold_price=0.5,
        large_step_threshold_volume=3,
        missing_data_num=0,
        market="all",
    ):
        """
        初始化数据健康检查器
        
        Args:
            csv_path: CSV文件目录路径
            qlib_dir: QLib数据目录路径
            freq: 数据频率，如"day"、"1min"等
            large_step_threshold_price: 价格大幅变动阈值
            large_step_threshold_volume: 成交量大幅变动阈值
            missing_data_num: 缺失数据阈值
            market: 市场标识，默认为"all"
        """
        assert csv_path or qlib_dir, "One of csv_path or qlib_dir should be provided."
        assert not (csv_path and qlib_dir), "Only one of csv_path or qlib_dir should be provided."

        self.data = {}
        self.problems = {}
        self.freq = freq
        self.large_step_threshold_price = large_step_threshold_price
        self.large_step_threshold_volume = large_step_threshold_volume
        self.missing_data_num = missing_data_num
        self.market = market

        if csv_path:
            assert os.path.isdir(csv_path), f"{csv_path} should be a directory."
            files = [f for f in os.listdir(csv_path) if f.endswith(".csv")]
            for filename in tqdm(files, desc="Loading data"):
                df = pd.read_csv(os.path.join(csv_path, filename))
                self.data[filename] = df

        elif qlib_dir:
            # 针对加密货币数据和不同频率的初始化
            self.qlib_dir = qlib_dir
            self.init_qlib_with_freq()
            self.load_qlib_data()
    
    def init_qlib_with_freq(self):
        """
        根据指定频率初始化QLib，支持加密货币数据格式
        """
        try:
            # 构建包含频率的配置
            provider_uri_dict = {
                self.freq: os.path.join(self.qlib_dir, self.freq)
            }
            
            # 尝试直接用频率路径初始化
            qlib.init(provider_uri=provider_uri_dict)
            logger.info(f"✅ QLib initialized successfully with frequency: {self.freq}")
        except Exception as e:
            logger.warning(f"Failed to initialize with frequency-specific path: {e}")
            logger.info("Trying default initialization...")
            # 备用方案：使用默认路径初始化
            qlib.init(provider_uri=self.qlib_dir)
    
    def load_qlib_data(self):
        """
        加载QLib格式的数据，支持加密货币和不同频率
        """
        try:
            # 尝试获取所有可用的instruments
            instruments = D.instruments(market=self.market)
            instrument_list = D.list_instruments(instruments=instruments, as_list=True, freq=self.freq)
            
            if not instrument_list:
                logger.warning(f"No instruments found for frequency: {self.freq}")
                # 尝试直接从文件系统读取
                self._load_instruments_from_filesystem()
                return
            
            # 定义需要的字段，加密货币可能不需要factor
            required_fields = ["$open", "$close", "$low", "$high", "$volume"]
            # 对于日频数据，尝试包含factor字段
            if self.freq in ["day", "1d"]:
                required_fields.append("$factor")
            
            logger.info(f"Loading {len(instrument_list)} instruments with frequency: {self.freq}")
            
            for instrument in tqdm(instrument_list, desc="Loading QLib data"):
                try:
                    df = D.features([instrument], required_fields, freq=self.freq)
                    # 重命名列
                    rename_map = {
                        "$open": "open",
                        "$close": "close",
                        "$low": "low",
                        "$high": "high",
                        "$volume": "volume"
                    }
                    if "$factor" in df.columns:
                        rename_map["$factor"] = "factor"
                    
                    df.rename(columns=rename_map, inplace=True)
                    self.data[instrument] = df
                except Exception as e:
                    logger.error(f"Failed to load instrument {instrument}: {e}")
            
            logger.info(f"Successfully loaded {len(self.data)} instruments")
            
        except Exception as e:
            logger.error(f"Error loading QLib data: {e}")
            # 如果QLib API失败，尝试直接从文件系统读取
            self._load_instruments_from_filesystem()
    
    def _load_instruments_from_filesystem(self):
        """
        从文件系统直接读取数据，作为QLib API的备选方案
        """
        logger.info("Attempting to load data directly from filesystem...")
        
        # 尝试查找instruments目录
        instruments_dir = os.path.join(self.qlib_dir, "instruments")
        if os.path.exists(instruments_dir):
            # 读取instruments文件
            for root, _, files in os.walk(instruments_dir):
                for file in files:
                    if file.endswith(".txt"):
                        market_name = os.path.splitext(file)[0]
                        instrument_file = os.path.join(root, file)
                        try:
                            with open(instrument_file, 'r') as f:
                                instruments = []
                                for line in f:
                                    stripped_line = line.strip()
                                    if stripped_line:
                                        # 处理空格分隔的格式，提取第一个元素作为instrument名称
                                        parts = stripped_line.split()
                                        if parts:
                                            instrument = parts[0]
                                            instruments.append(instrument)
                            
                            logger.info(f"Found {len(instruments)} instruments in {market_name}")
                            
                            # 尝试加载每个instrument的数据
                            for instrument in instruments:
                                self._load_instrument_data(instrument)
                        except Exception as e:
                            logger.error(f"Failed to process instruments file {instrument_file}: {e}")
        else:
            logger.warning(f"Instruments directory not found: {instruments_dir}")
            # 尝试直接查找features目录下的文件
            features_dir = os.path.join(self.qlib_dir, "features")
            if os.path.exists(features_dir):
                logger.info("Looking for features data...")
                # 这里可以添加直接读取features数据的逻辑
            else:
                logger.warning(f"Features directory not found: {features_dir}")
    
    def _load_instrument_data(self, instrument):
        """
        尝试加载单个instrument的数据
        
        Args:
            instrument: 交易对/股票代码
        """
        try:
            # 加密货币数据通常存储在features目录下的特定频率文件夹中
            # 构建可能的数据文件路径
            features_dir = os.path.join(self.qlib_dir, "features", self.freq)
            instrument_data_path = os.path.join(features_dir, f"{instrument}.bin")
            
            # 尝试使用QLib的D.features直接加载特定instrument
            if instrument not in self.data:
                try:
                    # 为单个instrument定义需要的字段
                    required_fields = ["$open", "$close", "$low", "$high", "$volume"]
                    if self.freq in ["day", "1d"]:
                        required_fields.append("$factor")
                    
                    logger.debug(f"Trying to load {instrument} using D.features")
                    df = D.features([instrument], required_fields, freq=self.freq)
                    
                    # 重命名列
                    rename_map = {
                        "$open": "open",
                        "$close": "close",
                        "$low": "low",
                        "$high": "high",
                        "$volume": "volume"
                    }
                    if "$factor" in df.columns:
                        rename_map["$factor"] = "factor"
                    
                    df.rename(columns=rename_map, inplace=True)
                    self.data[instrument] = df
                    logger.info(f"Successfully loaded data for {instrument}")
                except Exception as e:
                    logger.warning(f"Failed to load {instrument} using D.features: {e}")
                    
                    # 如果D.features失败，尝试查找可能的CSV或其他格式文件
                    # 检查常见的数据文件路径
                    potential_paths = [
                        os.path.join(self.qlib_dir, self.freq, f"{instrument}.csv"),
                        os.path.join(features_dir, f"{instrument}.csv"),
                        os.path.join(self.qlib_dir, "features", f"{instrument}_{self.freq}.csv")
                    ]
                    
                    for path in potential_paths:
                        if os.path.exists(path):
                            logger.info(f"Found data file at {path}")
                            try:
                                df = pd.read_csv(path)
                                # 尝试解析日期索引
                                if 'datetime' in df.columns:
                                    df.set_index('datetime', inplace=True)
                                elif 'date' in df.columns:
                                    df.set_index('date', inplace=True)
                                self.data[instrument] = df
                                logger.info(f"Loaded {instrument} data from {path}")
                                break
                            except Exception as csv_e:
                                logger.error(f"Failed to read {path}: {csv_e}")
        except Exception as e:
            logger.error(f"Failed to load data for {instrument}: {e}")

    def check_missing_data(self) -> Optional[pd.DataFrame]:
        """
        检查数据中是否存在缺失值
        
        Returns:
            包含缺失数据信息的DataFrame，如果没有缺失则返回None
        """
        result_dict = {
            "instruments": [],
            "open": [],
            "high": [],
            "low": [],
            "close": [],
            "volume": [],
        }
        
        for filename, df in self.data.items():
            try:
                # 检查必需的列是否存在
                required_columns = ["open", "high", "low", "close", "volume"]
                for col in required_columns:
                    if col not in df.columns:
                        df[col] = pd.NA
                
                missing_data_columns = df.isnull().sum()[df.isnull().sum() > self.missing_data_num].index.tolist()
                if len(missing_data_columns) > 0:
                    result_dict["instruments"].append(filename)
                    for col in required_columns:
                        result_dict[col].append(df.isnull().sum()[col] if col in df.columns else len(df))
            except Exception as e:
                logger.error(f"Error checking missing data for {filename}: {e}")

        result_df = pd.DataFrame(result_dict).set_index("instruments") if result_dict["instruments"] else None
        if result_df is not None and not result_df.empty:
            return result_df
        else:
            logger.info(f"✅ There are no missing data.")
            return None

    def check_large_step_changes(self) -> Optional[pd.DataFrame]:
        """
        检查OHLCV列中是否存在超过阈值的大幅变动
        
        Returns:
            包含大幅变动信息的DataFrame，如果没有则返回None
        """
        result_dict = {
            "instruments": [],
            "col_name": [],
            "timestamp": [],
            "pct_change": [],
        }
        
        for filename, df in self.data.items():
            try:
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in df.columns and len(df) > 1:
                        try:
                            # 计算百分比变化，忽略NaN值
                            pct_change = df[col].pct_change(fill_method=None).abs()
                            threshold = self.large_step_threshold_volume if col == "volume" else self.large_step_threshold_price
                            
                            if pct_change.max() > threshold:
                                large_steps = pct_change[pct_change > threshold]
                                if not large_steps.empty:
                                    # 获取第一个大幅变动的数据点
                                    first_large_step_idx = large_steps.index[0]
                                    
                                    # 处理不同类型的索引格式
                                    if isinstance(first_large_step_idx, tuple):
                                        # 对于多级索引
                                        timestamp = str(first_large_step_idx[1])
                                    else:
                                        # 对于单级索引
                                        timestamp = str(first_large_step_idx)
                                    
                                    result_dict["instruments"].append(filename)
                                    result_dict["col_name"].append(col)
                                    result_dict["timestamp"].append(timestamp)
                                    result_dict["pct_change"].append(float(pct_change.max()))
                        except Exception as e:
                            logger.error(f"Error calculating pct_change for {filename}:{col}: {e}")
            except Exception as e:
                logger.error(f"Error checking large step changes for {filename}: {e}")

        result_df = pd.DataFrame(result_dict).set_index("instruments") if result_dict["instruments"] else None
        if result_df is not None and not result_df.empty:
            return result_df
        else:
            logger.info(f"✅ There are no large step changes in the OHLCV column above the threshold.")
            return None

    def check_required_columns(self) -> Optional[pd.DataFrame]:
        """
        检查必需的OHLCV列是否存在
        
        Returns:
            包含缺失列信息的DataFrame，如果没有缺失则返回None
        """
        required_columns = ["open", "high", "low", "close", "volume"]
        result_dict = {
            "instruments": [],
            "missing_col": [],
        }
        
        for filename, df in self.data.items():
            try:
                if not all(column in df.columns for column in required_columns):
                    missing_required_columns = [column for column in required_columns if column not in df.columns]
                    result_dict["instruments"].append(filename)
                    result_dict["missing_col"].append(", ".join(missing_required_columns))
            except Exception as e:
                logger.error(f"Error checking required columns for {filename}: {e}")

        result_df = pd.DataFrame(result_dict).set_index("instruments") if result_dict["instruments"] else None
        if result_df is not None and not result_df.empty:
            return result_df
        else:
            logger.info(f"✅ The columns (OLHCV) are complete and not missing.")
            return None

    def check_missing_factor(self) -> Optional[pd.DataFrame]:
        """
        检查factor列是否缺失（针对加密货币数据，factor列是可选的）
        
        Returns:
            包含factor缺失信息的DataFrame，如果没有问题则返回None
        """
        # 对于加密货币数据，factor列可能不是必需的
        if self.freq in ["1min", "5min", "15min", "30min", "60min"]:
            logger.info(f"⚠️ Factor column check skipped for {self.freq} frequency data")
            return None
            
        result_dict = {
            "instruments": [],
            "missing_factor_col": [],
            "missing_factor_data": [],
        }
        
        for filename, df in self.data.items():
            try:
                # 跳过特定的指数文件检查
                if any(idx in str(filename) for idx in ["000300", "000903", "000905"]):
                    continue
                
                has_factor_col = "factor" in df.columns
                result_dict["instruments"].append(filename)
                result_dict["missing_factor_col"].append(not has_factor_col)
                
                if has_factor_col:
                    result_dict["missing_factor_data"].append(df["factor"].isnull().all())
                else:
                    result_dict["missing_factor_data"].append(True)
            except Exception as e:
                logger.error(f"Error checking factor column for {filename}: {e}")

        result_df = pd.DataFrame(result_dict).set_index("instruments") if result_dict["instruments"] else None
        if result_df is not None and not result_df.empty:
            # 只返回确实有问题的行
            problematic_rows = result_df[(result_df["missing_factor_col"] == True) | (result_df["missing_factor_data"] == True)]
            if not problematic_rows.empty:
                return problematic_rows
        
        logger.info(f"✅ The `factor` column check passed.")
        return None

    def check_data(self):
        """
        执行所有数据健康检查并显示结果
        """
        logger.info(f"Starting data health check for {len(self.data)} instruments with frequency: {self.freq}")
        
        check_missing_data_result = self.check_missing_data()
        check_large_step_changes_result = self.check_large_step_changes()
        check_required_columns_result = self.check_required_columns()
        check_missing_factor_result = self.check_missing_factor()
        
        # 检查是否有任何问题
        has_problems = (
            check_missing_data_result is not None
            or check_large_step_changes_result is not None
            or check_required_columns_result is not None
            or check_missing_factor_result is not None
        )
        
        if has_problems:
            print(f"\nSummary of data health check ({len(self.data)} instruments checked):")
            print("-------------------------------------------------")
            if isinstance(check_missing_data_result, pd.DataFrame):
                logger.warning(f"❌ There is missing data.")
                print(check_missing_data_result)
                print()
            if isinstance(check_large_step_changes_result, pd.DataFrame):
                logger.warning(f"❌ The OHLCV column has large step changes.")
                print(check_large_step_changes_result)
                print()
            if isinstance(check_required_columns_result, pd.DataFrame):
                logger.warning(f"❌ Columns (OLHCV) are missing.")
                print(check_required_columns_result)
                print()
            if isinstance(check_missing_factor_result, pd.DataFrame):
                logger.warning(f"❌ The factor column does not exist or is empty")
                print(check_missing_factor_result)
                print()
        else:
            logger.info(f"🎉 All data health checks passed for {len(self.data)} instruments!")
            print(f"\nData health check summary ({len(self.data)} instruments checked):")
            print("-------------------------------------------------")
            print("✅ No data issues found!")


if __name__ == "__main__":
    # 设置日志级别
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level="INFO")
    fire.Fire(DataHealthChecker)
