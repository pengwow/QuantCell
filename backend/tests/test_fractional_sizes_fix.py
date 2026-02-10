#!/usr/bin/env python3
"""
Fractional Sizes 修复验证测试

测试内容:
1. 最大回撤计算修复验证
2. 夏普比率计算验证
3. 回测结果一致性验证
4. 与Backtrader对比验证
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

# 添加路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

backtrader_path = Path("/Users/liupeng/workspace/quant/backtrader")
if str(backtrader_path) not in sys.path:
    sys.path.insert(0, str(backtrader_path))

from strategies.fractional_sizes_quantcell import (
    FractionalSizesStrategy, 
    FractionalSizesAdapter,
    run_backtrader_fractional,
    run_quantcell_fractional
)
import backtrader as bt


class TestMetricsCalculation:
    """测试指标计算"""
    
    def test_max_drawdown_positive(self):
        """测试最大回撤返回正值"""
        adapter = FractionalSizesAdapter(None)
        
        # 构造权益曲线
        equity = np.array([100, 110, 105, 120, 115, 100, 130], dtype=np.float64)
        
        # 计算最大回撤
        max_dd = adapter._calculate_max_drawdown(equity)
        
        # 验证结果
        assert max_dd >= 0, f"最大回撤应该是正值，但得到 {max_dd}"
        assert max_dd <= 100, f"最大回撤不应超过100%，但得到 {max_dd}%"
        
        # 手动计算验证
        # peak: [100, 110, 110, 120, 120, 120, 130]
        # drawdown: [0, 0, -4.545%, 0, -4.167%, -16.667%, 0]
        # max_drawdown = 16.667%
        expected_dd = 16.67
        assert abs(max_dd - expected_dd) < 0.1, f"最大回撤计算错误: 期望 {expected_dd}%, 实际 {max_dd}%"
    
    def test_max_drawdown_no_drawdown(self):
        """测试无回撤情况"""
        adapter = FractionalSizesAdapter(None)
        
        # 一直上涨的权益曲线
        equity = np.array([100, 110, 120, 130, 140], dtype=np.float64)
        max_dd = adapter._calculate_max_drawdown(equity)
        
        assert max_dd == 0, f"无回撤时应返回0，但得到 {max_dd}"
    
    def test_sharpe_ratio_calculation(self):
        """测试夏普比率计算"""
        adapter = FractionalSizesAdapter(None)
        
        # 构造收益率序列
        returns = np.array([0.01, -0.005, 0.008, -0.002, 0.015], dtype=np.float64)
        
        # 计算夏普比率
        sharpe = adapter._calculate_sharpe(returns)
        
        # 验证结果
        assert not np.isnan(sharpe), "夏普比率不应为NaN"
        assert -10 < sharpe < 10, f"夏普比率应在合理范围内，但得到 {sharpe}"
    
    def test_sharpe_ratio_insufficient_data(self):
        """测试数据不足时的夏普比率"""
        adapter = FractionalSizesAdapter(None)
        
        # 只有一个数据点
        returns = np.array([0.01], dtype=np.float64)
        sharpe = adapter._calculate_sharpe(returns)
        
        assert sharpe == 0, f"数据不足时应返回0，但得到 {sharpe}"
    
    def test_sharpe_ratio_zero_std(self):
        """测试标准差为0时的夏普比率"""
        adapter = FractionalSizesAdapter(None)
        
        # 所有收益率相同
        returns = np.array([0.01, 0.01, 0.01, 0.01], dtype=np.float64)
        sharpe = adapter._calculate_sharpe(returns)
        
        assert sharpe == 0, f"标准差为0时应返回0，但得到 {sharpe}"


class TestBacktestConsistency:
    """测试回测一致性"""
    
    def test_backtest_reproducibility(self):
        """测试回测结果可重复性"""
        datapath = "/Users/liupeng/workspace/quant/backtrader/datas/2005-2006-day-001.txt"
        
        # 运行两次回测
        result1 = run_quantcell_fractional(datapath, cash=100000.0)
        result2 = run_quantcell_fractional(datapath, cash=100000.0)
        
        # 验证结果一致
        assert result1['final_value'] == result2['final_value'], "回测结果应可重复"
        assert result1['total_trades'] == result2['total_trades'], "交易次数应一致"
    
    def test_equity_curve_no_negative(self):
        """测试权益曲线无负值"""
        datapath = "/Users/liupeng/workspace/quant/backtrader/datas/2005-2006-day-001.txt"
        
        strategy = FractionalSizesStrategy(params={
            'p1': 10,
            'p2': 30,
            'target': 0.5,
        })
        
        data = pd.read_csv(datapath, parse_dates=True, index_col=0)
        adapter = FractionalSizesAdapter(strategy)
        
        result = adapter.run_backtest(data, cash=100000.0, commission=0.0, slippage=0.0, target=0.5)
        
        equity_curve = result['_equity_curve']
        
        # 验证权益曲线无负值
        assert np.all(equity_curve >= 0), "权益曲线不应出现负值"
        assert not np.any(np.isnan(equity_curve)), "权益曲线不应出现NaN"


class TestComparisonWithBacktrader:
    """与Backtrader对比测试"""
    
    def test_return_rate_difference(self):
        """测试收益率差异在可接受范围内"""
        datapath = "/Users/liupeng/workspace/quant/backtrader/datas/2005-2006-day-001.txt"
        
        bt_result = run_backtrader_fractional(datapath, cash=100000.0)
        qc_result = run_quantcell_fractional(datapath, cash=100000.0)
        
        # 允许5%的差异
        return_diff = abs(bt_result['total_return_pct'] - qc_result['total_return_pct'])
        assert return_diff < 5, f"收益率差异过大: {return_diff:.2f}%"
    
    def test_trade_count_difference(self):
        """测试交易次数差异在可接受范围内"""
        datapath = "/Users/liupeng/workspace/quant/backtrader/datas/2005-2006-day-001.txt"
        
        bt_result = run_backtrader_fractional(datapath, cash=100000.0)
        qc_result = run_quantcell_fractional(datapath, cash=100000.0)
        
        # 允许1笔交易的差异
        trade_diff = abs(bt_result['total_trades'] - qc_result['total_trades'])
        assert trade_diff <= 1, f"交易次数差异过大: {trade_diff}笔"


def run_all_tests():
    """运行所有测试"""
    print("="*80)
    print("Fractional Sizes 修复验证测试")
    print("="*80)
    
    test_classes = [
        TestMetricsCalculation(),
        TestBacktestConsistency(),
        TestComparisonWithBacktrader(),
    ]
    
    passed = 0
    failed = 0
    
    for test_class in test_classes:
        class_name = test_class.__class__.__name__
        print(f"\n【测试类】{class_name}")
        print("-"*80)
        
        for method_name in dir(test_class):
            if method_name.startswith('test_'):
                try:
                    method = getattr(test_class, method_name)
                    method()
                    print(f"✓ {method_name}")
                    passed += 1
                except Exception as e:
                    print(f"❌ {method_name}: {e}")
                    failed += 1
    
    print("\n" + "="*80)
    print(f"测试结果: 通过 {passed} 项, 失败 {failed} 项")
    print("="*80)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
