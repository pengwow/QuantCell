# 确保在导入任何QLib模块之前，将项目根目录添加到sys.path
import sys
from pathlib import Path

# 获取当前文件的绝对路径
current_file = Path(__file__).resolve()
# 获取项目根目录 (backend/qlib_integration/custom_freq.py -> backend -> qbot)
project_root = current_file.parent.parent.parent

# 将项目根目录添加到sys.path
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
    print(f"[INFO] custom_freq: 已将项目根目录添加到sys.path: {project_root}")

import re
from typing import Tuple, Union

print(f"[INFO] custom_freq: 开始导入QLib的Freq类")
from qlib.utils.time import Freq as QlibFreq

print(f"[INFO] custom_freq: 成功导入QLib的Freq类")

# 保存原始Freq类，以便需要时恢复
OriginalFreq = QlibFreq
print(f"[INFO] custom_freq: 已保存原始Freq类")

class CustomFreq(QlibFreq):
    """
    自定义Freq类，支持更多频率格式
    """
    
    @staticmethod
    def parse(freq: str) -> Tuple[int, str]:
        """
        解析频率字符串，支持更多格式
        
        Parameters
        ----------
        freq : str
            原始频率字符串，支持格式：
            - 分钟：(n)minute/min/m
            - 小时：(n)hour/h
            - 天：(n)day/d
            - 周：(n)week/w
            - 月：(n)month/mon
        
        Returns
        -------
        Tuple[int, str]
            解析后的频率计数和单位
        """
        freq = freq.lower()
        # 更新正则表达式，支持小时（h）和分钟简写（m）
        match_obj = re.match(r"^([0-9]*)(month|mon|week|w|day|d|hour|h|minute|min|m)$", freq)
        if match_obj is None:
            raise ValueError(
                "freq format is not supported, the freq should be like (n)month/mon, (n)week/w, (n)day/d, (n)hour/h, (n)minute/min/m"
            )
        _count = int(match_obj.group(1)) if match_obj.group(1) else 1
        _freq = match_obj.group(2)
        _freq_format_dict = {
            "month": CustomFreq.NORM_FREQ_MONTH,
            "mon": CustomFreq.NORM_FREQ_MONTH,
            "week": CustomFreq.NORM_FREQ_WEEK,
            "w": CustomFreq.NORM_FREQ_WEEK,
            "day": CustomFreq.NORM_FREQ_DAY,
            "d": CustomFreq.NORM_FREQ_DAY,
            "hour": "hour",  # 小时格式
            "h": "hour",  # 小时简写
            "minute": CustomFreq.NORM_FREQ_MINUTE,
            "min": CustomFreq.NORM_FREQ_MINUTE,
            "m": CustomFreq.NORM_FREQ_MINUTE,  # 分钟简写
        }
        return _count, _freq_format_dict[_freq]
    
    def __str__(self) -> str:
        """
        重写__str__方法，确保返回正确的文件名格式
        - 分钟：返回"1m"而不是"1min"
        - 小时：返回"1h"而不是"1hour"
        - 天：返回"1d"而不是"day"
        - 其他格式保持不变
        
        Returns
        -------
        str
            格式化后的频率字符串，用于生成文件名
        """
        # 特殊处理分钟、小时和天格式
        if self.base == "min":
            # 分钟频率使用m作为后缀
            return f"{self.count}m" if self.count > 1 else "1m"
        elif self.base == "hour":
            # 小时频率使用h作为后缀
            return f"{self.count}h" if self.count > 1 else "1h"
        elif self.base == "day":
            # 天频率使用d作为后缀，确保返回1d而不是day
            return f"{self.count}d" if self.count > 1 else "1d"
        # 其他格式使用默认实现
        return super().__str__()
    
    def __repr__(self) -> str:
        """
        重写__repr__方法，提供更有用的调试信息
        
        Returns
        -------
        str
            格式化后的频率字符串，用于调试
        """
        return f"CustomFreq(base={self.base}, count={self.count}, str={str(self)})"

# Monkey patching：替换qlib.utils.time.Freq为自定义类
print(f"[INFO] custom_freq: 开始替换QLib的Freq类")
import qlib.utils.time

# 替换原始Freq类为自定义类
qlib.utils.time.Freq = CustomFreq
print(f"[INFO] custom_freq: 已将QLib的Freq类替换为CustomFreq")

# 验证替换是否成功
from qlib.utils.time import Freq

print(f"[INFO] custom_freq: 验证替换结果，Freq类是: {Freq}")
print(f"[INFO] custom_freq: Freq.__str__方法是: {Freq.__str__}")

# 测试CustomFreq的__str__方法
freq_obj = Freq("1d")
print(f"[INFO] custom_freq: 测试Freq('1d'): {freq_obj}, str(freq_obj): {str(freq_obj)}")
print(f"[INFO] custom_freq: freq_obj.base: {freq_obj.base}, freq_obj.count: {freq_obj.count}")

# 更新SUPPORT_CAL_LIST，添加小时支持
print(f"[INFO] custom_freq: 开始更新SUPPORT_CAL_LIST")
qlib.utils.time.Freq.SUPPORT_CAL_LIST = [
    qlib.utils.time.Freq.NORM_FREQ_MINUTE, 
    "hour", 
    qlib.utils.time.Freq.NORM_FREQ_DAY
]
print(f"[INFO] custom_freq: SUPPORT_CAL_LIST已更新为: {qlib.utils.time.Freq.SUPPORT_CAL_LIST}")

# 更新get_timedelta方法，添加小时处理
print(f"[INFO] custom_freq: 开始更新get_timedelta方法")
original_get_timedelta = QlibFreq.get_timedelta

def custom_get_timedelta(n: int, freq: str):
    """
    自定义get_timedelta方法，支持小时
    """
    if freq == "hour":
        return original_get_timedelta(n * 60, "minute")
    return original_get_timedelta(n, freq)

qlib.utils.time.Freq.get_timedelta = custom_get_timedelta
print(f"[INFO] custom_freq: get_timedelta方法已更新")

# 更新minutes_map，添加小时对应的分钟数
print(f"[INFO] custom_freq: 开始更新get_min_delta方法")
original_get_min_delta = QlibFreq.get_min_delta

def custom_get_min_delta(left_frq: str, right_freq: str):
    """
    自定义get_min_delta方法，支持小时
    """
    from qlib.utils.time import Freq
    
    minutes_map = {
        Freq.NORM_FREQ_MINUTE: 1,
        "hour": 60,  # 小时对应60分钟
        Freq.NORM_FREQ_DAY: 60 * 24,
        Freq.NORM_FREQ_WEEK: 7 * 60 * 24,
        Freq.NORM_FREQ_MONTH: 30 * 7 * 60 * 24,
    }
    
    left_freq = Freq(left_frq)
    left_minutes = left_freq.count * minutes_map[left_freq.base]
    
    right_freq = Freq(right_freq)
    right_minutes = right_freq.count * minutes_map[right_freq.base]
    
    return left_minutes - right_minutes

qlib.utils.time.Freq.get_min_delta = custom_get_min_delta
print(f"[INFO] custom_freq: get_min_delta方法已更新")
print(f"[INFO] custom_freq: 所有补丁已应用完成")
