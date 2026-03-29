#!/usr/bin/env python3
"""测试策略加载逻辑"""

import sys
sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')

import types
import typing

# 模拟加载策略代码
module = types.ModuleType('test_strategy')

# 读取策略代码
with open('/Users/liupeng/workspace/quant/QuantCell/backend/strategies/test_logging_strategy.py', 'r') as f:
    code = f.read()

# 执行代码
exec(code, module.__dict__)

# 模拟查找逻辑
strategy_class = None
for attr_name in dir(module):
    attr = getattr(module, attr_name)
    if (isinstance(attr, type) and 
        attr_name not in ['StrategyBase', 'object'] and
        not attr_name.startswith('_') and
        attr is not typing.Any and
        attr is not typing.Dict and
        attr is not typing.List and
        attr is not typing.Optional and
        not hasattr(typing, attr_name)):
        strategy_class = attr
        print(f'找到策略类: {attr_name} -> {attr}')
        break

if strategy_class:
    from strategy.core import StrategyBase
    print(f'是否继承自 StrategyBase: {issubclass(strategy_class, StrategyBase)}')
    print(f'MRO: {strategy_class.__mro__}')
    
    # 检查是否是 Config 类
    if 'Config' in strategy_class.__name__:
        print('警告：找到的是 Config 类，不是策略类！')
