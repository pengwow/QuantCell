"""
Worker 配置模块

检测运行时环境可用性
"""

from dataclasses import dataclass

# axon-quant 可用性检测
try:
    import axon_quant

    AXON_QUANT_AVAILABLE = True
except ImportError:
    AXON_QUANT_AVAILABLE = False


# =============================================================================
# ZMQ 通信配置（Worker 独立进程 IPC）
# =============================================================================


@dataclass
class ZmqConfig:
    """ZMQ 通信配置。"""

    event_pull_addr: str = "tcp://127.0.0.1:5558"
    cmd_push_addr: str = "tcp://127.0.0.1:5559"
    heartbeat_interval: float = 5.0
    handshake_timeout: float = 5.0
    health_check_interval: float = 30.0
    offline_threshold: float = 60.0
    cmd_timeout: float = 5.0
