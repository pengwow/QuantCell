"""
加密货币数据收集模块（兼容层）

⚠️ 警告：此模块已迁移
请使用新的导入路径：
    from exchange import BinanceCollector, OKXCollector
    from exchange import CryptoBaseCollector

此模块保留用于向后兼容，将在未来版本中移除。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

import warnings

# 发出弃用警告
warnings.warn(
    "collector.crypto 模块已迁移，"
    "请更新导入路径。此模块将在未来版本中移除。",
    DeprecationWarning,
    stacklevel=2
)

# 从新的位置重新导出
from exchange import CryptoBaseCollector, BinanceCollector, OKXCollector

__all__ = [
    "CryptoBaseCollector",
    "BinanceCollector",
    "OKXCollector",
]
