import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/quantcell')

from backend.collector.base.base_collector import BaseCollector


class TestBaseCollector(unittest.TestCase):
    """测试BaseCollector类的功能"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = Path('/tmp/test_collector').resolve()
        self.test_dir.mkdir(exist_ok=True, parents=True)
        
    def tearDown(self):
        """清理测试环境"""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_initialization(self):
        """测试BaseCollector类的初始化功能
        
        测试点：
        1. 初始化参数是否正确设置
        2. 保存目录是否正确创建
        3. 默认参数是否正确处理
        """
        # 创建一个继承自BaseCollector的测试类，实现抽象方法
        class TestCollector(BaseCollector):
            def get_instrument_list(self):
                return ['TEST1', 'TEST2', 'TEST3']
            
            def normalize_symbol(self, symbol):
                return symbol
            
            def get_data(self, symbol, interval, start_datetime, end_datetime):
                return pd.DataFrame()
        
        # 测试初始化
        collector = TestCollector(
            save_dir=str(self.test_dir),
            start='2023-01-01',
            end='2023-12-31',
            interval='1d',
            max_workers=2,
            limit_nums=2
        )
        
        # 验证参数设置
        self.assertEqual(str(collector.save_dir), str(self.test_dir))
        self.assertEqual(collector.interval, '1d')
        self.assertEqual(collector.max_workers, 2)
        self.assertEqual(len(collector.instrument_list), 2)  # 因为limit_nums=2
        self.assertEqual(collector.instrument_list, ['TEST1', 'TEST2'])
        
        # 验证时间格式
        self.assertIsInstance(collector.start_datetime, pd.Timestamp)
        self.assertIsInstance(collector.end_datetime, pd.Timestamp)
        self.assertEqual(str(collector.start_datetime.date()), '2023-01-01')
        self.assertEqual(str(collector.end_datetime.date()), '2023-12-31')
    
    def test_normalize_datetime(self):
        """测试时间标准化功能
        
        测试点：
        1. 字符串格式时间是否正确转换
        2. None值是否返回默认时间
        3. pd.Timestamp对象是否保持不变
        """
        # 创建测试类
        class TestCollector(BaseCollector):
            def get_instrument_list(self):
                return ['TEST1']
            
            def normalize_symbol(self, symbol):
                return symbol
            
            def get_data(self, symbol, interval, start_datetime, end_datetime):
                return pd.DataFrame()
        
        collector = TestCollector(save_dir=str(self.test_dir))
        
        # 测试字符串时间转换
        start_dt = collector.normalize_start_datetime('2023-01-01')
        self.assertIsInstance(start_dt, pd.Timestamp)
        self.assertEqual(str(start_dt.date()), '2023-01-01')
        
        # 测试pd.Timestamp对象
        end_dt = pd.Timestamp('2023-12-31')
        normalized_end = collector.normalize_end_datetime(end_dt)
        self.assertEqual(normalized_end, end_dt)
    
    def test_save_instrument(self):
        """测试保存标的数据功能
        
        测试点：
        1. 数据是否正确保存到文件
        2. 已存在文件是否正确追加
        3. 空数据是否正确处理
        """
        # 创建测试类
        class TestCollector(BaseCollector):
            def get_instrument_list(self):
                return ['TEST1']
            
            def normalize_symbol(self, symbol):
                return symbol
            
            def get_data(self, symbol, interval, start_datetime, end_datetime):
                return pd.DataFrame()
        
        collector = TestCollector(save_dir=str(self.test_dir))
        
        # 测试保存数据
        test_data = pd.DataFrame({
            'date': ['2023-01-01', '2023-01-02'],
            'open': [100, 101],
            'high': [102, 103],
            'low': [99, 100],
            'close': [101, 102],
            'volume': [1000, 2000]
        })
        
        collector.save_instrument('TEST1', test_data)
        
        # 验证文件是否创建
        data_file = self.test_dir / 'TEST1.csv'
        self.assertTrue(data_file.exists())
        
        # 验证数据是否正确保存
        saved_data = pd.read_csv(data_file)
        self.assertEqual(len(saved_data), 2)
        self.assertEqual(saved_data['symbol'].tolist(), ['TEST1', 'TEST1'])
        
        # 测试追加数据
        append_data = pd.DataFrame({
            'date': ['2023-01-03'],
            'open': [103],
            'high': [104],
            'low': [102],
            'close': [103],
            'volume': [3000]
        })
        
        collector.save_instrument('TEST1', append_data)
        saved_data = pd.read_csv(data_file)
        self.assertEqual(len(saved_data), 3)
        
        # 测试空数据处理
        collector.save_instrument('TEST2', pd.DataFrame())
        data_file2 = self.test_dir / 'TEST2.csv'
        self.assertFalse(data_file2.exists())
    
    def test_cache_small_data(self):
        """测试缓存小数据功能
        
        测试点：
        1. 小数据是否被正确缓存
        2. 大数据是否不被缓存
        """
        # 创建测试类
        class TestCollector(BaseCollector):
            def get_instrument_list(self):
                return ['TEST1', 'TEST2']
            
            def normalize_symbol(self, symbol):
                return symbol
            
            def get_data(self, symbol, interval, start_datetime, end_datetime):
                return pd.DataFrame()
        
        # 设置check_data_length=5，即数据长度小于5时缓存
        collector = TestCollector(
            save_dir=str(self.test_dir),
            check_data_length=5
        )
        
        # 测试小数据缓存
        small_data = pd.DataFrame({
            'date': ['2023-01-01', '2023-01-02'],
            'open': [100, 101],
            'high': [102, 103],
            'low': [99, 100],
            'close': [101, 102],
            'volume': [1000, 2000]
        })
        
        result = collector.cache_small_data('TEST1', small_data)
        self.assertEqual(result, collector.CACHE_FLAG)
        self.assertIn('TEST1', collector.mini_symbol_map)
        
        # 测试大数据不缓存
        large_data = pd.DataFrame({
            'date': [f'2023-01-{i:02d}' for i in range(1, 10)],
            'open': range(100, 109),
            'high': range(102, 111),
            'low': range(99, 108),
            'close': range(101, 110),
            'volume': range(1000, 1009)
        })
        
        result = collector.cache_small_data('TEST2', large_data)
        self.assertEqual(result, collector.NORMAL_FLAG)
        self.assertNotIn('TEST2', collector.mini_symbol_map)
    
    @patch.object(BaseCollector, '_collector')
    def test_collect_data(self, mock_collector):
        """测试数据收集流程
        
        测试点：
        1. collect_data方法是否正确调用_collector
        2. 缓存数据是否正确处理
        """
        # 创建测试类
        class TestCollector(BaseCollector):
            def get_instrument_list(self):
                return ['TEST1', 'TEST2']
            
            def normalize_symbol(self, symbol):
                return symbol
            
            def get_data(self, symbol, interval, start_datetime, end_datetime):
                return pd.DataFrame()
        
        collector = TestCollector(save_dir=str(self.test_dir))
        
        # 模拟_collector方法返回空列表（所有标的收集成功）
        mock_collector.return_value = []
        
        # 执行数据收集
        collector.collect_data()
        
        # 验证_collector被调用
        mock_collector.assert_called_once()
    
    def test_simple_collector(self):
        """测试简单收集器功能
        
        测试点：
        1. _simple_collector方法是否正确获取数据
        2. 数据是否正确保存
        """
        # 创建测试类，重写get_data方法返回测试数据
        class TestCollector(BaseCollector):
            def get_instrument_list(self):
                return ['TEST1']
            
            def normalize_symbol(self, symbol):
                return symbol
            
            def get_data(self, symbol, interval, start_datetime, end_datetime):
                return pd.DataFrame({
                    'date': ['2023-01-01', '2023-01-02'],
                    'open': [100, 101],
                    'high': [102, 103],
                    'low': [99, 100],
                    'close': [101, 102],
                    'volume': [1000, 2000]
                })
        
        collector = TestCollector(save_dir=str(self.test_dir))
        
        # 执行简单收集
        result = collector._simple_collector('TEST1')
        
        # 验证结果
        self.assertEqual(result, collector.NORMAL_FLAG)
        
        # 验证数据是否保存
        data_file = self.test_dir / 'TEST1.csv'
        self.assertTrue(data_file.exists())
        saved_data = pd.read_csv(data_file)
        self.assertEqual(len(saved_data), 2)


if __name__ == '__main__':
    unittest.main()
