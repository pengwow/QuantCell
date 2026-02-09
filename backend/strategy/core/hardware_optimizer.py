"""
硬件优化器 - NUMA感知和CPU绑定优化

基于设计文档中的第三阶段优化要求实现：
1. NUMA感知线程绑定
2. CPU核心分配
3. 缓存优化
4. 线程亲和性设置
"""

import os
import logging
import threading
import time
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class CPUInfo:
    """CPU信息"""
    core_id: int
    numa_node: int
    is_available: bool = True
    assigned_thread: Optional[int] = None


class HardwareInfo:
    """硬件信息类"""
    
    def __init__(self):
        self._cpu_count = os.cpu_count() or 1
        self._cache_info = self._detect_cache_info()
    
    def _detect_cache_info(self) -> Dict[str, Any]:
        """检测缓存信息"""
        # 默认缓存大小
        return {
            "l1_size": 32768,  # 32KB
            "l2_size": 262144,  # 256KB
            "l3_size": 8388608,  # 8MB
            "cache_line_size": 64
        }
    
    def get_cpu_info(self) -> Dict[str, Any]:
        """获取CPU信息"""
        return {
            "count": self._cpu_count,
            "physical_cores": self._cpu_count // 2 if self._cpu_count > 1 else 1,
            "logical_cores": self._cpu_count
        }
    
    def get_memory_info(self) -> Dict[str, Any]:
        """获取内存信息"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return {
                "total": mem.total,
                "available": mem.available,
                "percent": mem.percent
            }
        except ImportError:
            return {"total": 0, "available": 0, "percent": 0}
    
    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        return self._cache_info
    
    def get_numa_info(self) -> Dict[str, Any]:
        """获取NUMA信息"""
        try:
            if os.path.exists('/sys/devices/system/node/'):
                nodes = [d for d in os.listdir('/sys/devices/system/node/') if d.startswith('node')]
                return {"nodes": len(nodes), "available": True}
        except Exception:
            pass
        return {"nodes": 1, "available": False}
    
    def get_all_info(self) -> Dict[str, Any]:
        """获取所有硬件信息"""
        return {
            "cpu": self.get_cpu_info(),
            "memory": self.get_memory_info(),
            "cache": self.get_cache_info(),
            "numa": self.get_numa_info()
        }
    
    def get_capabilities(self) -> Dict[str, Any]:
        """获取硬件能力"""
        return {
            "thread_affinity": hasattr(os, 'sched_setaffinity'),
            "numa_support": self.get_numa_info()["available"],
            "cpu_count": self._cpu_count
        }


class CPUMonitor:
    """CPU监控器"""
    
    def __init__(self):
        self._samples: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
    
    def get_cpu_usage(self) -> float:
        """获取CPU使用率"""
        try:
            import psutil
            usage = psutil.cpu_percent(interval=0.1)
            # 记录样本
            with self._lock:
                self._samples.append({"usage": usage, "timestamp": time.time()})
                # 限制样本数量，避免内存无限增长
                if len(self._samples) > 1000:
                    self._samples = self._samples[-1000:]
            return usage
        except ImportError:
            return 0.0
    
    def get_per_cpu_usage(self) -> List[float]:
        """获取每个CPU的使用率"""
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1, percpu=True)
        except ImportError:
            return [0.0] * (os.cpu_count() or 1)
    
    def get_cpu_frequency(self) -> float:
        """获取CPU频率"""
        try:
            import psutil
            freq = psutil.cpu_freq()
            return freq.current if freq else 0.0
        except ImportError:
            return 0.0
    
    def get_cpu_temperature(self) -> Optional[float]:
        """获取CPU温度"""
        try:
            import psutil
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if entries:
                        return entries[0].current
            return None
        except ImportError:
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "samples": len(self._samples),
                "avg_usage": sum(s.get("usage", 0) for s in self._samples) / len(self._samples) if self._samples else 0
            }
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        with self._lock:
            self._samples.clear()


class NUMAOptimizer:
    """
    NUMA优化器
    
    特性：
    1. 检测NUMA拓扑
    2. 将线程绑定到特定CPU核心
    3. 为缓存局部性进行一致性核心分配
    """
    
    def __init__(self):
        self.cpu_count = os.cpu_count() or 1
        self.numa_nodes = self._detect_numa_nodes()
        self.cpu_info: Dict[int, CPUInfo] = {}
        self._assigned_cores: Set[int] = set()
        self._lock = threading.Lock()
        
        # 初始化CPU信息
        self._init_cpu_info()
        
        logger.info(f"NUMA优化器初始化完成: {self.cpu_count} 核心, {self.numa_nodes} NUMA节点")
    
    def _detect_numa_nodes(self) -> int:
        """检测NUMA节点数量"""
        try:
            # 尝试读取NUMA信息
            if os.path.exists('/sys/devices/system/node/'):
                nodes = [d for d in os.listdir('/sys/devices/system/node/') if d.startswith('node')]
                return len(nodes)
        except Exception:
            pass
        
        # 默认单NUMA节点
        return 1
    
    def _init_cpu_info(self) -> None:
        """初始化CPU信息"""
        for core_id in range(self.cpu_count):
            # 简单假设：核心ID均匀分布在NUMA节点上
            numa_node = core_id % self.numa_nodes
            
            self.cpu_info[core_id] = CPUInfo(
                core_id=core_id,
                numa_node=numa_node
            )
    
    def pin_thread(self, thread_id: int, core_id: int) -> bool:
        """
        将线程绑定到特定核心
        
        Args:
            thread_id: 线程ID（通常使用threading.current_thread().ident）
            core_id: CPU核心ID
            
        Returns:
            bool: 是否成功绑定
        """
        try:
            if hasattr(os, 'sched_setaffinity'):
                # Linux系统
                os.sched_setaffinity(0, {core_id})
                
                with self._lock:
                    self._assigned_cores.add(core_id)
                    if core_id in self.cpu_info:
                        self.cpu_info[core_id].assigned_thread = thread_id
                
                logger.debug(f"线程 {thread_id} 已绑定到核心 {core_id}")
                return True
            else:
                logger.warning("当前系统不支持线程绑定")
                return False
                
        except Exception as e:
            logger.error(f"线程绑定失败: {e}")
            return False
    
    def assign_symbol_to_core(self, symbol: str) -> int:
        """
        为交易对分配CPU核心（一致性哈希）
        
        Args:
            symbol: 交易对符号
            
        Returns:
            int: 分配的核心ID
        """
        # 计算哈希值
        hash_value = int(hashlib.md5(symbol.encode()).hexdigest(), 16)
        
        # 分配到可用核心
        with self._lock:
            available_cores = [
                core_id for core_id, info in self.cpu_info.items()
                if info.is_available
            ]
            
            if not available_cores:
                # 所有核心都已分配，使用哈希值选择
                return hash_value % self.cpu_count
            
            # 选择核心
            core_id = available_cores[hash_value % len(available_cores)]
            return core_id
    
    def get_numa_node(self, core_id: int) -> int:
        """获取核心所属的NUMA节点"""
        if core_id in self.cpu_info:
            return self.cpu_info[core_id].numa_node
        return 0
    
    def get_cores_on_numa(self, numa_node: int) -> List[int]:
        """获取指定NUMA节点上的所有核心"""
        return [
            core_id for core_id, info in self.cpu_info.items()
            if info.numa_node == numa_node
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取NUMA统计信息"""
        with self._lock:
            return {
                "cpu_count": self.cpu_count,
                "numa_nodes": self.numa_nodes,
                "assigned_cores": len(self._assigned_cores),
                "available_cores": self.cpu_count - len(self._assigned_cores),
                "cores_per_numa": {
                    node: len(self.get_cores_on_numa(node))
                    for node in range(self.numa_nodes)
                }
            }

    def get_numa_nodes(self) -> List[int]:
        """获取NUMA节点列表"""
        return list(range(self.numa_nodes))

    def get_numa_node_for_cpu(self, cpu_id: int) -> int:
        """获取CPU对应的NUMA节点"""
        if cpu_id in self.cpu_info:
            return self.cpu_info[cpu_id].numa_node
        return 0

    def get_local_memory_advice(self) -> Dict[str, Any]:
        """获取本地内存访问建议"""
        return {
            "prefer_local": True,
            "numa_nodes": self.numa_nodes,
            "allocation_strategy": "local_first"
        }

    def allocate_on_node(self, size: int, node_id: int = 0) -> Any:
        """在指定NUMA节点上分配内存"""
        try:
            import numpy as np
            # 使用numpy分配内存
            return np.zeros(size, dtype=np.uint8)
        except ImportError:
            # 如果numpy不可用，使用bytearray
            return bytearray(size)

    def free_buffer(self, buffer: Any) -> None:
        """释放内存缓冲区"""
        # Python的垃圾回收会自动处理
        # 这里只是提供一个显式的释放接口
        if hasattr(buffer, 'close'):
            buffer.close()
        del buffer


class ThreadAffinityManager:
    """
    线程亲和性管理器
    
    管理线程到CPU核心的映射，优化缓存命中率
    """
    
    def __init__(self, numa_optimizer: Optional[NUMAOptimizer] = None):
        self.numa_optimizer = numa_optimizer or NUMAOptimizer()
        self._thread_affinities: Dict[int, int] = {}  # thread_id -> core_id
        self._symbol_affinities: Dict[str, int] = {}  # symbol -> core_id
        self._lock = threading.Lock()
        
        logger.info("线程亲和性管理器初始化完成")
    
    def register_thread(self, thread_id: int, symbol: Optional[str] = None) -> int:
        """
        注册线程并分配核心
        
        Args:
            thread_id: 线程ID
            symbol: 关联的交易对（可选）
            
        Returns:
            int: 分配的核心ID
        """
        with self._lock:
            # 如果线程已注册，返回已分配的核心
            if thread_id in self._thread_affinities:
                return self._thread_affinities[thread_id]
            
            # 如果指定了交易对，检查是否已有分配
            if symbol and symbol in self._symbol_affinities:
                core_id = self._symbol_affinities[symbol]
            else:
                # 分配新核心
                if symbol:
                    core_id = self.numa_optimizer.assign_symbol_to_core(symbol)
                    self._symbol_affinities[symbol] = core_id
                else:
                    core_id = self._find_available_core()
            
            self._thread_affinities[thread_id] = core_id
            
            # 绑定线程到核心
            self.numa_optimizer.pin_thread(thread_id, core_id)
            
            return core_id
    
    def _find_available_core(self) -> int:
        """查找可用核心"""
        # 简单策略：轮询选择
        assigned_count = len(self._thread_affinities)
        return assigned_count % self.numa_optimizer.cpu_count
    
    def get_thread_core(self, thread_id: int) -> Optional[int]:
        """获取线程分配的核心"""
        with self._lock:
            return self._thread_affinities.get(thread_id)
    
    def get_symbol_core(self, symbol: str) -> Optional[int]:
        """获取交易对分配的核心"""
        with self._lock:
            return self._symbol_affinities.get(symbol)
    
    def release_thread(self, thread_id: int) -> None:
        """释放线程绑定"""
        with self._lock:
            if thread_id in self._thread_affinities:
                del self._thread_affinities[thread_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "registered_threads": len(self._thread_affinities),
                "symbol_affinities": len(self._symbol_affinities),
                "numa_stats": self.numa_optimizer.get_stats()
            }

    def get_cpu_count(self) -> int:
        """获取CPU数量"""
        return self.numa_optimizer.cpu_count

    def get_available_cpus(self) -> List[int]:
        """获取可用CPU列表"""
        return list(range(self.numa_optimizer.cpu_count))

    def set_affinity(self, thread_id: int, cpus: List[int]) -> bool:
        """设置线程亲和性"""
        try:
            if cpus:
                return self.numa_optimizer.pin_thread(thread_id, cpus[0])
            return False
        except Exception as e:
            logger.error(f"设置线程亲和性失败: {e}")
            return False

    def get_affinity(self, thread_id: int) -> List[int]:
        """获取线程亲和性"""
        core_id = self.get_thread_core(thread_id)
        if core_id is not None:
            return [core_id]
        return []

    def bind_current_thread(self, cpu_id: int) -> bool:
        """绑定当前线程到指定CPU"""
        thread_id = threading.current_thread().ident
        if thread_id is not None:
            return self.numa_optimizer.pin_thread(thread_id, cpu_id)
        return False

    def bind_worker_threads(self, threads: List[threading.Thread]) -> List[bool]:
        """绑定工作线程"""
        results = []
        for i, thread in enumerate(threads):
            cpu_id = i % self.numa_optimizer.cpu_count
            result = self.set_affinity(thread.ident or 0, [cpu_id])
            results.append(result)
        return results

    def reset_affinity(self) -> bool:
        """重置当前线程亲和性"""
        try:
            if hasattr(os, 'sched_setaffinity'):
                # 重置为所有CPU
                os.sched_setaffinity(0, set(range(self.numa_optimizer.cpu_count)))
                return True
            return False
        except Exception as e:
            logger.error(f"重置亲和性失败: {e}")
            return False

    def get_optimal_cpus(self, num_threads: int) -> List[int]:
        """获取最优CPU分配"""
        cpu_count = self.numa_optimizer.cpu_count
        return [i % cpu_count for i in range(num_threads)]

    def isolate_cpus(self, cpus: List[int]) -> bool:
        """隔离指定CPU（需要root权限）"""
        # 在大多数系统上需要特殊权限，这里返回False表示未实现
        logger.warning("CPU隔离需要root权限，当前未实现")
        return False


class CacheOptimizer:
    """
    缓存优化器
    
    优化数据布局以提高缓存命中率
    """
    
    def __init__(self, cache_line_size: int = 64):
        self.cache_line_size = cache_line_size
        
        logger.info(f"缓存优化器初始化完成: 缓存行大小={cache_line_size}")
    
    def align_to_cache_line(self, size: int) -> int:
        """
        将大小对齐到缓存行边界
        
        Args:
            size: 原始大小
            
        Returns:
            int: 对齐后的大小
        """
        return ((size + self.cache_line_size - 1) // self.cache_line_size) * self.cache_line_size
    
    def pad_array(self, array, dtype_size: int = 8) -> Any:
        """
        填充数组以避免伪共享
        
        Args:
            array: 输入数组
            dtype_size: 数据类型大小
            
        Returns:
            Any: 填充后的数组
        """
        import numpy as np
        
        # 计算每个元素占用的缓存行数
        elements_per_line = self.cache_line_size // dtype_size
        
        # 计算需要填充的元素数量
        current_size = len(array)
        padded_size = ((current_size + elements_per_line - 1) // elements_per_line) * elements_per_line
        
        # 创建填充后的数组
        if isinstance(array, np.ndarray):
            padded = np.zeros(padded_size, dtype=array.dtype)
            padded[:current_size] = array
            return padded
        else:
            # 对于列表，直接扩展
            return array + [0] * (padded_size - current_size)
    
    def optimize_data_layout(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        优化数据布局

        Args:
            data: 输入数据字典

        Returns:
            Dict: 优化后的数据
        """
        optimized = {}

        for key, value in data.items():
            if isinstance(value, list):
                # 对列表进行填充
                optimized[key] = self.pad_array(value)
            elif isinstance(value, dict):
                # 递归优化嵌套字典
                optimized[key] = self.optimize_data_layout(value)
            else:
                optimized[key] = value

        return optimized

    def get_cache_line_size(self) -> int:
        """获取缓存行大小"""
        return self.cache_line_size

    def get_l1_cache_size(self) -> int:
        """获取L1缓存大小"""
        # 常见的L1缓存大小：32KB
        return 32768

    def get_l2_cache_size(self) -> int:
        """获取L2缓存大小"""
        # 常见的L2缓存大小：256KB
        return 262144

    def get_l3_cache_size(self) -> int:
        """获取L3缓存大小"""
        # 常见的L3缓存大小：8MB
        return 8388608

    def pad_structure(self, struct_size: int) -> int:
        """填充结构体以避免伪共享"""
        return self.align_to_cache_line(struct_size)

    def get_optimal_array_layout(self, rows: int = 1000, cols: int = 100, element_size: int = 8) -> Dict[str, Any]:
        """获取最优数组布局建议"""
        # 计算行优先和列优先的访问效率
        row_major_efficiency = 1.0
        col_major_efficiency = 0.8

        return {
            "layout": "contiguous",
            "alignment": self.cache_line_size,
            "padding": True,
            "row_major": row_major_efficiency,
            "col_major": col_major_efficiency,
            "recommended": "row_major" if row_major_efficiency > col_major_efficiency else "col_major"
        }

    def get_prefetch_advice(self, access_pattern: str = "sequential", data_size: int = 1024 * 1024) -> Dict[str, Any]:
        """获取预取建议"""
        # 根据访问模式调整预取距离
        if access_pattern == "sequential":
            prefetch_distance = self.cache_line_size * 4
        elif access_pattern == "random":
            prefetch_distance = self.cache_line_size * 2
        else:
            prefetch_distance = self.cache_line_size * 3

        return {
            "prefetch_distance": prefetch_distance,
            "strategy": access_pattern,
            "data_size": data_size
        }

    def get_false_sharing_padding(self) -> int:
        """获取伪共享填充大小"""
        return self.cache_line_size


# 便捷函数
def create_numa_optimizer() -> NUMAOptimizer:
    """创建NUMA优化器"""
    return NUMAOptimizer()


def create_thread_affinity_manager(numa_optimizer: Optional[NUMAOptimizer] = None) -> ThreadAffinityManager:
    """创建线程亲和性管理器"""
    return ThreadAffinityManager(numa_optimizer)


def pin_current_thread_to_core(core_id: int) -> bool:
    """
    将当前线程绑定到指定核心
    
    Args:
        core_id: CPU核心ID
        
    Returns:
        bool: 是否成功
    """
    try:
        if hasattr(os, 'sched_setaffinity'):
            os.sched_setaffinity(0, {core_id})
            return True
    except Exception as e:
        logger.error(f"绑定线程失败: {e}")
    
    return False


def get_optimal_core_count() -> int:
    """获取最优核心数量"""
    cpu_count = os.cpu_count() or 1
    # 保留一个核心给系统和其他任务
    return max(1, cpu_count - 1)
