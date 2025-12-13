#!/usr/bin/env python3
"""
文件存储补丁：修复qlib的FileCalendarStorage使用错误的日历文件名
"""

# 确保在导入任何QLib模块之前，将项目根目录添加到sys.path
import sys
from pathlib import Path

# 获取当前文件的绝对路径
current_file = Path(__file__).resolve()
# 获取项目根目录 (backend/qlib_integration/file_storage_patch.py -> backend -> qbot)
project_root = current_file.parent.parent.parent

# 将项目根目录添加到sys.path
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
    print(f"[INFO] 已将项目根目录添加到sys.path: {project_root}")

import re

# 调试日志
DEBUG = True

def debug_print(message):
    """调试打印"""
    if DEBUG:
        print(f"[DEBUG] {message}")

# 确保模块加载时应用补丁
# 我们需要延迟导入，直到模块加载完成
# 这样可以确保在任何进程中加载该模块时，都会应用补丁

def apply_patches():
    """
    应用所有补丁
    这个函数会在模块加载时自动调用
    """
    print("[INFO] 开始应用补丁")
    
    # 先确保custom_freq被导入，这样Freq类的修复才能生效
    try:
        from backend.qlib_integration import custom_freq
        print("[INFO] 成功导入custom_freq")
    except ImportError as e:
        print(f"[ERROR] 导入custom_freq失败: {e}")
        # 尝试相对导入
        try:
            sys.path.append(str(Path(__file__).parent.parent))
            from backend.qlib_integration import custom_freq
            print("[INFO] 使用相对导入成功导入custom_freq")
        except ImportError as e2:
            print(f"[ERROR] 相对导入custom_freq也失败: {e2}")
            # 尝试直接导入
            try:
                import backend.qlib_integration.custom_freq
                print("[INFO] 使用直接导入成功导入custom_freq")
            except ImportError as e3:
                print(f"[ERROR] 直接导入custom_freq也失败: {e3}")
                raise
    
    try:
        from pathlib import Path
        from qlib.data.storage.file_storage import FileCalendarStorage
        print("[INFO] 成功导入QLib模块")
    except ImportError as e:
        print(f"[ERROR] 导入QLib模块失败: {e}")
        raise
    
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
        - 当freq='day'作为字符串时，直接返回'1d.txt'
        
        Returns
        -------
        str
            修复后的文件名
        """
        debug_print(f"当前freq: {self.freq}, 类型: {type(self.freq)}")
        
        # 直接处理字符串频率的特殊情况
        if isinstance(self.freq, str):
            debug_print(f"处理字符串频率: {self.freq}")
            freq_str = self.freq.lower()
            
            # 直接匹配常见的频率格式
            if freq_str in ['1d', 'day']:
                debug_print(f"直接匹配到1d/day，返回1d.txt")
                return f"1d_future.txt" if self.future else f"1d.txt"
            
            # 匹配频率字符串，如 "1d", "15m", "30min", "1h", "2hour", "day"
            match = re.match(r'^(\d+)?(\w+)$', freq_str)
            if match:
                count_str, unit = match.groups()
                count = int(count_str) if count_str else 1
                debug_print(f"匹配到频率: count={count}, unit={unit}")
                
                # 单位映射表，将不同的单位映射到统一的后缀
                unit_map = {
                    'd': 'd', 'day': 'd',
                    'h': 'h', 'hour': 'h',
                    'm': 'm', 'min': 'm', 'minute': 'm',
                    's': 's', 'sec': 's', 'second': 's'
                }
                
                if unit in unit_map:
                    # 构建频率字符串，如 1d, 15m, 30min, 1h
                    suffix = unit_map[unit]
                    # 对于单复数处理：如果count > 1或者count_str存在，使用复数形式
                    # 例如：1d, 2d, 15m, 30min, 1h, 2hour -> 转换为 1d, 2d, 15m, 30m, 1h, 2h
                    freq_file = f"{count}{suffix}"
                    debug_print(f"构建的频率文件名为: {freq_file}")
                    return f"{freq_file}_future.txt" if self.future else f"{freq_file}.txt"
            
            # 无法解析的频率字符串，使用默认逻辑
            debug_print(f"无法解析频率字符串，使用默认逻辑: {freq_str}")
            from qlib.utils.time import Freq
            freq_obj = Freq(freq_str)
        else:
            debug_print(f"使用Freq对象处理: {self.freq}")
            freq_obj = self.freq
        
        # 获取count和base
        count = freq_obj.count
        base = freq_obj.base
        debug_print(f"Freq对象属性: count={count}, base={base}")
        
        # 直接处理不同的base，不依赖__str__方法
        if base == "min":
            # 分钟频率使用m作为后缀
            suffix = "m"
        elif base == "hour":
            # 小时频率使用h作为后缀
            suffix = "h"
        elif base == "day":
            # 天频率使用d作为后缀，无论count是多少
            suffix = "d"
        else:
            # 其他频率使用默认逻辑
            debug_print(f"未知base: {base}，使用默认逻辑")
            return OriginalFileName.__get__(self)
        
        # 构建频率字符串，如1m, 5m, 1h, 1d, 5d
        # 对于day频率，始终显示count，确保生成1d而不是day
        freq_file = f"{count}{suffix}"
        debug_print(f"最终构建的频率文件名为: {freq_file}")
        
        return f"{freq_file}_future.txt" if self.future else f"{freq_file}.txt"

    # 重写 uri 属性，确保使用正确的频率格式
    @property
    def patched_uri(self) -> Path:
        """
        修复uri属性，确保使用正确的频率格式
        
        Returns
        -------
        Path
            修复后的uri路径
        """
        debug_print(f"调用patched_uri, freq: {self.freq}, 类型: {type(self.freq)}")
        
        # 获取正确的freq参数
        freq = self.freq
        freq_obj = None
        
        if isinstance(freq, str):
            from qlib.utils.time import Freq
            debug_print(f"字符串频率处理: {freq}")
            # 直接处理day字符串
            if freq.lower() == "day":
                # 使用 "1d" 作为频率参数
                debug_print(f"将day转换为1d")
                freq_obj = Freq("1d")
            else:
                # 其他字符串频率，直接创建Freq对象
                debug_print(f"使用Freq创建对象: {freq}")
                freq_obj = Freq(freq)
        else:
            debug_print(f"使用现有Freq对象")
            freq_obj = freq
        
        debug_print(f"使用的freq_obj: {freq_obj}, base: {freq_obj.base}, count: {freq_obj.count}")
        
        # 使用正确的freq获取数据路径
        data_uri = self.dpm.get_data_uri(freq_obj)
        debug_print(f"数据路径: {data_uri}")
        
        # 使用修复后的file_name
        file_name = self.file_name
        debug_print(f"使用的file_name: {file_name}")
        
        result_uri = data_uri.joinpath(f"{self.storage_name}s", file_name)
        debug_print(f"最终uri: {result_uri}")
        
        return result_uri

    # 重写FileCalendarStorage的_freq_file属性
    @property
    def patched_freq_file(self) -> str:
        """
        修复_freq_file属性，确保返回正确的频率字符串
        - 当freq='1d'时，返回'1d'而不是'day'
        - 当freq='day'时，返回'1d'而不是'day'
        
        Returns
        -------
        str
            修复后的频率字符串
        """
        debug_print(f"获取_freq_file，当前freq: {self.freq}, 类型: {type(self.freq)}")
        
        # 检查是否有缓存
        if hasattr(self, "_freq_file_cache"):
            cached_value = getattr(self, "_freq_file_cache")
            # 如果缓存是字符串，直接返回
            if isinstance(cached_value, str):
                return cached_value
            
            # 如果缓存是Freq对象，转换为正确的字符串表示
            freq_obj = cached_value
        else:
            # 处理freq属性，获取Freq对象
            if isinstance(self.freq, str):
                from qlib.utils.time import Freq
                freq_obj = Freq(self.freq)
            else:
                freq_obj = self.freq
            
            # 检查是否支持该频率
            if freq_obj not in self.support_freq:
                from qlib.utils.time import Freq
                # 尝试获取最近的频率
                freq_obj = Freq.get_recent_freq(freq_obj, self.support_freq)
                if freq_obj is None:
                    raise ValueError(f"can't find a freq from {self.support_freq} that can resample to {self.freq}!")
            
            # 设置缓存
            setattr(self, "_freq_file_cache", freq_obj)
        
        # 直接使用count和base属性生成频率字符串
        count = freq_obj.count
        base = freq_obj.base
        debug_print(f"Freq对象属性: count={count}, base={base}")
        
        # 根据base生成后缀
        if base == "min":
            suffix = "m"
        elif base == "hour":
            suffix = "h"
        elif base == "day":
            suffix = "d"
        else:
            # 其他频率使用默认逻辑
            return str(freq_obj)
        
        # 生成频率字符串，确保生成1d而不是day
        freq_str = f"{count}{suffix}"
        debug_print(f"生成的_freq_file: {freq_str}")
        
        return freq_str

    # 应用补丁
    FileCalendarStorage.file_name = patched_file_name
    FileCalendarStorage.uri = patched_uri
    FileCalendarStorage._freq_file = patched_freq_file

    print("✓ FileCalendarStorage.file_name已成功补丁")
    print("✓ FileCalendarStorage.uri已成功补丁")
    print("✓ FileCalendarStorage._freq_file已成功补丁")

# 创建一个初始化函数，用于在子进程启动时应用所有补丁
def init_worker():
    """
    子进程初始化函数
    当使用joblib/ParallelExt创建子进程时，这个函数会被调用
    确保在子进程中也应用了所有补丁
    """
    print("[INFO] 子进程初始化：开始应用补丁")
    apply_patches()
    print("[INFO] 子进程初始化：补丁应用完成")

# 确保在导入qlib之前应用补丁
# 这是为了确保在任何进程中，只要导入了这个模块，就会应用补丁

# 当模块被加载时，自动应用补丁
print("[INFO] 文件存储补丁模块正在加载...")
apply_patches()
print("[INFO] 文件存储补丁模块加载完成")

# 尝试注册子进程初始化函数到joblib
# 这样当使用joblib/ParallelExt创建子进程时，会自动调用我们的初始化函数
try:
    import joblib
    from joblib.parallel import register_parallel_backend
    from joblib.parallel import Parallel
    
    # 修改joblib.Parallel的默认初始化器
    original_init = Parallel.__init__
    def patched_init(self, *args, **kwargs):
        # 如果没有指定initializer，则使用我们的init_worker
        if 'initializer' not in kwargs:
            kwargs['initializer'] = init_worker
        return original_init(self, *args, **kwargs)
    
    # 应用补丁
    Parallel.__init__ = patched_init
    print("[INFO] 已成功修改joblib.Parallel的默认初始化器")
    
except ImportError as e:
    print(f"[INFO] joblib未安装或不可访问，跳过子进程初始化函数注册: {e}")
    pass

# 尝试修改QLib的ParallelExt类
try:
    from qlib.utils.paral import ParallelExt
    from joblib.parallel import Parallel
    
    # 修改ParallelExt的默认初始化器
    original_paral_init = ParallelExt.__init__
    def patched_paral_init(self, *args, **kwargs):
        # 如果没有指定initializer，则使用我们的init_worker
        if 'initializer' not in kwargs:
            kwargs['initializer'] = init_worker
        return original_paral_init(self, *args, **kwargs)
    
    # 应用补丁
    ParallelExt.__init__ = patched_paral_init
    print("[INFO] 已成功修改QLib.ParallelExt的默认初始化器")
    
except ImportError as e:
    print(f"[INFO] QLib.ParallelExt未找到或不可访问，跳过修改: {e}")
    pass