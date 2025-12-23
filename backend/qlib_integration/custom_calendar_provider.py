from typing import List

from qlib.data.data import LocalCalendarProvider
# 导入FileCalendarStorage类
from qlib.data.storage.file_storage import FileCalendarStorage
# 现在导入的Freq就是自定义的Freq类
from qlib.utils.time import Freq

# 确保先导入自定义Freq类，这样修改load_calendar方法时使用的就是自定义的Freq类
from backend.qlib_integration import custom_freq
# 导入配置
from backend.qlib_integration.config import CALENDAR_DIR, FREQ_MAP


class CustomFileCalendarStorage(FileCalendarStorage):
    """
    自定义日历存储类，替代猴子补丁实现
    
    支持：
    - 动态数字+时间范围的文件名
    - 从calendars/目录加载日历文件
    """
    
    @property
    def _freq_file(self) -> str:
        """
        自定义_freq_file属性，支持动态数字+时间范围的文件名
        - 当freq='1m'时，返回'1m'
        - 当freq='1min'时，返回'1m'
        - 当freq='5m'时，返回'5m'
        - 当freq='1h'时，返回'1h'
        - 当freq='1d'时，返回'1d'
        - 当freq='day'时，返回'1d'（处理qlib内部的情况）
        
        Returns
        -------
        str
            自定义的频率字符串
        """
        # 处理字符串形式的freq
        if isinstance(self.freq, str):
            freq_str = self.freq.lower()
            # 直接映射常见的频率字符串
            if freq_str == "day":
                return "1d"
            if freq_str == "hour":
                return "1h"
            if freq_str == "min":
                return "1m"
            
            # 解析频率对象
            freq_obj = Freq(self.freq)
        else:
            freq_obj = self.freq
        
        # 获取count和base
        count = freq_obj.count
        base = freq_obj.base
        
        # 根据base属性决定使用哪个后缀
        if base == "min":
            # 分钟频率使用m作为后缀
            suffix = "m"
        elif base == "hour":
            # 小时频率使用h作为后缀
            suffix = "h"
        elif base == "day":
            # 天频率使用d作为后缀
            suffix = "d"
        else:
            # 其他频率使用默认逻辑
            return super()._freq_file
        
        # 构建频率字符串，如1m, 5m, 1h, 1d, 5d
        return f"{count}{suffix}"
    
    @property
    def file_name(self) -> str:
        """
        自定义file_name属性，确保使用正确的文件名格式
        - 当freq='1d'时，返回'1d.txt'而不是'd.txt'
        - 当freq='day'时，返回'1d.txt'而不是'd.txt'
        
        Returns
        -------
        str
            自定义的文件名
        """
        # 使用_freq_file的结果构建文件名
        return f"{self._freq_file}_future.txt" if self.future else f"{self._freq_file}.txt"
    
    @property
    def uri(self):
        """
        自定义uri属性，支持从calendars/目录加载日历文件
        
        Returns
        -------
        Path
            自定义的日历文件路径
        """
        # 构建自定义路径
        # 获取正确的freq参数，确保使用原始freq而不是_freq_file
        freq = self.freq
        if isinstance(freq, str):
            freq_obj = Freq(freq)
        else:
            freq_obj = freq
        
        # 使用正确的freq获取数据路径
        data_uri = self.dpm.get_data_uri(freq_obj)
        # 使用自定义的file_name
        return data_uri.joinpath(f"{self.storage_name}s", self.file_name)


class CustomCalendarProvider(LocalCalendarProvider):
    """
    自定义日历提供类，使用自定义存储类替代猴子补丁
    
    使用方法：
    ```python
    from backend.qlib_integration.custom_calendar_provider import CustomCalendarProvider
    
    # 创建自定义日历提供器实例
    calendar_provider = CustomCalendarProvider()
    
    # 使用日历提供器获取日历
    calendar = calendar_provider.calendar(start_time="2023-01-01", end_time="2023-12-31", freq="1d")
    ```
    """
    
    def __init__(self, remote=False, backend=None):
        """
        初始化自定义日历提供类
        
        Parameters
        ----------
        remote : bool, optional
            是否使用远程日历，默认为False
        backend : dict, optional
            后端配置，默认为None，此时会使用自定义存储类
        """
        # 如果没有提供backend配置，使用默认配置
        if backend is None:
            backend = {
                "class": "CustomFileCalendarStorage",
                "module_path": "backend.qlib_integration.custom_calendar_provider"
            }
        super().__init__(remote=remote, backend=backend)






