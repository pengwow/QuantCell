# 代码因子接入 FactorService：沙箱计算 → analyze 全指标 → 入库/删除/明细
import pytest

from factor.service import FactorError


class FakeProvider:
    def __init__(self, n=200):
        import numpy as np
        import pandas as pd

        self.n = n
        rng = np.random.default_rng(1)
        close = 100 + np.cumsum(rng.normal(0, 1, n))
        ts = pd.date_range("2026-01-01", periods=n, freq="1h")
        self.df = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": rng.uniform(100, 1000, n),
                "quote_volume": close * rng.uniform(100, 1000, n),
                "timestamp": ts.astype("int64"),
            }
        )

    def get_kline_data(self, symbol, interval, candle_type, start, end, columns=None):
        return self.df.copy()


MOM_CODE = 'factor = df["close"].pct_change(5)'


def test_save_and_list_detail(svc):
    svc.save_code_factor("llm_mom_1", MOM_CODE, description="测试动量")
    details = {d["name"]: d for d in svc.get_factor_details()}
    assert "llm_mom_1" in details
    assert details["llm_mom_1"]["kind"] == "code"
    assert details["llm_mom_1"]["category"] == "llm_code"
    assert "llm_mom_1" in svc.get_factor_list()


def test_save_rejects_unsafe_code(db_session, monkeypatch):
    from contextlib import contextmanager

    from factor.sandbox import FactorSandbox, SandboxSecurityError
    from factor.service import FactorService

    @contextmanager
    def _fake_get_db_session():
        yield db_session

    monkeypatch.setattr("factor.service.get_db_session", _fake_get_db_session)
    # 这个测试用真实沙箱：测安全策略拒绝 import os
    svc = FactorService(sandbox=FactorSandbox())
    with pytest.raises(SandboxSecurityError):
        svc.save_code_factor("evil", "import os")


def test_save_rejects_builtin_and_expression_name(svc):
    with pytest.raises(FactorError):
        svc.save_code_factor("close", MOM_CODE)
    svc.add_factor("my_expr", "close - open")
    with pytest.raises(FactorError):
        svc.save_code_factor("my_expr", MOM_CODE)


def test_save_rejects_bad_name(svc):
    with pytest.raises(FactorError):
        svc.save_code_factor("1bad", MOM_CODE)


def test_delete_code_factor(svc):
    svc.save_code_factor("llm_mom_1", MOM_CODE)
    assert svc.delete_factor("llm_mom_1") is True
    assert "llm_mom_1" not in svc.get_factor_list()


def test_expression_name_collision_blocked(svc):
    svc.save_code_factor("llm_mom_1", MOM_CODE)
    with pytest.raises(FactorError):
        svc.add_factor("llm_mom_1", "close - open")


def test_save_rejects_duplicate_code_under_other_name(svc):
    svc.save_code_factor("dup_a", MOM_CODE)
    with pytest.raises(FactorError) as exc:
        svc.save_code_factor("dup_b", MOM_CODE)
    assert "dup_a" in str(exc.value)


def test_save_same_name_same_code_is_idempotent(svc):
    svc.save_code_factor("same_one", MOM_CODE)
    assert svc.save_code_factor("same_one", MOM_CODE) is True
    assert set(svc._code_map) == {"same_one"}


def test_save_isomorphic_whitespace_deduped(svc):
    code_a = 'a = 1\nfactor = df["close"].pct_change(5)'
    code_b = 'a = 1   \n\nfactor = df["close"].pct_change(5)\n\n'
    svc.save_code_factor("iso_a", code_a)
    with pytest.raises(FactorError) as exc:
        svc.save_code_factor("iso_b", code_b)
    assert "iso_a" in str(exc.value)
