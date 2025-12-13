#!/usr/bin/env python3
"""
测试脚本：测试D.instruments("all")方法和D.features()方法的组合使用
"""

import sys
from pathlib import Path

# 模拟Jupyter Notebook的工作目录和路径设置
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # backend/examples -> backend -> qbot

sys.path.append(str(project_root))
print(f"已将项目根目录添加到sys.path: {project_root}")

# 导入文件存储补丁，修复freq="1d"导致的日历文件路径错误
print("\n1. 导入文件存储补丁")
try:
    from backend.qlib_integration import file_storage_patch
    print("✓ 已应用文件存储补丁")
except Exception as e:
    print(f"✗ 导入文件存储补丁失败: {e}")
    sys.exit(1)

# 初始化qlib
print("\n2. 初始化qlib")
try:
    import qlib
    data_dir = '/Users/liupeng/workspace/qbot/backend/data/source'
    qlib.init(provider_uri=data_dir)
    print("✓ qlib初始化成功")
except Exception as e:
    print(f"✗ qlib初始化失败: {e}")
    sys.exit(1)

# 测试D.instruments()方法
print("\n3. 测试D.instruments()方法")
try:
    from qlib.data import D
    
    # 测试使用D.instruments("all")获取标的列表
    instruments = D.instruments(market="all")
    print(f"✓ D.instruments(market='all')调用成功")
    print(f"  返回的instruments: {instruments}")
    
    # 测试使用D.list_instruments()获取标的列表
    instrument_list = D.list_instruments(instruments=instruments, as_list=True, freq="1d")
    print(f"✓ D.list_instruments()调用成功")
    print(f"  返回的标的数量: {len(instrument_list)}")
    print(f"  前5个标的: {instrument_list[:5] if len(instrument_list) > 5 else instrument_list}")

except Exception as e:
    print(f"✗ D.instruments()或D.list_instruments()调用失败: {e}")
    import traceback
    traceback.print_exc()
    # 继续测试，不退出

# 测试D.features()方法，使用D.instruments()的结果
print("\n4. 测试D.features()方法，使用D.instruments()的结果")
try:
    from qlib.data import D
    
    # 使用前5个标的进行测试，避免数据量过大
    instruments = ["btcusdt"]  # 只测试btcusdt，避免数据量过大
    
    # 测试使用freq="1d"参数
    df = D.features(
        instruments,
        ["$open", "$high", "$low", "$close", "$volume"],
        start_time="2025-10-01",
        end_time="2025-10-10",
        freq="1d"
    )
    
    print("✓ D.features()调用成功")
    print(f"返回的数据形状: {df.shape}")
    print("\n数据预览:")
    print(df.head())
    
except Exception as e:
    print(f"✗ D.features()调用失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试D.features()方法，使用D.instruments("all")的结果
print("\n5. 测试D.features()方法，使用D.instruments(\"all\")的结果")
try:
    from qlib.data import D
    
    # 获取instruments
    instruments = D.instruments(market="all")
    # 使用前1个标的进行测试，避免数据量过大
    instrument_list = D.list_instruments(instruments=instruments, as_list=True, freq="1d")[:1]
    
    # 测试使用freq="1d"参数
    df = D.features(
        instrument_list,
        ["$open", "$high", "$low", "$close", "$volume"],
        start_time="2025-10-01",
        end_time="2025-10-10",
        freq="1d"
    )
    
    print("✓ D.features()调用成功，使用D.instruments(\"all\")的结果")
    print(f"使用的标的: {instrument_list}")
    print(f"返回的数据形状: {df.shape}")
    print("\n数据预览:")
    print(df.head())
    
except Exception as e:
    print(f"✗ D.features()调用失败，使用D.instruments(\"all\")的结果: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n测试完成！修复有效")
