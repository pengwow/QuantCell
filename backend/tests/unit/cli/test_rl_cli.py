"""rl CLI 测试：train 参数透传 + models 只读列表（不跑真实训练/回测）。"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import rl as rl_cli
from services import rl_service


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def captured_config(monkeypatch):
    """替换 RLService，捕获传进 train() 的 RLTrainConfig。"""
    captured: dict[str, object] = {}

    class FakeRLService:
        def train(self, config):
            captured["config"] = config
            return rl_service.RLTrainResult(
                model_id="model-1",
                model_path="/tmp/model-1.zip",
                metrics={
                    "steps": config.total_timesteps,
                    "algorithm": config.algorithm,
                    "elapsed_seconds": 0.0,
                },
            )

    monkeypatch.setattr(rl_cli, "RLService", FakeRLService)
    return captured


def test_rl_train_maps_flags_to_config(runner, captured_config):
    """CLI 选项逐字段落到 RLTrainConfig（字段名以 dataclass 为准）。"""
    result = runner.invoke(
        rl_cli.app,
        [
            "train",
            "--symbol",
            "ETHUSDT",
            "--algorithm",
            "sac",
            "--timesteps",
            "1234",
            "--reward",
            "sharpe",
            "--interval",
            "4h",
            "--name",
            "eth_sac",
            "--walk-forward",
        ],
    )

    assert result.exit_code == 0, result.output
    cfg = captured_config["config"]
    assert isinstance(cfg, rl_service.RLTrainConfig)
    assert cfg.symbol == "ETHUSDT"
    assert cfg.algorithm == "sac"
    assert cfg.total_timesteps == 1234
    assert cfg.reward_type == "sharpe"
    assert cfg.interval == "4h"
    assert cfg.model_name == "eth_sac"
    assert cfg.walk_forward is True
    assert "训练完成" in result.stdout


def test_rl_train_defaults_model_name_from_symbol_and_algorithm(runner, captured_config):
    """缺省 model_name 由 symbol_algorithm 拼出；步数用 CLI 默认 5000。"""
    result = runner.invoke(rl_cli.app, ["train", "--symbol", "BTCUSDT", "--algorithm", "ppo"])

    assert result.exit_code == 0, result.output
    cfg = captured_config["config"]
    assert cfg.model_name == "BTCUSDT_ppo"
    assert cfg.total_timesteps == 5000
    assert cfg.walk_forward is False


def test_rl_models_lists_zip_files_from_models_dir(runner, tmp_path, monkeypatch):
    """models 只读 MODELS_DIR 下的 .zip 文件。"""
    (tmp_path / "BTCUSDT_ppo.zip").write_bytes(b"x" * 1024)
    (tmp_path / "ETHUSDT_sac.zip").write_bytes(b"x" * 2048)
    (tmp_path / "ignore.txt").write_bytes(b"not a model")
    monkeypatch.setattr(rl_service, "MODELS_DIR", Path(tmp_path))

    result = runner.invoke(rl_cli.app, ["models"])

    assert result.exit_code == 0, result.output
    assert "BTCUSDT_ppo" in result.stdout
    assert "ETHUSDT_sac" in result.stdout
    assert "ignore" not in result.stdout


def test_rl_models_empty_models_dir(runner, tmp_path, monkeypatch):
    """空目录时提示暂无模型。"""
    monkeypatch.setattr(rl_service, "MODELS_DIR", Path(tmp_path))

    result = runner.invoke(rl_cli.app, ["models"])

    assert result.exit_code == 0, result.output
    assert "暂无已训练模型" in result.stdout
