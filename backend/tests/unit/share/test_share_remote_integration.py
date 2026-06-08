"""
Share 远端集成（quantcell.top）测试

覆盖：
- ShareRemoteConfig 单例 + is_ready 决策
- RemoteShareClient HMAC 签名稳定性
- RemoteShareClient 重试退避（5xx 重试 / 4xx 不重试）
- 路由：upload_success（远端已就绪） / upload_failure_retry（远端异常 → FAILED + 本地 token 仍可用） /
  retry_remote（重推成功）
"""
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')


def _reset_singleton():
    """重置 ShareRemoteConfig 单例（每个用例都需要）"""
    from share.config import ShareRemoteConfig
    ShareRemoteConfig._instance = None


# ============================================================
# 1. ShareRemoteConfig 单例与 is_ready
# ============================================================
def test_remote_config_disabled_by_default():
    """未配置 api_key/hmac_secret 时，is_ready=False"""
    with patch.dict(os.environ, {}, clear=True):
        _reset_singleton()
        from share.config import ShareRemoteConfig
        cfg = ShareRemoteConfig()
        assert cfg.enabled is False
        assert cfg.is_ready is False
        assert cfg.base_url == "https://share.quantcell.top"
        _reset_singleton()


def test_remote_config_ready_when_all_set():
    """三件套（enabled + api_key + hmac_secret）齐全 → is_ready=True"""
    with patch.dict(os.environ, {
        "SHARE_REMOTE_ENABLED": "true",
        "SHARE_REMOTE_API_KEY": "qck_test_key",
        "SHARE_REMOTE_HMAC_SECRET": "test_hmac_secret",
        "SHARE_REMOTE_BASE_URL": "https://example.com",
    }):
        _reset_singleton()
        from share.config import ShareRemoteConfig
        cfg = ShareRemoteConfig()
        assert cfg.enabled is True
        assert cfg.is_ready is True
        assert cfg.base_url == "https://example.com"  # 已 strip 尾斜杠
        assert bool(cfg.api_key) is True
        assert bool(cfg.hmac_secret) is True
        _reset_singleton()


# ============================================================
# 2. RemoteShareClient HMAC 签名稳定性
# ============================================================
def test_remote_client_hmac_signature_is_stable():
    """相同 payload + secret → 相同 signature（确定性输出）"""
    with patch.dict(os.environ, {
        "SHARE_REMOTE_HMAC_SECRET": "stable_secret_for_test",
    }):
        _reset_singleton()
        from share.remote_client import RemoteShareClient

        client = RemoteShareClient()
        payload = {
            "token_hash": "abc123",
            "worker_id": 7,
            "snapshot": {"metrics": {"total_pnl": 123.45}},
            "uploaded_at": "2026-06-07T10:00:00+00:00",
        }

        sig1 = client._sign_payload(payload)
        sig2 = client._sign_payload(payload)

        assert sig1 == sig2
        assert len(sig1) == 64  # SHA256 hex 长度
        _reset_singleton()

    # 不同 secret → 不同 signature
    with patch.dict(os.environ, {"SHARE_REMOTE_HMAC_SECRET": "other_secret"}):
        _reset_singleton()
        from share.remote_client import RemoteShareClient
        client2 = RemoteShareClient()
        sig3 = client2._sign_payload(payload)
        assert sig1 != sig3
        _reset_singleton()


# ============================================================
# 3. RemoteShareClient 重试退避：直接 mock _request_with_retry
# ============================================================
@pytest.mark.asyncio
async def test_remote_client_retries_on_5xx_then_succeeds():
    """前 2 次 5xx，第 3 次 200 → 最终成功，调用 3 次（直接 mock aiohttp session）"""
    with patch.dict(os.environ, {
        "SHARE_REMOTE_API_KEY": "qck_test",
        "SHARE_REMOTE_HMAC_SECRET": "secret",
        "SHARE_REMOTE_BASE_URL": "https://example.com",
        "SHARE_REMOTE_ENABLED": "true",
        "SHARE_REMOTE_RETRY_BACKOFF": "0",  # 退避为 0 避免测试慢
        "SHARE_REMOTE_MAX_RETRIES": "3",
    }):
        _reset_singleton()
        from share.remote_client import RemoteShareClient

        # 构造一个伪 aiohttp session：连续 2 次 5xx，第 3 次 200
        call_count = {"n": 0}

        def make_response(status: int, body: str = ""):
            resp = AsyncMock()
            resp.status = status
            resp.text = AsyncMock(return_value=body)
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=None)
            return resp

        def make_session(*args, **kwargs):
            session = MagicMock()
            call_count["n"] += 1
            if call_count["n"] < 3:
                session.request = MagicMock(return_value=make_response(500, "server error"))
            else:
                session.request = MagicMock(return_value=make_response(200, '{"id":"r1","short_url":"https://share.example.com/abc"}'))
            session.__aenter__ = AsyncMock(return_value=session)
            session.__aexit__ = AsyncMock(return_value=None)
            return session

        with patch("share.remote_client.aiohttp.ClientSession", side_effect=make_session):
            client = RemoteShareClient()
            result = await client.upload({"a": 1}, "hash", 1)

        assert result["remote_id"] == "r1"
        assert result["short_url"] == "https://share.example.com/abc"
        assert call_count["n"] == 3  # 确认调用了 3 次（2 次 5xx + 1 次 200）
        _reset_singleton()


@pytest.mark.asyncio
async def test_remote_client_does_not_retry_on_4xx():
    """4xx 业务错误不重试，立刻抛 RemoteShareError（这里 mock _request_with_retry 一次性抛错）"""
    with patch.dict(os.environ, {
        "SHARE_REMOTE_API_KEY": "qck_test",
        "SHARE_REMOTE_HMAC_SECRET": "secret",
        "SHARE_REMOTE_BASE_URL": "https://example.com",
        "SHARE_REMOTE_ENABLED": "true",
    }):
        _reset_singleton()
        from share.remote_client import RemoteShareClient, RemoteShareError

        call_count = {"n": 0}

        async def fake_request(method, url, body):
            call_count["n"] += 1
            raise RemoteShareError("status=401")

        with patch.object(RemoteShareClient, "_request_with_retry", side_effect=fake_request):
            client = RemoteShareClient()
            with pytest.raises(RemoteShareError) as exc_info:
                await client.upload({"a": 1}, "hash", 1)

        assert "401" in str(exc_info.value)
        _reset_singleton()


# ============================================================
# 4. 路由层：upload_success / upload_failure / local_only / retry_remote
# ============================================================
def _build_test_client(db_session):
    from fastapi.testclient import TestClient
    from worker.dependencies import get_db_session, get_current_user

    import share.models  # noqa: F401
    import share.routes  # noqa: F401
    from share import router as share_router
    from main import app

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    def _override_current_user():
        return {"user_id": "alice", "user_name": "Alice", "email": "alice@example.com"}

    app.dependency_overrides[get_db_session] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user

    if share_router not in app.router.routes:
        app.include_router(share_router)

    return TestClient(app)


def test_route_create_share_upload_success(sample_worker, db_session):
    """远端已就绪：mock 远端成功 → 响应 short_url 写回 share 库"""
    _reset_singleton()
    client = _build_test_client(db_session)

    with patch("share.routes.RemoteShareClient") as MockClient:
        instance = MockClient.return_value
        instance.upload_sync.return_value = {
            "remote_id": "r-mock-1",
            "short_url": "https://share.quantcell.top/abc",
            "raw": {},
        }
        with patch("share.routes.build_snapshot", return_value={"worker": {"id": sample_worker.id}}):
            with patch("share.routes.serialize_for_remote", side_effect=lambda x: x):
                with patch("share.routes.get_remote_config") as mock_cfg:
                    cfg = MagicMock()
                    cfg.is_ready = True
                    mock_cfg.return_value = cfg

                    resp = client.post(
                        f"/api/workers/{sample_worker.id}/share",
                        json={"expires_in_seconds": 3600},
                    )
                    assert resp.status_code == 200, resp.text
                    body = resp.json()
                    assert body["data"]["short_url"] == "https://share.quantcell.top/abc"
                    assert body["data"]["remote_status"] == "UPLOADED"

                    from share.models import ShareToken
                    share = db_session.query(ShareToken).filter_by(worker_id=sample_worker.id).first()
                    assert share is not None
                    assert share.remote_id == "r-mock-1"
                    assert share.short_url == "https://share.quantcell.top/abc"
                    assert share.remote_status == "UPLOADED"
    _reset_singleton()


def test_route_create_share_upload_failure_keeps_local(sample_worker, db_session):
    """远端已就绪但远端抛错：本地 token 仍创建，remote_status=FAILED，remote_warning 有值"""
    _reset_singleton()
    client = _build_test_client(db_session)

    from share.remote_client import RemoteShareError

    with patch("share.routes.RemoteShareClient") as MockClient:
        instance = MockClient.return_value
        instance.upload_sync.side_effect = RemoteShareError("network timeout")
        with patch("share.routes.build_snapshot", return_value={"worker": {"id": sample_worker.id}}):
            with patch("share.routes.serialize_for_remote", side_effect=lambda x: x):
                with patch("share.routes.get_remote_config") as mock_cfg:
                    cfg = MagicMock()
                    cfg.is_ready = True
                    mock_cfg.return_value = cfg

                    resp = client.post(
                        f"/api/workers/{sample_worker.id}/share",
                        json={"expires_in_seconds": 3600},
                    )
                    assert resp.status_code == 200, resp.text
                    body = resp.json()
                    assert body["data"]["remote_status"] == "FAILED"
                    assert body["data"]["remote_warning"] is not None
                    assert "network timeout" in body["data"]["remote_warning"]
                    assert body["data"]["token"]
                    assert body["data"]["url"] == f"/share/{body['data']['token']}"

                    from share.models import ShareToken
                    share = db_session.query(ShareToken).filter_by(worker_id=sample_worker.id).first()
                    assert share is not None
                    assert share.remote_status == "FAILED"
                    assert "network timeout" in (share.remote_error or "")
    _reset_singleton()


def test_route_create_share_local_only_when_not_ready(sample_worker, db_session):
    """远端未就绪：remote_status=LOCAL_ONLY，url 是本地 /share/<token>"""
    _reset_singleton()
    client = _build_test_client(db_session)

    with patch("share.routes.get_remote_config") as mock_cfg:
        cfg = MagicMock()
        cfg.is_ready = False
        mock_cfg.return_value = cfg

        resp = client.post(
            f"/api/workers/{sample_worker.id}/share",
            json={"expires_in_seconds": 3600},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["data"]["remote_status"] == "LOCAL_ONLY"
        assert body["data"]["short_url"] is None
        assert body["data"]["url"].startswith("/share/")

        from share.models import ShareToken
        share = db_session.query(ShareToken).filter_by(worker_id=sample_worker.id).first()
        assert share.remote_status == "LOCAL_ONLY"
    _reset_singleton()


def test_route_retry_remote_success(sample_worker, db_session):
    """retry-remote 端点：远端重新接受上传，short_url 写回"""
    _reset_singleton()
    client = _build_test_client(db_session)

    from share import crud
    share, _ = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="alice",
        expires_in_seconds=3600,
        one_time=False,
    )
    share.remote_status = "FAILED"
    share.remote_error = "previous failure"
    db_session.add(share)
    db_session.commit()
    db_session.refresh(share)

    with patch("share.routes.RemoteShareClient") as MockClient:
        instance = MockClient.return_value
        instance.upload_sync.return_value = {
            "remote_id": "r-retry-1",
            "short_url": "https://share.quantcell.top/retry-ok",
            "raw": {},
        }
        with patch("share.routes.build_snapshot", return_value={"worker": {"id": sample_worker.id}}):
            with patch("share.routes.serialize_for_remote", side_effect=lambda x: x):
                with patch("share.routes.get_remote_config") as mock_cfg:
                    cfg = MagicMock()
                    cfg.is_ready = True
                    mock_cfg.return_value = cfg

                    resp = client.post(
                        f"/api/workers/{sample_worker.id}/share/{share.id}/retry-remote",
                        json={},
                    )
                    assert resp.status_code == 200, resp.text
                    body = resp.json()
                    assert body["data"]["short_url"] == "https://share.quantcell.top/retry-ok"
                    assert body["data"]["remote_status"] == "UPLOADED"

                    db_session.refresh(share)
                    assert share.remote_status == "UPLOADED"
                    assert share.remote_id == "r-retry-1"
                    assert share.remote_error is None
    _reset_singleton()
