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
    """真实模板冒烟：grid.py 应提取出 lower/upper/levels/position_limit。"""
    src = Path("strategy/templates/grid.py").read_text(encoding="utf-8")
    info = StrategyService()._parse_strategy_file("grid", src)
    names = [p["name"] for p in info["params"]]
    assert {"lower", "upper", "levels"} <= set(names)


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
    """真实模板冒烟：martingale.py 的 direction 应解析为 select + options。"""
    src = Path("strategy/templates/martingale.py").read_text(encoding="utf-8")
    info = StrategyService()._parse_strategy_file("martingale", src)
    direction = next(p for p in info["params"] if p["name"] == "direction")
    assert direction["type"] == "select"
    assert direction["options"] == ["long", "short", "both"]
