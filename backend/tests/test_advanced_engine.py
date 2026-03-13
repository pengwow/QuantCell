#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证 AdvancedEngine 实现"""

from backtest.engines.advanced_engine import AdvancedEngine
from backtest.engines.base import BacktestEngineBase, EngineType

# 验证继承关系
print("是否继承自 BacktestEngineBase:", issubclass(AdvancedEngine, BacktestEngineBase))

# 验证 engine_type 属性
engine = AdvancedEngine({})
print("engine_type 属性值:", engine.engine_type)
print("是否为 advanced:", engine.engine_type == EngineType.advanced)

# 验证抽象方法是否实现
abstract_methods = ['initialize', 'run_backtest', 'get_results', 'cleanup']
for method in abstract_methods:
    has_method = hasattr(engine, method) and callable(getattr(engine, method))
    print(f"实现了 {method}: {has_method}")

print("所有验证通过！")
