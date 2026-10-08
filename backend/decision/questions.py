"""bar 窗口 → Jev {state, questions} 的确定性构造与请求指纹。

- 特征由代码预算（pandas），Jev 只做语义判断，不做数学计算。
- v1 特征集冻结为 5 个；修改即改变 state schema，录制指纹自动失效。
- 所有浮点 round(6)，保证同输入字节级一致（指纹稳定）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

ACTION_BUY = "buy"
ACTION_SELL = "sell"
ACTION_HOLD = "hold"
ACTIONS: tuple[str, ...] = (ACTION_BUY, ACTION_SELL, ACTION_HOLD)

DEFAULT_WINDOW = 20

# 特征集合冻结，新增/改名必须同步改 build_state 与测试
FEATURE_NAMES: tuple[str, ...] = (
    "ret_1",
    "ret_5",
    "vol_20",
    "sma5_vs_sma20",
    "volume_z",
)

_ROUND = 6


def _r6(x: float) -> float:
    return round(float(x), _ROUND)


def compute_features(window: pd.DataFrame) -> dict[str, float]:
    """从恰好 20 根 bar 的 DataFrame 计算 5 个冻结特征。

    调用方保证 len(window) >= 20（iloc[-6] 需要 6 根）。
    """
    close = window["close"].astype(float)
    volume = window["volume"].astype(float)
    pct = close.pct_change().dropna()

    ret_1 = close.iloc[-1] / close.iloc[-2] - 1.0
    ret_5 = close.iloc[-1] / close.iloc[-6] - 1.0
    vol_20 = float(pct.std(ddof=0))
    sma5 = float(close.tail(5).mean())
    sma20 = float(close.tail(20).mean())
    vol_std = float(volume.std(ddof=0))
    volume_z = 0.0 if vol_std == 0.0 else (float(volume.iloc[-1]) - float(volume.mean())) / vol_std

    values = (ret_1, ret_5, vol_20, sma5 / sma20 - 1.0, volume_z)
    return {name: _r6(v) for name, v in zip(FEATURE_NAMES, values, strict=True)}


def _to_ms(value: Any) -> int:
    """timestamp 支持整型毫秒与 ISO 字符串两种 CSV 形态。"""
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    if text.isdigit():
        return int(text)
    return int(pd.Timestamp(text).timestamp() * 1000)


def build_state(window: pd.DataFrame, *, symbol: str, bar_type: str) -> dict:
    """构造冻结结构的 state：20 根精简 bar + 5 个特征。"""
    rows = [
        {
            "t": _to_ms(row["timestamp"]),
            "o": _r6(row["open"]),
            "h": _r6(row["high"]),
            "l": _r6(row["low"]),
            "c": _r6(row["close"]),
            "v": _r6(row["volume"]),
        }
        for _, row in window.iterrows()
    ]
    return {
        "symbol": symbol,
        "bar_type": bar_type,
        "window": rows,
        "features": compute_features(window),
    }


def build_questions(*, cost_threshold: float) -> dict[str, dict]:
    """构造 1 主问题 + 3 并行原子子问题。criteria 边界写死模板。"""
    pct_text = f"{cost_threshold * 100:.2f}%"
    return {
        "next_direction": {
            "type": "choice",
            "instructions": {
                "question": "基于 state.window 最近 20 根 bar 与 state.features，预测下一根 bar 的收盘方向。",
                "focus": "仅依据给定数据判断，不要假设未提供的信息。",
            },
            "criteria": {
                ACTION_BUY: {
                    "what": f"预计下一根 bar 涨幅超过 {pct_text}（扣除双边交易成本后仍有正收益）",
                },
                ACTION_SELL: {
                    "what": f"预计下一根 bar 跌幅超过 {pct_text}",
                },
                ACTION_HOLD: {
                    "what": "预计涨跌幅不超过上述阈值、方向不明或处于震荡",
                },
            },
        },
        "trend_confirms": {
            "type": "noul",
            "instructions": "features 中的 sma5_vs_sma20 与 ret_1/ret_5 是否方向一致、互相印证，支持 next_direction 所选方向的趋势延续？",
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
    }


def canonical_request(state: dict, questions: dict) -> str:
    """完整请求体的规范化 JSON：sort_keys + 无空格 + UTF-8 原文。"""
    return json.dumps(
        {"state": state, "questions": questions},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def request_fingerprint(state: dict, questions: dict) -> str:
    """请求指纹：ReplayClient 的精确匹配键。"""
    return hashlib.sha256(canonical_request(state, questions).encode("utf-8")).hexdigest()
