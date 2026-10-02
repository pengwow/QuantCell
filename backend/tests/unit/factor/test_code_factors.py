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


def test_save_rejects_duplicate_code_under_other_name(service):
    service.save_code_factor("dup_a", MOM_CODE)
    # 同代码换名保存：命中 hash 去重，消息需包含已存在的因子名
    with pytest.raises(FactorError) as exc:
        service.save_code_factor("dup_b", MOM_CODE)
    assert "dup_a" in str(exc.value)


def test_save_same_name_same_code_is_idempotent(service):
    service.save_code_factor("same_one", MOM_CODE)
    # 同名同代码覆盖保存允许（幂等，不抛错），沙箱仍重新校验
    assert service.save_code_factor("same_one", MOM_CODE) is True
    assert set(service._code_store.all()) == {"same_one"}


def test_save_isomorphic_whitespace_deduped(service):
    # 两行语义相同的代码，仅空行/行尾空白差异 → 规范化后同 hash，拒绝
    code_a = 'a = 1\nfactor = df["close"].pct_change(5)'
    code_b = 'a = 1   \n\nfactor = df["close"].pct_change(5)\n\n'
    service.save_code_factor("iso_a", code_a)
    with pytest.raises(FactorError) as exc:
        service.save_code_factor("iso_b", code_b)
    assert "iso_a" in str(exc.value)


def test_legacy_json_without_code_hash_deduped(tmp_path):
    import json

    # 老格式条目无 code_hash 字段：加载时补算，新名保存同代码仍被去重命中
    path = tmp_path / "code_factors.json"
    legacy = {
        "legacy_mom": {
            "code": MOM_CODE,
            "description": "老格式因子",
            "provenance": {"model": "old-model"},
            "created_at": "2026-09-30T00:00:00+00:00",
        }
    }
    path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    svc = FactorService(code_store=CodeFactorStore(path), sandbox=FactorSandbox())
    with pytest.raises(FactorError) as exc:
        svc.save_code_factor("brand_new", MOM_CODE)
    assert "legacy_mom" in str(exc.value)
