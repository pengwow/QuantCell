# 数据加载模块，用于从qlib_dir加载已下载的数据

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# 添加项目根目录到Python路径
backend_root = Path(__file__).parent.parent  # /Users/liupeng/workspace/quantcell/backend
project_root = backend_root.parent  # /Users/liupeng/workspace/quantcell
sys.path.append(str(project_root))

# 添加qlib目录到Python路径
qlib_dir = project_root / "qlib"
sys.path.append(str(qlib_dir))

# 导入自定义日历提供者，触发monkey patching
# try:
#     from qlib_integration import custom_calendar_provider
#     logger.info("成功导入custom_calendar_provider模块")
# except Exception as e:
#     logger.error(f"导入custom_calendar_provider模块失败: {e}")
#     raise

# 导入QLib相关模块
# try:
#     from qlib.config import C
#     from qlib.data import D
#     from qlib.data.dataset.handler import DataHandlerLP
#     logger.info("成功导入QLib模块")
# except Exception as e:
#     logger.error(f"导入QLib模块失败: {e}")
#     raise


class QLibDataLoader:
    """QLib数据加载器，用于加载和管理QLib格式的数据
    
    实现单例模式，确保全局只有一个数据加载器实例
    """
    
    _instance = None
    
    def __new__(cls):
        """创建单例实例
        
        Returns:
            QLibDataLoader: 数据加载器实例
        """
        if cls._instance is None:
            cls._instance = super(QLibDataLoader, cls).__new__(cls)
            cls._instance._initialized = False
            cls._instance._qlib_dir = None
            cls._instance._data_loaded = False
            cls._instance._instruments = None
            cls._instance._calendars = None
            cls._instance._features = None
        return cls._instance
    
    def __init__(self):
        """初始化数据加载器
        """
        if not self._initialized:
            self._initialized = True
            logger.info("初始化QLib数据加载器")
    
    def init_qlib(self, qlib_dir: str) -> bool:
        """初始化QLib，设置数据目录
        
        Args:
            qlib_dir: QLib数据目录，可以是绝对路径或相对路径
            
        Returns:
            bool: 初始化成功返回True，失败返回False
        """
        try:
            logger.info(f"开始初始化QLib，数据目录: {qlib_dir}")
            
            # 处理相对路径，将相对路径转换为基于backend目录的绝对路径
            qlib_dir_path = Path(qlib_dir)
            if not qlib_dir_path.is_absolute():
                # 相对路径，基于backend目录
                qlib_dir_path = backend_root / qlib_dir_path
                logger.info(f"相对路径转换为绝对路径: {qlib_dir} -> {qlib_dir_path}")
            
            # 检查目录是否存在
            qlib_dir_path = qlib_dir_path.expanduser().resolve()
            if not qlib_dir_path.exists():
                logger.error(f"QLib数据目录不存在: {qlib_dir_path}")
                return False
            
            # 导入qlib模块
            import qlib

            # 初始化qlib
            qlib.init(
                provider_uri=str(qlib_dir_path),
            )
            logger.info(f"成功调用qlib.init()，数据目录: {qlib_dir_path}")
            
            # 设置QLib数据目录
            C["qlib_data_dir"] = str(qlib_dir_path)
            self._qlib_dir = qlib_dir_path
            
            # 尝试加载数据
            self.load_data()
            
            logger.info(f"QLib初始化成功，数据目录: {qlib_dir_path}")
            return True
        except Exception as e:
            logger.error(f"初始化QLib失败: {e}")
            logger.exception(e)
            return False
    
    def load_data(self) -> bool:
        """加载QLib数据
        
        Returns:
            bool: 加载成功返回True，失败返回False
        """
        try:
            logger.info("开始加载QLib数据")
            
            # 移除过时的D.init()调用，D对象在qlib.init()后应该已经可用
            # 尝试直接使用D对象，测试其是否可用
            try:
                # 尝试获取一个日历，测试D对象是否可用
                D.calendar(freq="1d")
                logger.info("D对象可用，无需调用init方法")
            except Exception as e:
                logger.warning(f"测试D对象时出现异常: {e}，但继续尝试加载数据")
            
            self._data_loaded = True
            
            # 加载交易日历
            self._calendars = self._load_calendars()
            
            # 加载成分股信息
            self._instruments = self._load_instruments()
            
            # 加载特征信息
            self._features = self._load_features()
            
            logger.info("QLib数据加载成功")
            return True
        except Exception as e:
            logger.error(f"加载QLib数据失败: {e}")
            logger.exception(e)
            self._data_loaded = False
            return False
    
    def _load_calendars(self) -> Dict[str, List[str]]:
        """加载交易日历
        
        Returns:
            Dict[str, List[str]]: 交易日历字典，键为频率，值为日期列表
        """
        try:
            calendars = {}
            
            # 支持的频率列表
            supported_freqs = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "day"]
            
            # 使用D.calendar()函数获取日历信息
            for freq in supported_freqs:
                try:
                    logger.info(f"尝试加载频率为{freq}的交易日历")
                    # 使用D.calendar()获取日历
                    calendar = D.calendar(freq=freq)
                    logger.info(f"获取频率为{freq}的交易日历结果: {calendar}")
                    if calendar is not None and len(calendar) > 0:
                        # 将numpy.ndarray转换为Python标准类型列表，将Timestamp对象转换为字符串
                        calendar_list = []
                        for date in calendar:
                            try:
                                # 转换Timestamp对象为字符串格式
                                date_str = str(date)
                                calendar_list.append(date_str)
                            except Exception as e:
                                logger.warning(f"转换日期时出现异常: {e}, 日期: {date}")
                                continue
                        
                        calendars[freq] = calendar_list
                        logger.info(f"加载交易日历成功: {freq}, 共 {len(calendar_list)} 个交易日")
                    else:
                        logger.warning(f"加载交易日历失败: {freq}, 日历为空")
                except Exception as e:
                    logger.warning(f"加载交易日历失败: {freq}, 错误: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            logger.info(f"最终加载的交易日历: {list(calendars.keys())}")
            return calendars
        except Exception as e:
            logger.error(f"加载交易日历失败: {e}")
            logger.exception(e)
            import traceback
            traceback.print_exc()
            return {}
    
    def _load_instruments(self) -> Dict[str, List[str]]:
        """加载成分股信息
        
        Returns:
            Dict[str, List[str]]: 成分股字典，键为指数名称，值为股票列表
        """
        try:
            instruments = {}
            
            # 获取成分股目录
            instruments_dir = self._qlib_dir / "instruments"
            if not instruments_dir.exists():
                logger.warning(f"成分股目录不存在: {instruments_dir}")
                return instruments
            
            # 遍历成分股文件
            for instrument_file in instruments_dir.glob("*.txt"):
                index_name = instrument_file.stem
                with open(instrument_file, "r") as f:
                    stocks = [line.strip() for line in f if line.strip()]
                instruments[index_name] = stocks
                logger.info(f"加载成分股成功: {index_name}, 共 {len(stocks)} 只股票")
            
            return instruments
        except Exception as e:
            logger.error(f"加载成分股失败: {e}")
            logger.exception(e)
            return {}
    
    def _load_features(self) -> Dict[str, List[str]]:
        """加载特征信息
        
        Returns:
            Dict[str, List[str]]: 特征字典，键为股票代码，值为特征列表
        """
        try:
            features = {}
            
            # 获取特征目录
            features_dir = self._qlib_dir / "features"
            if not features_dir.exists():
                logger.warning(f"特征目录不存在: {features_dir}")
                return features
            
            # 遍历股票目录
            for stock_dir in features_dir.iterdir():
                if stock_dir.is_dir():
                    symbol = stock_dir.name
                    # 获取该股票的所有特征文件
                    feature_files = list(stock_dir.glob("*.bin"))
                    feature_names = [f.stem for f in feature_files]
                    features[symbol] = feature_names
                    logger.info(f"加载特征成功: {symbol}, 共 {len(feature_names)} 个特征")
            
            return features
        except Exception as e:
            logger.error(f"加载特征失败: {e}")
            logger.exception(e)
            return {}
    
    def get_loaded_data_info(self) -> Dict[str, Any]:
        """获取已加载的数据信息
        
        Returns:
            Dict[str, Any]: 已加载的数据信息
        """
        return {
            "qlib_dir": str(self._qlib_dir) if self._qlib_dir else None,
            "data_loaded": self._data_loaded,
            "calendars": self._calendars,
            "instruments": self._instruments,
            "features": self._features,
            "total_instruments": sum(len(stocks) for stocks in self._instruments.values()) if self._instruments else 0,
            "total_features": sum(len(features) for features in self._features.values()) if self._features else 0
        }
    
    def get_calendars(self) -> Dict[str, List[str]]:
        """获取交易日历
        
        Returns:
            Dict[str, List[str]]: 交易日历字典
        """
        return self._calendars or {}
    
    def get_instruments(self) -> Dict[str, List[str]]:
        """获取成分股信息
        
        Returns:
            Dict[str, List[str]]: 成分股字典
        """
        return self._instruments or {}
    
    def get_features(self) -> Dict[str, List[str]]:
        """获取特征信息
        
        Returns:
            Dict[str, List[str]]: 特征字典
        """
        return self._features or {}
    
    def get_symbol_features(self, symbol: str) -> List[str]:
        """获取指定股票的特征列表
        
        Args:
            symbol: 股票代码
            
        Returns:
            List[str]: 特征列表
        """
        if self._features and symbol in self._features:
            return self._features[symbol]
        return []
    
    def is_data_loaded(self) -> bool:
        """检查数据是否已加载
        
        Returns:
            bool: 数据已加载返回True，否则返回False
        """
        return self._data_loaded
    
    def get_qlib_dir(self) -> Optional[str]:
        """获取QLib数据目录
        
        Returns:
            Optional[str]: QLib数据目录
        """
        return str(self._qlib_dir) if self._qlib_dir else None


# 创建全局数据加载器实例
data_loader = QLibDataLoader()
