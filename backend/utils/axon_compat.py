# -*- coding: utf-8 -*-
"""axon_quant 兼容性检测模块

统一管理 axon_quant 的可用性检测，避免在多个服务文件中重复定义。

使用方式:
    from utils.axon_compat import AXON_AVAILABLE

ponytail: 延迟导入避免启动时失败,仅在需要时检测
"""
from __future__ import annotations

try:
    import axon_quant  # noqa: F401
    import axon_bridge  # noqa: F401
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
