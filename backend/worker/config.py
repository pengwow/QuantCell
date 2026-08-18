"""
Worker 配置模块

检测运行时环境可用性
"""

# axon-quant 可用性检测
try:
    import axon_quant

    AXON_QUANT_AVAILABLE = True
except ImportError:
    AXON_QUANT_AVAILABLE = False
