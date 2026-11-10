"""EnsembleService 单元测试:SB3 zip 加载 / 连续动作拒绝 / pickle 旧路径。

SB3 zip 用 tmp_path 内存构造(不训练,仅撑起模型结构),并 monkeypatch
ensemble_service.MODELS_DIR 把 stem 解析根指到 tmp,避免读写 backend/data/models 真实目录。
"""

import pickle

import gymnasium as gym
import numpy as np
import pytest

from services import ensemble_service
from services.ensemble_service import EnsembleService


class _DiscreteDummyEnv(gym.Env):
    """最小离散动作环境,仅用于实例化 SB3 模型(不做训练)。"""

    observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=(3,), dtype=float)
    action_space = gym.spaces.Discrete(3)

    def reset(self, seed=None, options=None):
        return np.zeros(3, dtype=float), {}

    def step(self, action):
        return np.zeros(3, dtype=float), 0.0, True, False, {}


class _BoxDummyEnv(gym.Env):
    """连续动作环境(与 SAC 动作空间同构)。"""

    observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=(3,), dtype=float)
    action_space = gym.spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=float)

    def reset(self, seed=None, options=None):
        return np.zeros(3, dtype=float), {}

    def step(self, action):
        return np.zeros(3, dtype=float), 0.0, True, False, {}


@pytest.fixture
def models_dir(tmp_path, monkeypatch):
    """stem 解析根与元数据落盘都指向 tmp_path,测试不读写 backend/data/ 真实目录。"""
    monkeypatch.setattr(ensemble_service, "MODELS_DIR", tmp_path)
    # raising=False:ENSEMBLES_STORE 在 Task 2 才引入;Task 2 落地后本 fixture 隔离 create 的磁盘写入
    monkeypatch.setattr(ensemble_service, "ENSEMBLES_STORE", tmp_path / "ensembles.json", raising=False)
    return tmp_path


def _save_discrete_ppo(models_dir, stem: str):
    from stable_baselines3 import PPO

    # n_steps/batch_size 取最小可整除值,纯构造不训练
    model = PPO("MlpPolicy", _DiscreteDummyEnv(), n_steps=4, batch_size=4)
    model.save(str(models_dir / f"{stem}.zip"))


def test_ensemble_service_creation():
    from services.ensemble_service import EnsembleService

    svc = EnsembleService()
    assert svc is not None


def test_sb3_zip_create_and_list(models_dir):
    _save_discrete_ppo(models_dir, "ppo_dummy")
    svc = EnsembleService()

    ensemble_id = svc.create_ensemble("soft_vote", ["ppo_dummy"])

    items = svc.list_ensembles()
    assert len(items) == 1
    assert items[0]["id"] == ensemble_id
    # 关键口径:创建后 models > 0,证明 SB3 分支真实加载而非静默跳过
    assert items[0]["models"] == 1


def test_sb3_zip_predict(models_dir):
    _save_discrete_ppo(models_dir, "ppo_dummy2")
    svc = EnsembleService()
    ensemble_id = svc.create_ensemble("soft_vote", ["ppo_dummy2"])

    result = svc.predict(ensemble_id, {"market_features": [0.1, -0.2, 0.3]})
    assert result["action"] in {"hold", "buy", "sell"}
    assert 0.0 <= result["confidence"] <= 1.0


def test_continuous_action_rejected(models_dir):
    from stable_baselines3 import SAC

    model = SAC("MlpPolicy", _BoxDummyEnv(), batch_size=4, buffer_size=1000)
    model.save(str(models_dir / "sac_cont.zip"))

    svc = EnsembleService()
    # 连续动作模型无法参与离散投票:create 阶段整单拒绝,不静默降级(spec §4)
    with pytest.raises(ValueError, match="连续动作模型"):
        svc.create_ensemble("soft_vote", ["sac_cont"])


def test_pickle_abs_path_still_works(tmp_path, models_dir):
    from sklearn.linear_model import LogisticRegression

    clf = LogisticRegression().fit(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]), [0, 1])
    pkl = tmp_path / "clf.pkl"
    with open(pkl, "wb") as f:
        pickle.dump(clf, f)

    svc = EnsembleService()
    ensemble_id = svc.create_ensemble("soft_vote", [str(pkl)])

    assert svc.list_ensembles()[0]["models"] == 1
    result = svc.predict(ensemble_id, {"market_features": [1.0, 1.0, 1.0]})
    assert result["action"] in {"hold", "buy", "sell"}
