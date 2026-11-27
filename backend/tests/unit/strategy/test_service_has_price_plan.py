"""has_price_plan AST 探测 + 注册表注入的单测（spec §3.2/§5.3）"""

import textwrap

from strategy.service import _has_price_plan_method


def _write(tmp_path, body: str):
    f = tmp_path / "demo.py"
    f.write_text(textwrap.dedent(body), encoding="utf-8")
    return f


def test_detects_price_plan_in_class(tmp_path):
    f = _write(
        tmp_path,
        """
        class Foo:
            @classmethod
            def price_plan(cls, params, ref_price):
                return {"levels": [], "summary": {}, "warnings": []}
    """,
    )
    assert _has_price_plan_method(f) is True


def test_ignores_standalone_function(tmp_path):
    # price_plan 定义在类外 = 不算协议声明（协议锚定在策略类上）
    f = _write(
        tmp_path,
        """
        def price_plan(params, ref_price):
            return {}
    """,
    )
    assert _has_price_plan_method(f) is False


def test_syntax_error_returns_false(tmp_path):
    # 探测永不炸：坏文件当作“无计划”处理，注册表其余策略照常
    f = tmp_path / "bad.py"
    f.write_text("def broken(:\n", encoding="utf-8")
    assert _has_price_plan_method(f) is False


def test_builtin_strategies_flagged():
    # get_strategy_service 工厂定义在 routes.py（单例注入层），不在 service.py
    from strategy.routes import get_strategy_service

    svc = get_strategy_service()
    info = svc.get_strategy("grid")
    assert_info_flag(info)  # helper：兼容 dict / 模型两种返回形态


def assert_info_flag(info) -> None:
    flag = info.get("has_price_plan") if isinstance(info, dict) else info.has_price_plan
    assert flag is True
