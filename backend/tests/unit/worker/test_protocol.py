"""ZMQ 消息协议测试。"""

import pytest

from worker.protocol import (
    CMD_PING,
    CMD_START,
    CMD_STATUS,
    CMD_STOP,
    PROTOCOL_SCHEMA_VERSION,
    EventType,
    MessageType,
    decode_message,
    encode_message,
    make_command,
    make_event,
    make_response,
    validate_message,
)


class TestEncodeDecode:
    def test_roundtrip_command(self):
        msg = {
            "type": "command",
            "worker_id": 11,
            "cmd": "ping",
            "params": {},
            "request_id": "req-001",
            "timestamp": 1724745600.0,
        }
        encoded = encode_message(msg)
        decoded = decode_message(encoded)
        assert decoded == msg

    def test_roundtrip_response(self):
        msg = {
            "type": "response",
            "worker_id": 11,
            "request_id": "req-001",
            "status": "ok",
            "data": {"pid": 12345},
            "timestamp": 1724745600.0,
        }
        encoded = encode_message(msg)
        decoded = decode_message(encoded)
        assert decoded == msg

    def test_roundtrip_event(self):
        msg = {
            "type": "event",
            "worker_id": 11,
            "event_type": "trade",
            "payload": {"symbol": "BTCUSDT", "side": "buy", "price": 65000.0},
            "timestamp": 1724745600.0,
        }
        encoded = encode_message(msg)
        decoded = decode_message(encoded)
        assert decoded == msg

    def test_decode_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            decode_message(b"not json")

    def test_decode_non_dict(self):
        with pytest.raises(ValueError, match="Message must be a dict"):
            decode_message(b'"just a string"')


class TestValidation:
    def test_valid_command(self):
        msg = {
            "type": "command",
            "worker_id": 11,
            "cmd": "start",
            "params": {"strategy_name": "dual_ma"},
            "request_id": "req-001",
            "timestamp": 1724745600.0,
        }
        assert validate_message(msg) is None

    def test_missing_type(self):
        msg = {"worker_id": 11, "cmd": "ping"}
        err = validate_message(msg)
        assert err is not None
        assert "type" in err

    def test_command_missing_cmd(self):
        msg = {"type": "command", "worker_id": 11, "params": {}, "request_id": "r", "timestamp": 0}
        err = validate_message(msg)
        assert err is not None
        assert "cmd" in err

    def test_event_missing_event_type(self):
        msg = {"type": "event", "worker_id": 11, "payload": {}, "timestamp": 0}
        err = validate_message(msg)
        assert err is not None
        assert "event_type" in err


class TestSchemaVersion:
    """P2-09 控制面信封 schema_version：组装注入 + 兼容读旧版。"""

    @pytest.mark.parametrize("factory", [make_command, make_response, make_event])
    def test_envelope_carries_version(self, factory):
        args = {"make_command": (11, "ping"), "make_response": (11, "r", "ok"), "make_event": (11, "heartbeat")}[
            factory.__name__
        ]
        assert factory(*args)["schema_version"] == PROTOCOL_SCHEMA_VERSION

    def test_version_0_accepted(self):
        # 旧版消息显式标 0 也放行
        msg = {
            "schema_version": 0,
            "type": "event",
            "worker_id": 11,
            "event_type": "log",
            "payload": {},
            "timestamp": 0,
        }
        assert validate_message(msg) is None

    def test_missing_version_treated_as_v0(self):
        # 存量旧版消息没有该字段 → 向后兼容读
        msg = {"type": "event", "worker_id": 11, "event_type": "log", "payload": {}, "timestamp": 0}
        assert validate_message(msg) is None

    @pytest.mark.parametrize("bad_version", ["1", 1.5, -1, True])
    def test_invalid_version_rejected(self, bad_version):
        msg = {
            "schema_version": bad_version,
            "type": "event",
            "worker_id": 11,
            "event_type": "log",
            "payload": {},
            "timestamp": 0,
        }
        err = validate_message(msg)
        assert err is not None
        assert "schema_version" in err

    def test_future_version_rejected(self):
        msg = {
            "schema_version": PROTOCOL_SCHEMA_VERSION + 1,
            "type": "event",
            "worker_id": 11,
            "event_type": "log",
            "payload": {},
            "timestamp": 0,
        }
        err = validate_message(msg)
        assert err is not None
        assert "Unsupported" in err


class TestFactories:
    def test_make_command(self):
        cmd = make_command(11, "ping")
        assert cmd["type"] == "command"
        assert cmd["worker_id"] == 11
        assert cmd["cmd"] == "ping"
        assert "request_id" in cmd

    def test_make_response(self):
        resp = make_response(11, "req-1", "ok", {"pong": True})
        assert resp["type"] == "response"
        assert resp["request_id"] == "req-1"
        assert resp["status"] == "ok"

    def test_make_event(self):
        evt = make_event(11, "heartbeat", {"pid": 123})
        assert evt["type"] == "event"
        assert evt["event_type"] == "heartbeat"
        assert evt["payload"]["pid"] == 123


class TestConstants:
    def test_command_constants(self):
        assert CMD_PING == "ping"
        assert CMD_START == "start"
        assert CMD_STOP == "stop"
        assert CMD_STATUS == "status"

    def test_message_types(self):
        assert MessageType.COMMAND == "command"
        assert MessageType.RESPONSE == "response"
        assert MessageType.EVENT == "event"

    def test_event_types(self):
        assert EventType.TRADE == "trade"
        assert EventType.HEARTBEAT == "heartbeat"
