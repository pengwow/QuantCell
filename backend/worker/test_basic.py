"""
Worker 模块基础测试

测试 Worker 模块的基本功能
"""

import asyncio
import sys
import os

# 添加 backend 到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker import (
    WorkerState,
    WorkerStatus,
    StateMachine,
    Message,
    MessageType,
    DataSubscription,
)


def test_state_machine():
    """测试状态机"""
    print("测试状态机...")

    # 创建状态机
    sm = StateMachine(WorkerState.INITIALIZING)
    assert sm.current_state == WorkerState.INITIALIZING

    # 测试状态转换
    assert sm.transition_to(WorkerState.INITIALIZED)
    assert sm.current_state == WorkerState.INITIALIZED

    assert sm.transition_to(WorkerState.STARTING)
    assert sm.current_state == WorkerState.STARTING

    assert sm.transition_to(WorkerState.RUNNING)
    assert sm.current_state == WorkerState.RUNNING

    # 测试非法转换
    assert not sm.transition_to(WorkerState.INITIALIZING)  # 不能回到初始状态

    print("✓ 状态机测试通过")


def test_worker_status():
    """测试 Worker 状态"""
    print("测试 Worker 状态...")

    status = WorkerStatus(worker_id="test-worker")
    assert status.worker_id == "test-worker"
    assert status.state == WorkerState.INITIALIZING

    # 测试状态更新（按照正确的状态转换路径）
    assert status.update_state(WorkerState.INITIALIZED)
    assert status.state == WorkerState.INITIALIZED

    assert status.update_state(WorkerState.STARTING)
    assert status.state == WorkerState.STARTING

    assert status.update_state(WorkerState.RUNNING)
    assert status.state == WorkerState.RUNNING
    assert status.started_at is not None

    # 测试心跳
    status.update_heartbeat()
    assert status.last_heartbeat is not None

    # 测试健康检查
    assert status.is_healthy()

    # 测试错误记录
    status.record_error("测试错误")
    assert status.errors_count == 1
    assert status.last_error == "测试错误"

    # 测试字典转换
    data = status.to_dict()
    assert data["worker_id"] == "test-worker"
    assert data["state"] == "running"

    print("✓ Worker 状态测试通过")


def test_message_protocol():
    """测试消息协议"""
    print("测试消息协议...")

    # 创建心跳消息
    msg = Message.create_heartbeat("worker-1", "running")
    assert msg.msg_type == MessageType.HEARTBEAT
    assert msg.worker_id == "worker-1"
    assert msg.payload["status"] == "running"

    # 测试序列化和反序列化
    json_str = msg.to_json()
    msg2 = Message.from_json(json_str)
    assert msg2.msg_type == MessageType.HEARTBEAT
    assert msg2.worker_id == "worker-1"

    # 创建市场数据消息
    market_msg = Message.create_market_data(
        symbol="BTC/USDT",
        data_type="kline",
        data={"open": 50000, "close": 51000},
        source="binance",
    )
    assert market_msg.msg_type == MessageType.MARKET_DATA
    assert market_msg.payload["symbol"] == "BTC/USDT"

    # 创建控制消息
    control_msg = Message.create_control(
        MessageType.STOP,
        "worker-1",
        {"reason": "test"},
    )
    assert control_msg.msg_type == MessageType.STOP
    assert control_msg.payload["reason"] == "test"

    print("✓ 消息协议测试通过")


def test_data_subscription():
    """测试数据订阅"""
    print("测试数据订阅...")

    sub = DataSubscription(worker_id="worker-1")
    assert sub.worker_id == "worker-1"
    assert len(sub.symbols) == 0

    # 添加交易对
    sub.add_symbols(["BTC/USDT", "ETH/USDT"])
    assert "BTC/USDT" in sub.symbols
    assert "ETH/USDT" in sub.symbols

    # 添加数据类型
    sub.add_data_types(["kline", "tick"])
    assert "kline" in sub.data_types
    assert "tick" in sub.data_types

    # 获取主题
    topics = sub.get_topics()
    assert len(topics) == 4  # 2 symbols * 2 data types

    # 移除交易对
    sub.remove_symbols(["BTC/USDT"])
    assert "BTC/USDT" not in sub.symbols

    print("✓ 数据订阅测试通过")


async def test_async_components():
    """测试异步组件"""
    print("测试异步组件...")

    from worker import CommManager

    # 创建通信管理器（不实际启动）
    comm_manager = CommManager(
        host="127.0.0.1",
        data_port=5555,
        control_port=5556,
        status_port=5557,
    )

    assert comm_manager.host == "127.0.0.1"
    assert comm_manager.data_port == 5555

    print("✓ 异步组件测试通过")


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("Worker 模块基础测试")
    print("=" * 50)

    try:
        test_state_machine()
        test_worker_status()
        test_message_protocol()
        test_data_subscription()

        # 运行异步测试
        asyncio.run(test_async_components())

        print("=" * 50)
        print("所有测试通过！")
        print("=" * 50)
        return True

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
