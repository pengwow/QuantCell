"""QUANTCELL_DESKTOP_LOCAL 鉴权豁免三态测试。"""


def test_desktop_local_flag_disables_auth(monkeypatch):
    import utils.auth as auth

    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.setattr(auth, "IS_DEBUG_MODE", False)
    monkeypatch.setenv("QUANTCELL_DESKTOP_LOCAL", "1")

    assert auth._auth_disabled() is True


def test_without_desktop_flag_auth_stays_enabled(monkeypatch):
    import utils.auth as auth

    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("QUANTCELL_DESKTOP_LOCAL", raising=False)
    monkeypatch.setattr(auth, "IS_DEBUG_MODE", False)

    assert auth._auth_disabled() is False


def test_production_env_overrides_desktop_local(monkeypatch):
    import utils.auth as auth

    # 生产环境即使误带开关也必须 fail-closed，不允许豁免
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("QUANTCELL_DESKTOP_LOCAL", "1")

    assert auth._auth_disabled() is False
