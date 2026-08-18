"""account CLI 测试。"""

import pytest
from typer.testing import CliRunner

from cli.account import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def isolated_credentials(tmp_path, monkeypatch):
    """每个测试用临时 DB。"""
    db_path = str(tmp_path / "cli_test.db")
    monkeypatch.setenv("QC_CREDENTIALS_DB", db_path)
    yield


def test_account_add_then_list(runner):
    """add 后 list 可见。"""
    result = runner.invoke(
        app,
        [
            "add",
            "--name",
            "main",
            "--exchange",
            "binance",
            "--api-key",
            "k1",
            "--api-secret",
            "s1",
        ],
    )
    assert result.exit_code == 0
    result = runner.invoke(app, ["list"])
    assert "main" in result.stdout
    assert "binance" in result.stdout


def test_account_list_secret_never_leaks(runner):
    """list 输出绝不包含 api_secret。"""
    runner.invoke(
        app,
        [
            "add",
            "--name",
            "main",
            "--exchange",
            "binance",
            "--api-key",
            "AK_123",
            "--api-secret",
            "SUPER_SECRET_XYZ",
        ],
    )
    result = runner.invoke(app, ["list"])
    assert "SUPER_SECRET_XYZ" not in result.stdout
    # api_key 也不在 list 中（仅 add 时 echo 一次，list 不返回）
    assert "AK_123" not in result.stdout


def test_account_remove(runner):
    """remove 后 list 为空。"""
    runner.invoke(
        app,
        [
            "add",
            "--name",
            "main",
            "--exchange",
            "binance",
            "--api-key",
            "k",
            "--api-secret",
            "s",
        ],
    )
    result = runner.invoke(app, ["remove", "--name", "main"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["list"])
    assert "(无账号)" in result.stdout


def test_account_remove_not_found(runner):
    """remove 不存在的账号 exit code 1。"""
    result = runner.invoke(app, ["remove", "--name", "ghost"])
    assert result.exit_code == 1
