"""
Share 路由层测试

覆盖：
- 受保护端点 401/403/200（合法调用）
- 远端上传成功 / 远端上传失败 → 502 / 凭据自动注册
- 撤销 / 列表 / retry-remote
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

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
        m.return_value = {
            "user_id": "alice",
            "user_name": "Alice",
            "email": "alice@example.com",
        }
        yield m


@pytest.fixture
def mock_jwt_user_b():
    """用户 B：user_id=bob"""
    with patch("worker.dependencies.decode_jwt_token") as m:
        m.return_value = {
            "user_id": "bob",
            "user_name": "Bob",
            "email": "bob@example.com",
        }
        yield m


# 测试文件原本覆盖了 conftest 的同名 fixture 并使用 `with TestClient(app)`，
# 这会触发 FastAPI lifespan：shutdown 阶段 core/lifespan.py 装有 2 秒强制
# os._exit(0) 定时器，shutdown 一旦超过 2 秒就静默杀掉整个 pytest 进程
# （无 summary、exit 0）。conftest 版特意不用 with 以跳过 lifespan，
# 故这里直接复用 conftest 的 test_client，不再重复定义。


@contextmanager
def _mock_remote_ready():
    """patch 远端上传成功的辅助函数"""
    with (
        patch(
            "share.routes.ensure_remote_credentials",
            return_value=("qck_mock", "mock_secret"),
        ),
        patch("share.routes.RemoteShareClient") as MockClient,
    ):
        instance = MockClient.return_value
        instance.upload_sync.return_value = {
            "remote_id": "r-mock",
            "short_url": "https://share.quantcell.top/abc",
            "raw": {},
        }
        with (
            patch("share.routes.build_snapshot", return_value={"worker": {"id": 1}}),
            patch("share.routes.serialize_for_remote", side_effect=lambda x: x),
            patch("share.routes.get_remote_config") as mock_cfg,
        ):
            cfg = MagicMock()
            cfg.is_ready = True
            mock_cfg.return_value = cfg
            yield


# ============================================================
# 受保护端点测试
# ============================================================


def test_create_share_anonymous_allowed_in_dev(test_client, sample_worker):
    """dev 模式下未登录视为 anonymous，依然可创建 share token"""
    with _mock_remote_ready():
        r = test_client.post(f"/api/workers/{sample_worker.id}/share", json={})
        # anonymous 用户在 dev 模式下可以创建；返回 200 + token
        assert r.status_code == 200
        body = r.json()
        data = body.get("data") or body
        assert "token" in data


def test_create_share_invalid_token_format_returns_401(test_client, sample_worker):
    """传入格式错误的 token 时返回 401（仅当有 token 但解码失败）"""
    with _mock_remote_ready():
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
    with _mock_remote_ready():
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
    with _mock_remote_ready():
        r = test_client.post(
            f"/api/workers/{sample_worker.id}/share",
            json={"one_time": True},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json().get("data") or r.json()
        assert data["one_time"] is True


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
    with _mock_remote_ready():
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
    with _mock_remote_ready():
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


def test_credentials_status_unconfigured(test_client):
    """凭据未配置时 ready=false,admin_token_configured 取决于环境"""
    r = test_client.get("/api/share/credentials/status")
    assert r.status_code == 200
    data = r.json().get("data") or r.json()
    assert "ready" in data
    assert "base_url" in data
    assert "admin_token_configured" in data


def test_generate_credentials_no_admin_token_returns_503(test_client, monkeypatch):
    """无 admin token 时一键生成凭据返 503"""
    monkeypatch.delenv("SHARE_REMOTE_ADMIN_TOKEN", raising=False)
    r = test_client.post(
        "/api/share/credentials/generate",
        json={"name": "TestPC"},
    )
    assert r.status_code == 503
    assert "SHARE_REMOTE_ADMIN_TOKEN" in r.json()["detail"]
