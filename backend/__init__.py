# quantcell/backend/__init__.py
import os
import sys

# 获取当前__init__.py文件的绝对路径（即backend目录下的__init__.py）
current_init_path = os.path.abspath(__file__)
# 获取backend目录的绝对路径
backend_dir = os.path.dirname(current_init_path)

# 将backend目录加入sys.path最前端（确保优先搜索）
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 可选：提前导入常用模块，让main.py导入更简洁
# from .backtest.routes import xxx