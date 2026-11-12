"""P1-07 工人属地：owner_id 落库与契约测试

覆盖：
- crud.create_worker 将路由层注入的 owner_id 持久化（迁移 34 / create_all 双通道）
- Worker.to_dict 输出 owner_id（前端与后续归属过滤消费）
- WorkerCreate 显式声明 owner_id：extra="forbid" 下服务端注入合法，
  JWT sub 常见的数字字符串经 pydantic lax 模式强转为 int
"""

from worker import crud, schemas


def _worker_payload(**overrides):
    payload = {
        "name": "owner-test",
        "strategy_id": 1,
        "trading_config": {
            "exchange": "binance",
            "symbols_config": {"type": "symbols", "symbols": ["BTCUSDT"]},
            "timeframe": "1h",
            "market_type": "spot",
            "trading_mode": "paper",
        },
    }
    payload.update(overrides)
    return payload


class TestWorkerOwnerId:
    def test_create_persists_owner_id(self, db_session):
        """路由层注入的 owner_id 应完整落库并以 to_dict 输出"""
        worker = crud.create_worker(db_session, schemas.WorkerCreate(**_worker_payload(owner_id=42)))
        db_session.refresh(worker)
        assert worker.owner_id == 42
        assert worker.to_dict()["owner_id"] == 42

    def test_owner_id_defaults_none(self, db_session):
        """未登录/历史数据 owner_id 为 None（无归属，单用户语义不变）"""
        worker = crud.create_worker(db_session, schemas.WorkerCreate(**_worker_payload()))
        db_session.refresh(worker)
        assert worker.owner_id is None
        assert worker.to_dict()["owner_id"] is None

    def test_schema_accepts_numeric_string_sub(self):
        """JWT sub 为数字字符串时 schema lax 强转 int；非数字由路由层 suppress 归 None"""
        data = schemas.WorkerCreate(**_worker_payload(owner_id="7"))
        assert data.owner_id == 7
