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
