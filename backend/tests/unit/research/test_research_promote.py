"""promote 契约：幂等、provenance 合并、复用既有因子入库路径。"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import factor.service as factor_service_module
import research.scenarios.factor as factor_scenario_module
import strategy.models  # 注册 Strategy，保证 Worker 关系的 mapper 可初始化
from collector.db.database import Base
from factor.engine import code_hash
from factor.models import FactorCatalog
from factor.service import FactorService
from research import service
from research.models import ResearchKnowledge, ResearchSession, ResearchTrial
from research.scenarios.factor import FactorScenario

CODE = "def calc(df):\n    return df['close'].pct_change(5)\n"


class _NoopSandbox:
    """静态校验即可；单测不真的拉起沙箱子进程。"""

    def validate(self, code: str) -> None:
        return None


@pytest.fixture()
def promote_env(monkeypatch):
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        eng,
        tables=[
            ResearchSession.__table__,
            ResearchTrial.__table__,
            ResearchKnowledge.__table__,
            FactorCatalog.__table__,
        ],
    )
    Session = sessionmaker(bind=eng)
    db = Session()

    @contextmanager
    def fake_db():
        yield db

    # promote / save_code_factor / update_trial 都走同一个内存会话
    monkeypatch.setattr(factor_scenario_module, "get_db_session", fake_db)
    monkeypatch.setattr(factor_service_module, "get_db_session", fake_db)
    yield db, fake_db


def _seed_trial(db) -> ResearchTrial:
    session = service.create_session(
        db,
        owner_id="u1",
        name="deep-test",
        mode="deep",
        scenario="factor",
        config={"loop_n": 1},
        n_candidates=1,
    )
    service.set_session_status(db, session, "running")
    return service.add_trial(
        db,
        session.id,
        {
            "loop_idx": 1,
            "candidate_idx": 1,
            "status": "judged",
            "hypothesis": "量价背离",
            "code": CODE,
            "code_hash": code_hash(CODE),
        },
    )


def test_promote_writes_catalog_and_provenance(promote_env):
    db, _ = promote_env
    trial = _seed_trial(db)
    scenario = FactorScenario(service=FactorService(sandbox=_NoopSandbox()))

    name = scenario.promote(service.trial_to_dict(trial))
    assert name == f"rs_{trial.session_id}_{trial.id}"

    row = db.query(FactorCatalog).filter_by(name=name).one()
    assert row.kind == "code"  # factorSource() 按 kind 判定为 code，既有筛选不受影响
    assert row.category == "llm_code"
    assert row.lifecycle_status == "DISCOVERED"
    provenance = json.loads(row.provenance)
    assert provenance["source"] == "research"
    assert provenance["session_id"] == trial.session_id
    assert provenance["trial_id"] == trial.id

    db.refresh(trial)
    assert trial.promoted_factor_name == name


def test_promote_is_idempotent(promote_env):
    db, _ = promote_env
    trial = _seed_trial(db)
    scenario = FactorScenario(service=FactorService(sandbox=_NoopSandbox()))

    first = scenario.promote(service.trial_to_dict(trial))
    # 模拟路由每次从 DB 重建 payload
    second = scenario.promote(service.trial_to_dict(service.get_trial_row(db, trial.id)))

    assert first == second
    assert db.query(FactorCatalog).filter_by(kind="code").count() == 1


def test_promote_reuses_existing_code_factor_and_keeps_source(promote_env):
    """同代码已在库里（例如 quick 挖掘产出）时复用既有因子，不改原 source。"""
    db, _ = promote_env
    trial = _seed_trial(db)
    db.add(
        FactorCatalog(
            name="legacy_momentum",
            kind="code",
            code=CODE,
            code_hash=code_hash(CODE),
            category="llm_code",
            provenance=json.dumps({"source": "llm_mine"}),
            lifecycle_status="DISCOVERED",
        )
    )
    db.commit()
    scenario = FactorScenario(service=FactorService(sandbox=_NoopSandbox()))

    name = scenario.promote(service.trial_to_dict(trial))
    assert name == "legacy_momentum"

    row = db.query(FactorCatalog).filter_by(kind="code").one()
    provenance = json.loads(row.provenance)
    assert provenance["source"] == "llm_mine"  # 保留原取值
    assert provenance["session_id"] == trial.session_id
    assert provenance["trial_id"] == trial.id
    assert db.query(FactorCatalog).filter_by(kind="code").count() == 1
