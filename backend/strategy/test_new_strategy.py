#!/usr/bin/env python3
"""
测试新的 Strategy 类
"""

import sys
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from strategy.core import Strategy, StrategyConfig


class TestStrategy(Strategy):
    """测试策略"""
    
    def on_init(self):
        print("策略初始化")
    
    def on_bar(self, bar):
        print(f"收到K线数据: {bar}")


def test_strategy():
    """测试策略基类"""
    print("=" * 60)
    print("测试新的 Strategy 类")
    print("=" * 60)
    
    # 测试配置
    config = StrategyConfig(
        stop_loss=0.03,
        take_profit=0.08,
        max_position_size=0.5,
    )
    
    print(f"\n配置信息:")
    print(f"  止损: {config.stop_loss}")
    print(f"  止盈: {config.take_profit}")
    print(f"  最大仓位: {config.max_position_size}")
    
    # 测试策略创建
    try:
        strategy = TestStrategy(config)
        print(f"\n策略创建成功: {strategy.__class__.__name__}")
        print(f"策略ID: {strategy.id}")
    except Exception as e:
        print(f"策略创建失败: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("测试通过!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_strategy()
    sys.exit(0 if success else 1)
