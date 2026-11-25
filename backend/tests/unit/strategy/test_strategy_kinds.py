"""strategy_kinds 单测：回测列表「类型」列的取值口径。

口径必须与策略管理页的 kind 同源（同一个 `_strategy_kind`）：
rule / rl / llm，取不到（策略文件已删）→ None，不按名字猜。
"""

import pytest

from strategy.service import StrategyService

RULE_SRC = '''"""规则策略探针"""


class RuleProbe:
    def on_bar(self, bar):
        return None
'''

LLM_SRC = '''"""LLM 策略探针"""


class LlmProbe:
    def on_bar(self, bar):
        mode = self.get_param("mode", "llm")
        return mode
'''


@pytest.fixture
def service(tmp_path):
    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir()
    svc = StrategyService()
    svc.strategy_dir = strategies_dir
    return svc


def _write(service, name: str, src: str) -> None:
    (service.strategy_dir / f"{name}.py").write_text(src, encoding="utf-8")


def test_rule_strategy(service):
    _write(service, "rule_probe", RULE_SRC)
    assert service.strategy_kinds(["rule_probe"]) == {"rule_probe": "rule"}


def test_llm_strategy_via_mode_param(service):
    # llm 的库内标识是参数字面量 mode="llm"（与 backtest/routes.py 的
    # params.get("mode") == "llm" 同口径），不是策略名或注释
    _write(service, "llm_probe", LLM_SRC)
    assert service.strategy_kinds(["llm_probe"]) == {"llm_probe": "llm"}


def test_rl_prefix_needs_no_file(service):
    # 模型中心直发的 RL 回测任务不落策略文件，靠前缀归 rl
    kinds = service.strategy_kinds(["rl_model:ppo_1", "rl_ensemble:mix_2"])
    assert kinds == {"rl_model:ppo_1": "rl", "rl_ensemble:mix_2": "rl"}


def test_missing_file_is_none(service):
    # 策略已删但历史任务还在：返回 None 让前端显示「—」，不猜类型
    assert service.strategy_kinds(["gone_strategy"]) == {"gone_strategy": None}


def test_batch_dedup_and_empty(service):
    _write(service, "rule_probe", RULE_SRC)
    kinds = service.strategy_kinds(["rule_probe", "rule_probe", "gone"])
    assert kinds == {"rule_probe": "rule", "gone": None}
    assert service.strategy_kinds([]) == {}
    assert service.strategy_kinds(None) == {}
