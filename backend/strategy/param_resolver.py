"""策略参数按标的覆盖解析（spec 2026-11-28 §3.2，D1 合并唯一出口）。

合并序：公共 params < 标的覆盖；覆盖值 None/'' 视同未覆盖（与表单空值过滤口径一致）。
symbol 键统一经 normalize_symbol_key 规范化（expand_symbol → BASE/QUOTE），
写入端（worker 创建/param-overrides）与读取端（启动/固化/预览/回测）共用同一函数，
避免「存 BTCUSDT 查 BTC/USDT」的键失配。
"""

from __future__ import annotations

from typing import Any

from vocab import expand_symbol

# 视同「未覆盖」的空值（与前端 cleanStrategyParams 的过滤口径一致）
_EMPTY_OVERRIDES = (None, "")


def normalize_symbol_key(symbol: str) -> str:
    """覆盖表存储/查找键的统一形态（BASE/QUOTE，与引擎 instrument key 一致）。"""
    return expand_symbol(symbol)


def resolve_strategy_params(
    base_params: dict[str, Any] | None,
    by_symbol: dict[str, dict[str, Any]] | None,
    symbol: str | None,
) -> dict[str, Any]:
    """合并「公共参数 + 标的覆盖」并返回新 dict（不修改入参）。

    - symbol 为空 / by_symbol 为空或无该标的 → 返回公共参数副本；
    - 覆盖值 None/'' 不参与合并；
    - 策略 schema 默认值不在本函数职责内（由 preview 注册表 / load_strategy 模板兜底），
      这里只做「公共 < 覆盖」两层，避免出现第二套默认值逻辑。
    """
    merged = dict(base_params or {})
    if symbol is None or not by_symbol:
        return merged
    # 存储键也过同一规范化（幂等）：写入端已规范化，这里兜底防「存 BTCUSDT 查 BTC/USDT」键失配。
    # ponytail: 每次调用重建规范化映射是 O(n)（n=标的数，通常个位数），合并唯一出口可接受；
    # 标的规模到百级时改为「先直接 get，miss 再规范化扫描」的惰性兜底。
    normalized = {normalize_symbol_key(k): v for k, v in by_symbol.items()}
    overrides = normalized.get(normalize_symbol_key(symbol))
    if not overrides:
        return merged
    for key, value in overrides.items():
        if value not in _EMPTY_OVERRIDES:
            merged[key] = value
    return merged
