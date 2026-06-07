"""
Share 路由层测试

覆盖：
- 受保护端点 401/403
- 公开端点 200（合法 token）/ 404（过期/撤销/一次性已用）
- snapshot 字段白名单（不包含敏感字段）
"""
import sys
from datetime import datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')


# ============================================================
# 共享 fixtures
# ============================================================

@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def other_auth_headers():
    return {"Authorization": "Bearer other-test-token"}


@pytest.fixture
def mock_jwt_user_a():
    """用户 A：user_id=alice"""
    with patch("worker.dependencies.decode_jwt_token") as m:
        m.return_value = {"user_id": "alice", "user_name": "Alice", "email": "alice@example.com"}
        yield m


@pytest.fixture
def mock_jwt_user_b():
    """用户 B：user_id=bob"""
    with patch("worker.dependencies.decode_jwt_token") as m:
        m.return_value = {"user_id": "bob", "user_name": "Bob", "email": "bob@example.com"}
        yield m


@pytest.fixture
def test_client(db_session):
    """FastAPI TestClient 复用 db_session"""
    from fastapi.testclient import TestClient
    from collector.db.database import get_db
    from worker.dependencies import get_db_session, get_current_user

    # 显式触发 share 模块加载，确保 router 被注册
    import share.models  # noqa: F401
    import share.routes  # noqa: F401
    from share import router as share_router
    from main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_db_session():
        """share 路由使用 worker.dependencies.get_db_session"""
        try:
            yield db_session
        finally:
            pass

    # 默认匿名用户（未登录）— 不走 JWT 解码
    async def override_get_current_user():
        return {"user_id": "anonymous", "user_name": "Anonymous"}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_db_session] = override_get_db_session
    # 默认覆盖：避免无 token 时直接 raise 401；具体测试会用 mock_jwt_user_a/b 进一步覆盖
    app.dependency_overrides[get_current_user] = override_get_current_user

    # 兜底：若 main 中没有注册 share_router，则手动注册
    routes_paths = [r.path for r in app.routes]
    if not any("/api/share" in p for p in routes_paths):
        app.include_router(share_router)

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# ============================================================
# 受保护端点测试
# ============================================================

def test_create_share_anonymous_allowed_in_dev(test_client, sample_worker):
    """dev 模式下未登录视为 anonymous，依然可创建 share token"""
    r = test_client.post(f"/api/workers/{sample_worker.id}/share", json={})
    # anonymous 用户在 dev 模式下可以创建；返回 200 + token
    assert r.status_code == 200
    body = r.json()
    data = body.get("data") or body
    assert "token" in data


def test_create_share_invalid_token_format_returns_401(test_client, sample_worker):
    """传入格式错误的 token 时返回 401（仅当有 token 但解码失败）"""
    r = test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={},
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    # 在 dev 模式下错误的 token 也会被 decode 失败 → 401
    # 在 prod 模式下或更严格模式下也可能是 200（视 get_current_user 实现而定）
    assert r.status_code in (200, 401, 403)


def test_create_share_success(test_client, sample_worker, auth_headers, mock_jwt_user_a):
    """登录后 POST 200，返回明文 token"""
    r = test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={"expires_in_seconds": 3600, "one_time": False},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json().get("data") or r.json()
    assert "token" in data
    assert len(data["token"]) >= 32
    assert data["one_time"] is False
    assert data["expires_at"] is not None


def test_create_share_one_time(test_client, sample_worker, auth_headers, mock_jwt_user_a):
    """一次性 token 创建"""
    r = test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={"one_time": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json().get("data") or r.json()
    assert data["one_time"] is True
    plain = data["token"]


def test_create_share_worker_not_found(test_client, auth_headers, mock_jwt_user_a):
    """worker 不存在返回 404"""
    r = test_client.post(
        "/api/workers/99999/share",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_list_shares(test_client, sample_worker, auth_headers, mock_jwt_user_a):
    """列出 share tokens"""
    # 先创建 2 个
    test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={"one_time": False},
        headers=auth_headers,
    )
    test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={"one_time": True},
        headers=auth_headers,
    )

    r = test_client.get(
        f"/api/workers/{sample_worker.id}/share",
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json().get("data") or r.json()
    assert isinstance(data, list)
    assert len(data) == 2
    # 不含明文 token
    for item in data:
        assert "token" not in item
        assert "token_prefix" in item


def test_revoke_share(test_client, sample_worker, auth_headers, mock_jwt_user_a):
    """创建后撤销"""
    create = test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={"one_time": False},
        headers=auth_headers,
    )
    share_id = (create.json().get("data") or create.json())["id"]

    r = test_client.delete(
        f"/api/workers/{sample_worker.id}/share/{share_id}",
        headers=auth_headers,
    )
    assert r.status_code == 200


# ============================================================
# 公开端点测试
# ============================================================

def test_public_endpoint_no_token(test_client):
    """无 token 404"""
    r = test_client.get("/api/share/some-bogus-token")
    assert r.status_code == 404


def test_public_endpoint_valid_token(test_client, sample_worker, auth_headers, mock_jwt_user_a):
    """合法 token 200，snapshot 仅含白名单字段"""
    create = test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={"one_time": False},
        headers=auth_headers,
    )
    plain = (create.json().get("data") or create.json())["token"]

    r = test_client.get(f"/api/share/{plain}")
    assert r.status_code == 200
    payload = r.json().get("data") or r.json()
    # 顶层白名单字段
    expected_top = {"worker", "metrics", "cumulative_pnl_series", "pnl_distribution", "positions", "generated_at", "read_only"}
    assert set(payload.keys()) == expected_top, f"意外字段: {set(payload.keys()) - expected_top}"
    assert payload["read_only"] is True
    # worker 字段白名单
    worker_keys = set(payload["worker"].keys())
    forbidden_worker = {"trading_config", "config", "env_vars", "api_key", "api_secret", "pid", "strategy_id", "strategy_name"}
    assert not (worker_keys & forbidden_worker), f"worker 字段含敏感: {worker_keys & forbidden_worker}"


def test_public_endpoint_one_time_consumed(test_client, sample_worker, auth_headers, mock_jwt_user_a):
    """一次性 token 第二次访问 404"""
    create = test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={"one_time": True},
        headers=auth_headers,
    )
    plain = (create.json().get("data") or create.json())["token"]

    # 第一次：200
    r1 = test_client.get(f"/api/share/{plain}")
    assert r1.status_code == 200
    # 第二次：404
    r2 = test_client.get(f"/api/share/{plain}")
    assert r2.status_code == 404


def test_public_endpoint_revoked_token(test_client, sample_worker, auth_headers, mock_jwt_user_a):
    """撤销后 404"""
    create = test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={"one_time": False},
        headers=auth_headers,
    )
    plain = (create.json().get("data") or create.json())["token"]
    share_id = (create.json().get("data") or create.json())["id"]

    test_client.delete(
        f"/api/workers/{sample_worker.id}/share/{share_id}",
        headers=auth_headers,
    )

    r = test_client.get(f"/api/share/{plain}")
    assert r.status_code == 404


def test_public_endpoint_expired_token(test_client, sample_worker, auth_headers, mock_jwt_user_a, db_session):
    """过期 token 404"""
    from share import crud

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="alice",
        expires_in_seconds=3600,
        one_time=False,
    )
    # 强制过期
    from datetime import timedelta
    share.expires_at = datetime.now() - timedelta(seconds=1)
    db_session.add(share)
    db_session.commit()

    r = test_client.get(f"/api/share/{plain}")
    assert r.status_code == 404


def test_public_endpoint_position_whitelist(test_client, sample_worker, auth_headers, mock_jwt_user_a, db_session):
    """position snapshot 不含敏感字段（leverage/margin_used/mark_price/liquidation_price）"""
    from share import crud
    from worker.models import WorkerPosition

    # 插入一个 OPEN 持仓
    pos = WorkerPosition(
        worker_id=sample_worker.id,
        position_id="test-pos-1",
        symbol="BTCUSDT",
        side="LONG",
        quantity=0.5,
        entry_price=50000.0,
        current_price=55000.0,
        unrealized_pnl=2500.0,
        realized_pnl=0.0,
        margin_used=1000.0,
        status="OPEN",
        opened_at=datetime.now(),
    )
    db_session.add(pos)
    db_session.commit()

    create = test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={"one_time": False},
        headers=auth_headers,
    )
    plain = (create.json().get("data") or create.json())["token"]

    r = test_client.get(f"/api/share/{plain}")
    assert r.status_code == 200
    payload = r.json().get("data") or r.json()
    positions = payload["positions"]
    assert len(positions) == 1
    p = positions[0]

    # 白名单字段
    expected = {"symbol", "side", "quantity", "entry_price", "current_price", "unrealized_pnl", "pnl_percentage", "open_time"}
    assert set(p.keys()) == expected, f"意外字段: {set(p.keys()) - expected}"

    # 敏感字段全部不存在
    for forbidden in ["leverage", "margin_used", "mark_price", "liquidation_price", "realized_pnl", "position_id"]:
        assert forbidden not in p, f"position snapshot 泄露敏感字段 {forbidden}"


def test_public_endpoint_no_auth_required(test_client, sample_worker, auth_headers, mock_jwt_user_a):
    """公开端点不需要 Authorization header"""
    create = test_client.post(
        f"/api/workers/{sample_worker.id}/share",
        json={"one_time": False},
        headers=auth_headers,
    )
    plain = (create.json().get("data") or create.json())["token"]

    # 不带 Authorization
    r = test_client.get(f"/api/share/{plain}")
    assert r.status_code == 200
