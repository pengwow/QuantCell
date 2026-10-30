"""scripts/sync_version.py 的最小自检（pytest 直跑，无 fixture 依赖）

运行（仓库根）：
    uv run --no-project --with typer --with pytest pytest scripts/test_sync_version.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 让 import 直接命中同目录的 sync_version 模块（脚本目录不在默认搜索路径上）
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

import sync_version as sv

# 含行内表 version 与 version.workspace 的 toml 样例：包声明必须被替换、其余两处不能被波及
SAMPLE_TOML = """\
[package]
name = "quantcell-desktop"
version = "0.1.0"
description = "QuantCell desktop shell"

[dependencies]
tauri = { version = "2", features = [] }

[dev-dependencies]
serde = { version = "1", features = ["derive"] }

[lib]
version.workspace = true
"""


# ---------- semver 校验 / 版本解析 ----------

@pytest.mark.parametrize("raw", ["0.0.1.1", "abc", "", "v0.0.1", "0.0", "0.0.1-rc1"])
def test_resolve_rejects_invalid(raw):
    with pytest.raises(ValueError):
        sv.resolve_target_version("0.0.1", raw)


def test_resolve_semver_passthrough():
    assert sv.resolve_target_version("0.0.9", "0.1.0") == "0.1.0"


def test_resolve_increment_requires_current():
    with pytest.raises(ValueError):
        sv.resolve_target_version(None, "patch")


def test_resolve_rejects_increment_on_invalid_current():
    with pytest.raises(ValueError):
        sv.resolve_target_version("0.1", "patch")


@pytest.mark.parametrize(
    ("current", "part", "expected"),
    [
        ("0.0.9", "patch", "0.0.10"),  # 末位 +1，无进制进位概念
        ("0.0.9", "minor", "0.1.0"),   # 中位 +1，末位归零
        ("0.2.9", "major", "1.0.0"),   # 首位 +1，余位归零
        ("1.2.3", "patch", "1.2.4"),
    ],
)
def test_bump_version(current, part, expected):
    assert sv.bump_version(current, part) == expected


# ---------- toml 替换 ----------

def test_replace_toml_version_only_package_decl():
    out = sv.replace_toml_version(SAMPLE_TOML, "0.0.1")
    # 行内表的 version（tauri = { version = "2" } 等）不在行首，绝不能被改
    assert 'tauri = { version = "2", features = [] }' in out
    assert 'serde = { version = "1", features = ["derive"] }' in out
    # version.workspace = true 同样不能被波及
    assert "version.workspace = true" in out
    # 只有包声明一处被替换
    assert out.count('version = "0.0.1"') == 1
    assert 'version = "0.1.0"' not in out


def test_replace_toml_version_raises_without_decl():
    with pytest.raises(ValueError):
        sv.replace_toml_version('[project]\nname = "x"\n', "0.0.1")


# ---------- JSON 落盘格式 ----------

def test_render_json_format():
    data = {"productName": "QuantCell", "version": "0.1.0", "备注": "中文值"}
    out = sv.render_json(data)
    assert out.endswith("\n")  # 尾换行
    assert "中文值" in out  # ensure_ascii=False，中文不转义
    assert any(line.startswith('  "version"') for line in out.splitlines())  # 2 空格缩进
    assert '"version": "0.1.0"' in out


def test_set_json_version_roundtrip(tmp_path):
    f = tmp_path / "tauri.conf.json"
    f.write_text(
        '{"productName": "Q", "version": "0.1.0", "bundle": {"active": true}}',
        encoding="utf-8",
    )
    sv.set_json_version(f, "0.0.1")
    data = json.loads(f.read_text(encoding="utf-8"))
    assert data["version"] == "0.0.1"  # 版本已更新
    assert data["productName"] == "Q"  # 其余键原样保留
    assert data["bundle"] == {"active": True}  # 嵌套结构不受影响


# ---------- settings.py 特殊项的正则探测 ----------

def test_settings_default_regex_probe_dev():
    """守卫：settings.py 的 app_version default 必须能被体检正则探到且仍为 dev；
    若有人改注释密度/字段结构导致正则失配，体检会误报，这里第一时间暴露"""
    text = sv.SETTINGS_FILE.read_text(encoding="utf-8")
    m = sv.SETTINGS_DEFAULT_RE.search(text)
    assert m is not None, "SETTINGS_DEFAULT_RE 探不到 app_version 的 default"
    assert m.group(1) == "dev"
