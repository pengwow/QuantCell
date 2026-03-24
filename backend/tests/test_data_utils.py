"""
数据工具模块测试

测试数据清理和转换功能。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-24
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.data_utils import sanitize_for_json, DataSanitizer


class TestSanitizeForJson(unittest.TestCase):
    """测试 sanitize_for_json 函数"""

    def test_dict_sanitization(self):
        """测试字典清理"""
        data = {
            "key1": "value1",
            "key2": pd.Timestamp("2023-01-01"),
            "key3": np.nan,
            "key4": np.inf,
            "nested": {
                "key5": pd.Timestamp("2023-06-01"),
                "key6": np.nan
            }
        }
        result = sanitize_for_json(data)

        self.assertEqual(result["key1"], "value1")
        self.assertEqual(result["key2"], "2023-01-01 00:00:00")
        self.assertIsNone(result["key3"])
        self.assertIsNone(result["key4"])
        self.assertEqual(result["nested"]["key5"], "2023-06-01 00:00:00")
        self.assertIsNone(result["nested"]["key6"])

    def test_list_sanitization(self):
        """测试列表清理"""
        data = [
            pd.Timestamp("2023-01-01"),
            np.nan,
            np.inf,
            "string",
            123
        ]
        result = sanitize_for_json(data)

        self.assertEqual(result[0], "2023-01-01 00:00:00")
        self.assertIsNone(result[1])
        self.assertIsNone(result[2])
        self.assertEqual(result[3], "string")
        self.assertEqual(result[4], 123)

    def test_timestamp_sanitization(self):
        """测试 Timestamp 清理"""
        ts = pd.Timestamp("2023-01-15 10:30:00")
        result = sanitize_for_json(ts)
        self.assertEqual(result, "2023-01-15 10:30:00")

    def test_datetime_sanitization(self):
        """测试 datetime 清理"""
        dt = datetime(2023, 1, 15, 10, 30, 0)
        result = sanitize_for_json(dt)
        self.assertEqual(result, "2023-01-15 10:30:00")

    def test_timedelta_sanitization(self):
        """测试 Timedelta 清理"""
        td = pd.Timedelta(days=1, hours=2)
        result = sanitize_for_json(td)
        self.assertEqual(result, "1 days 02:00:00")

    def test_nan_sanitization(self):
        """测试 NaN 清理"""
        result = sanitize_for_json(np.nan)
        self.assertIsNone(result)

    def test_nat_sanitization(self):
        """测试 NaT 清理"""
        result = sanitize_for_json(pd.NaT)
        self.assertIsNone(result)

    def test_inf_sanitization(self):
        """测试 Infinity 清理"""
        result_pos = sanitize_for_json(np.inf)
        result_neg = sanitize_for_json(-np.inf)
        self.assertIsNone(result_pos)
        self.assertIsNone(result_neg)

    def test_numpy_int_sanitization(self):
        """测试 NumPy 整数类型清理"""
        result_int64 = sanitize_for_json(np.int64(123))
        result_int32 = sanitize_for_json(np.int32(456))
        self.assertEqual(result_int64, 123)
        self.assertEqual(result_int32, 456)
        self.assertIsInstance(result_int64, int)
        self.assertIsInstance(result_int32, int)

    def test_numpy_float_sanitization(self):
        """测试 NumPy 浮点类型清理"""
        result_float64 = sanitize_for_json(np.float64(123.456))
        result_float32 = sanitize_for_json(np.float32(789.012))
        self.assertAlmostEqual(result_float64, 123.456, places=3)
        self.assertAlmostEqual(result_float32, 789.012, places=2)
        self.assertIsInstance(result_float64, float)
        self.assertIsInstance(result_float32, float)

    def test_numpy_float_nan_sanitization(self):
        """测试 NumPy 浮点 NaN 清理"""
        result = sanitize_for_json(np.float64(np.nan))
        self.assertIsNone(result)

    def test_numpy_float_inf_sanitization(self):
        """测试 NumPy 浮点 Infinity 清理"""
        result = sanitize_for_json(np.float64(np.inf))
        self.assertIsNone(result)

    def test_string_sanitization(self):
        """测试字符串清理"""
        result = sanitize_for_json("test string")
        self.assertEqual(result, "test string")

    def test_int_sanitization(self):
        """测试整数清理"""
        result = sanitize_for_json(123)
        self.assertEqual(result, 123)

    def test_float_sanitization(self):
        """测试浮点数清理"""
        result = sanitize_for_json(123.456)
        self.assertEqual(result, 123.456)

    def test_none_sanitization(self):
        """测试 None 清理"""
        result = sanitize_for_json(None)
        self.assertIsNone(result)


class TestDataSanitizer(unittest.TestCase):
    """测试 DataSanitizer 类"""

    def setUp(self):
        """测试前准备"""
        self.sanitizer = DataSanitizer()

    def test_sanitize_for_json_method(self):
        """测试 sanitize_for_json 方法"""
        data = {
            "timestamp": pd.Timestamp("2023-01-01"),
            "value": np.nan
        }
        result = self.sanitizer.sanitize_for_json(data)
        self.assertEqual(result["timestamp"], "2023-01-01 00:00:00")
        self.assertIsNone(result["value"])

    def test_translate_metrics(self):
        """测试指标翻译"""
        stats = {
            "Return [%]": 15.5,
            "Max. Drawdown [%]": -5.2,
            "Sharpe Ratio": 1.8,
            "Start": pd.Timestamp("2023-01-01"),
            "Duration": pd.Timedelta(days=30),
            "_strategy": "should be skipped",
            "_equity_curve": pd.DataFrame()
        }

        # 使用默认语言（zh-CN）
        result = self.sanitizer.translate_metrics(stats)

        # 验证结果
        self.assertEqual(len(result), 5)  # 跳过 _strategy 和 _equity_curve

        # 检查指标类型
        metric_dict = {item["key"]: item for item in result}

        self.assertEqual(metric_dict["Return [%]"]["type"], "percentage")
        self.assertEqual(metric_dict["Max. Drawdown [%]"]["type"], "percentage")
        self.assertEqual(metric_dict["Sharpe Ratio"]["type"], "number")
        self.assertEqual(metric_dict["Start"]["type"], "datetime")
        self.assertEqual(metric_dict["Duration"]["type"], "duration")

        # 检查值是否正确
        self.assertEqual(metric_dict["Return [%]"]["value"], 15.5)
        self.assertEqual(metric_dict["Start"]["value"], "2023-01-01 00:00:00")


if __name__ == "__main__":
    unittest.main()
