"""滑点成本曲线（P4-1 v1）：名义成交额分档 → 单笔成本 bps 查表。

设计边界
--------
- **只做「量 → 成本」曲线**：给定一笔成交的名义额（quote 单位），产出该笔的
  成本率（bps → rate）。档位是**折线节点**，档间线性插值、两端钳制。
- **不承诺 L2 撮合**：曲线不是逐档深度吃单模型，也不模拟冲击的时序衰减。
  它只把「大单更贵」写成一个可标定的标量函数。
- **没数据就不编**：不内置默认曲线。未显式配置 `CostProfile.slippage_curve`
  时行为与 P2 的标量费率完全一致（零漂移），见 `services/rl_service.py`。

数据通路（2026-11-18 侦察结论）
------------------------------
collector **已有** bookTicker 通道，无需新建采集器：

- 采集入口：`collector/api/archive.py` 的 ``POST /api/data/archive/download``
  （``kind=bookTicker`` 在 `collector/schemas/data.py` 的 ``_ARCHIVE_TYPES`` 里）
  → `collector/services/archive_service.py::ArchiveService.create_download_task`
  → `exchange/binance/archive/fetchers/book_ticker.py::BookTickerFetcher`。
- 落盘（`BinanceArchiveFactory` / `get_save_dir` 决定）：
  ``<base_dir>/<market>/bookTicker/<SYMBOL>/<SYMBOL>-bookTicker-<date>.parquet``。
  7 列 schema 见 `book_ticker.py` 的 ``BOOK_TICKER_SCHEMA``：
  ``update_id / timestamp / symbol / best_bid_price / best_bid_qty / best_ask_price / best_ask_qty``。
  base_dir 有两个来源：`collector/config.py::get_archive_base_dir`（默认
  ``data/source/archive``，走 REST API）与 `ArchiveCollector` 门面（默认
  ``data/source``）。两者用的是同一套 ``<market>/<kind>/<symbol>`` 布局。
- 查询：``GET /api/data/archive/data``；进程内直接 ``pd.read_parquet(<目录>/*.parquet)``。
- 注意：`backtest/data_adapters/base_adapter.py::_find_parquet` 期望的是
  ``<source>/<data_type>/<market>/<symbol>/``（训练取数布局），与归档落点不同；
  标定直接读归档目录即可，不必先搬成适配器布局，也不要指望适配器能扫到。

spread **不单独落盘**：它是 bid/ask 的派生量，存两份必然与原始盘口对不齐。
「最小补丁」= 读的时候现算（`relative_spread_bps`），因此 collector 侧零改动
（该通道已能下载 + 查询，只是还没人跑过）。回测/训练侧派生列见
`backtest/data_adapters/orderbook_adapter.py`：``feature_spread``（绝对价差，quote
单位）+ ``feature_mid_price``，可直接过 `relative_spread_bps` 换 bps。

本地实测（``backend/data/source``）只有空的 ``spot/bookTicker`` / ``um/bookTicker``
目录，**零 parquet**（现有 41 个 parquet 全是 kline）。所以本仓还没有可用于标定的
真实观测——`calibrate_curve` 是为「有数据那天」准备的，v1 不编默认曲线。

ponytail: v1 一条全局曲线（不分交易对/时段）。要做 per-symbol 曲线时，升级路径是
把曲线塞进 `CostProfile.by_symbol` 同构的嵌套映射，而不是再加一层类。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

#: bps → 小数费率
BPS = 1e-4

#: 默认名义额档位（quote，如 USDT）：1 万 / 10 万 / 100 万。
#: 只作为 `calibrate_curve` 的缺省骨架，不是内置曲线——没标定就不生效。
DEFAULT_NOTIONAL_TIERS: tuple[float, ...] = (10_000.0, 100_000.0, 1_000_000.0)

#: 默认分位点：p50 → 首档，p90 → 中档，p99 → 高档。
DEFAULT_QUANTILES: tuple[float, ...] = (0.5, 0.9, 0.99)


@dataclass(frozen=True)
class SlippageCurve:
    """名义成交额分档的成本曲线（折线 + 线性插值 + 端点钳制）。

    `tiers` 是 ``(notional, cost_bps)`` 节点序列，名义额必须严格递增、成本非负，
    至少 2 档。节点之间线性插值；低于首档取首档成本，高于末档取末档成本
    （大单不因超出标定范围而免费，也不外推到无穷）。

    单位约定：``notional`` 是 quote 货币名义额（USDT 等），``cost_bps`` 是该笔
    成交**总成本**（费率 + 滑点）相对名义额的万分比，两者不混用。
    """

    tiers: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        points = tuple((float(n), float(b)) for n, b in self.tiers)
        object.__setattr__(self, "tiers", points)
        if len(points) < 2:
            msg = f"滑点曲线至少需要 2 档，当前 {len(points)} 档"
            raise ValueError(msg)
        previous: float | None = None
        for notional, bps in points:
            if not math.isfinite(notional) or notional < 0:
                msg = f"滑点曲线名义额档位必须是有限非负数: {notional}"
                raise ValueError(msg)
            if previous is not None and notional <= previous:
                msg = f"滑点曲线名义额档位必须严格递增: {previous} -> {notional}"
                raise ValueError(msg)
            if not math.isfinite(bps) or bps < 0:
                msg = f"滑点曲线成本必须是有限非负数(bps): {bps}"
                raise ValueError(msg)
            previous = notional

    @property
    def notionals(self) -> tuple[float, ...]:
        return tuple(notional for notional, _ in self.tiers)

    @property
    def costs_bps(self) -> tuple[float, ...]:
        return tuple(bps for _, bps in self.tiers)

    def cost_bps(self, notional: float) -> float:
        """按名义额取成本（bps）。负数/非有限额显式报错，不静默当 0。"""
        value = float(notional)
        if not math.isfinite(value) or value < 0:
            msg = f"名义成交额必须是有限非负数: {notional}"
            raise ValueError(msg)
        return float(np.interp(value, self.notionals, self.costs_bps))

    def cost_rate(self, notional: float) -> float:
        """按名义额取成本率（小数费率，供训练环境 / 内核标量口径使用）。"""
        return self.cost_bps(notional) * BPS

    def representative_rate(self) -> float:
        """首档成本率——内核只吃标量 ``fee_rate`` 时的近似代表值。

        首档是最保守（最便宜）的一端：它等价于「每笔名义额都不超过首档」的假设。
        真实大单更贵，内核回测因此可能低估成本，见 `services/rl_service.py` 的
        `_cost_rate` 语义说明。
        """
        return self.cost_rate(self.notionals[0])

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> SlippageCurve:
        """从 JSON 友好的 dict 构造：``{"tiers": [[notional, bps], ...]}``。"""
        if not isinstance(raw, dict):
            msg = f"slippage_curve 必须是 dict，当前 {type(raw).__name__}"
            raise ValueError(msg)
        unknown = set(raw) - {"tiers"}
        if unknown:
            msg = f"未知 slippage_curve 字段: {sorted(unknown)}"
            raise ValueError(msg)
        tiers = raw.get("tiers")
        if not isinstance(tiers, (list, tuple)):
            msg = "slippage_curve 缺少 tiers 列表"
            raise ValueError(msg)
        points: list[tuple[float, float]] = []
        for entry in tiers:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                msg = f"slippage_curve.tiers 结构非法（需要 [[名义额, 成本bps], ...]）: {entry!r}"
                raise ValueError(msg)
            try:
                points.append((float(entry[0]), float(entry[1])))
            except (TypeError, ValueError) as exc:
                msg = f"slippage_curve.tiers 含非数值项: {entry!r}"
                raise ValueError(msg) from exc
        return cls(tuple(points))

    def to_mapping(self) -> dict[str, Any]:
        """序列化为 JSON 友好 dict（meta 落盘 / API 回显用）。"""
        return {"tiers": [[notional, bps] for notional, bps in self.tiers]}


def relative_spread_bps(spread: Any, mid: Any) -> np.ndarray:
    """绝对价差（quote 单位）→ 相对价差（bps）。

    bookTicker 的 ``best_ask_price - best_bid_price``（或适配器的
    ``feature_spread``）是绝对价差，成本却要按名义额的比例算，所以必须除以
    中间价。``mid`` 可以是标量或与 ``spread`` 同形状的序列。
    非正/非有限的中间价会产出 inf/NaN——交给调用方过滤，不在这里吞掉。
    """
    spread_arr = np.asarray(spread, dtype=np.float64)
    mid_arr = np.asarray(mid, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        return spread_arr / mid_arr * 10_000.0


def calibrate_curve(
    spread_obs: Any,
    *,
    mid_price: float | None = None,
    notional_tiers: tuple[float, ...] = DEFAULT_NOTIONAL_TIERS,
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES,
    buffer_bps: float = 1.0,
    fee_bps: float = 0.0,
) -> SlippageCurve:
    """从观测价差分布一键标定曲线。

    每个分位点对应一个名义额档：p50 → 首档、p90 → 中档、p99 → 高档
    （按顺序一一对应，长度必须一致）。单笔成本取「半个价差」——吃单方跨越
    买卖价差时平均只付一半——再叠加 ``buffer_bps`` 安全边际与 ``fee_bps`` 费率。

    Args:
        spread_obs: 观测价差。给 ``mid_price`` 时按 quote 单位（binance
            bookTicker 原值）；不给时按相对 bps（调用方已用 `relative_spread_bps`
            换算）。
        mid_price: 标量中间价，用于把绝对价差换成 bps。每 bar 中间价不同的场景
            请先自行换算成 bps 再传入。
        notional_tiers: 名义额档位（严格递增，长度 = ``quantiles`` 长度）。
        quantiles: 分位点，必须递增且落在 (0, 1)。
        buffer_bps: 安全边际（bps），覆盖未建模的冲击与延迟。
        fee_bps: 交易所费率（bps）。曲线是**总成本**口径，替换标量费率时若不计入
            费率，等于白送手续费。

    Raises:
        ValueError: 观测为空 / 全为无效值 / 档位与分位点长度不一致 / 参数非法。
    """
    values = np.asarray(list(spread_obs) if not isinstance(spread_obs, np.ndarray) else spread_obs, dtype=np.float64)
    values = values[np.isfinite(values)]
    values = values[values >= 0]
    if values.size == 0:
        msg = "标定失败：spread 观测为空或全为无效值"
        raise ValueError(msg)
    if mid_price is not None:
        if not math.isfinite(float(mid_price)) or float(mid_price) <= 0:
            msg = f"标定失败：mid_price 必须是有限正数: {mid_price}"
            raise ValueError(msg)
        values = values / float(mid_price) * 10_000.0
    if len(notional_tiers) != len(quantiles):
        msg = f"名义额档位与分位点数量必须一致: {len(notional_tiers)} != {len(quantiles)}"
        raise ValueError(msg)
    for q in quantiles:
        if not 0.0 < float(q) < 1.0:
            msg = f"分位点必须落在 (0, 1): {q}"
            raise ValueError(msg)
    if not math.isfinite(buffer_bps) or buffer_bps < 0 or not math.isfinite(fee_bps) or fee_bps < 0:
        msg = f"buffer_bps / fee_bps 必须是有限非负数: {buffer_bps} / {fee_bps}"
        raise ValueError(msg)

    quantile_spreads = np.quantile(values, np.asarray(quantiles, dtype=np.float64))
    tiers = tuple(
        (float(notional), float(spread) / 2.0 + float(buffer_bps) + float(fee_bps))
        for notional, spread in zip(notional_tiers, quantile_spreads, strict=True)
    )
    return SlippageCurve(tiers)
