"""strategy 场景单测：JSON 解析、judge 硬门、OOS 口径、内核评估、策略入库。

evaluate 用例真跑统一回测内核（合成单边上涨数据 + 满仓策略），与回测页同路径。
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import research.scenarios.strategy as strategy_scenario_module
import strategy.models  # 注册 Strategy，保证 Worker 关系的 mapper 可初始化
from collector.db.database import Base
from research import service
from research.models import ResearchSession, ResearchTrial
from research.scenarios.strategy import StrategyScenario, _extract_json

STRATEGY_CODE = '''
from axon_quant import Action, ActionType
from strategy.base import BaseStrategy

class AlwaysLong(BaseStrategy):
    """单边上涨数据 + 满仓：稳定产生盈利与成交。"""

    def on_bar(self, bar, ctx=None):
        return Action(ActionType.Buy, 1.0, 1.0, "always_long", 0)
'''


def _synth_ohlcv(n: int = 120) -> pd.DataFrame:
    """单边上涨的合成 K 线：timestamp 为纳秒整数，列名与数据源一致。"""
    rows = []
    ts = 1_700_000_000_000_000_000
    price = 100.0
    for _ in range(n):
        o = price
        price += 0.5
        rows.append({"timestamp": ts, "open": o, "high": price + 0.2, "low": o - 0.2, "close": price, "volume": 100.0})
        ts += 3_600_000_000_000
    return pd.DataFrame(rows)


# ---------- JSON 抽取 ----------


def test_extract_json_array_in_fence():
    """回归：JSON 数组结尾是 ] 不是 }，旧实现在数组场景截出残片。"""
    content = '```json\n[{"name": "a"}, {"name": "b"}]\n```'
    data = _extract_json(content)
    assert isinstance(data, list) and len(data) == 2


def test_extract_json_object_with_prefix():
    data = _extract_json('好的，结果如下：{"hypothesis": "x"} 以上。')
    assert data == {"hypothesis": "x"}


# ---------- build_tasks ----------


def test_build_tasks_parses_array_and_skips_bad_items():
    def llm(system, user, stage=None):
        content = (
            '[{"name": "a", "description": "d"}, "garbage", {"name": "b", "description": "d2", "params": {"fast": 5}}]'
        )
        return content, {"total_tokens": 10}

    tasks, usage = StrategyScenario().build_tasks(llm_call=llm, hypothesis="h", context="c", n=2)
    assert [t.name for t in tasks] == ["a", "b"]
    assert tasks[1].params == {"fast": 5.0}
    assert usage["total_tokens"] == 10


# ---------- judge 硬门 ----------


def _judge(**kw):
    base = {"metrics": {"sharpe_ratio": 1.0, "total_pnl": 100.0, "trades": 5}}
    base.update(kw)
    return StrategyScenario().judge(**base)


def test_judge_all_gates_pass():
    out = _judge(oos_flag="ok")
    assert out["decision"] is True


def test_judge_sharpe_and_trades_floor():
    assert _judge(oos_flag=None, metrics={"sharpe_ratio": 0.2, "total_pnl": 1.0, "trades": 5})["decision"] is False
    assert _judge(oos_flag=None, metrics={"sharpe_ratio": 1.0, "total_pnl": 1.0, "trades": 2})["decision"] is False
    # 自定义下限生效
    out = _judge(
        oos_flag=None,
        cfg={"sharpe_floor": 1.5, "min_trades": 1},
        metrics={"sharpe_ratio": 1.0, "total_pnl": 1.0, "trades": 3},
    )
    assert out["decision"] is False and out["gates"]["sharpe"]["floor"] == 1.5


def test_judge_oos_flip_blocked_but_none_allowed():
    assert _judge(oos_flag="sign_flip")["decision"] is False
    assert _judge(oos_flag="weak")["decision"] is False
    # 未启用样本外段不拦截
    assert _judge(oos_flag=None)["decision"] is True


# ---------- OOS 口径 ----------


def test_oos_metrics_flags():
    sc = StrategyScenario()
    analysis = {"train": {"sharpe_ratio": 2.0}, "test": {"sharpe_ratio": -0.5, "total_pnl": -10}}
    _, flag, note = sc.oos_metrics(analysis, analysis["train"], {})
    assert flag == "sign_flip" and "test_sharpe" in note

    analysis["test"]["sharpe_ratio"] = 0.5  # 0.3*2.0=0.6 之下 → weak
    _, flag, _ = sc.oos_metrics(analysis, analysis["train"], {})
    assert flag == "weak"

    analysis["test"]["sharpe_ratio"] = 1.8
    _, flag, _ = sc.oos_metrics(analysis, analysis["train"], {})
    assert flag == "ok"

    _, flag, note = sc.oos_metrics({"train": {}}, {}, {})
    assert flag is None and note


# ---------- 加载策略类 ----------


def test_load_strategy_class_finds_subclass():
    cls = StrategyScenario()._load_strategy_class(STRATEGY_CODE)
    assert cls.__name__ == "AlwaysLong"


def test_load_strategy_class_rejects_no_subclass():
    with pytest.raises(ValueError, match="BaseStrategy"):
        StrategyScenario()._load_strategy_class("x = 1")


# ---------- evaluate（真跑统一内核）----------


def test_evaluate_runs_kernel_and_splits_oos():
    sc = StrategyScenario()
    cfg = {"symbols": ["BTC/USDT"], "interval": "1h", "test_ratio": 0.2}
    analysis = sc.evaluate(STRATEGY_CODE, {"BTC/USDT": _synth_ohlcv(120)}, cfg)

    # 120 * 0.8 = 96 训练段；test 段 24 根 ≥ MIN_TEST_BARS
    assert analysis["train"]["bar_count"] == 96
    assert analysis["test"]["bar_count"] == 24
    assert analysis["per_symbol"]["BTC/USDT"]["train"]["trades"] > 0
    # 单边上涨 + 满仓：样本内应盈利
    assert analysis["train"]["total_pnl"] > 0
    # 策略没有因子序列，train_factor 故意缺省（相关性去重自动跳过）
    assert "train_factor" not in analysis


def test_evaluate_rejects_short_window():
    with pytest.raises(ValueError, match="训练段"):
        StrategyScenario().evaluate(STRATEGY_CODE, {"BTC/USDT": _synth_ohlcv(30)}, {"test_ratio": 0.0})


# ---------- promote（落策略库，幂等）----------


@pytest.fixture()
def promote_env(monkeypatch, tmp_path):
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[ResearchSession.__table__, ResearchTrial.__table__])
    db = sessionmaker(bind=eng)()

    @contextlib.contextmanager
    def fake_db():
        yield db

    class _StubStrategyService:
        """落文件路径重定向到临时目录，避免污染 backend/strategies。"""

        def __init__(self):
            self.strategy_dir = tmp_path

        def save_strategy(self, name, content):
            Path(self.strategy_dir, f"{name}.py").write_text(content, encoding="utf-8")
            return {"name": name}

    monkeypatch.setattr(strategy_scenario_module, "get_db_session", fake_db)
    monkeypatch.setattr(strategy_scenario_module, "StrategyService", _StubStrategyService)
    return db, tmp_path


def _seed_strategy_trial(db):
    session = service.create_session(
        db, owner_id="u1", name="s-test", mode="deep", scenario="strategy", config={}, n_candidates=1
    )
    service.set_session_status(db, session, "running")
    return service.add_trial(
        db,
        session.id,
        {
            "loop_idx": 1,
            "candidate_idx": 1,
            "status": "judged",
            "hypothesis": "趋势跟随",
            "code": STRATEGY_CODE,
            "code_hash": "stub",
        },
    )


def test_promote_writes_strategy_file_and_records_trial(promote_env):
    db, strategy_dir = promote_env
    trial = _seed_strategy_trial(db)

    name = StrategyScenario().promote(service.trial_to_dict(trial))
    assert name == f"rs_{trial.session_id}_{trial.id}"

    content = (Path(strategy_dir) / f"{name}.py").read_text(encoding="utf-8")
    assert "AlwaysLong" in content and "来源：研究会话" in content  # provenance 头 + 候选代码

    db.refresh(trial)
    assert trial.promoted_factor_name == name


def test_promote_is_idempotent(promote_env):
    db, strategy_dir = promote_env
    trial = _seed_strategy_trial(db)
    sc = StrategyScenario()

    first = sc.promote(service.trial_to_dict(trial))
    second = sc.promote(service.trial_to_dict(service.get_trial_row(db, trial.id)))
    assert first == second
    # 没有产生第二个文件
    assert len(list(Path(strategy_dir).glob("*.py"))) == 1
