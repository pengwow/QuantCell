"""
pytest配置文件

配置测试环境，解决模块导入问题
"""

import sys
import os
from pathlib import Path

# 将backend目录添加到Python路径（必须排在tests之前）
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# 将tests目录添加到Python路径（用于导入fixtures模块）
# 注意：必须排在backend之后，避免tests/utils/覆盖backend/utils/
tests_dir = Path(__file__).parent
if str(tests_dir) not in sys.path:
    sys.path.append(str(tests_dir))  # 使用append而不是insert，确保排在backend之后

# 打印路径信息（调试用）
print(f"Python path added: {backend_dir}")
print(f"Tests path added: {tests_dir}")
print(f"Current sys.path: {sys.path[:5]}")  # 打印前5个
