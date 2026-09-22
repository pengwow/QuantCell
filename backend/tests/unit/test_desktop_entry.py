"""desktop_entry 环境变量推导的单测（不启动服务）。"""


def test_build_runtime_env_points_into_data_dir(tmp_path):
    from desktop_entry import build_runtime_env

    env = build_runtime_env(str(tmp_path))

    assert env["QUANTCELL_DATA_DIR"] == str(tmp_path)
    assert env["DB_FILE"] == str(tmp_path / "quantcell_sqlite.db")
    assert env["PORT_CONFIG_PATH"] == str(tmp_path / "port_config.json")
    # Tauri WebView 各平台 origin + Vite dev 端口
    assert "tauri://localhost" in env["CORS_ORIGINS"]
    assert "http://tauri.localhost" in env["CORS_ORIGINS"]
    assert "http://localhost:1420" in env["CORS_ORIGINS"]


def test_build_runtime_env_enables_desktop_local_bypass_and_dev_cors():
    from desktop_entry import build_runtime_env

    env = build_runtime_env("/tmp/whatever")

    # local 模式免登录开关，供 utils.auth._auth_disabled 读取
    assert env["QUANTCELL_DESKTOP_LOCAL"] == "1"
    # M2 dev 时前端 Vite 跑在 5173，需放行（M1 的 1420 保留）
    assert "http://localhost:5173" in env["CORS_ORIGINS"]
    assert "http://127.0.0.1:5173" in env["CORS_ORIGINS"]
