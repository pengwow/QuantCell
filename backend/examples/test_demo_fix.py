#!/usr/bin/env python3
"""
测试脚本：模拟data_demo.ipynb的运行环境，测试D.features()方法
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

# 测试D.features()方法
print("\n3. 测试D.features()方法")
try:
    from qlib.data import D

    # 测试使用freq="1d"参数
    df = D.features(
        ["btcusdt"],
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

print("\n测试完成！修复有效")
