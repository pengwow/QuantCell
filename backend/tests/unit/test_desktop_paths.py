"""桌面 sidecar 数据目录环境变量覆盖的单测。"""

import importlib

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
    database = importlib.reload(importlib.import_module("collector.db.database"))
    assert database.default_db_path == tmp_path


def test_credentials_default_db_path_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))
    from credentials import service

    assert service._default_db_path() == str(tmp_path / "credentials.db")
