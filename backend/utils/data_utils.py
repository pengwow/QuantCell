"""
数据工具模块

提供数据清理、转换等通用工具函数。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-24
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Dict, List, Optional
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


def sanitize_for_json(data: Any) -> Any:
    """
    递归清理数据，使其可以被 JSON 序列化

    处理以下特殊情况：
    - NaT (Not a Time) 值
    - NaN (Not a Number) 值
    - Infinity 值
    - Timestamp 对象
    - Timedelta 对象
    - NumPy 类型

    Args:
        data: 需要清理的数据，可以是任意类型

    Returns:
        Any: 清理后的数据，可以被 JSON 序列化

    Examples:
        >>> sanitize_for_json(pd.Timestamp('2023-01-01'))
        '2023-01-01 00:00:00'
        >>> sanitize_for_json(np.nan)
        None
        >>> sanitize_for_json(np.inf)
        None
    """
    try:
        # 处理字典类型
        if isinstance(data, dict):
            return {k: sanitize_for_json(v) for k, v in data.items()}

        # 处理列表类型
        elif isinstance(data, list):
            return [sanitize_for_json(item) for item in data]

        # 处理 Timestamp 和 datetime 对象
        elif isinstance(data, (pd.Timestamp, datetime)):
            if pd.isna(data):
                return None
            return data.strftime('%Y-%m-%d %H:%M:%S')

        # 处理 Timedelta 对象
        elif isinstance(data, pd.Timedelta):
            if pd.isna(data):
                return None
            return str(data)

        # 处理 NaT、NaN、None 值
        elif pd.isna(data):
            return None

        # 处理浮点数的无穷大值
        elif isinstance(data, float):
            if np.isinf(data):
                return None
            return data

        # 处理 NumPy 整数类型
        elif isinstance(data, (np.integer, np.int64, np.int32)):
            return int(data)

        # 处理 NumPy 浮点类型
        elif isinstance(data, (np.floating, np.float64, np.float32)):
            if np.isnan(data) or np.isinf(data):
                return None
            return float(data)

        # 其他类型直接返回
        else:
            return data
    except Exception as e:
        logger.warning(f"清理数据时发生异常: {e}, 数据类型: {type(data)}")
        return None


class DataSanitizer:
    """数据清理器，负责数据清理和转换"""

    def sanitize_for_json(self, data: Any) -> Any:
        """
        递归清理数据，使其可以被JSON序列化
        处理 NaT, NaN, Infinity, Timestamp 等

        Args:
            data: 需要清理的数据

        Returns:
            Any: 清理后的数据
        """
        return sanitize_for_json(data)

    def translate_metrics(
        self,
        stats: Dict[str, Any],
        language: str = "zh-CN"
    ) -> List[Dict[str, Any]]:
        """
        翻译回测结果指标为多语言

        Args:
            stats: 回测结果统计
            language: 目标语言

        Returns:
            List[Dict[str, Any]]: 翻译后的指标列表
        """
        from i18n.utils import load_translations

        # 加载翻译
        trans = load_translations(language)

        translated_metrics = []
        for key, value in stats.items():
            # 跳过内部字段
            if key in ['_strategy', '_equity_curve', '_trade_list', '_trades']:
                continue

            # 获取翻译
            name = trans.get(key, key)
            desc = trans.get(f"{key}.desc", name)

            # 处理特殊类型的值
            metric_info = self._process_metric_value(key, value)
            if metric_info is None:
                continue

            translated_metrics.append({
                'name': name,
                'key': key,
                'value': metric_info['value'],
                'description': desc,
                'type': metric_info['type']
            })

        return translated_metrics

    def _process_metric_value(self, key: str, value: Any) -> Optional[Dict[str, Any]]:
        """
        处理指标值，返回处理后的值和类型

        Args:
            key: 指标键
            value: 指标值

        Returns:
            Optional[Dict[str, Any]]: 包含 value 和 type 的字典，如果应该跳过则返回 None
        """
        # 处理 Timestamp
        if isinstance(value, pd.Timestamp):
            return {
                'value': self.sanitize_for_json(value),
                'type': 'datetime'
            }

        # 处理 Timedelta
        if isinstance(value, pd.Timedelta):
            return {
                'value': self.sanitize_for_json(value),
                'type': 'duration'
            }

        # 跳过复杂数据结构
        if isinstance(value, (pd.Series, pd.DataFrame)):
            return None

        # 处理数值类型
        if isinstance(value, (int, float)):
            metric_type = 'number'
            if '[%]' in key:
                metric_type = 'percentage'
            elif '[$]' in key:
                metric_type = 'currency'

            return {
                'value': value,
                'type': metric_type
            }

        # 其他类型
        return {
            'value': value,
            'type': 'string'
        }
