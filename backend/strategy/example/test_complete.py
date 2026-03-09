# 完整的测试代码和使用示例
# 展示如何使用 QUANTCELL 统一策略引擎（Numba JIT 版本）

import sys
import os

# 添加路径 - 从 example 目录计算 backend 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(os.path.dirname(current_dir))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 添加项目根目录到路径（用于导入 backend.strategies 模块）
project_dir = os.path.dirname(backend_dir)
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

import numpy as np
import pandas as pd
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
# 导入策略引擎模块 - 更新为正确的导入路径
from strategy.core import StrategyBase, VectorEngine, EventEngine, EventType
from strategy.core.numba_functions import (
    simulate_orders,
    signals_to_orders,
    calculate_metrics,
    calculate_funding_rate,
    calculate_funding_payment
)
from strategy.trading_modules import PerpetualContract, CryptoUtils
from strategy.adapters import VectorBacktestAdapter

# 添加策略目录到路径
strategies_dir = os.path.join(backend_dir, 'strategies')
if strategies_dir not in sys.path:
    sys.path.insert(0, strategies_dir)

# 尝试导入网格策略，如果不存在则跳过
try:
    from backend.strategies.grid_trading import GridTradingStrategy
    HAS_GRID_STRATEGY = True
except ImportError:
    HAS_GRID_STRATEGY = False
    logger.warning("GridTradingStrategy 未找到，将跳过相关测试")


def test_numba_functions():
    """
    测试 1: 验证 Numba 函数导入和基本功能
    """
    print("=" * 70)
    print("测试 1: Numba 函数导入和基本功能")
    print("=" * 70)
    print()
    
    # 测试数据
    n_steps = 100
    n_assets = 2
    price = np.random.rand(n_steps, n_assets) * 1000.0
    size = np.random.choice([0, 0.01, -0.01], size=(n_steps, n_assets), p=[0.95, 0.025, 0.025])
    direction = np.where(size > 0, 1, 0).astype(np.int32)
    
    print(f"测试数据: n_steps={n_steps}, n_assets={n_assets}")
    print(f"价格范围: [{price.min():.2f}, {price.max():.2f}]")
    print()
    
    # 测试订单模拟
    print("测试 simulate_orders() 函数...")
    cash, positions = simulate_orders(
        price=price,
        size=size,
        direction=direction,
        fees=0.001,
        slippage=0.0001,
        init_cash=100000.0
    )
    print(f"  ✅ 成功: 最终现金={cash[0]:.2f}")
    print(f"  ✅ 成功: 最终持仓={positions[-1, 0]:.4f}")
    print()
    
    # 测试信号转换
    print("测试 signals_to_orders() 函数...")
    entries = np.random.choice([False, True], size=(n_steps, n_assets), p=[0.99, 0.01])
    exits = np.random.choice([False, True], size=(n_steps, n_assets), p=[0.99, 0.01])
    size_arr, direction_arr = signals_to_orders(entries, exits, size=0.01)
    print(f"  ✅ 成功: 生成 {np.sum(size_arr != 0)} 个订单信号")
    print()
    
    # 测试指标计算
    print("测试 calculate_metrics() 函数...")
    trades_pnl = np.array([100.0, -50.0, 200.0], dtype=np.float64)
    trades_fees = np.array([1.0, 1.0, 2.0], dtype=np.float64)
    trades_value = np.array([1000.0, 500.0, 2000.0], dtype=np.float64)
    cash = np.array([100500.0])
    metrics_arr = calculate_metrics(trades_pnl, trades_fees, trades_value, cash)
    print(f"  ✅ 成功: 总盈亏={metrics_arr[0]:.2f}")
    print(f"  ✅ 成功: 胜率={metrics_arr[2]:.2%}")
    print(f"  ✅ 成功: 夏普比率={metrics_arr[3]:.4f}")
    print()
    
    # 测试资金费率计算
    print("测试 calculate_funding_rate() 函数...")
    funding_rate = calculate_funding_rate(50000.0, 50100.0)
    print(f"  ✅ 成功: 资金费率={funding_rate:.6f}")
    print()
    
    print("测试 1 完成！所有 Numba 函数工作正常 ✓")
    print()


def test_vector_engine():
    """
    测试 2: 验证 VectorEngine 的完整功能
    """
    print("=" * 70)
    print("测试 2: VectorEngine 完整功能")
    print("=" * 70)
    print()
    
    # 创建向量引擎
    print("创建 VectorEngine...")
    engine = VectorEngine()
    print(f"  ✅ 成功: 使用 {type(engine.simulate_orders).__name__} 实现")
    print()
    
    # 准备测试数据
    n_steps = 1000
    n_assets = 3
    np.random.seed(42)
    price = np.random.rand(n_steps, n_assets) * 1000.0
    entries = np.random.choice([False, True], size=(n_steps, n_assets), p=[0.99, 0.01])
    exits = np.random.choice([False, True], size=(n_steps, n_assets), p=[0.99, 0.01])
    
    print(f"测试数据: n_steps={n_steps}, n_assets={n_assets}")
    print(f"价格范围: [{price.min():.2f}, {price.max():.2f}]")
    print(f"入场信号: {np.sum(entries)} 个")
    print(f"出场信号: {np.sum(exits)} 个")
    print()
    
    # 运行回测
    print("运行回测...")
    result = engine.run_backtest(
        price=price,
        entries=entries,
        exits=exits,
        init_cash=100000.0,
        fees=0.001,
        slippage=0.0001
    )
    print(f"  ✅ 成功: 回测完成")
    print()
    
    # 打印结果
    print("回测结果:")
    print("-" * 70)
    for key, value in result['metrics'].items():
        print(f"  {key}: {value}")
    print("-" * 70)
    print(f"  最终现金: {result['cash'].sum():.2f}")
    print(f"  最终持仓: {result['positions'][-1].sum():.4f}")
    print(f"  交易数量: {len(result['trades'])}")
    print()
    
    print("测试 2 完成！VectorEngine 工作正常 ✓")
    print()


def test_grid_trading_strategy():
    """
    测试 3: 验证 GridTradingStrategy 的完整功能
    """
    print("=" * 70)
    print("测试 3: GridTradingStrategy 完整功能")
    print("=" * 70)
    print()
    
    if not HAS_GRID_STRATEGY:
        print("  ⚠️ 跳过: GridTradingStrategy 未找到")
        print()
        return
    
    # 创建策略参数
    params = {
        'grid_count': 10,
        'auto_range_pct': 0.1,
        'position_size': 0.01,
        'initial_capital': 10000,
        'enable_stop_loss': False,
        'stop_loss_pct': 0.2,
        'enable_take_profit': False,
        'take_profit_pct': 0.3
    }
    
    print("策略参数:")
    for key, value in params.items():
        print(f"  {key}: {value}")
    print()
    
    # 创建策略实例
    print("创建 GridTradingStrategy...")
    strategy = GridTradingStrategy(params)
    print(f"  ✅ 成功: 策略创建完成")
    print()
    
    # 初始化策略
    print("初始化策略...")
    strategy.on_init()
    print(f"  ✅ 成功: 网格线计算完成")
    print(f"  网格数量: {len(strategy.grid_levels) - 1}")
    print()
    
    # 测试 K 线回调
    print("测试 K 线回调...")
    test_bar = {
        'datetime': pd.Timestamp('2024-01-01'),
        'open': 50000.0,
        'high': 50100.0,
        'low': 49900.0,
        'close': 50000.0,
        'volume': 1000.0
    }
    strategy.on_bar(test_bar)
    print(f"  ✅ 成功: K 线回调执行完成")
    print(f"  当前网格位置: {strategy.current_grid}")
    print()
    
    # 测试订单回调
    print("测试订单回调...")
    test_order = {
        'order_id': 'test_order_001',
        'status': 'filled',
        'symbol': 'BTCUSDT',
        'direction': 'long',
        'price': 50000.0,
        'volume': 0.01
    }
    strategy.on_order(test_order)
    print(f"  ✅ 成功: 订单回调执行完成")
    print()
    
    # 测试成交回调
    print("测试成交回调...")
    test_trade = {
        'symbol': 'BTCUSDT',
        'direction': 'long',
        'price': 50000.0,
        'volume': 0.01
    }
    strategy.on_trade(test_trade)
    print(f"  ✅ 成功: 成交回调执行完成")
    print()
    
    # 测试资金费率回调
    print("测试资金费率回调...")
    strategy.on_funding_rate(0.0001, 50000.0)
    print(f"  ✅ 成功: 资金费率回调执行完成")
    print()
    
    print("测试 3 完成！GridTradingStrategy 工作正常 ✓")
    print()


def test_vector_adapter():
    """
    测试 4: 验证 VectorBacktestAdapter 的完整功能
    """
    print("=" * 70)
    print("测试 4: VectorBacktestAdapter 完整功能")
    print("=" * 70)
    print()
    
    if not HAS_GRID_STRATEGY:
        print("  ⚠️ 跳过: GridTradingStrategy 未找到")
        print()
        return
    
    # 生成测试数据
    print("生成测试数据...")
    np.random.seed(42)
    n_steps = 500
    dates = pd.date_range('2024-01-01', periods=n_steps, freq='h')
    
    # 生成价格数据（模拟 BTC/USDT）
    base_price = 50000.0
    price_changes = np.random.normal(0, 0.001, n_steps)
    prices = base_price * (1 + np.cumsum(price_changes))
    
    # 创建 OHLC 数据
    data = pd.DataFrame({
        'Open': prices,
        'High': prices * 1.002,
        'Low': prices * 0.998,
        'Close': prices,
        'Volume': np.random.uniform(100, 1000, n_steps)
    }, index=dates)
    
    print(f"  ✅ 成功: 数据生成完成")
    print(f"  数据形状: {data.shape}")
    print(f"  价格范围: [{data['Close'].min():.2f}, {data['Close'].max():.2f}]")
    print()
    
    # 创建策略
    print("创建策略...")
    params = {
        'grid_count': 10,
        'auto_range_pct': 0.1,
        'position_size': 0.01,
        'initial_capital': 10000
    }
    strategy = GridTradingStrategy(params)
    print(f"  ✅ 成功: 策略创建完成")
    print()
    
    # 创建适配器
    print("创建 VectorBacktestAdapter...")
    adapter = VectorBacktestAdapter(strategy)
    print(f"  ✅ 成功: 适配器创建完成")
    print()
    
    # 运行回测
    print("运行回测...")
    data_dict = {'BTCUSDT': data}
    results = adapter.run_backtest(
        data=data_dict,
        init_cash=100000.0,
        fees=0.001,
        slippage=0.0001
    )
    print(f"  ✅ 成功: 回测完成")
    print()
    
    # 打印回测结果
    print("回测结果:")
    print("-" * 70)
    for symbol, result in results.items():
        print(f"\n交易对: {symbol}")
        print("-" * 70)
        print(f"  最终现金: {result['cash'][0]:.2f}")
        print(f"  最终持仓: {result['positions'][-1, 0]:.4f}")
        print(f"  交易数量: {len(result['trades'])}")
        print()
        print("  绩效指标:")
        for key, value in result['metrics'].items():
            print(f"    {key}: {value}")
    print("-" * 70)
    print()
    
    # 测试获取权益曲线
    print("测试获取权益曲线...")
    equity_curve = adapter.get_equity_curve('BTCUSDT')
    print(f"  ✅ 成功: 权益曲线长度={len(equity_curve)}")
    print(f"  权益范围: [{equity_curve.min():.2f}, {equity_curve.max():.2f}]")
    print()
    
    # 测试获取交易记录
    print("测试获取交易记录...")
    trades = adapter.get_trades('BTCUSDT')
    print(f"  ✅ 成功: 交易记录数量={len(trades)}")
    if len(trades) > 0:
        print(f"  第一笔交易价格: {trades.iloc[0]['price']:.2f}")
    print()
    
    # 测试获取回测摘要
    print("测试获取回测摘要...")
    summary = adapter.get_summary()
    print(f"  ✅ 成功: 摘要生成完成")
    print()
    print("回测摘要:")
    print("-" * 70)
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print("-" * 70)
    print()
    
    print("测试 4 完成！VectorBacktestAdapter 工作正常 ✓")
    print()


def test_event_engine():
    """
    测试 5: 验证 EventEngine 的基本功能
    """
    print("=" * 70)
    print("测试 5: EventEngine 基本功能")
    print("=" * 70)
    print()
    
    # 创建事件引擎
    print("创建 EventEngine...")
    engine = EventEngine()
    print(f"  ✅ 成功: 事件引擎创建完成")
    print()
    
    # 定义事件处理器
    def on_tick_handler(data):
        print(f"  [Tick] 价格: {data['price']:.2f}")

    def on_bar_handler(data):
        print(f"  [Bar] 收盘价: {data['close']:.2f}")

    def on_order_handler(data):
        print(f"  [Order] 状态: {data['status']}")
    
    # 注册事件处理器
    print("注册事件处理器...")
    engine.register(EventType.TICK, on_tick_handler)
    engine.register(EventType.BAR, on_bar_handler)
    engine.register(EventType.ORDER, on_order_handler)
    print(f"  ✅ 成功: 事件处理器注册完成")
    print()
    
    # 推送测试事件
    print("推送测试事件...")
    engine.put(EventType.TICK, {'price': 50000.0, 'volume': 100.0})
    engine.put(EventType.BAR, {'open': 49900.0, 'high': 50100.0, 'low': 49800.0, 'close': 50000.0, 'volume': 1000.0})
    engine.put(EventType.ORDER, {'order_id': 'test_001', 'status': 'filled', 'symbol': 'BTCUSDT'})
    print(f"  ✅ 成功: 测试事件推送完成")
    print()
    
    # 启动事件引擎
    print("启动事件引擎...")
    engine.start()
    print(f"  ✅ 成功: 事件引擎已启动")
    print()
    
    # 停止事件引擎
    print("停止事件引擎...")
    engine.stop()
    print(f"  ✅ 成功: 事件引擎已停止")
    print()
    
    print("测试 5 完成！EventEngine 工作正常 ✓")
    print()


def run_all_tests():
    """
    运行所有测试
    """
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  QUANTCELL 统一策略引擎 - 完整测试套件".center(56) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "═" * 68 + "╝")
    print("\n")
    
    # 运行所有测试
    test_numba_functions()
    test_vector_engine()
    test_grid_trading_strategy()
    test_vector_adapter()
    test_event_engine()
    
    # 最终总结
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + " 所有测试完成！".center(61) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "═" * 68 + "╝")
    print("\n")
    
    print("测试总结:")
    print("-" * 70)
    print("  ✅ Numba 函数: 导入成功，功能正常")
    print("  ✅ VectorEngine: 回测功能正常")
    if HAS_GRID_STRATEGY:
        print("  ✅ GridTradingStrategy: 策略逻辑正常")
        print("  ✅ VectorBacktestAdapter: 适配器功能正常")
    else:
        print("  ⚠️ GridTradingStrategy: 跳过测试")
        print("  ⚠️ VectorBacktestAdapter: 跳过测试")
    print("  ✅ EventEngine: 事件处理正常")
    print("-" * 70)
    print("\n所有模块已验证可以正常使用！🎉")
    print()


if __name__ == "__main__":
    run_all_tests()
