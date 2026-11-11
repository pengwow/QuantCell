"""ensemble_aggregator 纯函数单测:成员适配 + 均值聚合语义。"""

import numpy as np
import pytest
from gymnasium import spaces


class FakeModel:
    """最小 SB3 模型替身:predict 返回预设序列,action_space 决定适配分支。"""

    def __init__(self, action_space, outputs):
        self.action_space = action_space
        self._outputs = iter(outputs)

    def predict(self, obs, deterministic=True):
        return next(self._outputs), None


BOX = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)
DISCRETE = spaces.Discrete(3)

OBS = [0.1, 0.2, 0.3]


def _box_model(value):
    return FakeModel(BOX, [np.array([value], dtype=np.float32)])


def _discrete_model(idx):
    return FakeModel(DISCRETE, [np.array(idx, dtype=np.int64)])


def test_continuous_member_clips_to_unit_range():
    from services.ensemble_aggregator import member_ratio_predict_fn

    fn = member_ratio_predict_fn(_box_model(2.5))
    assert fn(OBS) == 1.0  # 超出上界被 clip
    fn2 = member_ratio_predict_fn(_box_model(-0.2))
    assert fn2(OBS) == 0.0


def test_discrete_buy_sell_hold_mapping():
    from services.ensemble_aggregator import member_ratio_predict_fn

    assert member_ratio_predict_fn(_discrete_model(1))(OBS) == 1.0  # buy
    assert member_ratio_predict_fn(_discrete_model(2))(OBS) == 0.0  # sell
    assert member_ratio_predict_fn(_discrete_model(0))(OBS) is None  # hold 弃权


def test_aggregate_mixed_mean_skips_abstains():
    from services.ensemble_aggregator import aggregate_ratios

    ratio, _conf = aggregate_ratios([1.0, None, 0.0])
    assert ratio == pytest.approx(0.5)  # 参与者 {1.0, 0.0} 的均值,弃权不计分母


def test_aggregate_all_abstain_returns_zero():
    from services.ensemble_aggregator import aggregate_ratios

    assert aggregate_ratios([None, None]) == (0.0, 0.0)


def test_aggregate_confidence_bounds():
    from services.ensemble_aggregator import aggregate_ratios

    _, conf_single = aggregate_ratios([0.3])  # 单成员 std=0 → 置信 1.0
    assert conf_single == pytest.approx(1.0)
    _, conf_divergent = aggregate_ratios([0.0, 1.0])  # 完全分歧 std=0.5 → 0.5
    assert conf_divergent == pytest.approx(0.5)


def test_ensemble_predict_fn_abstains_on_member_error():
    from services.ensemble_aggregator import make_ensemble_predict_fn

    def boom(_obs):
        raise RuntimeError("成员挂了")

    fns = [lambda o: 1.0, boom, lambda o: None]
    ratio = make_ensemble_predict_fn(fns)(OBS)
    assert ratio == pytest.approx(1.0)  # 异常成员视为弃权,不影响其余成员


def test_ensemble_predict_fn_all_abstain_zero():
    from services.ensemble_aggregator import make_ensemble_predict_fn, member_ratio_predict_fn

    fns = [member_ratio_predict_fn(_discrete_model(0))]
    assert make_ensemble_predict_fn(fns)(OBS) == 0.0
