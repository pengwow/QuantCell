"""方向词汇 canonical 契约与归一层（single source of truth，设计文档 §3）。

三条铁律：
1. 落库/传输/类型/日志只允许 canonical 小写；交易所原生大小写（BINANCE 返回的
   "BUY"、"LONG" 等）只存在于 exchange adapter 边界内，跨越本模块即被归一。
2. Side 不携带仓位信息；PositionSide 是「下单时声明的仓位归属」，不从 side 推导。
   成交/订单行上的 position_side 是声明值透传（回报直取或固定 both），不是算出来的。
3. 展示一律 i18n，任何文案/翻译逻辑不得进入本模块。
"""

from typing import Literal, cast

Side = Literal["buy", "sell"]
PositionSide = Literal["long", "short", "both"]

_SIDES = frozenset({"buy", "sell"})
_POSITION_SIDES = frozenset({"long", "short", "both"})


def normalize_side(value: str) -> Side:
    """任意大小写的 side（含两侧空白）归一为 canonical 小写；非法值抛 ValueError。"""
    v = str(value or "").strip().lower()
    if v in _SIDES:
        return cast(Side, v)
    raise ValueError(f"invalid side: {value!r}（期望 buy/sell，大小写均可）")


def normalize_position_side(value: str) -> PositionSide:
    """任意大小写的 position_side 归一为 canonical 小写；非法值抛 ValueError。"""
    v = str(value or "").strip().lower()
    if v in _POSITION_SIDES:
        return cast(PositionSide, v)
    raise ValueError(f"invalid position_side: {value!r}（期望 long/short/both，大小写均可）")
