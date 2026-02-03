#!/usr/bin/env python3
"""数据健康检查脚本

参考 /Users/liupeng/workspace/quantcell/qlib/scripts/check_data_health.py 脚本，拆分成两个部分：
1. 检查下载后的数据源文件（CSV文件）
2. 检查转成bin后的文件（QLib数据目录）

支持两个路径参数：
- csv_path：下载后的数据源文件目录
- qlib_dir：转成bin后的文件目录
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

# 添加项目根目录到Python路径
backend_root = Path(__file__).parent.parent
project_root = backend_root.parent
sys.path.append(str(project_root))

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)


class DataHealthChecker:
    """数据健康检查类
    
    检查数据的完整性和正确性，包括：
    - 缺失的数据
    - 大的价格或成交量波动
    - 缺失的必要列（OHLCV）
    - 缺失的factor列
    """
    
    def __init__(
        self,
        csv_path: Optional[str] = None,
        qlib_dir: Optional[str] = None,
        freq: str = "day",
        large_step_threshold_price: float = 0.5,
        large_step_threshold_volume: float = 3,
        missing_data_num: int = 0,
    ):
        """初始化数据健康检查类
        
        Args:
            csv_path: 下载后的数据源文件目录
            qlib_dir: 转成bin后的文件目录
            freq: 数据频率（默认：day）
            large_step_threshold_price: 价格大波动的阈值（默认：0.5）
            large_step_threshold_volume: 成交量大波动的阈值（默认：3）
            missing_data_num: 允许的缺失数据数量（默认：0）
        """
        self.csv_path = csv_path
        self.qlib_dir = qlib_dir
        self.freq = freq
        self.large_step_threshold_price = large_step_threshold_price
        self.large_step_threshold_volume = large_step_threshold_volume
        self.missing_data_num = missing_data_num
    
    def check_csv_data(self, csv_path: Optional[str] = None) -> Dict[str, Optional[pd.DataFrame]]:
        """检查CSV文件数据
        
        Args:
            csv_path: CSV文件目录路径，如果不提供则使用实例变量中的csv_path
            
        Returns:
            Dict[str, Optional[pd.DataFrame]]: 检查结果字典，包含各个检查项的结果
        """
        # 使用实例变量中的csv_path如果没有提供参数
        csv_path = csv_path if csv_path is not None else self.csv_path
        
        if not csv_path:
            logger.error("CSV文件目录路径未提供")
            return {}
        
        logger.info(f"开始检查CSV文件数据，目录: {csv_path}")
        
        # 检查目录是否存在
        if not os.path.isdir(csv_path):
            logger.error(f"CSV目录不存在: {csv_path}")
            return {}
        
        # 获取所有CSV文件
        csv_files = [f for f in os.listdir(csv_path) if f.endswith(".csv")]
        logger.info(f"找到 {len(csv_files)} 个CSV文件")
        
        if not csv_files:
            logger.warning(f"CSV目录中没有CSV文件: {csv_path}")
            return {}
        
        # 加载CSV文件
        data = {}
        for filename in csv_files:
            file_path = os.path.join(csv_path, filename)
            try:
                df = pd.read_csv(file_path)
                data[filename] = df
                logger.info(f"成功加载CSV文件: {filename}")
            except Exception as e:
                logger.error(f"加载CSV文件失败: {filename}, 错误: {e}")
                continue
        
        # 执行检查
        results = {
            "missing_data": self._check_missing_data(data),
            "large_step_changes": self._check_large_step_changes(data),
            "required_columns": self._check_required_columns(data),
            "missing_factor": self._check_missing_factor(data)
        }
        
        # 输出检查结果
        self._output_results(results, "CSV文件")
        
        return results
    
    def check_qlib_data(self, qlib_dir: Optional[str] = None, freq: Optional[str] = None) -> Dict[str, Optional[pd.DataFrame]]:
        """检查QLib数据
        
        Args:
            qlib_dir: QLib数据目录路径，如果不提供则使用实例变量中的qlib_dir
            freq: 数据频率，如果不提供则使用实例变量中的freq
            
        Returns:
            Dict[str, Optional[pd.DataFrame]]: 检查结果字典，包含各个检查项的结果
        """
        # 使用实例变量中的qlib_dir和freq如果没有提供参数
        qlib_dir = qlib_dir if qlib_dir is not None else self.qlib_dir
        freq = freq if freq is not None else self.freq
        
        if not qlib_dir:
            logger.error("QLib数据目录路径未提供")
            return {}
        
        logger.info(f"开始检查QLib数据，目录: {qlib_dir}, 频率: {freq}")
        
        # 检查目录是否存在
        if not os.path.isdir(qlib_dir):
            logger.error(f"QLib目录不存在: {qlib_dir}")
            return {}
        
        # 导入QLib模块
        try:
            import qlib
            from qlib.data import D

            # 初始化QLib
            qlib.init(provider_uri=qlib_dir)
            logger.info(f"成功初始化QLib，数据目录: {qlib_dir}")
        except Exception as e:
            logger.error(f"初始化QLib失败: {e}")
            return {}
        
        # 加载QLib数据
        data = {}
        try:
            # 获取所有标的
            instruments = D.instruments(market="all")
            instrument_list = D.list_instruments(instruments=instruments, as_list=True, freq=freq)
            logger.info(f"找到 {len(instrument_list)} 个标的")
            
            if not instrument_list:
                logger.warning(f"QLib数据中没有标的: {qlib_dir}")
                return {}
            
            # 加载标的数据
            required_fields = ["$open", "$close", "$low", "$high", "$volume", "$factor"]
            for instrument in instrument_list:
                try:
                    df = D.features([instrument], required_fields, freq=freq)
                    # 重命名列
                    df = df.rename(columns={
                        "$open": "open",
                        "$close": "close",
                        "$low": "low",
                        "$high": "high",
                        "$volume": "volume",
                        "$factor": "factor",
                    })
                    data[instrument] = df
                    logger.info(f"成功加载标的数据: {instrument}")
                except Exception as e:
                    logger.error(f"加载标的数据失败: {instrument}, 错误: {e}")
                    continue
        except Exception as e:
            logger.error(f"加载QLib数据失败: {e}")
            return {}
        
        # 执行检查
        results = {
            "missing_data": self._check_missing_data(data),
            "large_step_changes": self._check_large_step_changes(data),
            "required_columns": self._check_required_columns(data),
            "missing_factor": self._check_missing_factor(data)
        }
        
        # 输出检查结果
        self._output_results(results, "QLib数据")
        
        return results
    
    def _check_missing_data(self, data: Dict[str, pd.DataFrame]) -> Optional[pd.DataFrame]:
        """检查是否有缺失的数据
        
        Args:
            data: 数据字典，键为文件名或标的名，值为DataFrame
            
        Returns:
            Optional[pd.DataFrame]: 缺失数据的检查结果，没有缺失数据则返回None
        """
        logger.info("开始检查缺失数据")
        
        result_dict = {
            "instruments": [],
            "open": [],
            "high": [],
            "low": [],
            "close": [],
            "volume": [],
        }
        
        for name, df in data.items():
            missing_data_columns = df.isnull().sum()[df.isnull().sum() > self.missing_data_num].index.tolist()
            if len(missing_data_columns) > 0:
                result_dict["instruments"].append(name)
                result_dict["open"].append(df.isnull().sum()["open"] if "open" in df.columns else None)
                result_dict["high"].append(df.isnull().sum()["high"] if "high" in df.columns else None)
                result_dict["low"].append(df.isnull().sum()["low"] if "low" in df.columns else None)
                result_dict["close"].append(df.isnull().sum()["close"] if "close" in df.columns else None)
                result_dict["volume"].append(df.isnull().sum()["volume"] if "volume" in df.columns else None)
        
        result_df = pd.DataFrame(result_dict).set_index("instruments")
        if not result_df.empty:
            logger.warning(f"发现缺失数据的标的: {len(result_df)} 个")
            return result_df
        else:
            logger.info(f"✅ 没有缺失数据")
            return None
    
    def _check_large_step_changes(self, data: Dict[str, pd.DataFrame]) -> Optional[pd.DataFrame]:
        """检查是否有大的价格或成交量波动
        
        Args:
            data: 数据字典，键为文件名或标的名，值为DataFrame
            
        Returns:
            Optional[pd.DataFrame]: 大波动的检查结果，没有大波动则返回None
        """
        logger.info("开始检查大的价格或成交量波动")
        
        result_dict = {
            "instruments": [],
            "col_name": [],
            "date": [],
            "pct_change": [],
        }
        
        for name, df in data.items():
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    pct_change = df[col].pct_change(fill_method=None).abs()
                    threshold = self.large_step_threshold_volume if col == "volume" else self.large_step_threshold_price
                    if pct_change.max() > threshold:
                        large_steps = pct_change[pct_change > threshold]
                        if not large_steps.empty:
                            # 获取第一个大波动的日期
                            first_large_step = large_steps.iloc[0]
                            # 处理日期格式
                            date = None
                            if isinstance(large_steps.index, pd.MultiIndex):
                                # 对于MultiIndex，日期在第二级
                                date = large_steps.index[0][1].strftime("%Y-%m-%d")
                            else:
                                # 对于普通Index，直接使用
                                date = large_steps.index[0].strftime("%Y-%m-%d")
                            
                            result_dict["instruments"].append(name)
                            result_dict["col_name"].append(col)
                            result_dict["date"].append(date)
                            result_dict["pct_change"].append(first_large_step)
        
        result_df = pd.DataFrame(result_dict).set_index("instruments")
        if not result_df.empty:
            logger.warning(f"发现大波动的标的: {len(result_df)} 个")
            return result_df
        else:
            logger.info(f"✅ 没有大的价格或成交量波动")
            return None
    
    def _check_required_columns(self, data: Dict[str, pd.DataFrame]) -> Optional[pd.DataFrame]:
        """检查是否有缺失的必要列（OHLCV）
        
        Args:
            data: 数据字典，键为文件名或标的名，值为DataFrame
            
        Returns:
            Optional[pd.DataFrame]: 缺失必要列的检查结果，没有缺失则返回None
        """
        logger.info("开始检查缺失的必要列（OHLCV）")
        
        required_columns = ["open", "high", "low", "close", "volume"]
        result_dict = {
            "instruments": [],
            "missing_col": [],
        }
        
        for name, df in data.items():
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                result_dict["instruments"].append(name)
                result_dict["missing_col"].append(", ".join(missing_columns))
        
        result_df = pd.DataFrame(result_dict).set_index("instruments")
        if not result_df.empty:
            logger.warning(f"发现缺失必要列的标的: {len(result_df)} 个")
            return result_df
        else:
            logger.info(f"✅ 没有缺失的必要列（OHLCV）")
            return None
    
    def _check_missing_factor(self, data: Dict[str, pd.DataFrame]) -> Optional[pd.DataFrame]:
        """检查是否有缺失的factor列
        
        Args:
            data: 数据字典，键为文件名或标的名，值为DataFrame
            
        Returns:
            Optional[pd.DataFrame]: 缺失factor列的检查结果，没有缺失则返回None
        """
        logger.info("开始检查缺失的factor列")
        
        result_dict = {
            "instruments": [],
            "missing_factor_col": [],
            "missing_factor_data": [],
        }
        
        for name, df in data.items():
            # 跳过指数标的
            if "000300" in name or "000903" in name or "000905" in name:
                continue
            
            has_missing_col = "factor" not in df.columns
            has_missing_data = False
            if "factor" in df.columns:
                has_missing_data = df["factor"].isnull().all()
            
            if has_missing_col or has_missing_data:
                result_dict["instruments"].append(name)
                result_dict["missing_factor_col"].append(has_missing_col)
                result_dict["missing_factor_data"].append(has_missing_data)
        
        result_df = pd.DataFrame(result_dict).set_index("instruments")
        if not result_df.empty:
            logger.warning(f"发现缺失factor列的标的: {len(result_df)} 个")
            return result_df
        else:
            logger.info(f"✅ 没有缺失的factor列")
            return None
    
    def _output_results(self, results: Dict[str, Optional[pd.DataFrame]], data_type: str):
        """输出检查结果
        
        Args:
            results: 检查结果字典
            data_type: 数据类型（CSV文件或QLib数据）
        """
        logger.info(f"\n{data_type}健康检查结果:")
        logger.info("=" * 50)
        
        has_issues = False
        
        # 输出缺失数据检查结果
        if results["missing_data"] is not None:
            has_issues = True
            logger.warning(f"缺失数据检查: 发现 {len(results['missing_data'])} 个问题")
            print(results["missing_data"])
            print()
        
        # 输出大波动检查结果
        if results["large_step_changes"] is not None:
            has_issues = True
            logger.warning(f"大波动检查: 发现 {len(results['large_step_changes'])} 个问题")
            print(results["large_step_changes"])
            print()
        
        # 输出缺失必要列检查结果
        if results["required_columns"] is not None:
            has_issues = True
            logger.warning(f"缺失必要列检查: 发现 {len(results['required_columns'])} 个问题")
            print(results["required_columns"])
            print()
        
        # 输出缺失factor列检查结果
        if results["missing_factor"] is not None:
            has_issues = True
            logger.warning(f"缺失factor列检查: 发现 {len(results['missing_factor'])} 个问题")
            print(results["missing_factor"])
            print()
        
        # 输出总体结果
        if not has_issues:
            logger.info(f"✅ {data_type}健康检查通过，没有发现问题")
        else:
            logger.error(f"❌ {data_type}健康检查失败，发现多个问题")
        
        logger.info("=" * 50)
    
    def run(self):
        """执行健康检查
        
        根据实例变量中的csv_path和qlib_dir来执行相应的健康检查
        """
        # 检查参数
        if not self.csv_path and not self.qlib_dir:
            logger.error("必须提供 csv_path 或 qlib_dir 参数")
            import sys
            sys.exit(1)
        
        # 执行检查
        if self.csv_path:
            self.check_csv_data()
        
        if self.qlib_dir:
            self.check_qlib_data()


if __name__ == "__main__":
    import fire
    fire.Fire(DataHealthChecker)
