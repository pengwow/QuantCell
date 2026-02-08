==================================================================== short test summary info ====================================================================
FAILED tests/unit/test_async_event_engine.py::TestAsyncEventEngine::test_wait_for_completion - assert 0 == 1
 +  where 0 = len([])
FAILED tests/unit/test_async_event_engine.py::TestAsyncEventEngine::test_async_backpressure - assert 7.319450378417969e-05 >= 0.1
FAILED tests/unit/test_async_event_engine.py::TestAsyncPerformanceBenchmarks::test_async_throughput_benchmark - TimeoutError
FAILED tests/unit/test_batching_engine.py::TestBatchingEngine::test_batch_time_trigger - AssertionError: assert 5 == 2
 +  where 5 = len('data1')
FAILED tests/unit/test_batching_engine.py::TestBatchingEngine::test_multiple_handlers - AssertionError: assert 1 == 2
 +  where 1 = len([('handler2', 4)])
FAILED tests/unit/test_batching_engine.py::TestBatchingEngine::test_batch_contents - AssertionError: assert 2 == 3
 +  where 2 = len({'id': 0, 'value': 'data0'})
FAILED tests/unit/test_batching_engine.py::TestBatchingEngine::test_metrics_collection - KeyError: 'total_events'
FAILED tests/unit/test_batching_engine.py::TestBatchingEngine::test_get_all_handlers - TypeError: object of type 'function' has no len()
FAILED tests/unit/test_batching_engine.py::TestBatchStrategy::test_should_flush_by_size - TypeError: '>=' not supported between instances of 'EventBatch' and 'int'
FAILED tests/unit/test_batching_engine.py::TestBatchStrategy::test_should_flush_by_time - TypeError: '>=' not supported between instances of 'EventBatch' and 'int'
FAILED tests/unit/test_batching_engine.py::TestBatchStrategy::test_should_flush_empty_batch - TypeError: '>=' not supported between instances of 'EventBatch' and 'int'
FAILED tests/unit/test_batching_engine.py::TestBatchStrategy::test_strategy_reset_timer - TypeError: '>=' not supported between instances of 'EventBatch' and 'int'
FAILED tests/unit/test_batching_engine.py::TestVectorizedBatchProcessor::test_process_prices - TypeError: float() argument must be a string or a real number, not 'dict'
FAILED tests/unit/test_batching_engine.py::TestVectorizedBatchProcessor::test_process_empty_batch - KeyError: 'count'
FAILED tests/unit/test_batching_engine.py::TestVectorizedBatchProcessor::test_process_indicators - assert np.float64(101.99999999999999) == 101.0 ± 1.0e-04
  
  comparison failed
  Obtained: 101.99999999999999
  Expected: 101.0 ± 1.0e-04
FAILED tests/unit/test_batching_engine.py::TestBatchMetrics::test_metrics_initialization - KeyError: 'total_events'
FAILED tests/unit/test_batching_engine.py::TestBatchMetrics::test_metrics_record_batch - AttributeError: 'BatchingMetrics' object has no attribute 'record_batch'
FAILED tests/unit/test_batching_engine.py::TestBatchMetrics::test_metrics_record_event - AttributeError: 'BatchingMetrics' object has no attribute 'record_event'
FAILED tests/unit/test_batching_engine.py::TestBatchMetrics::test_metrics_record_error - AttributeError: 'BatchingMetrics' object has no attribute 'record_error'
FAILED tests/unit/test_batching_engine.py::TestBatchMetrics::test_metrics_thread_safety - KeyError: 'total_batches'
FAILED tests/unit/test_batching_engine.py::TestBatchMetrics::test_metrics_reset - AttributeError: 'BatchingMetrics' object has no attribute 'record_batch'
FAILED tests/unit/test_batching_engine.py::TestBatchingPerformanceBenchmarks::test_batching_throughput_benchmark - assert 78890 == 10000
FAILED tests/unit/test_batching_engine.py::TestBatchingPerformanceBenchmarks::test_vectorized_processing_benchmark - TypeError: float() argument must be a string or a real number, not 'dict'
FAILED tests/unit/test_batching_engine.py::TestBatchingPerformanceBenchmarks::test_latency_vs_batch_size - assert 0 > 0
 +  where 0 = len({})
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentEventEngine::test_basic_concurrent_event_processing - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentEventEngine::test_symbol_based_routing - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentEventEngine::test_concurrent_processing - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentEventEngine::test_shard_isolation - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentEventEngine::test_metrics_collection - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentEventEngine::test_handler_exception_isolation - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentEventEngine::test_unregister_handler - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentEventEngine::test_clear_handlers - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentEventEngine::test_put_without_symbol - TypeError: ConcurrentEventEngine.put() missing 1 required positional argument: 'data'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentEventEngine::test_queue_size_per_shard - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestSymbolShard::test_shard_initialization - AttributeError: 'SymbolShard' object has no attribute 'running'. Did you mean: '_running'?
FAILED tests/unit/test_concurrent_event_engine.py::TestSymbolShard::test_shard_start_stop - AttributeError: 'SymbolShard' object has no attribute 'running'. Did you mean: '_running'?
FAILED tests/unit/test_concurrent_event_engine.py::TestSymbolShard::test_shard_put_event - AttributeError: 'SymbolShard' object has no attribute 'register'
FAILED tests/unit/test_concurrent_event_engine.py::TestShardRouter::test_none_symbol - AttributeError: 'NoneType' object has no attribute 'encode'
FAILED tests/unit/test_concurrent_event_engine.py::TestSymbolEvent::test_event_default_priority - AssertionError: assert 2 == 0
 +  where 2 = SymbolEvent(event_type='TICK', symbol='BTCUSDT', data={'price': 50000}, priority=2, timestamp=1770567355.454452).priority
FAILED tests/unit/test_concurrent_event_engine.py::TestSymbolEvent::test_event_comparison - TypeError: '<' not supported between instances of 'SymbolEvent' and 'SymbolEvent'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentPerformanceBenchmarks::test_concurrent_throughput_benchmark - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentPerformanceBenchmarks::test_shard_load_balance_benchmark - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_concurrent_event_engine.py::TestConcurrentPerformanceBenchmarks::test_symbol_ordering_guarantee - TypeError: ConcurrentEventEngine.put() got multiple values for argument 'symbol'
FAILED tests/unit/test_event_engine_optimized.py::TestOptimizedEventEngine::test_multi_worker_parallel_processing - AssertionError: 并行处理应该更快，实际耗时0.5051438808441162秒
assert 0.5051438808441162 < 0.15
FAILED tests/unit/test_event_engine_optimized.py::TestOptimizedEventEngine::test_unregister_handler - assert False == True
FAILED tests/unit/test_event_engine_optimized.py::TestOptimizedEventEngine::test_blocking_put_with_timeout - assert 8.20159912109375e-05 >= 0.1
FAILED tests/unit/test_hardware_optimizer.py::TestNUMAOptimizer::test_numa_node_detection - AttributeError: 'NUMAOptimizer' object has no attribute 'get_numa_nodes'. Did you mean: 'get_numa_node'?
FAILED tests/unit/test_hardware_optimizer.py::TestNUMAOptimizer::test_cpu_to_numa_mapping - AttributeError: 'NUMAOptimizer' object has no attribute 'get_numa_node_for_cpu'
FAILED tests/unit/test_hardware_optimizer.py::TestNUMAOptimizer::test_local_memory_access - AttributeError: 'NUMAOptimizer' object has no attribute 'get_local_memory_advice'
FAILED tests/unit/test_hardware_optimizer.py::TestThreadAffinityManager::test_get_cpu_count - AttributeError: 'ThreadAffinityManager' object has no attribute 'get_cpu_count'
FAILED tests/unit/test_hardware_optimizer.py::TestThreadAffinityManager::test_get_available_cpus - AttributeError: 'ThreadAffinityManager' object has no attribute 'get_available_cpus'
FAILED tests/unit/test_hardware_optimizer.py::TestThreadAffinityManager::test_optimal_cpu_selection - AttributeError: 'ThreadAffinityManager' object has no attribute 'get_optimal_cpus'
FAILED tests/unit/test_hardware_optimizer.py::TestCacheOptimizer::test_cache_line_size - AttributeError: 'CacheOptimizer' object has no attribute 'get_cache_line_size'. Did you mean: 'cache_line_size'?
FAILED tests/unit/test_hardware_optimizer.py::TestCacheOptimizer::test_l1_cache_size - AttributeError: 'CacheOptimizer' object has no attribute 'get_l1_cache_size'
FAILED tests/unit/test_hardware_optimizer.py::TestCacheOptimizer::test_l2_cache_size - AttributeError: 'CacheOptimizer' object has no attribute 'get_l2_cache_size'
FAILED tests/unit/test_hardware_optimizer.py::TestCacheOptimizer::test_l3_cache_size - AttributeError: 'CacheOptimizer' object has no attribute 'get_l3_cache_size'
FAILED tests/unit/test_hardware_optimizer.py::TestCacheOptimizer::test_align_to_cache_line - AttributeError: 'CacheOptimizer' object has no attribute 'get_cache_line_size'. Did you mean: 'cache_line_size'?
FAILED tests/unit/test_hardware_optimizer.py::TestCacheOptimizer::test_pad_structure - AttributeError: 'CacheOptimizer' object has no attribute 'pad_structure'
FAILED tests/unit/test_hardware_optimizer.py::TestCacheOptimizer::test_optimal_array_layout - AttributeError: 'CacheOptimizer' object has no attribute 'get_optimal_array_layout'
FAILED tests/unit/test_hardware_optimizer.py::TestCacheOptimizer::test_prefetch_advice - AttributeError: 'CacheOptimizer' object has no attribute 'get_prefetch_advice'
FAILED tests/unit/test_hardware_optimizer.py::TestCacheOptimizer::test_false_sharing_prevention - AttributeError: 'CacheOptimizer' object has no attribute 'get_false_sharing_padding'
FAILED tests/unit/test_hardware_optimizer.py::TestCPUMonitor::test_monitor_statistics - assert 0 >= 5
FAILED tests/unit/test_hardware_optimizer.py::TestHardwareOptimizerBenchmarks::test_cache_aligned_access - AttributeError: 'CacheOptimizer' object has no attribute 'get_cache_line_size'. Did you mean: 'cache_line_size'?
FAILED tests/unit/test_hardware_optimizer.py::TestHardwareOptimizerBenchmarks::test_cpu_monitoring_overhead - assert 103.07455062866211 < 5
FAILED tests/unit/test_memory_pool.py::TestObjectPool::test_pool_max_size_limit - RuntimeError: 对象池已满，无法获取对象
FAILED tests/unit/test_memory_pool.py::TestTickEvent::test_tick_event_memory_efficiency - AssertionError: assert not True
 +  where True = hasattr(TickEvent(BTCUSDT, 50000.0, 1.0), '__dict__')
FAILED tests/unit/test_memory_pool.py::TestTickEvent::test_tick_event_comparison - assert TickEvent(BTCUSDT, 50000.0, 1.0) == TickEvent(BTCUSDT, 50000.0, 1.0)
FAILED tests/unit/test_memory_pool.py::TestBarEvent::test_bar_event_from_dict - KeyError: 'interval'
FAILED tests/unit/test_memory_pool.py::TestBarEvent::test_bar_event_memory_efficiency - AssertionError: assert not True
 +  where True = hasattr(<strategy.core.memory_pool.BarEvent object at 0x11aaad6d0>, '__dict__')
FAILED tests/unit/test_memory_pool.py::TestBarEvent::test_bar_event_typical_price - AttributeError: 'BarEvent' object has no attribute 'typical_price'
FAILED tests/unit/test_memory_pool.py::TestBarEvent::test_bar_event_price_range - AttributeError: 'BarEvent' object has no attribute 'price_range'
FAILED tests/unit/test_memory_pool.py::TestSharedMemoryMarketData::test_write_and_read_tick - TypeError: SharedMemoryMarketData.write_tick() missing 3 required positional arguments: 'price', 'volume', and 'timestamp'
FAILED tests/unit/test_memory_pool.py::TestSharedMemoryMarketData::test_write_and_read_bar - AttributeError: 'SharedMemoryMarketData' object has no attribute 'write_bar'
FAILED tests/unit/test_memory_pool.py::TestSharedMemoryMarketData::test_multiple_symbols - TypeError: SharedMemoryMarketData.write_tick() missing 3 required positional arguments: 'price', 'volume', and 'timestamp'
FAILED tests/unit/test_memory_pool.py::TestSharedMemoryMarketData::test_update_existing_symbol - TypeError: SharedMemoryMarketData.write_tick() missing 3 required positional arguments: 'price', 'volume', and 'timestamp'
FAILED tests/unit/test_memory_pool.py::TestSharedMemoryMarketData::test_get_all_symbols - TypeError: SharedMemoryMarketData.write_tick() missing 3 required positional arguments: 'price', 'volume', and 'timestamp'
FAILED tests/unit/test_memory_pool.py::TestSharedMemoryMarketData::test_clear_symbol - TypeError: SharedMemoryMarketData.write_tick() missing 3 required positional arguments: 'price', 'volume', and 'timestamp'
FAILED tests/unit/test_memory_pool.py::TestSharedMemoryMarketData::test_clear_all - TypeError: SharedMemoryMarketData.write_tick() missing 3 required positional arguments: 'price', 'volume', and 'timestamp'
FAILED tests/unit/test_memory_pool.py::TestPreallocatedBuffers::test_buffers_initialization - AttributeError: 'PreallocatedBuffers' object has no attribute 'buffer_sizes'
FAILED tests/unit/test_memory_pool.py::TestPreallocatedBuffers::test_buffer_statistics - AttributeError: 'PreallocatedBuffers' object has no attribute 'get_stats'
FAILED tests/unit/test_memory_pool.py::TestMemoryPoolPerformanceBenchmarks::test_object_pool_vs_allocation - assert 0.02764272689819336 < 0.003084897994995117
FAILED tests/unit/test_memory_pool.py::TestMemoryPoolPerformanceBenchmarks::test_tick_event_memory_usage - assert 104 < 100
FAILED tests/unit/test_memory_pool.py::TestMemoryPoolPerformanceBenchmarks::test_shared_memory_throughput - TypeError: SharedMemoryMarketData.write_tick() missing 3 required positional arguments: 'price', 'volume', and 'timestamp'