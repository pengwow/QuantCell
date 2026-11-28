"""打包升级不丢历史数据的守门测试。

背景：PyInstaller onefile 下 ``__file__`` 位于每次启动重新解压的临时目录，
凡以模块相对路径写入的数据（策略文件、K线源数据、插件、日志、agent 工作区…），
桌面端重启/升级即蒸发。所有持久写入必须落 QUANTCELL_DATA_DIR。

本文件守护三类入口：
1. utils.paths.get_persistent_dir —— env 注入的核心逻辑；
2. 各实例的显式目录属性（strategy_dir / base_dir / plugin_dir …）—— 构造函数里写死的
   Path("xxx") 必须能通过 persistent 重定向；
3. **get_source_data_dir** —— standalone_downloader / backtest provider 等走
   utils.data_utils 里的路径解析，collector 那套 SOURCE_DATA_DIR 已经 persistent 了，
   这里必须对齐否则"回测加载与独立下载写进两个物理目录"。
"""

import os
from pathlib import Path

import pytest

from utils.data_utils import get_source_data_dir
from utils.paths import get_persistent_dir


def test_env_set_redirects_to_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))
    legacy = Path("/legacy/dev/path")
    assert get_persistent_dir("strategies", legacy) == tmp_path / "strategies"
    assert get_persistent_dir("data/source", legacy) == tmp_path / "data" / "source"
    assert get_persistent_dir("", legacy) == tmp_path  # 数据根自身


def test_env_unset_keeps_legacy(monkeypatch):
    monkeypatch.delenv("QUANTCELL_DATA_DIR", raising=False)
    legacy = Path("/legacy/dev/path")
    assert get_persistent_dir("strategies", legacy) == legacy


@pytest.mark.parametrize(
    "ctor,attr",
    [
        pytest.param(
            lambda: __import__("strategy.service", fromlist=["StrategyService"]).StrategyService(),
            "strategy_dir",
            id="strategy-files",
        ),
        pytest.param(
            lambda: __import__("utils.kline_file_manager", fromlist=["KlineFileManager"]).KlineFileManager(),
            "base_dir",
            id="kline-source",
        ),
        pytest.param(
            lambda: __import__("plugins.plugin_manager", fromlist=["PluginManager"]).PluginManager(),
            "plugin_dir",
            id="installed-plugins",
        ),
    ],
)
def test_runtime_sites_write_into_data_dir(monkeypatch, tmp_path, ctor, attr):
    """桌面场景：实例级解析的持久目录必须位于 QUANTCELL_DATA_DIR 内。"""
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))
    obj = ctor()
    resolved = Path(getattr(obj, attr)).resolve()
    assert resolved.is_relative_to(tmp_path.resolve()), f"{resolved} not under {tmp_path}"


def test_source_data_dir_redirects_with_persistent_env(monkeypatch, tmp_path):
    """get_source_data_dir 必须跟随 QUANTCELL_DATA_DIR 重定向，否则 standalone_downloader
    和 backtest provider 写进临时解压目录、重启即丢。"""
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))
    resolved = get_source_data_dir().resolve()
    assert resolved.is_relative_to(tmp_path.resolve()), (
        f"get_source_data_dir {resolved} not under QUANTCELL_DATA_DIR {tmp_path}"
    )


def test_source_data_dir_legacy_when_env_unset(monkeypatch):
    monkeypatch.delenv("QUANTCELL_DATA_DIR", raising=False)
    from utils.data_utils import get_backend_root

    assert get_source_data_dir() == get_backend_root() / "data" / "source"


def test_standalone_downloader_has_no_home_dir_leak():
    """死代码守门：StandaloneDataDownloader 不得再带 home-dir 路径属性/方法。

    历史 bug：__init__ 里硬 Path.home() / ".quantcell" / "data" / "kline"，
    且 __init__(save_local=True) 默认开启、同时落 DB 和 ~/.quantcell 分片（后者无人读）。
    2026-11-27 重构后所有持久写入走 source parquet（经 get_source_data_dir → persistent）。
    """
    from backtest.standalone_downloader import StandaloneDataDownloader

    # 死属性必须不存在
    downloader = StandaloneDataDownloader()
    for bad_attr in ("save_local", "local_storage_dir"):
        assert not hasattr(downloader, bad_attr), f"StandaloneDataDownloader leaked home-dir attr: {bad_attr}"
    for bad_method in ("_save_to_local_file",):
        assert not hasattr(StandaloneDataDownloader, bad_method), (
            f"StandaloneDataDownloader leaked dead method: {bad_method}"
        )
    # 持久写入入口必须是我们认的那两个
    assert hasattr(downloader, "_merge_to_source_parquet")
    assert hasattr(downloader, "_save_to_database")
