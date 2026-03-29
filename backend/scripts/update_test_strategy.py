#!/usr/bin/env python3
"""
更新 test_logging_strategy 策略代码到数据库
"""
import sys
sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')

# 读取策略文件内容
with open('strategies/test_logging_strategy.py', 'r', encoding='utf-8') as f:
    strategy_code = f.read()

# 更新数据库
from collector.db.database import init_database_config, SessionLocal
from strategy.models import Strategy

init_database_config()

db = SessionLocal()
try:
    # 查找 test_logging_strategy 策略
    strategy = db.query(Strategy).filter(Strategy.name == 'test_logging_strategy').first()

    if strategy:
        # 更新代码
        strategy.code = strategy_code
        db.commit()
        print(f"策略 '{strategy.name}' (ID: {strategy.id}) 代码已更新")
        print(f"代码长度: {len(strategy_code)} 字符")
    else:
        print("策略 'test_logging_strategy' 未找到")

    # 显示所有策略
    print("\n所有策略列表:")
    all_strategies = db.query(Strategy).all()
    for s in all_strategies:
        code_status = "有代码" if s.code else "无代码"
        print(f"  - ID: {s.id}, 名称: {s.name}, 状态: {code_status}")

except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
