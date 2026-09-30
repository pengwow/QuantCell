# 代码因子接入 FactorService：沙箱计算 → analyze 全指标 → 入库/删除/明细
import pytest

from factor.code_store import CodeFactorStore
from factor.sandbox import FactorSandbox
from factor.service import FactorError, FactorService


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


@pytest.fixture
def service(tmp_path):
    return FactorService(code_store=CodeFactorStore(tmp_path / "code.json"), sandbox=FactorSandbox())


MOM_CODE = 'factor = df["close"].pct_change(5)'


def test_save_and_list_detail(service):
    service.save_code_factor("llm_mom_1", MOM_CODE, description="测试动量")
    details = {d["name"]: d for d in service.get_factor_details()}
    assert "llm_mom_1" in details
    assert details["llm_mom_1"]["kind"] == "code"
    assert details["llm_mom_1"]["category"] == "llm_code"
    assert "llm_mom_1" in service.get_factor_list()


def test_save_rejects_unsafe_code(service):
    from factor.sandbox import SandboxSecurityError

    with pytest.raises(SandboxSecurityError):
        service.save_code_factor("evil", "import os")


def test_save_rejects_builtin_and_expression_name(service):
    with pytest.raises(FactorError):
        service.save_code_factor("close", MOM_CODE)
    service.add_factor("my_expr", "close - open")
    with pytest.raises(FactorError):
        service.save_code_factor("my_expr", MOM_CODE)


def test_save_rejects_bad_name(service):
    with pytest.raises(FactorError):
        service.save_code_factor("1bad", MOM_CODE)


def test_calculate_code_factor(service):
    service.save_code_factor("llm_mom_1", MOM_CODE)
    df = service.calculate_factor("llm_mom_1", ["BTCUSDT"], None, None, provider=FakeProvider())
    assert df.index.names == ["datetime", "symbol"]
    assert list(df.columns) == ["llm_mom_1"]
    assert len(df) == 200


def test_analyze_code_factor(service):
    service.save_code_factor("llm_mom_1", MOM_CODE)
    res = service.analyze("llm_mom_1", ["BTCUSDT", "ETHUSDT"], "1h", "spot", None, None, provider=FakeProvider())
    assert res["factor_name"] == "llm_mom_1"
    assert res["bar_count"] > 50
    assert "coverage" in res["inspection"]


def test_delete_code_factor(service):
    service.save_code_factor("llm_mom_1", MOM_CODE)
    assert service.delete_factor("llm_mom_1") is True
    assert "llm_mom_1" not in service.get_factor_list()


def test_expression_name_collision_blocked(service):
    service.save_code_factor("llm_mom_1", MOM_CODE)
    with pytest.raises(FactorError):
        service.add_factor("llm_mom_1", "close - open")


def test_analyze_expression_still_works(service):
    # 回归：表达式因子路径行为不变
    res = service.analyze("momentum_5d", ["BTCUSDT"], "1h", "spot", None, None, provider=FakeProvider())
    assert res["bar_count"] > 0
