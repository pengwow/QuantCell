"""价格计划 — 闭式计算的唯一公式权威（spec §3.1/3.2）。

纪律：预览 API、grid/martingale 策略 on_start 固化、自定义策略 price_plan 类方法
       全部从本模块取公式。任何消费方不得复制公式（契约测试守护）。
约束：无 IO、无状态、不出网络请求；入参出参均为可 JSON 序列化结构。

区间缺省规则（spec §2）：grid_plan 的 params 显式 lower/upper > ref_price ±20% 推导；
       预览 / 启动固化 / 详情三处同走此公式。复核备注：martingale_plan 全部层价
       由 entry=ref_price 相对推导、无绝对价格参数，无需本规则。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

GRID_DEFAULT_SPREAD = 0.20  # grid 缺省区间 = ref ±20%（spec §2，仅 params 未提供时）


class PricePlanLevel(BaseModel):
    """单条计划价位。语义沿用 Action：target_position 正=建/加仓、负=减仓。"""

    index: int
    price: float
    action: Literal["buy", "sell", "tp", "mid"]
    target_position: float
    label: str
    note: str | None = None


class PricePlanSummary(BaseModel):
    price_min: float
    price_max: float
    entry_price: float
    extra: dict[str, Any] = Field(default_factory=dict)  # 档距/中枢/满层仓位/篮子止盈等


class PricePlan(BaseModel):
    levels: list[PricePlanLevel]
    summary: PricePlanSummary
    warnings: list[str] = []


def linear_levels(lower: float, upper: float, count: int) -> list[float]:
    """供自定义策略拼装的通用构件：等距价位数组（含两端，count 条）。"""
    if count <= 0 or upper <= lower:
        return []
    if count == 1:
        return [lower]
    step = (upper - lower) / (count - 1)
    return [lower + i * step for i in range(count)]


def grid_plan(params: dict[str, Any], ref_price: float) -> PricePlan:
    """等距网格计划。公式 = 现 on_bar 档位语义的静态展开（spec 3.1）。

    缺省区间（spec §2）：params 无 lower/upper 时由 ref_price ± GRID_DEFAULT_SPREAD
    推导；键存在但值非法仍走下方 warnings 分支，不做兜底。
    """
    # 键缺失才推导；键存在但值非法走原有 warnings 分支
    if "lower" not in params:
        lower = round(float(ref_price) * (1 - GRID_DEFAULT_SPREAD), 8)
    else:
        lower = float(params["lower"])
    if "upper" not in params:
        upper = round(float(ref_price) * (1 + GRID_DEFAULT_SPREAD), 8)
    else:
        upper = float(params["upper"])
    levels = int(params.get("levels", 20))
    limit = float(params.get("position_limit", 0.1))
    warnings: list[str] = []

    if upper <= lower or levels <= 0:
        warnings.append("网格参数非法（要求 upper > lower 且 levels ≥ 1），请修正后重试")
        return PricePlan(
            levels=[],
            summary=PricePlanSummary(
                price_min=min(lower, upper), price_max=max(lower, upper), entry_price=ref_price, extra={}
            ),
            warnings=warnings,
        )

    half = levels / 2.0
    level_prices = linear_levels(lower, upper, levels + 1)  # demo 定稿：n+1 条档位线
    out: list[PricePlanLevel] = []
    for i, price in enumerate(level_prices):
        target = -(i - half) / half * limit
        if i * 2 == levels:
            out.append(PricePlanLevel(index=i, price=round(price, 10), action="mid", target_position=0.0, label="中枢"))
        elif target > 0:
            out.append(
                PricePlanLevel(
                    index=i, price=round(price, 10), action="buy", target_position=round(target, 10), label="低位挂买"
                )
            )
        else:
            out.append(
                PricePlanLevel(
                    index=i, price=round(price, 10), action="sell", target_position=round(target, 10), label="高位挂卖"
                )
            )
    if not (lower <= ref_price <= upper):
        warnings.append(
            f"参考价 {ref_price:g} 在网格区间外 [{lower:g}, {upper:g}]：启动后将保持 hold 直到价格进入区间（自适应扩展已移除）"
        )
    return PricePlan(
        levels=out,
        summary=PricePlanSummary(
            price_min=lower,
            price_max=upper,
            entry_price=ref_price,
            extra={"step": round((upper - lower) / levels, 10), "bands": levels + 1},
        ),
        warnings=warnings,
    )


def martingale_plan(params: dict[str, Any], ref_price: float) -> PricePlan:
    """分层马丁计划（spec §2.1 闭式公式，仓位口径与现 on_bar 完全同源）。

    price_k = entry × (1 − Σ_{j=1..k} spacing_pct/100 × spacing_multiplier^(j−1))
    pos_k   = position_limit × base_position × min(multiplier^max(k−1, 0), max_multiplier)
              （建仓层 k=0 倍数恒为 1；加仓层按 multiplier^(k−1) 增长，超 max_multiplier 后恒取 max）
    tp      = Σ(p_k×pos_k)/Σ(pos_k) × (1 + take_profit_pct/100)
    """
    entry = float(ref_price)
    spacing_pct = float(params.get("spacing_pct", 2.0))
    spacing_mul = float(params.get("spacing_multiplier", 1.5))
    layer_count = max(1, int(params.get("layer_count", 5)))
    base = float(params.get("base_position", 0.1))
    mult = float(params.get("multiplier", 2.0))
    max_mult = float(params.get("max_multiplier", 4.0))
    limit = float(params.get("position_limit", 0.1))
    tp_pct = float(params.get("take_profit_pct", 1.0))
    warnings: list[str] = []

    buys: list[PricePlanLevel] = []
    dip_total, prices, poss = 0.0, [], []
    for k in range(layer_count):
        if k > 0:
            dip_total += spacing_pct / 100.0 * spacing_mul ** (k - 1)
        price = entry * (1.0 - dip_total)
        # 建仓层（k=0）倍数为 1；加仓层指数 k−1（黄金用例 §5.1：k=2→×2、k=4 截断到 max）
        pos = limit * base * min(mult ** max(k - 1, 0), max_mult)
        if price <= 0:
            warnings.append(
                f"第 {k} 层价格 {price:g} 非正：间距参数累计过大，请调小 spacing_pct/spacing_multiplier 或 layer_count"
            )
            break
        label = "建仓" if k == 0 else f"第 {k + 1} 层加仓"
        buys.append(
            PricePlanLevel(index=k, price=round(price, 10), action="buy", target_position=round(pos, 10), label=label)
        )
        prices.append(price)
        poss.append(pos)

    full = sum(poss)
    if full > limit and buys:
        warnings.append(
            f"满层累计仓位 {full:.0%} 映射到 position_limit {limit:.0%}（内含基数 {base:.0%}）已超上限：max_multiplier 建议 ≤ 4"
        )
    out = list(buys)
    avg = 0.0
    if buys:
        avg = sum(p * q for p, q in zip(prices, poss, strict=True)) / sum(poss)
        tp_price = avg * (1.0 + tp_pct / 100.0)
        out.append(
            PricePlanLevel(
                index=len(buys),
                price=round(tp_price, 10),
                action="tp",
                target_position=0.0,
                label="篮子止盈",
                note=f"篮子加权均价 {avg:g}",
            )
        )
    return PricePlan(
        levels=out,
        summary=PricePlanSummary(
            price_min=min([b.price for b in buys], default=entry),
            price_max=max([b.price for b in buys], default=entry),
            entry_price=entry,
            extra={"full_position": round(full, 10), "basket_avg": round(avg, 10) if buys else 0.0},
        ),
        warnings=warnings,
    )
