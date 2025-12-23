#!/usr/bin/env python3
# 测试数据加载功能

import sys
from pathlib import Path

# 添加项目根目录到Python路径
backend_root = Path(__file__).parent
sys.path.append(str(backend_root))

# 导入数据加载器
from collector.data_loader import data_loader
from collector.db import SystemConfigBusiness as SystemConfig


# 测试数据加载功能
def test_data_loader():
    print("开始测试数据加载功能...")
    
    # 获取qlib_data_dir配置
    qlib_dir = SystemConfig.get("qlib_data_dir")
    if not qlib_dir:
        qlib_dir = "data/crypto_data"
        print(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")
    else:
        print(f"从数据库中读取到qlib_data_dir: {qlib_dir}")
    
    # 初始化QLib
    print(f"开始初始化QLib，数据目录: {qlib_dir}")
    success = data_loader.init_qlib(qlib_dir)
    if success:
        print("QLib初始化成功")
        
        # 获取已加载的数据信息
        data_info = data_loader.get_loaded_data_info()
        print(f"已加载的数据信息: {data_info}")
        
        # 检查数据是否加载成功
        if data_info["data_loaded"]:
            print("数据加载成功！")
            
            # 测试获取日历
            calendars = data_loader.get_calendars()
            print(f"获取到的交易日历: {list(calendars.keys())}")
            
            # 测试获取成分股
            instruments = data_loader.get_instruments()
            print(f"获取到的成分股: {list(instruments.keys())}")
            
            # 测试获取特征
            features = data_loader.get_features()
            print(f"获取到的特征: {list(features.keys())}")
            
            return True
        else:
            print("数据加载失败！")
            return False
    else:
        print("QLib初始化失败！")
        return False

if __name__ == "__main__":
    success = test_data_loader()
    sys.exit(0 if success else 1)