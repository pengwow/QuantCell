"""
分享凭据自动生成/落盘/重载测试

覆盖:
- credentials.generate_api_key / generate_hmac_secret 格式正确
- write_credentials_to_local_toml 保留其他字段
- reload_remote_config 清空单例
- is_admin_token_configured 读取 env
- /share/credentials/status 端点
- /share/credentials/generate 端点(仅 remote 路径)
- ensure_remote_credentials 触发远端自动注册
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')


def _reset_singleton():
    from share.config import ShareRemoteConfig
    ShareRemoteConfig._instance = None


# ============================================================
# 1. 密钥生成格式
# ============================================================
def test_generate_api_key_format():
    """返回值以 qck_ 开头、总长 36(4 + 32 hex)"""
    from share.credentials import generate_api_key
    key = generate_api_key()
    assert key.startswith("qck_")
    assert len(key) == 4 + 32
    # 后 32 位必须是 hex
    int(key[4:], 16)


def test_generate_api_key_unique():
    """连续两次调用结果不同(熵足够)"""
    from share.credentials import generate_api_key
    a, b = generate_api_key(), generate_api_key()
    assert a != b


def test_generate_hmac_secret_length():
    """返回值长度 64(32 字节 hex)"""
    from share.credentials import generate_hmac_secret
    secret = generate_hmac_secret()
    assert len(secret) == 64
    int(secret, 16)  # 必须是 hex


# ============================================================
# 2. write_credentials_to_local_toml
# ============================================================
def test_write_credentials_preserves_existing_fields(tmp_path, monkeypatch):
    """预写 [other] 段,凭据写入后 [other] 段仍在"""
    from share import credentials
    from share import config as share_config
    monkeypatch.setattr(share_config, "CONFIG_LOCAL", tmp_path / "config.local.toml")
    # credentials.py 重导出同一对象,需同步 patch
    monkeypatch.setattr(credentials, "CONFIG_LOCAL", tmp_path / "config.local.toml")
    (tmp_path / "config.local.toml").write_text(
        '[other]\nfoo = "bar"\n[share]\nx = 1\n',
        encoding="utf-8",
    )
    credentials.write_credentials_to_local_toml("qck_aaaa", "hhhh")
    import tomli
    data = tomli.loads((tmp_path / "config.local.toml").read_text(encoding="utf-8"))
    assert data["other"]["foo"] == "bar"
    assert data["share"]["x"] == 1
    assert data["share_remote"]["api_key"] == "qck_aaaa"
    assert data["share_remote"]["hmac_secret"] == "hhhh"


def test_write_credentials_creates_file_if_missing(tmp_path, monkeypatch):
    """config.local.toml 不存在时也能写入"""
    from share import credentials
    from share import config as share_config
    target = tmp_path / "config.local.toml"
    monkeypatch.setattr(share_config, "CONFIG_LOCAL", target)
    monkeypatch.setattr(credentials, "CONFIG_LOCAL", target)
    credentials.write_credentials_to_local_toml("qck_bbbb", "ssss")
    assert target.exists()
    import tomli
    data = tomli.loads(target.read_text(encoding="utf-8"))
    assert data["share_remote"]["api_key"] == "qck_bbbb"


def test_write_credentials_overwrites_existing_share_remote(tmp_path, monkeypatch):
    """已存在 [share_remote] 时,新值会覆盖"""
    from share import credentials
    from share import config as share_config
    target = tmp_path / "config.local.toml"
    target.write_text(
        '[share_remote]\nenabled = false\napi_key = "old"\nhmac_secret = "old_secret"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(share_config, "CONFIG_LOCAL", target)
    monkeypatch.setattr(credentials, "CONFIG_LOCAL", target)
    credentials.write_credentials_to_local_toml("qck_new", "new_secret")
    import tomli
    data = tomli.loads(target.read_text(encoding="utf-8"))
    assert data["share_remote"]["api_key"] == "qck_new"
    assert data["share_remote"]["hmac_secret"] == "new_secret"


# ============================================================
# 3. reload_remote_config
# ============================================================
def test_reload_remote_config_clears_singleton():
    """reload 后单例值会从最新 _load_toml_chain 重新加载"""
    from share import credentials
    from share.config import ShareRemoteConfig
    ShareRemoteConfig._instance = None

    # 第一次加载:返回 v1
    with patch(
        "share.config._load_toml_chain",
        return_value={
            "share_remote": {"api_key": "qck_v1", "hmac_secret": "s1"}
        },
    ):
        cfg1 = ShareRemoteConfig()
        assert cfg1.api_key == "qck_v1"
        assert cfg1.hmac_secret == "s1"

    # 改 _load_toml_chain 返回 v2,reload 后单例应反映新值
    with patch(
        "share.config._load_toml_chain",
        return_value={
            "share_remote": {"api_key": "qck_v2", "hmac_secret": "s2"}
        },
    ):
        cfg2 = credentials.reload_remote_config()
        assert cfg2.api_key == "qck_v2"
        assert cfg2.hmac_secret == "s2"


# ============================================================
# 4. is_admin_token_configured
# ============================================================
def test_is_admin_token_configured_true(monkeypatch):
    monkeypatch.setenv("SHARE_REMOTE_ADMIN_TOKEN", "dev-token")
    from share.credentials import is_admin_token_configured
    assert is_admin_token_configured() is True


def test_is_admin_token_configured_false(monkeypatch):
    monkeypatch.delenv("SHARE_REMOTE_ADMIN_TOKEN", raising=False)
    from share.credentials import is_admin_token_configured
    assert is_admin_token_configured() is False


# ============================================================
# 5. /share/credentials/status 端点
# ============================================================
def test_credentials_status_unconfigured(test_client, monkeypatch):
    """无 env 无 toml → ready=false, has_*=false"""
    from share.config import ShareRemoteConfig
    from share import credentials
    from share import config as share_config
    # 使用临时 toml(空)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
        tmp = f.name
    target = Path(tmp)
    monkeypatch.setattr(share_config, "CONFIG_LOCAL", target)
    monkeypatch.setattr(credentials, "CONFIG_LOCAL", target)
    ShareRemoteConfig._instance = None
    with patch.dict(os.environ, {}, clear=True):
        r = test_client.get("/api/share/credentials/status")
        assert r.status_code == 200
        data = r.json().get("data") or r.json()
        assert data["ready"] is False
        assert data["has_api_key"] is False
        assert data["has_hmac_secret"] is False
        assert data["admin_token_configured"] is False
    ShareRemoteConfig._instance = None


def test_credentials_status_ready(test_client, monkeypatch):
    """env 三件套齐全 → ready=true"""
    from share.config import ShareRemoteConfig
    ShareRemoteConfig._instance = None
    with patch.dict(os.environ, {
        "SHARE_REMOTE_API_KEY": "qck_env_key",
        "SHARE_REMOTE_HMAC_SECRET": "env_secret",
    }, clear=True):
        r = test_client.get("/api/share/credentials/status")
        assert r.status_code == 200
        data = r.json().get("data") or r.json()
        assert data["ready"] is True
        assert data["has_api_key"] is True
        assert data["has_hmac_secret"] is True
    ShareRemoteConfig._instance = None


# ============================================================
# 6. /share/credentials/generate 端点
# ============================================================
def test_generate_credentials_remote_path(test_client, monkeypatch, tmp_path):
    """有 admin token + mock 远端 → source=remote,api_key 前缀正确"""
    from share.config import ShareRemoteConfig
    from share import credentials
    from share import config as share_config
    target = tmp_path / "config.local.toml"
    monkeypatch.setattr(share_config, "CONFIG_LOCAL", target)
    monkeypatch.setattr(credentials, "CONFIG_LOCAL", target)
    ShareRemoteConfig._instance = None

    monkeypatch.setenv("SHARE_REMOTE_ADMIN_TOKEN", "dev-admin-token")

    # mock RemoteShareClient.register_device_sync
    from share import remote_client
    mock_result = {
        "id": 1,
        "api_key": "qck_remote_aaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "hmac_secret": "r" * 64,
        "user_id": "alice",
        "created_at": "2026-06-08T00:00:00",
    }
    with patch.object(
        remote_client.RemoteShareClient,
        "register_device_sync",
        return_value=mock_result,
    ):
        r = test_client.post(
            "/api/share/credentials/generate",
            json={"name": "TestPC"},
        )
        assert r.status_code == 200, r.text
        data = r.json().get("data") or r.json()
        assert data["success"] is True
        assert data["source"] == "remote"
        assert data["api_key_prefix"] == "qck_remo…"
        assert data["ready"] is True

    # 凭据已写入(应使用 mock 返回的值,而非 PC 自生成)
    import tomli
    toml_data = tomli.loads(target.read_text(encoding="utf-8"))
    assert toml_data["share_remote"]["api_key"] == "qck_remote_aaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert toml_data["share_remote"]["hmac_secret"] == "r" * 64

    ShareRemoteConfig._instance = None


def test_generate_credentials_no_admin_token_returns_503(test_client, monkeypatch, tmp_path):
    """无 admin token → 503(不再降级本地自生成)"""
    from share.config import ShareRemoteConfig
    from share import credentials
    from share import config as share_config
    target = tmp_path / "config.local.toml"
    monkeypatch.setattr(share_config, "CONFIG_LOCAL", target)
    monkeypatch.setattr(credentials, "CONFIG_LOCAL", target)
    ShareRemoteConfig._instance = None

    with patch.dict(os.environ, {}, clear=True):
        r = test_client.post(
            "/api/share/credentials/generate",
            json={"name": "TestPC"},
        )
        assert r.status_code == 503, r.text
        assert "SHARE_REMOTE_ADMIN_TOKEN" in r.json()["detail"]
        # 不应写入任何凭据
        assert not target.exists()
    ShareRemoteConfig._instance = None


def test_generate_credentials_remote_failure_returns_502(test_client, monkeypatch, tmp_path):
    """有 admin token + 远端抛错 → 502"""
    from share.config import ShareRemoteConfig
    from share import credentials
    from share import config as share_config
    target = tmp_path / "config.local.toml"
    monkeypatch.setattr(share_config, "CONFIG_LOCAL", target)
    monkeypatch.setattr(credentials, "CONFIG_LOCAL", target)
    ShareRemoteConfig._instance = None

    monkeypatch.setenv("SHARE_REMOTE_ADMIN_TOKEN", "dev-admin-token")

    from share import remote_client
    from share.remote_client import RemoteShareError

    with patch.object(
        remote_client.RemoteShareClient,
        "register_device_sync",
        side_effect=RemoteShareError("远端 500"),
    ):
        r = test_client.post(
            "/api/share/credentials/generate",
            json={"name": "TestPC"},
        )
        assert r.status_code == 502, r.text
        assert "远端 500" in r.json()["detail"]
        # 不应写入任何凭据
        assert not target.exists()
    ShareRemoteConfig._instance = None


# ============================================================
# 7. ensure_remote_credentials(create_share 自动调用)
# ============================================================
def test_ensure_remote_credentials_already_ready(monkeypatch):
    """凭据已就绪时,ensure_remote_credentials 不发起远端调用,直接返回"""
    from share.config import ShareRemoteConfig
    from share.credentials import ensure_remote_credentials
    ShareRemoteConfig._instance = None

    with patch.dict(os.environ, {
        "SHARE_REMOTE_API_KEY": "qck_existing",
        "SHARE_REMOTE_HMAC_SECRET": "existing_secret",
    }, clear=True):
        with patch("share.remote_client.RemoteShareClient") as MockClient:
            api_key, hmac = ensure_remote_credentials(name="X", user_id="alice")
            assert api_key == "qck_existing"
            assert hmac == "existing_secret"
            # 未发起远端注册
            MockClient.return_value.register_device_sync.assert_not_called()
    ShareRemoteConfig._instance = None


def test_ensure_remote_credentials_auto_registers_when_not_ready(monkeypatch, tmp_path):
    """凭据未配置 + 有 admin token + 远端注册成功 → 写入 toml + reload + 返回凭据"""
    from share.config import ShareRemoteConfig
    from share.credentials import ensure_remote_credentials
    from share import credentials
    from share import config as share_config
    target = tmp_path / "config.local.toml"
    monkeypatch.setattr(share_config, "CONFIG_LOCAL", target)
    monkeypatch.setattr(credentials, "CONFIG_LOCAL", target)
    ShareRemoteConfig._instance = None

    monkeypatch.setenv("SHARE_REMOTE_ADMIN_TOKEN", "dev-admin-token")

    from share import remote_client
    mock_result = {
        "id": 1,
        "api_key": "qck_auto_registered_aaaaaaaaaaaaaaaaaaaaaa",
        "hmac_secret": "a" * 64,
        "user_id": "alice",
    }
    with patch.object(
        remote_client.RemoteShareClient,
        "register_device_sync",
        return_value=mock_result,
    ):
        api_key, hmac = ensure_remote_credentials(name="TestPC", user_id="alice")
        assert api_key == "qck_auto_registered_aaaaaaaaaaaaaaaaaaaaaa"
        assert hmac == "a" * 64

    # 凭据已落盘
    import tomli
    toml_data = tomli.loads(target.read_text(encoding="utf-8"))
    assert toml_data["share_remote"]["api_key"] == "qck_auto_registered_aaaaaaaaaaaaaaaaaaaaaa"
    assert toml_data["share_remote"]["hmac_secret"] == "a" * 64
    ShareRemoteConfig._instance = None


def test_ensure_remote_credentials_raises_when_no_admin_token(monkeypatch, tmp_path):
    """凭据未配置 + 无 admin token → 抛 RemoteConfigError"""
    from share.config import ShareRemoteConfig
    from share.credentials import RemoteConfigError, ensure_remote_credentials
    from share import credentials
    from share import config as share_config
    target = tmp_path / "config.local.toml"
    monkeypatch.setattr(share_config, "CONFIG_LOCAL", target)
    monkeypatch.setattr(credentials, "CONFIG_LOCAL", target)
    ShareRemoteConfig._instance = None

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RemoteConfigError) as exc_info:
            ensure_remote_credentials()
        assert "SHARE_REMOTE_ADMIN_TOKEN" in str(exc_info.value)
    ShareRemoteConfig._instance = None


def test_ensure_remote_credentials_raises_when_remote_fails(monkeypatch, tmp_path):
    """凭据未配置 + 远端注册抛错 → 抛 RemoteConfigError,不写入 toml"""
    from share.config import ShareRemoteConfig
    from share.credentials import RemoteConfigError, ensure_remote_credentials
    from share import credentials
    from share import config as share_config
    target = tmp_path / "config.local.toml"
    monkeypatch.setattr(share_config, "CONFIG_LOCAL", target)
    monkeypatch.setattr(credentials, "CONFIG_LOCAL", target)
    ShareRemoteConfig._instance = None

    monkeypatch.setenv("SHARE_REMOTE_ADMIN_TOKEN", "dev-admin-token")

    from share import remote_client
    from share.remote_client import RemoteShareError

    with patch.object(
        remote_client.RemoteShareClient,
        "register_device_sync",
        side_effect=RemoteShareError("远端超时"),
    ):
        with pytest.raises(RemoteConfigError) as exc_info:
            ensure_remote_credentials()
        assert "远端超时" in str(exc_info.value)
    # toml 不应被创建
    assert not target.exists()
    ShareRemoteConfig._instance = None
