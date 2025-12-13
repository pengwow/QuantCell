#!/usr/bin/env python3
"""
文件存储补丁：修复qlib的FileCalendarStorage使用错误的日历文件名
"""

from qlib.data.storage.file_storage import FileCalendarStorage

# 保存原始的file_name属性
OriginalFileName = FileCalendarStorage.file_name
OriginalUri = FileCalendarStorage.uri

# 重写FileCalendarStorage的file_name属性
@property
def patched_file_name(self) -> str:
    """
    修复file_name属性，确保使用正确的文件名格式
    - 当freq='1d'时，返回'1d.txt'而不是'd.txt'
    - 当freq='day'时，返回'1d.txt'而不是'd.txt'
    
    Returns
    -------
    str
        修复后的文件名
    """
    # 获取频率对象
    freq = self.freq
    if isinstance(freq, str):
        from qlib.utils.time import Freq
        freq_obj = Freq(freq)
    else:
        freq_obj = freq
    
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
        return OriginalFileName.__get__(self)
    
    # 构建频率字符串，如1m, 5m, 1h, 1d, 5d
    freq_file = f"{count}{suffix}"
    
    # 构建文件名
    return f"{freq_file}_future.txt" if self.future else f"{freq_file}.txt"

# 应用补丁
FileCalendarStorage.file_name = patched_file_name

print("✓ FileCalendarStorage.file_name已成功补丁")
