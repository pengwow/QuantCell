# 性能基准测试脚本
# 对比 Numba、Cython 和 Python 实现的性能

import numpy as np
import pandas as pd
import time
from typing import Dict, Any
from loguru import logger


def generate_test_data(n_steps: int = 10000, n_assets: int = 10) -> Dict[str, np.ndarray]:
    """
    生成测试数据
    
    参数：
    - n_steps: 时间步数
    - n_assets: 资产数量
    
    返回：
    - dict: 包含测试数据的字典
    """
    np.random.seed(42)
    
    # 生成价格数据
    base_price = 50000.0
    price_changes = np.random.normal(0, 0.001, (n_steps, n_assets))
    price = base_price * (1 + np.cumsum(price_changes, axis=0))
    
    # 生成订单数据
    size = np.random.choice([0, 0.01, -0.01], size=(n_steps, n_assets), p=[0.95, 0.025, 0.025])
    direction = np.where(size > 0, 1, 0)
    
    # 生成信号数据
    entries = np.random.choice([False, True], size=(n_steps, n_assets), p=[0.99, 0.01])
    exits = np.random.choice([False, True], size=(n_steps, n_assets), p=[0.99, 0.01])
    
    return {
        'price': price,
        'size': size,
        'direction': direction,
        'entries': entries,
        'exits': exits
    }


def benchmark_python(data: Dict[str, np.ndarray], n_runs: int = 10) -> Dict[str, Any]:
    """
    Python 实现的性能基准测试
    
    参数：
    - data: 测试数据
    - n_runs: 运行次数
    
    返回：
    - dict: 包含平均运行时间的字典
    """
    logger.info("开始 Python 实现性能基准测试...")
    
    times = []
    for _ in range(n_runs):
        start_time = time.time()
        
        # Python 版本的订单模拟
        n_steps, n_assets = data['price'].shape
        cash = np.full(n_assets, 100000.0, dtype=np.float64)
        positions = np.zeros((n_steps, n_assets), dtype=np.float64)
        
        for i in range(n_steps):
            for j in range(n_assets):
                current_price = data['price'][i, j]
                if data['size'][i, j] != 0:
                    if data['direction'][i, j] == 1:
                        exec_price = current_price * 1.0001
                        req_cash = data['size'][i, j] * exec_price * 1.001
                        if cash[j] >= req_cash:
                            cash[j] -= req_cash
                            positions[i, j] += data['size'][i, j]
                    else:
                        exec_price = current_price * 0.9999
                        req_cash = data['size'][i, j] * exec_price * 1.001
                        if positions[i, j] >= data['size'][i, j]:
                            cash[j] += req_cash
                            positions[i, j] -= data['size'][i, j]
        
        end_time = time.time()
        times.append(end_time - start_time)
    
    avg_time = np.mean(times)
    logger.info(f"Python 实现平均运行时间: {avg_time:.4f} 秒")
    
    return {'python': avg_time}


def benchmark_numba(data: Dict[str, np.ndarray], n_runs: int = 10) -> Dict[str, float]:
    """
    Numba 实现的性能基准测试
    
    参数：
    - data: 测试数据
    - n_runs: 运行次数
    
    返回：
    - dict: 包含平均运行时间的字典
    """
    logger.info("开始 Numba 实现性能基准测试...")
    
    try:
        from core.numba_functions import simulate_orders
    except ImportError as e:
        logger.error(f"无法导入 Numba 模块: {e}")
        return {}
    
    times = []
    for _ in range(n_runs):
        start_time = time.time()
        
        # Numba 版本的订单模拟
        cash, positions = simulate_orders(
            price=data['price'],
            size=data['size'],
            direction=data['direction'].astype(np.int32),
            fees=0.001,
            slippage=0.0001,
            init_cash=100000.0
        )
        
        end_time = time.time()
        times.append(end_time - start_time)
    
    avg_time = np.mean(times)
    logger.info(f"Numba 实现平均运行时间: {avg_time:.4f} 秒")
    
    return {'numba': avg_time}


def benchmark_cython(data: Dict[str, np.ndarray], n_runs: int = 10) -> Dict[str, Any]:
    """
    Cython 实现的性能基准测试（已废弃）
    
    参数：
    - data: 测试数据
    - n_runs: 运行次数
    
    返回：
    - dict: 包含平均运行时间的字典
    """
    logger.warning("Cython 实现已废弃，跳过基准测试")
    return {}


def run_benchmarks(n_steps: int = 10000, n_assets: int = 10, n_runs: int = 10):
    """
    运行所有性能基准测试
    
    参数：
    - n_steps: 时间步数
    - n_assets: 资产数量
    - n_runs: 运行次数
    """
    logger.info("=" * 60)
    logger.info("性能基准测试")
    logger.info("=" * 60)
    logger.info(f"测试参数: n_steps={n_steps}, n_assets={n_assets}, n_runs={n_runs}")
    logger.info("")
    
    # 生成测试数据
    data = generate_test_data(n_steps, n_assets)
    logger.info(f"测试数据生成完成")
    logger.info("")
    
    # 运行基准测试
    results = {}
    
    # Python 基准
    python_times = benchmark_python(data, n_runs)
    results.update(python_times)
    logger.info("")
    
    # Numba 基准
    numba_times = benchmark_numba(data, n_runs)
    results.update(numba_times)
    logger.info("")
    
    # 打印结果
    logger.info("=" * 60)
    logger.info("性能对比结果")
    logger.info("=" * 60)
    
    for impl, time in results.items():
        logger.info(f"{impl:12s}: {time:.4f} 秒")
    
    logger.info("")
    
    # 计算性能提升
    if 'python' in results and 'numba' in results:
        speedup = results['python'] / results['numba']
        logger.info(f"Numba 相比 Python 的性能提升: {speedup:.2f}x")
    
    logger.info("")
    logger.info("=" * 60)
    
    return results


if __name__ == "__main__":
    # 运行基准测试
    results = run_benchmarks(n_steps=10000, n_assets=10, n_runs=10)
    
    logger.info("基准测试完成！")
