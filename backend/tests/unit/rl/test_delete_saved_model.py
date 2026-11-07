"""RLService.delete_saved_model 单测。

覆盖：正常删除（zip + meta 旁车）、meta 缺失时不阻塞、非法 ID 拦截、
路径穿越拦截、模型不存在。全程 monkeypatch MODELS_DIR 到 tmp_path，
绝不触碰真实 backend/data/models。
"""

from pathlib import Path

import pytest

from services import rl_service


@pytest.fixture
def models_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "models"
    d.mkdir()
    # delete_saved_model 与 RLService.__init__ 都引用模块级 MODELS_DIR，
    # 替换这一个名字即可完成隔离
    monkeypatch.setattr(rl_service, "MODELS_DIR", d)
    return d


def _make_model(models_dir: Path, name: str, with_meta: bool = True) -> None:
    models_dir.joinpath(f"{name}.zip").write_bytes(b"fake-model-bytes")
    if with_meta:
        rl_service.rl_meta_path(str(models_dir / f"{name}.zip")).write_text("{}", encoding="utf-8")


def test_delete_removes_zip_and_meta(models_dir: Path):
    _make_model(models_dir, "ppo_ppo_1700000000")
    rl_service.RLService().delete_saved_model("ppo_ppo_1700000000")
    assert not (models_dir / "ppo_ppo_1700000000.zip").exists()
    assert not (models_dir / "ppo_ppo_1700000000.zip.meta.json").exists()


def test_delete_without_meta_succeeds(models_dir: Path):
    _make_model(models_dir, "sac_sac_1", with_meta=False)
    rl_service.RLService().delete_saved_model("sac_sac_1")
    assert not (models_dir / "sac_sac_1.zip").exists()


def test_delete_keeps_other_models(models_dir: Path):
    _make_model(models_dir, "a")
    _make_model(models_dir, "b")
    rl_service.RLService().delete_saved_model("a")
    assert (models_dir / "b.zip").exists()
    assert (models_dir / "b.zip.meta.json").exists()


@pytest.mark.parametrize("bad_id", ["../evil", "a/b", "a\\b", "..", "", ".hidden/zip"])
def test_delete_rejects_illegal_id(models_dir: Path, bad_id: str):
    with pytest.raises(ValueError, match="非法"):
        rl_service.RLService().delete_saved_model(bad_id)


def test_delete_missing_model_raises_file_not_found(models_dir: Path):
    with pytest.raises(FileNotFoundError):
        rl_service.RLService().delete_saved_model("no_such_model")
