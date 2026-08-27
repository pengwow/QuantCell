"""ZMQ 传输层测试。需要 pyzmq 安装。"""

import pytest

try:
    import zmq

    HAS_ZMQ = True
except ImportError:
    HAS_ZMQ = False

pytestmark = pytest.mark.skipif(not HAS_ZMQ, reason="pyzmq not installed")

from worker.protocol import STATUS_OK, make_command, make_event, make_response
from worker.zmq_transport import OrchestratorZmqTransport, WorkerZmqTransport


class TestWorkerZmqTransport:
    def test_create_worker_transport(self):
        transport = WorkerZmqTransport(worker_id=11)
        assert transport.worker_id == 11
        assert transport.event_push is not None
        assert transport.cmd_dealer is not None
        transport.close()

    def test_worker_send_event(self):
        """Worker 发送事件到 Orchestrator。"""
        orchestrator = OrchestratorZmqTransport()
        worker = WorkerZmqTransport(
            worker_id=11,
            event_pull_addr=orchestrator.event_pull_endpoint,
            cmd_push_addr=orchestrator.cmd_push_endpoint,
        )
        event = make_event(11, "heartbeat", {"pid": 12345})
        worker.send_event(event)
        received = orchestrator.recv_event(timeout_ms=2000)
        assert received is not None
        assert received["worker_id"] == 11
        assert received["event_type"] == "heartbeat"
        worker.close()
        orchestrator.close()

    def test_worker_recv_command(self):
        """Worker 接收 Orchestrator 的命令。"""
        orchestrator = OrchestratorZmqTransport()
        worker = WorkerZmqTransport(
            worker_id=11,
            event_pull_addr=orchestrator.event_pull_endpoint,
            cmd_push_addr=orchestrator.cmd_push_endpoint,
        )
        command = make_command(11, "ping")
        orchestrator.send_command(11, command)
        received = worker.recv_command(timeout_ms=2000)
        assert received is not None
        assert received["cmd"] == "ping"
        worker.close()
        orchestrator.close()

    def test_worker_send_response(self):
        """Worker 发送响应到 Orchestrator。"""
        orchestrator = OrchestratorZmqTransport()
        worker = WorkerZmqTransport(
            worker_id=11,
            event_pull_addr=orchestrator.event_pull_endpoint,
            cmd_push_addr=orchestrator.cmd_push_endpoint,
        )
        command = make_command(11, "ping")
        req_id = command["request_id"]
        orchestrator.send_command(11, command)
        received = worker.recv_command(timeout_ms=2000)
        assert received is not None
        response = make_response(11, req_id, STATUS_OK, {"pong": True})
        worker.send_response(response)
        result = orchestrator.wait_for_response(11, req_id, timeout_ms=2000)
        assert result is not None
        assert result["status"] == "ok"
        worker.close()
        orchestrator.close()


class TestOrchestratorZmqTransport:
    def test_create_orchestrator(self):
        transport = OrchestratorZmqTransport()
        assert transport.event_pull is not None
        assert transport.cmd_router is not None
        transport.close()

    def test_orchestrator_multiple_workers(self):
        """测试多 Worker 连接。"""
        orchestrator = OrchestratorZmqTransport()
        worker1 = WorkerZmqTransport(
            worker_id=1,
            event_pull_addr=orchestrator.event_pull_endpoint,
            cmd_push_addr=orchestrator.cmd_push_endpoint,
        )
        worker2 = WorkerZmqTransport(
            worker_id=2,
            event_pull_addr=orchestrator.event_pull_endpoint,
            cmd_push_addr=orchestrator.cmd_push_endpoint,
        )
        worker1.send_event(make_event(1, "heartbeat", {"pid": 1001}))
        worker2.send_event(make_event(2, "heartbeat", {"pid": 1002}))
        evt1 = orchestrator.recv_event(timeout_ms=2000)
        evt2 = orchestrator.recv_event(timeout_ms=2000)
        worker_ids = {evt1["worker_id"], evt2["worker_id"]}
        assert worker_ids == {1, 2}
        worker1.close()
        worker2.close()
        orchestrator.close()

    def test_orchestrator_command_routing(self):
        """测试命令路由到正确的 Worker。"""
        orchestrator = OrchestratorZmqTransport()
        worker1 = WorkerZmqTransport(
            worker_id=1,
            event_pull_addr=orchestrator.event_pull_endpoint,
            cmd_push_addr=orchestrator.cmd_push_endpoint,
        )
        worker2 = WorkerZmqTransport(
            worker_id=2,
            event_pull_addr=orchestrator.event_pull_endpoint,
            cmd_push_addr=orchestrator.cmd_push_endpoint,
        )
        cmd = make_command(1, "ping")
        orchestrator.send_command(1, cmd)
        r1 = worker1.recv_command(timeout_ms=2000)
        assert r1 is not None
        assert r1["cmd"] == "ping"
        r2 = worker2.recv_command(timeout_ms=500)
        assert r2 is None
        worker1.close()
        worker2.close()
        orchestrator.close()
