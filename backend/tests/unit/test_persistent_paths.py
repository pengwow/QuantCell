"""打包升级不丢历史数据的守门测试。

背景：PyInstaller onefile 下 ``__file__`` 位于每次启动重新解压的临时目录，
凡以模块相对路径写入的数据（策略文件、K线源数据、插件、日志、agent 工作区…），
桌面端重启/升级即蒸发。所有持久写入必须落 QUANTCELL_DATA_DIR。
"""

import os
from pathlib import Path

import pytest

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
