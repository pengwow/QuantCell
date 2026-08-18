"""CLI `quantcell data archive` 子命令单元测试。

覆盖 3 个子命令:
- archive download
- archive list
- archive meta

通过 monkeypatch 注入 ArchiveService, 不实际访问数据库 / 文件。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

runner = CliRunner()


# =================== archive download ===================


def test_archive_download_creates_task():
    """archive download 必须创建任务并打印 task_id。"""
    from cli.data import app

    fake_svc = MagicMock()
    fake_svc.create_download_task.return_value = "task-cli-001"
    fake_svc.base_dir = "/tmp/qc"

    with patch(
        "collector.services.archive_service.ArchiveService",
        return_value=fake_svc,
    ):
        result = runner.invoke(
            app,
            [
                "archive",
                "download",
                "-k",
                "aggTrades",
                "-m",
                "spot",
                "-s",
                "BTCUSDT,ETHUSDT",
                "--start",
                "2024-12-01",
                "--end",
                "2024-12-02",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "task-cli-001" in result.output
    assert "aggTrades" in result.output
    assert "spot" in result.output
    fake_svc.create_download_task.assert_called_once()
    kwargs = fake_svc.create_download_task.call_args.kwargs
    assert kwargs["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert kwargs["start_date"] == "2024-12-01"
    assert kwargs["end_date"] == "2024-12-02"
    assert kwargs["mode"] == "inc"
    assert kwargs["interval"] is None


def test_archive_download_passes_interval_for_kline():
    """K 线类必须把 interval 传给 service。"""
    from cli.data import app

    fake_svc = MagicMock()
    fake_svc.create_download_task.return_value = "task-kline-002"
    fake_svc.base_dir = "/tmp/qc"

    with patch(
        "collector.services.archive_service.ArchiveService",
        return_value=fake_svc,
    ):
        result = runner.invoke(
            app,
            [
                "archive",
                "download",
                "-k",
                "markPriceKlines",
                "-m",
                "um",
                "-s",
                "BTCUSDT",
                "--start",
                "2024-12-01",
                "--end",
                "2024-12-02",
                "-i",
                "1h",
                "--mode",
                "full",
            ],
        )

    assert result.exit_code == 0, result.output
    kwargs = fake_svc.create_download_task.call_args.kwargs
    assert kwargs["interval"] == "1h"
    assert kwargs["mode"] == "full"


def test_archive_download_invalid_kind_returns_error():
    """非法 kind 必须报错并 exit 非 0。"""
    from cli.data import app

    result = runner.invoke(
        app,
        [
            "archive",
            "download",
            "-k",
            "not_a_kind",
            "-m",
            "spot",
            "-s",
            "BTCUSDT",
            "--start",
            "2024-12-01",
            "--end",
            "2024-12-02",
        ],
    )
    assert result.exit_code != 0


def test_archive_download_kline_without_interval_returns_error():
    """K 线类缺 interval 必须被 service 拒绝, exit 非 0。"""
    from cli.data import app

    fake_svc = MagicMock()
    fake_svc.create_download_task.side_effect = ValueError("kind=markPriceKlines requires interval in ['1m','3m',...]")
    fake_svc.base_dir = "/tmp/qc"

    with patch(
        "collector.services.archive_service.ArchiveService",
        return_value=fake_svc,
    ):
        result = runner.invoke(
            app,
            [
                "archive",
                "download",
                "-k",
                "markPriceKlines",
                "-m",
                "um",
                "-s",
                "BTCUSDT",
                "--start",
                "2024-12-01",
                "--end",
                "2024-12-02",
            ],
        )
    assert result.exit_code != 0
    fake_svc.create_download_task.assert_called_once()


def test_archive_download_empty_symbols_returns_error():
    """空 symbols 必须报错。"""
    from cli.data import app

    result = runner.invoke(
        app,
        [
            "archive",
            "download",
            "-k",
            "aggTrades",
            "-m",
            "spot",
            "-s",
            "  , , ",
            "--start",
            "2024-12-01",
            "--end",
            "2024-12-02",
        ],
    )
    assert result.exit_code != 0


def test_archive_download_invalid_mode_returns_error():
    """非法 mode 必须报错。"""
    from cli.data import app

    result = runner.invoke(
        app,
        [
            "archive",
            "download",
            "-k",
            "aggTrades",
            "-m",
            "spot",
            "-s",
            "BTCUSDT",
            "--start",
            "2024-12-01",
            "--end",
            "2024-12-02",
            "--mode",
            "weekly",
        ],
    )
    assert result.exit_code != 0


# =================== archive list ===================


def test_archive_list_prints_symbols():
    """archive list 必须打印 symbols 列表。"""
    from cli.data import app

    fake_svc = MagicMock()
    fake_svc.list_symbols.return_value = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
    fake_svc.base_dir = "/tmp/qc"

    with patch(
        "collector.services.archive_service.ArchiveService",
        return_value=fake_svc,
    ):
        result = runner.invoke(
            app,
            ["archive", "list", "-k", "aggTrades", "-m", "spot"],
        )
    assert result.exit_code == 0, result.output
    assert "BTCUSDT" in result.output
    assert "ETHUSDT" in result.output
    assert "ADAUSDT" in result.output
    fake_svc.list_symbols.assert_called_once()


def test_archive_list_empty():
    """空目录时打印 (无) 并正常退出。"""
    from cli.data import app

    fake_svc = MagicMock()
    fake_svc.list_symbols.return_value = []
    fake_svc.base_dir = "/tmp/qc"

    with patch(
        "collector.services.archive_service.ArchiveService",
        return_value=fake_svc,
    ):
        result = runner.invoke(
            app,
            ["archive", "list", "-k", "aggTrades", "-m", "spot"],
        )
    assert result.exit_code == 0, result.output
    assert "0" in result.output  # "0 个交易对"
    assert "(无)" in result.output


def test_archive_list_invalid_kind_returns_error():
    """非法 kind 必须 exit 非 0。"""
    from cli.data import app

    result = runner.invoke(
        app,
        ["archive", "list", "-k", "bad", "-m", "spot"],
    )
    assert result.exit_code != 0


# =================== archive meta ===================


def test_archive_meta_prints_dict():
    """archive meta 必须 JSON 美化打印 _meta.json。"""
    from cli.data import app

    fake_svc = MagicMock()
    fake_svc.get_meta.return_value = {
        "symbol": "BTCUSDT",
        "kind": "aggTrades",
        "latest_date": "2024-12-02",
    }
    fake_svc.base_dir = "/tmp/qc"

    with patch(
        "collector.services.archive_service.ArchiveService",
        return_value=fake_svc,
    ):
        result = runner.invoke(
            app,
            [
                "archive",
                "meta",
                "-k",
                "aggTrades",
                "-m",
                "spot",
                "-s",
                "BTCUSDT",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "BTCUSDT" in result.output
    assert "2024-12-02" in result.output


def test_archive_meta_missing():
    """_meta.json 不存在时打印 (无 _meta.json)。"""
    from cli.data import app

    fake_svc = MagicMock()
    fake_svc.get_meta.return_value = None
    fake_svc.base_dir = "/tmp/qc"

    with patch(
        "collector.services.archive_service.ArchiveService",
        return_value=fake_svc,
    ):
        result = runner.invoke(
            app,
            [
                "archive",
                "meta",
                "-k",
                "aggTrades",
                "-m",
                "spot",
                "-s",
                "BTCUSDT",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "(无 _meta.json)" in result.output


def test_archive_meta_invalid_market_returns_error():
    """非法 market 必须 exit 非 0。"""
    from cli.data import app

    result = runner.invoke(
        app,
        ["archive", "meta", "-k", "aggTrades", "-m", "bad", "-s", "BTCUSDT"],
    )
    assert result.exit_code != 0
