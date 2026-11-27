"""StrategyService 参数 AST 提取（self.get_param / self._param + _DEFAULTS）。

回归背景：11 个内置模板全用 self.get_param("k", v) 取参，旧提取器只认
self.config.params.get(...)，导致前端参数表单全部显示"无可配置参数"。
"""

import ast
from pathlib import Path

from strategy.service import StrategyService

GET_PARAM_SRC = """
class Dummy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)

    def on_bar(self, bar, ctx):
        fast = self.get_param("fast", 10)
        slow = self.get_param("slow", 30)
        # 非 self 接收者不应被提取
        other.get_param("noise", 1)
        return None
"""

PARAM_DEFAULTS_SRC = """
class Dummy2(BaseStrategy):
    _DEFAULTS = {
        "entry_threshold": 0.0003,
        "min_hold_bars": 8,
        "enabled": True,
    }

    def on_bar(self, bar, ctx):
        entry = self._param("entry_threshold")
        hold = self._param("min_hold_bars")
        flag = self._param("enabled")
        return None
"""


def _params(src: str) -> dict[str, dict]:
    tree = ast.parse(src)
    return {p["name"]: p for p in StrategyService._extract_params_from_get_param(tree)}


def test_extract_get_param_with_defaults():
    ps = _params(GET_PARAM_SRC)
    assert ps["fast"] == {"name": "fast", "type": "int", "default": 10, "description": "", "required": False}
    assert ps["slow"]["default"] == 30
    # 非 self 接收者不提取
    assert "noise" not in ps


def test_extract_param_with_class_defaults():
    ps = _params(PARAM_DEFAULTS_SRC)
    assert ps["entry_threshold"]["default"] == 0.0003
    assert ps["entry_threshold"]["type"] == "float"
    assert ps["min_hold_bars"]["default"] == 8
    # bool 必须在 int 判断前识别
    assert ps["enabled"]["default"] is True and ps["enabled"]["type"] == "bool"


def test_builtin_grid_template_has_params():
    """真实模板冒烟：grid.py 应提取出完整价格计划配置项（区间/档位/仓位上限）。"""
    from strategy.service import _has_price_plan_method

    src = Path("strategy/templates/grid.py").read_text(encoding="utf-8")
    info = StrategyService()._parse_strategy_file("grid", src)
    names = [p["name"] for p in info["params"]]
    # 2026-11 模板计划型升级：创建表单必须完整覆盖 grid_plan 公式四件套
    assert {"lower", "upper", "levels", "position_limit"} <= set(names)
    # has_price_plan 协议探测（与落盘 strategies/{name}.py 的探测同一函数本体）
    assert _has_price_plan_method(Path("strategy/templates/grid.py"))


LITERAL_BINDING_SRC = """
from typing import Literal

class Dummy3(BaseStrategy):
    def on_bar(self, bar, ctx):
        direction: Literal["long", "short", "both"] = self.get_param("direction", "long")
        fast = self.get_param("fast", 10)
        return None
"""


def test_literal_annotation_param_becomes_select():
    """Literal 注解 + get_param 绑定 → type=select + options；普通参数不受影响。"""
    ps = _params(LITERAL_BINDING_SRC)
    assert ps["direction"] == {
        "name": "direction",
        "type": "select",
        "default": "long",
        "description": "",
        "required": False,
        "options": ["long", "short", "both"],
    }
    # 无 Literal 注解的参数走普通逻辑：不带 options 键（既有测试断言精确 dict，不能多键）
    assert ps["fast"] == {"name": "fast", "type": "int", "default": 10, "description": "", "required": False}


def test_duplicate_literal_binding_extracted_once():
    """同名 Literal 绑定出现在多个方法（如 direction 在 _fix_plan/_open 各取一次）
    → 只提取一次。回归背景：2026-11-27 实测 templates 接口返回了两个 direction，
    表单会渲染重复字段（AnnAssign 分支漏检 seen）。"""
    src = """
from typing import Literal

class Dummy6(BaseStrategy):
    def _fix_plan(self):
        direction: Literal["long", "short", "both"] = self.get_param("direction", "long")
        return direction

    def _open(self, bar):
        direction: Literal["long", "short", "both"] = self.get_param("direction", "long")
        return direction
"""
    ps = _params(src)
    assert list(ps) == ["direction"]
    assert ps["direction"]["options"] == ["long", "short", "both"]


def test_literal_binding_requires_name_match():
    """注解目标名与 get_param 首参不一致 → 不绑定，内层 Call 降级为普通条目。"""
    src = """
class Dummy4(BaseStrategy):
    def on_bar(self, bar, ctx):
        direction: Literal["long", "short"] = self.get_param("dir", "long")
        return None
"""
    ps = _params(src)
    assert ps["dir"] == {"name": "dir", "type": "str", "default": "long", "description": "", "required": False}
    assert "direction" not in ps


def test_non_string_literal_not_binding():
    """Literal 选项含非字符串常量（int 枚举）→ 不绑定，降级普通条目。"""
    src = """
class Dummy5(BaseStrategy):
    def on_bar(self, bar, ctx):
        level: Literal[1, 2, 3] = self.get_param("level", 1)
        return None
"""
    ps = _params(src)
    assert ps["level"] == {"name": "level", "type": "int", "default": 1, "description": "", "required": False}


def test_martingale_template_direction_is_select():
    """真实模板冒烟：direction select + 价格计划配置项完整（2026-11 计划型模板）。"""
    from strategy.service import _has_price_plan_method

    martingale_src = Path("strategy/templates/martingale.py").read_text(encoding="utf-8")
    info = StrategyService()._parse_strategy_file("martingale", martingale_src)
    direction = next(p for p in info["params"] if p["name"] == "direction")
    assert direction["type"] == "select"
    assert direction["options"] == ["long", "short", "both"]
    # 价格计划完整配置项必须在创建表单提取源中（spacing/layer/take_profit 为 2026-11 补充）
    names = [p["name"] for p in info["params"]]
    assert {
        "base_position",
        "multiplier",
        "max_multiplier",
        "position_limit",
        "spacing_pct",
        "spacing_multiplier",
        "layer_count",
        "take_profit_pct",
    } <= set(names)
    assert _has_price_plan_method(Path("strategy/templates/martingale.py"))


def test_merge_db_params_backfills_select_options():
    """DB 旧记录缺 options → 按 name 用 AST 同名 select 参数补 type+options。"""
    db_params = [
        {"name": "direction", "type": "str", "default": "long", "description": "方向", "required": False},
        {"name": "base_position", "type": "float", "default": 0.1, "description": "", "required": False},
    ]
    ast_params = [
        {
            "name": "direction",
            "type": "select",
            "default": "long",
            "description": "",
            "required": False,
            "options": ["long", "short", "both"],
        },
    ]
    merged = StrategyService._merge_db_params_with_ast(db_params, ast_params)
    # DB 值全保留，仅渲染能力（type/options）由 AST 补
    assert merged[0] == {
        "name": "direction",
        "type": "select",
        "default": "long",
        "description": "方向",
        "required": False,
        "options": ["long", "short", "both"],
    }
    # AST 不认识的参数原样保留
    assert merged[1] == db_params[1]
