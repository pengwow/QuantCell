"""preview API 全链路（spec §5.3/§5.4）：happy path / 422 / 缺参回退 / 协议泛化"""

import shutil
import sys

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

GRID_PARAMS = {"lower": 62000.0, "upper": 68000.0, "levels": 8, "position_limit": 1000.0}


def test_grid_preview_equals_price_plan_module():
    """同源主证：API 输出 == 直接调 grid_plan（Task 1 纯函数）"""
    from strategy.price_plan import grid_plan

    api = client.post(
        "/api/v1/strategies/preview",
        json={"strategy_name": "grid", "params": GRID_PARAMS, "ref_price": 65123.45},
    )
    assert api.status_code == 200
    body = api.json()["data"]
    body.pop("params_resolved")
    assert body == grid_plan(GRID_PARAMS, 65123.45).model_dump()


def test_grid_preview_ref_outside_range_warns():
    r = client.post(
        "/api/v1/strategies/preview",
        json={"strategy_name": "grid", "params": GRID_PARAMS, "ref_price": 90000.0},
    )
    body = r.json()["data"]
    assert r.status_code == 200
    assert body["warnings"], "参考价在区间外必须有 warnings（spec §6 网格出界）"


def test_preview_missing_ref_price_422():
    r = client.post("/api/v1/strategies/preview", json={"strategy_name": "grid", "params": GRID_PARAMS})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "REF_PRICE_REQUIRED"


def test_preview_unsupported_strategy_422():
    from strategy.routes import get_strategy_service

    names = [
        (s if isinstance(s, dict) else {"name": s.name, "has_price_plan": s.has_price_plan})
        for s in get_strategy_service().list_strategies()
    ]
    plain = [n for n in names if not n["has_price_plan"]]
    assert plain, "注册表里必然存在未声明协议的内置策略"
    r = client.post(
        "/api/v1/strategies/preview",
        json={"strategy_name": plain[0]["name"], "params": {}, "ref_price": 1.0},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "PLAN_UNSUPPORTED"


FIXT_STRATEGY = '''\
"""临时 fixture 策略：验证任意自定义策略声明 price_plan 即自动获得预览（spec §3.2）"""
from strategy.base import BaseStrategy
from strategy.price_plan import PricePlan, PricePlanLevel, PricePlanSummary


class ZzPlanFixt(BaseStrategy):
    name = "zz_plan_fixt"

    def on_bar(self, bar, ctx=None):
        from strategy.core import Action, ActionType

        return Action(ActionType.Hold, 0.0, 0.0, self.name, 0)

    @staticmethod
    def price_plan(params, ref_price):
        ref = float(ref_price)
        lvl = PricePlanLevel(index=0, price=ref, action="buy", target_position=0.1, label="入场")
        summ = PricePlanSummary(price_min=ref, price_max=ref, entry_price=ref, extra={})
        return PricePlan(levels=[lvl], summary=summ, warnings=[])
'''


@pytest.fixture()
def registry_strategy(tmp_path):
    """把临时策略落进注册表目录（strategies/ 下模块名即策略名），结束后移到 tmp（仓库规范：不用 rm）。

    目录取 service 的 strategy_dir（跟随 QUANTCELL_DATA_DIR 重定向，不硬编码相对路径）。
    """
    from strategy.routes import get_strategy_service

    target = get_strategy_service().strategy_dir / "zz_plan_fixt.py"
    stale = tmp_path / "zz_plan_fixt.py"
    target.write_text(FIXT_STRATEGY, encoding="utf-8")
    sys.modules.pop("strategies.zz_plan_fixt", None)  # 清残留，防后续用例取到旧模块
    yield "zz_plan_fixt"
    shutil.move(str(target), str(stale))  # rename 跨设备（ExtDisk→系统 tmp）会 EXDEV，shutil.move 自动兜底
    sys.modules.pop("strategies.zz_plan_fixt", None)


def test_custom_strategy_protocol_full_chain(registry_strategy):
    r = client.post(
        "/api/v1/strategies/preview",
        json={"strategy_name": registry_strategy, "params": {}, "ref_price": 100.0},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["levels"][0]["label"] == "入场"
    assert body["params_resolved"] == {}
