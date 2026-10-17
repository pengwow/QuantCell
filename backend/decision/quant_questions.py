"""SDM v2 状态与问题模板（quant_questions）。

v2 相对 v1 (questions.py) 的增量：
- 特征集：v1 全部 5 个 + 新增 3 个（close_vs_sma20 / rsi_14 / volume_ratio）
- 问题：v1 全部 4 个（键名不变，cascade 层硬编码依赖）+ 新增 4 个

向后兼容：v1 函数 build_state()/build_questions() 保持不动。
v2 函数使用 build_state_v2()/build_questions_v2()/build_full_v2()。

Schema 对齐：本文件与 axon_quant crates/axon-llm/src/decision/quant_questions.rs
逐字段同构，Rust stub 后端必须能解析本模块输出的 state/questions。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

# ═══════════════════════════════════════════════════════════════════════
# V2 特征集
# ═══════════════════════════════════════════════════════════════════════

# 冻结顺序：Rust stub 按此名表读取，新增/改名必须同步
FEATURE_NAMES_V2: tuple[str, ...] = (
    # —— v1 既有，保留不动（cascade/stub 已硬编码依赖）
    "ret_1",
    "ret_5",
    "vol_20",
    "sma5_vs_sma20",
    "volume_z",
    # —— v2 新增
    "close_vs_sma20",
    "rsi_14",
    "volume_ratio",
)

_ROUND = 6


def _r6(x: float) -> float:
    return round(float(x), _ROUND)


def compute_features_v2(window: pd.DataFrame) -> dict[str, float]:
    """从 >= 20 根 bar 的 DataFrame 计算 v2 完整特征集（8 个）。"""
    close = window["close"].astype(float)
    volume = window["volume"].astype(float)
    pct = close.pct_change().dropna()

    # v1 全部 5 个（与 questions.py.compute_features 完全同算法，零漂移）
    ret_1 = close.iloc[-1] / close.iloc[-2] - 1.0
    ret_5 = close.iloc[-1] / close.iloc[-6] - 1.0
    vol_20 = float(pct.std(ddof=0))
    sma5 = float(close.tail(5).mean())
    sma20 = float(close.tail(20).mean())
    vol_std = float(volume.std(ddof=0))
    volume_z = 0.0 if vol_std == 0.0 else (float(volume.iloc[-1]) - float(volume.mean())) / vol_std

    # v2 新增 3 个
    close_vs_sma20 = close.iloc[-1] / sma20 - 1.0
    rsi_14 = _compute_rsi(close, period=14)
    volume_sma = float(volume.tail(20).mean())
    volume_ratio = 0.0 if volume_sma == 0 else float(volume.iloc[-1]) / volume_sma

    values = (ret_1, ret_5, vol_20, sma5 / sma20 - 1.0, volume_z, close_vs_sma20, rsi_14, volume_ratio)
    return {name: _r6(v) for name, v in zip(FEATURE_NAMES_V2, values, strict=True)}


def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    """Wilder's RSI，0-100。close 长度必须足够。"""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period, min_periods=period).mean()
    rs = gain / loss.replace(0, 1e-12)
    return float(100.0 - (100.0 / (1.0 + rs)).iloc[-1])


# ═══════════════════════════════════════════════════════════════════════
# V2 State 构造
# ═══════════════════════════════════════════════════════════════════════


def _to_ms(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    if text.isdigit():
        return int(text)
    return int(pd.Timestamp(text).timestamp() * 1000)


def build_state_v2(window: pd.DataFrame, *, symbol: str, bar_type: str) -> dict:
    """构造 v2 state：精简 bar 序列 + v2 完整特征集。

    window 必须 >= 20 根 bar。精简 bar 只保留最近 20 根（SDM 看近期形态即可）。
    """
    rows = [
        {
            "t": _to_ms(row["timestamp"]),
            "o": _r6(row["open"]),
            "h": _r6(row["high"]),
            "l": _r6(row["low"]),
            "c": _r6(row["close"]),
            "v": _r6(row["volume"]),
        }
        for _, row in window.tail(20).iterrows()
    ]
    return {
        "symbol": symbol,
        "bar_type": bar_type,
        "window": rows,
        "features": compute_features_v2(window),
    }


# ═══════════════════════════════════════════════════════════════════════
# V2 问题模板
# ═══════════════════════════════════════════════════════════════════════


def build_questions_v2(*, cost_threshold: float) -> dict[str, dict]:
    """构造 v2 完整问题集：v1 全部 4 个 + 新增 4 个 = 8 个问题。

    v1 的 4 个键名保持不变，cascade 层硬编码了：
      - "next_direction"  — 主决策 gate
      - "trend_confirms"  — 子信号归因
      - "risk_regime_bad" — 子信号归因
      - "signal_clarity"  — 子信号归因

    新增 4 个问题不参与 cascade gate，供上层 Harness Router 消费。
    """
    pct_text = f"{cost_threshold * 100:.2f}%"

    return {
        # —— Group 1: 主决策（影响 cascade gate）—— #
        "next_direction": {
            "type": "choice",
            "instructions": {
                "question": "基于 state.window 最近 20 根 bar 与 state.features，预测下一根 bar 的收盘方向。",
                "focus": "仅依据给定数据判断，不要假设未提供的信息。",
            },
            "criteria": {
                "buy": {"what": f"预计下一根 bar 涨幅超过 {pct_text}（扣除双边交易成本后仍有正收益）"},
                "sell": {"what": f"预计下一根 bar 跌幅超过 {pct_text}"},
                "hold": {"what": "预计涨跌幅不超过上述阈值、方向不明或处于震荡"},
            },
        },
        # —— Group 2: 信号确认（纯归因，不参与 gate）—— #
        "trend_confirms": {
            "type": "noul",
            "instructions": "state.features.sma5_vs_sma20 与 ret_1/ret_5 是否方向一致、互相印证？",
        },
        "risk_regime_bad": {
            "type": "noul",
            "instructions": "当前是否处于高波动（vol_20 显著偏高）或成交量异常放大（volume_z 绝对值大）等不利开仓状态？",
        },
        "signal_clarity": {
            "type": "score",
            "instructions": "当前交易信号的清晰度如何？",
            "criteria": [
                "信号混乱，多指标互相矛盾",
                "信号一般，方向不够明确",
                "信号清晰，指标方向一致",
            ],
        },
        # —— Group 3: v2 新增 —— #
        # 3a: 仓位分档（Choice，不做 gate，留给 harness position guard + risk engine）
        "position_size": {
            "type": "choice",
            "instructions": {
                "question": "建议的开仓分档比例？考虑当前波动率、信号清晰度和方向置信度。",
                "focus": "0% = 观望不进；25%/50% = 保守/常规；100% = 充分确信全仓（高风险）。",
            },
            "criteria": {
                "0pct": {"what": "不建议开仓，风险或不确定性过高"},
                "25pct": {"what": "小仓位试探性开仓，信号一般"},
                "50pct": {"what": "常规仓位开仓，信号较好"},
                "100pct": {"what": "全仓开仓，信号强烈且方向高度确定"},
            },
        },
        # 3b: 波动率 regime（Score，供 harness FastPathRouter）
        "volatility_regime": {
            "type": "score",
            "instructions": "当前波动率处于哪个 regime？参考 vol_20 的绝对水平与历史分布。",
            "criteria": [
                "低波动（vol_20 < 0.5%），安全区间",
                "正常波动（0.5% - 2%）",
                "高波动（vol_20 > 2%），谨慎开仓或缩量",
            ],
        },
        # 3c: 回撤风险（Noul，供 harness CircuitBreaker 预检查）
        "drawdown_risk": {
            "type": "noul",
            "instructions": "当前是否面临显著回撤风险？参考：RSI 是否超买/超卖、close_vs_sma20 偏离幅度、近期是否有连续同向 bar。",
        },
        # 3d: 执行紧急度（Choice，供 harness FastPathRouter 路由到不同执行策略）
        "execution_urgency": {
            "type": "choice",
            "instructions": {
                "question": "执行这个决策的时间敏感度如何？",
                "focus": "immediate = 价格稍纵即逝，必须立即执行；within_60s = 信号持续有效窗口 > 60s；cancel = 不值得执行。",
            },
            "criteria": {
                "immediate": {"what": "价格瞬时机会，必须立即 market 单"},
                "within_60s": {"what": "机会窗口有几秒到几十秒，可用限价或分批"},
                "cancel": {"what": "时机已过或不值得执行"},
            },
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# V2 便捷入口
# ═══════════════════════════════════════════════════════════════════════


def build_full_v2(
    window: pd.DataFrame,
    *,
    symbol: str,
    bar_type: str,
    cost_threshold: float,
) -> tuple[dict, dict]:
    """一次返回 (state, questions)，v2 全量。"""
    return (
        build_state_v2(window, symbol=symbol, bar_type=bar_type),
        build_questions_v2(cost_threshold=cost_threshold),
    )


def canonical_request(state: dict, questions: dict) -> str:
    """规范化 JSON，fingerprint 稳定的前提。"""
    return json.dumps(
        {"state": state, "questions": questions},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def request_fingerprint(state: dict, questions: dict) -> str:
    """请求指纹，ReplayClient 精确匹配键。v2 的 fingerprint 与 v1 天然不同（特征+问题都变了）。"""
    return hashlib.sha256(canonical_request(state, questions).encode("utf-8")).hexdigest()


__all__ = [
    "FEATURE_NAMES_V2",
    "build_full_v2",
    "build_questions_v2",
    "build_state_v2",
    "canonical_request",
    "compute_features_v2",
    "request_fingerprint",
]
