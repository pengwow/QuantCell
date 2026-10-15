"""桌面 sidecar 数据目录环境变量覆盖的单测。"""

import pytest


def test_get_data_dir_env_override(monkeypatch, tmp_path):
    from utils import get_data_dir, get_source_data_dir

    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))
    assert get_data_dir() == tmp_path
    assert get_source_data_dir() == tmp_path / "source"


def test_get_data_dir_default_unaffected(monkeypatch):
    from utils import get_backend_root, get_data_dir

    monkeypatch.delenv("QUANTCELL_DATA_DIR", raising=False)
    assert get_data_dir() == get_backend_root() / "data"


def test_database_default_path_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))
    from collector.db import database

    # 函数级验证路径解析逻辑。不要 importlib.reload(collector.db.database)：
    # reload 会重新执行 Base = declarative_base()，把全局 Base 单例换成新对象，
    # 而先于本测试 import 的模型模块（worker.models 等）仍注册在旧 Base 上，
    # 导致同进程后续测试 create_all 缺表 / relationship 跨 registry 解析失败。
    assert database._default_db_path() == tmp_path


def test_credentials_default_db_path_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))
    from credentials import service

    assert service._default_db_path() == str(tmp_path / "credentials.db")
