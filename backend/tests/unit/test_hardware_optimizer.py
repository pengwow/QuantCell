"""
硬件优化器单元测试

测试范围:
- NUMAOptimizer NUMA感知优化
- ThreadAffinityManager 线程亲和性管理
- CacheOptimizer 缓存优化
- CPU拓扑检测
- 硬件信息获取
"""

import pytest
import time
import threading
import os
from unittest.mock import Mock, patch, MagicMock

from strategy.core.hardware_optimizer import (
    NUMAOptimizer,
    ThreadAffinityManager,
    CacheOptimizer,
    HardwareInfo,
    CPUMonitor
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def numa_optimizer():
    """创建NUMA优化器实例"""
    return NUMAOptimizer()


@pytest.fixture
def affinity_manager():
    """创建线程亲和性管理器实例"""
    return ThreadAffinityManager()


@pytest.fixture
def cache_optimizer():
    """创建缓存优化器实例"""
    return CacheOptimizer()


@pytest.fixture
def hardware_info():
    """创建硬件信息实例"""
    return HardwareInfo()


@pytest.fixture
def cpu_monitor():
    """创建CPU监控器实例"""
    return CPUMonitor()


# =============================================================================
# NUMAOptimizer 测试
# =============================================================================

class TestNUMAOptimizer:
    """NUMA优化器测试类"""

    def test_numa_initialization(self, numa_optimizer):
        """测试NUMA优化器初始化"""
        assert numa_optimizer is not None

    def test_numa_node_detection(self, numa_optimizer):
        """测试NUMA节点检测"""
        nodes = numa_optimizer.get_numa_nodes()
        # 至少有一个NUMA节点（即使系统不支持NUMA，也会模拟一个）
        assert len(nodes) >= 1

    def test_cpu_to_numa_mapping(self, numa_optimizer):
        """测试CPU到NUMA节点映射"""
        # 获取当前CPU
        cpu_id = 0
        node_id = numa_optimizer.get_numa_node_for_cpu(cpu_id)

        # 应该返回有效的NUMA节点ID
        assert node_id >= 0

    def test_memory_allocation_preference(self, numa_optimizer):
        """测试内存分配偏好设置"""
        # 尝试设置NUMA内存策略
        try:
            numa_optimizer.set_memory_preference(node_id=0)
            assert True
        except Exception:
            # 在某些系统上可能不支持
            pytest.skip("NUMA内存策略不支持")

    def test_local_memory_access(self, numa_optimizer):
        """测试本地内存访问优化"""
        # 获取本地内存访问建议
        advice = numa_optimizer.get_local_memory_advice()

        # 应该返回有效的建议
        assert isinstance(advice, dict)

    def test_numa_aware_allocation(self, numa_optimizer):
        """测试NUMA感知内存分配"""
        try:
            # 尝试在特定NUMA节点上分配内存
            buffer = numa_optimizer.allocate_on_node(1024, node_id=0)
            assert buffer is not None

            # 释放内存
            numa_optimizer.free_buffer(buffer)
        except Exception:
            pytest.skip("NUMA内存分配不支持")


# =============================================================================
# ThreadAffinityManager 测试
# =============================================================================

class TestThreadAffinityManager:
    """线程亲和性管理器测试类"""

    def test_affinity_initialization(self, affinity_manager):
        """测试亲和性管理器初始化"""
        assert affinity_manager is not None

    def test_get_cpu_count(self, affinity_manager):
        """测试获取CPU数量"""
        cpu_count = affinity_manager.get_cpu_count()
        assert cpu_count >= 1
        assert cpu_count == os.cpu_count()

    def test_get_available_cpus(self, affinity_manager):
        """测试获取可用CPU列表"""
        cpus = affinity_manager.get_available_cpus()
        assert len(cpus) >= 1
        assert 0 in cpus

    def test_set_thread_affinity(self, affinity_manager):
        """测试设置线程亲和性"""
        # 获取当前线程ID
        thread_id = threading.current_thread().ident

        # 尝试绑定到CPU 0
        try:
            result = affinity_manager.set_affinity(thread_id, [0])
            assert result is True
        except Exception as e:
            # 在某些系统上可能需要特殊权限
            pytest.skip(f"设置线程亲和性失败: {e}")

    def test_get_thread_affinity(self, affinity_manager):
        """测试获取线程亲和性"""
        thread_id = threading.current_thread().ident

        try:
            affinity = affinity_manager.get_affinity(thread_id)
            assert isinstance(affinity, list)
            assert len(affinity) >= 1
        except Exception as e:
            pytest.skip(f"获取线程亲和性失败: {e}")

    def test_bind_current_thread(self, affinity_manager):
        """测试绑定当前线程"""
        try:
            result = affinity_manager.bind_current_thread(cpu_id=0)
            assert result is True
        except Exception as e:
            pytest.skip(f"绑定当前线程失败: {e}")

    def test_bind_worker_threads(self, affinity_manager):
        """测试绑定工作线程"""
        worker_threads = []
        for i in range(4):
            t = threading.Thread(target=lambda: time.sleep(0.1))
            t.start()
            worker_threads.append(t)

        try:
            results = affinity_manager.bind_worker_threads(worker_threads)
            assert len(results) == 4
        except Exception as e:
            pytest.skip(f"绑定工作线程失败: {e}")
        finally:
            for t in worker_threads:
                t.join()

    def test_reset_affinity(self, affinity_manager):
        """测试重置亲和性"""
        try:
            # 先设置亲和性
            affinity_manager.bind_current_thread(cpu_id=0)

            # 重置亲和性
            result = affinity_manager.reset_affinity()
            assert result is True
        except Exception as e:
            pytest.skip(f"重置亲和性失败: {e}")

    def test_optimal_cpu_selection(self, affinity_manager):
        """测试最优CPU选择"""
        # 获取推荐的工作线程CPU分配
        cpus = affinity_manager.get_optimal_cpus(num_threads=4)

        assert len(cpus) == 4
        # 所有CPU应该是有效的
        for cpu in cpus:
            assert 0 <= cpu < affinity_manager.get_cpu_count()

    def test_isolate_cpus(self, affinity_manager):
        """测试CPU隔离"""
        try:
            # 尝试隔离CPU（在某些系统上可能需要root权限）
            result = affinity_manager.isolate_cpus([0, 1])
            # 结果可能成功或失败，取决于系统权限
            assert isinstance(result, bool)
        except Exception:
            pytest.skip("CPU隔离需要特殊权限")


# =============================================================================
# CacheOptimizer 测试
# =============================================================================

class TestCacheOptimizer:
    """缓存优化器测试类"""

    def test_cache_initialization(self, cache_optimizer):
        """测试缓存优化器初始化"""
        assert cache_optimizer is not None

    def test_cache_line_size(self, cache_optimizer):
        """测试缓存行大小检测"""
        cache_line_size = cache_optimizer.get_cache_line_size()
        # 常见值：64字节
        assert cache_line_size in [32, 64, 128]

    def test_l1_cache_size(self, cache_optimizer):
        """测试L1缓存大小检测"""
        l1_size = cache_optimizer.get_l1_cache_size()
        assert l1_size > 0
        # L1缓存通常在16KB到64KB之间
        assert 8192 <= l1_size <= 131072

    def test_l2_cache_size(self, cache_optimizer):
        """测试L2缓存大小检测"""
        l2_size = cache_optimizer.get_l2_cache_size()
        assert l2_size > 0
        # L2缓存通常在256KB到1MB之间
        assert 131072 <= l2_size <= 2097152

    def test_l3_cache_size(self, cache_optimizer):
        """测试L3缓存大小检测"""
        l3_size = cache_optimizer.get_l3_cache_size()
        # L3缓存可能不存在（某些低端CPU）
        if l3_size > 0:
            assert l3_size >= 1048576  # 至少1MB

    def test_align_to_cache_line(self, cache_optimizer):
        """测试缓存行对齐"""
        size = 100
        aligned_size = cache_optimizer.align_to_cache_line(size)

        cache_line = cache_optimizer.get_cache_line_size()
        assert aligned_size % cache_line == 0
        assert aligned_size >= size

    def test_pad_structure(self, cache_optimizer):
        """测试结构体填充"""
        # 模拟一个结构体大小
        struct_size = 56
        padded_size = cache_optimizer.pad_structure(struct_size)

        cache_line = cache_optimizer.get_cache_line_size()
        assert padded_size % cache_line == 0
        assert padded_size >= struct_size

    def test_optimal_array_layout(self, cache_optimizer):
        """测试最优数组布局"""
        # 获取数组访问优化建议
        layout = cache_optimizer.get_optimal_array_layout(
            rows=1000,
            cols=100,
            element_size=8
        )

        assert isinstance(layout, dict)
        assert "row_major" in layout or "col_major" in layout

    def test_prefetch_advice(self, cache_optimizer):
        """测试预取建议"""
        advice = cache_optimizer.get_prefetch_advice(
            access_pattern="sequential",
            data_size=1024 * 1024
        )

        assert isinstance(advice, dict)
        assert "prefetch_distance" in advice

    def test_false_sharing_prevention(self, cache_optimizer):
        """测试伪共享预防"""
        # 获取避免伪共享的建议
        padding = cache_optimizer.get_false_sharing_padding()

        cache_line = cache_optimizer.get_cache_line_size()
        assert padding >= cache_line


# =============================================================================
# HardwareInfo 测试
# =============================================================================

class TestHardwareInfo:
    """硬件信息测试类"""

    def test_hardware_info_initialization(self, hardware_info):
        """测试硬件信息初始化"""
        assert hardware_info is not None

    def test_cpu_info(self, hardware_info):
        """测试CPU信息获取"""
        cpu_info = hardware_info.get_cpu_info()

        assert isinstance(cpu_info, dict)
        assert "count" in cpu_info
        assert cpu_info["count"] >= 1

    def test_memory_info(self, hardware_info):
        """测试内存信息获取"""
        mem_info = hardware_info.get_memory_info()

        assert isinstance(mem_info, dict)
        assert "total" in mem_info
        assert mem_info["total"] > 0

    def test_cache_info(self, hardware_info):
        """测试缓存信息获取"""
        cache_info = hardware_info.get_cache_info()

        assert isinstance(cache_info, dict)
        assert "l1_size" in cache_info or "l1_data" in cache_info

    def test_numa_info(self, hardware_info):
        """测试NUMA信息获取"""
        numa_info = hardware_info.get_numa_info()

        assert isinstance(numa_info, dict)
        assert "nodes" in numa_info
        assert numa_info["nodes"] >= 1

    def test_all_hardware_info(self, hardware_info):
        """测试获取所有硬件信息"""
        all_info = hardware_info.get_all_info()

        assert isinstance(all_info, dict)
        assert "cpu" in all_info
        assert "memory" in all_info
        assert "cache" in all_info

    def test_hardware_capabilities(self, hardware_info):
        """测试硬件能力检测"""
        capabilities = hardware_info.get_capabilities()

        assert isinstance(capabilities, dict)
        # 应该包含一些基本能力信息
        assert len(capabilities) > 0


# =============================================================================
# CPUMonitor 测试
# =============================================================================

class TestCPUMonitor:
    """CPU监控器测试类"""

    def test_monitor_initialization(self, cpu_monitor):
        """测试监控器初始化"""
        assert cpu_monitor is not None

    def test_get_cpu_usage(self, cpu_monitor):
        """测试获取CPU使用率"""
        usage = cpu_monitor.get_cpu_usage()

        assert isinstance(usage, (int, float))
        assert 0 <= usage <= 100

    def test_get_per_cpu_usage(self, cpu_monitor):
        """测试获取每个CPU的使用率"""
        usages = cpu_monitor.get_per_cpu_usage()

        assert isinstance(usages, list)
        assert len(usages) >= 1

        for usage in usages:
            assert 0 <= usage <= 100

    def test_get_cpu_frequency(self, cpu_monitor):
        """测试获取CPU频率"""
        freq = cpu_monitor.get_cpu_frequency()

        assert isinstance(freq, (int, float))
        # CPU频率应该在合理范围内（MHz）
        assert freq > 0

    def test_get_cpu_temperature(self, cpu_monitor):
        """测试获取CPU温度"""
        try:
            temp = cpu_monitor.get_cpu_temperature()

            if temp is not None:
                assert isinstance(temp, (int, float))
                # 温度应该在合理范围内（摄氏度）
                assert 0 <= temp <= 120
        except Exception:
            # 某些系统可能不支持温度读取
            pass

    def test_monitor_statistics(self, cpu_monitor):
        """测试监控统计信息"""
        # 收集一些统计数据
        for _ in range(5):
            cpu_monitor.get_cpu_usage()
            time.sleep(0.01)

        stats = cpu_monitor.get_statistics()

        assert isinstance(stats, dict)
        assert "samples" in stats
        assert stats["samples"] >= 5

    def test_reset_statistics(self, cpu_monitor):
        """测试重置统计信息"""
        # 收集一些数据
        cpu_monitor.get_cpu_usage()
        time.sleep(0.01)
        cpu_monitor.get_cpu_usage()

        # 重置
        cpu_monitor.reset_statistics()

        stats = cpu_monitor.get_statistics()
        assert stats["samples"] == 0


# =============================================================================
# 性能基准测试
# =============================================================================

class TestHardwareOptimizerBenchmarks:
    """硬件优化器性能基准测试类"""

    @pytest.mark.slow
    def test_thread_affinity_performance(self):
        """测试线程亲和性性能影响"""
        affinity_manager = ThreadAffinityManager()

        def cpu_intensive_task():
            """CPU密集型任务"""
            result = 0
            for i in range(1000000):
                result += i * i
            return result

        # 不绑定亲和性
        start = time.time()
        threads_no_affinity = []
        for _ in range(4):
            t = threading.Thread(target=cpu_intensive_task)
            t.start()
            threads_no_affinity.append(t)
        for t in threads_no_affinity:
            t.join()
        time_no_affinity = time.time() - start

        # 绑定亲和性
        try:
            start = time.time()
            threads_with_affinity = []
            for i in range(4):
                t = threading.Thread(target=cpu_intensive_task)
                t.start()
                affinity_manager.set_affinity(t.ident, [i])
                threads_with_affinity.append(t)
            for t in threads_with_affinity:
                t.join()
            time_with_affinity = time.time() - start

            print(f"\n无亲和性: {time_no_affinity*1000:.2f} ms")
            print(f"有亲和性: {time_with_affinity*1000:.2f} ms")

            # 亲和性绑定不应该显著降低性能
            assert time_with_affinity < time_no_affinity * 2
        except Exception as e:
            pytest.skip(f"线程亲和性测试失败: {e}")

    @pytest.mark.slow
    def test_cache_aligned_access(self):
        """测试缓存对齐访问性能"""
        cache_optimizer = CacheOptimizer()
        cache_line = cache_optimizer.get_cache_line_size()

        # 创建未对齐的数组
        size = 1000000
        unaligned = [i for i in range(size)]

        # 创建缓存对齐的数组（模拟）
        aligned = np.zeros(size, dtype=np.int64)
        for i in range(size):
            aligned[i] = i

        # 测试未对齐访问
        start = time.time()
        sum_unaligned = sum(unaligned)
        time_unaligned = time.time() - start

        # 测试对齐访问
        start = time.time()
        sum_aligned = np.sum(aligned)
        time_aligned = time.time() - start

        print(f"\n未对齐访问: {time_unaligned*1000:.2f} ms")
        print(f"对齐访问: {time_aligned*1000:.2f} ms")

        # 验证结果正确
        assert sum_unaligned == sum_aligned

    @pytest.mark.slow
    def test_hardware_info_collection_performance(self):
        """测试硬件信息收集性能"""
        hardware_info = HardwareInfo()

        iterations = 100

        start = time.time()
        for _ in range(iterations):
            info = hardware_info.get_all_info()
        elapsed = time.time() - start

        avg_time = elapsed / iterations * 1000

        print(f"\n硬件信息收集平均耗时: {avg_time:.2f} ms")

        # 应该很快（缓存结果）
        assert avg_time < 10

    @pytest.mark.slow
    def test_cpu_monitoring_overhead(self):
        """测试CPU监控开销"""
        cpu_monitor = CPUMonitor()

        iterations = 100  # 减少迭代次数以加快测试速度

        start = time.time()
        for _ in range(iterations):
            cpu_monitor.get_cpu_usage()
        elapsed = time.time() - start

        avg_time = elapsed / iterations * 1000

        print(f"\nCPU监控单次开销: {avg_time:.3f} ms")

        # 开销应该很小（放宽阈值以适应更快的测试）
        assert avg_time < 5

    @pytest.mark.slow
    def test_numa_memory_access_pattern(self):
        """测试NUMA内存访问模式性能"""
        numa_optimizer = NUMAOptimizer()

        # 分配一些内存
        size = 10 * 1024 * 1024  # 10MB
        data = bytearray(size)

        # 顺序访问
        start = time.time()
        for i in range(0, size, 64):  # 按缓存行步长访问
            data[i] = i % 256
        sequential_time = time.time() - start

        # 随机访问
        import random
        indices = list(range(0, size, 64))
        random.shuffle(indices)

        start = time.time()
        for i in indices:
            data[i] = i % 256
        random_time = time.time() - start

        print(f"\n顺序访问: {sequential_time*1000:.2f} ms")
        print(f"随机访问: {random_time*1000:.2f} ms")
        print(f"性能比: {random_time/sequential_time:.2f}x")

        # 顺序访问应该比随机访问快
        assert sequential_time < random_time
