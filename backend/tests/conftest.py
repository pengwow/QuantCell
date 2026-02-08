"""
pytest配置文件

配置测试环境，解决模块导入问题
"""

import sys
import os
from pathlib import Path

# 将backend目录添加到Python路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# 打印路径信息（调试用）
print(f"Python path added: {backend_dir}")
print(f"Current sys.path: {sys.path[:3]}")  # 只打印前3个
