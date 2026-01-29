# 方法1：使用os.getcwd()
import os
import sys
from pathlib import Path
from pprint import pprint

import pandas as pd

if __name__ == '__main__':
    current_dir = Path(os.getcwd())
    project_root = current_dir.parent.parent  # backend/examples -> backend -> quantcell
    
    # 方法2：手动构建路径
    project_root = Path("/Users/liupeng/workspace/quantcell")
    
    sys.path.append(str(project_root))
    print(f"已将项目根目录添加到sys.path: {project_root}")
    
    # from backend.qlib_integration import custom_calendar_provider
    # from backend.qlib_integration import CustomCalendarProvider
    # calendar_provider = CustomCalendarProvider()
    # 导入文件存储补丁，修复freq="1d"导致的日历文件路径错误
    import qlib

    from backend.qlib_integration import file_storage_patch
    
    print("已应用文件存储补丁")
    data_dir =os.path.join(project_root, 'backend/data/qlib_data')
    print(data_dir)
    # qlib.init()
    data_dir = '/Users/liupeng/workspace/quantcell/backend/data/source'
    qlib.init(provider_uri=data_dir)
    
    
    from qlib.data import D

    # from backend.qlib_integration import CustomCalendarProvider 
    # calendar_provider = CustomCalendarProvider()
    # from backend.qlib_integration import file_storage_patch
    # D = calendar_provider
    print(D.calendar(start_time="2025-10-01", end_time="2025-10-10", freq="1d")[:2])  # calendar data
    # from backend.qlib_integration.custom_calendar_provider import CustomCalendarProvider
        
        # 创建自定义日历提供器实例
    # calendar_provider = CustomCalendarProvider()
        
        # 使用日历提供器获取日历
    # calendar = calendar_provider.calendar(start_time="2025-10-01", end_time="2025-10-31", freq="1d")
    # print(calendar[:2])
    df = D.features(
        D.instruments("all"),
        ["$open", "$high", "$low", "$close", "$volume"],
        start_time="2025-10-01",
        end_time="2025-10-10",
        freq="1d"
    )
    print()