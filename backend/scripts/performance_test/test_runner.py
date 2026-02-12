#!/usr/bin/env python3
"""
性能测试运行器

负责协调多个框架的性能测试，收集结果并生成报告
"""

import platform
import psutil
import time
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from scripts.performance_test.base_test import PerformanceMetrics
from scripts.performance_test.quantcell_test import QuantCellPerformanceTest
from scripts.performance_test.backtrader_test import BacktraderPerformanceTest
from scripts.performance_test.freqtrade_test import FreqtradePerformanceTest


class SystemInfo:
    """系统信息收集器"""
    
    @staticmethod
    def get_info() -> Dict:
        """获取系统信息"""
        return {
            'platform': platform.platform(),
            'processor': platform.processor(),
            'cpu_count': psutil.cpu_count(logical=False),
            'cpu_count_logical': psutil.cpu_count(logical=True),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
            'python_version': platform.python_version(),
            'timestamp': datetime.now().isoformat(),
        }


class PerformanceTestRunner:
    """性能测试运行器"""
    
    def __init__(self, data_file: str, strategy_params: Optional[Dict] = None):
        self.data_file = data_file
        self.strategy_params = strategy_params or {'fast': 10, 'slow': 30}
        self.results: Dict[str, List[PerformanceMetrics]] = {}
        self.system_info = SystemInfo.get_info()
        
    def run_tests(self, iterations: int = 3, warmup: bool = True) -> Dict[str, List[PerformanceMetrics]]:
        """
        运行所有框架的性能测试
        
        Args:
            iterations: 每个框架运行的次数
            warmup: 是否进行预热
            
        Returns:
            Dict[str, List[PerformanceMetrics]]: 各框架的测试结果
        """
        # 初始化测试器
        testers = {
            'QuantCell': QuantCellPerformanceTest(),
            'Backtrader': BacktraderPerformanceTest(),
            'Freqtrade': FreqtradePerformanceTest(),
        }
        
        print("=" * 80)
        print("QuantCell 性能测试")
        print("=" * 80)
        print(f"\n系统信息:")
        for key, value in self.system_info.items():
            print(f"  {key}: {value}")
        print(f"\n测试配置:")
        print(f"  数据文件: {self.data_file}")
        print(f"  策略参数: {self.strategy_params}")
        print(f"  迭代次数: {iterations}")
        print(f"  预热: {'是' if warmup else '否'}")
        print("=" * 80)
        
        # 预热
        if warmup:
            print("\n[预热阶段]")
            for name, tester in testers.items():
                print(f"  {name} 预热中...", end=" ")
                tester.warmup(self.data_file, self.strategy_params)
                print("完成")
        
        # 执行测试
        print("\n[测试阶段]")
        for name, tester in testers.items():
            print(f"\n{name}:")
            self.results[name] = []
            
            for i in range(iterations):
                print(f"  第 {i+1}/{iterations} 次运行...", end=" ")
                
                # 添加小延迟，避免系统负载波动
                if i > 0:
                    time.sleep(0.5)
                
                metrics = tester.measure_performance(self.data_file, self.strategy_params)
                self.results[name].append(metrics)
                
                print(f"完成 ({metrics.total_time_ms:.2f} ms)")
        
        print("\n" + "=" * 80)
        print("测试完成")
        print("=" * 80)
        
        return self.results
    
    def get_summary(self) -> pd.DataFrame:
        """生成测试摘要"""
        if not self.results:
            return pd.DataFrame()
        
        summary_data = []
        
        for framework_name, metrics_list in self.results.items():
            # 计算平均值
            avg_metrics = {
                'Framework': framework_name,
                'Iterations': len(metrics_list),
                'Avg Total Time (ms)': np.mean([m.total_time_ms for m in metrics_list]),
                'Std Total Time (ms)': np.std([m.total_time_ms for m in metrics_list]),
                'Avg Data Load (ms)': np.mean([m.data_load_time_ms for m in metrics_list]),
                'Avg Strategy Exec (ms)': np.mean([m.strategy_execution_time_ms for m in metrics_list]),
                'Avg Memory Peak (MB)': np.mean([m.memory_peak_mb for m in metrics_list]),
                'Avg Memory Avg (MB)': np.mean([m.memory_avg_mb for m in metrics_list]),
                'Avg CPU (%)': np.mean([m.cpu_avg_percent for m in metrics_list]),
                'Peak CPU (%)': max([m.cpu_peak_percent for m in metrics_list]),
                'Total Trades': metrics_list[0].total_trades,
                'Signals Generated': metrics_list[0].signals_generated,
                'Data Points': metrics_list[0].data_points,
            }
            summary_data.append(avg_metrics)
        
        return pd.DataFrame(summary_data)
    
    def get_detailed_results(self) -> pd.DataFrame:
        """获取详细结果"""
        if not self.results:
            return pd.DataFrame()
        
        detailed_data = []
        
        for framework_name, metrics_list in self.results.items():
            for i, metrics in enumerate(metrics_list):
                row = metrics.to_dict()
                row['iteration'] = i + 1
                detailed_data.append(row)
        
        return pd.DataFrame(detailed_data)
    
    def compare_frameworks(self) -> Dict:
        """对比各框架性能"""
        if not self.results:
            return {}
        
        comparison = {}
        
        # 获取基准框架（QuantCell）
        baseline_metrics = self.results.get('QuantCell', [])
        if not baseline_metrics:
            return comparison
        
        baseline_avg_time = np.mean([m.total_time_ms for m in baseline_metrics])
        baseline_avg_memory = np.mean([m.memory_peak_mb for m in baseline_metrics])
        
        # 对比其他框架
        for framework_name, metrics_list in self.results.items():
            if framework_name == 'QuantCell':
                continue
            
            avg_time = np.mean([m.total_time_ms for m in metrics_list])
            avg_memory = np.mean([m.memory_peak_mb for m in metrics_list])
            
            comparison[framework_name] = {
                'time_ratio': avg_time / baseline_avg_time if baseline_avg_time > 0 else 0,
                'time_diff_ms': avg_time - baseline_avg_time,
                'memory_ratio': avg_memory / baseline_avg_memory if baseline_avg_memory > 0 else 0,
                'memory_diff_mb': avg_memory - baseline_avg_memory,
                'faster': avg_time < baseline_avg_time,
                'less_memory': avg_memory < baseline_avg_memory,
            }
        
        return comparison
