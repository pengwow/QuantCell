"""Worker 编排器测试。"""

import time

from worker.orchestrator import WorkerConnectionInfo, WorkerOrchestrator


class TestWorkerConnectionInfo:
    def test_create_info(self):
        info = WorkerConnectionInfo(
            worker_id=11, pid=12345, connected=True, last_heartbeat=time.time(), status="running"
        )
        assert info.is_alive is True

    def test_is_alive_with_old_heartbeat(self):
        info = WorkerConnectionInfo(
            worker_id=11, pid=12345, connected=True, last_heartbeat=time.time() - 120, status="running"
        )
        assert info.is_alive is False

    def test_is_alive_disconnected(self):
        info = WorkerConnectionInfo(
            worker_id=11, pid=12345, connected=False, last_heartbeat=time.time(), status="stopped"
        )
        assert info.is_alive is False


class TestWorkerOrchestrator:
    def setup_method(self):
        WorkerOrchestrator._instance = None

    def teardown_method(self):
        if WorkerOrchestrator._instance:
            WorkerOrchestrator._instance._running = False
            WorkerOrchestrator._instance.cleanup()
            WorkerOrchestrator._instance = None

    def test_singleton(self):
        o1 = WorkerOrchestrator()
        o2 = WorkerOrchestrator()
        assert o1 is o2

    def test_register_worker(self):
        o = WorkerOrchestrator()
        o._register_worker(11, pid=12345)
        assert o.is_connected(11)
        assert o.get_worker_info(11) is not None

    def test_unregister_worker(self):
        o = WorkerOrchestrator()
        o._register_worker(11, pid=12345)
        o._unregister_worker(11)
        assert not o.is_connected(11)

    def test_update_heartbeat(self):
        o = WorkerOrchestrator()
        o._register_worker(11, pid=12345)
        old_time = time.time() - 100
        o._registry[11].last_heartbeat = old_time
        o._update_heartbeat(11)
        assert o._registry[11].last_heartbeat > old_time

    def test_get_disconnected_workers(self):
        o = WorkerOrchestrator()
        o._register_worker(1, pid=100)
        o._register_worker(2, pid=200)
        o._registry[2].last_heartbeat = time.time() - 120
        disconnected = o._get_disconnected_workers()
        assert 2 in disconnected
        assert 1 not in disconnected

    def test_list_connected_workers(self):
        o = WorkerOrchestrator()
        o._register_worker(1, pid=100)
        o._register_worker(2, pid=200)
        o._unregister_worker(1)
        connected = o.list_connected_workers()
        assert len(connected) == 1
        assert connected[0]["worker_id"] == 2

    def test_check_health(self):
        o = WorkerOrchestrator()
        o._register_worker(1, pid=100)
        o._register_worker(2, pid=200)
        o._registry[2].last_heartbeat = time.time() - 120
        summary = o.check_health()
        assert summary["total"] == 2
        assert summary["disconnected"] == 1
        assert 2 in summary["disconnected_ids"]

    def test_check_health_drains_heartbeat_keeps_worker_alive(self):
        """drain 积压心跳后 last_heartbeat 被刷新，空闲 Worker 不再被误判离线。

        回归场景（P2-①）：event_pull 长期无人消费 → 心跳积压 → 60s 误判。
        """
        o = WorkerOrchestrator()

        class _FakeTransport:
            def __init__(self):
                self.queue = [
                    {
                        "type": "event",
                        "worker_id": 11,
                        "event_type": "heartbeat",
                        "payload": {"pid": 12345, "status": "running"},
                    }
                ]

            def recv_event(self, timeout_ms=100):
                return self.queue.pop(0) if self.queue else None

            def close(self, linger=0):
                pass

        o._transport = _FakeTransport()
        o._register_worker(11, pid=12345)
        o._registry[11].last_heartbeat = time.time() - 120  # 已"过期"的心跳
        summary = o.check_health()
        assert summary["disconnected"] == 0  # drain 刷新后不应误判离线
        assert o._registry[11].last_heartbeat > time.time() - 10

    def test_external_events_collected_and_popped(self):
        """order/log 等非心跳事件在 drain 时进入外部队列，可被 pop 提取。"""
        o = WorkerOrchestrator()

        class _FakeTransport:
            def __init__(self):
                self.queue = [
                    {
                        "type": "event",
                        "worker_id": 11,
                        "event_type": "order",
                        "payload": {"symbol": "BTCUSDT"},
                    }
                ]

            def recv_event(self, timeout_ms=100):
                return self.queue.pop(0) if self.queue else None

            def close(self, linger=0):
                pass

        o._transport = _FakeTransport()
        o.check_health()
        events = o.pop_external_events()
        assert len(events) == 1
        wid, etype, payload = events[0]
        assert wid == 11
        assert etype == "order"
        assert payload["symbol"] == "BTCUSDT"
        assert o.pop_external_events() == []  # pop 后清空

    def test_cleanup(self):
        o = WorkerOrchestrator()
        o._register_worker(11, pid=12345)
        o._running = True
        o.cleanup()
        assert o._running is False
        assert len(o._registry) == 0
