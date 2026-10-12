"""因子注入器 — 实盘逐 bar 计算因子值并注入 StrategyContext.features。

复用 factor.engine.evaluate_factor（内置 + 自定义表达式），输入来自
KlineBuffer.bars() 的历史 OHLCV，输出 {factor_name: value} dict。
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class FactorInjector:
    """实盘因子注入器。

    Args:
        factor_names: 需要计算的因子名列表（内置或自定义）。
        custom_factors: 自定义因子表达式映射 {name: expression}。
    """

    def __init__(
        self,
        factor_names: list[str],
        custom_factors: dict[str, str] | None = None,
    ) -> None:
        self._factor_names = list(factor_names)
        self._custom = custom_factors or {}

    @classmethod
    def from_factor_names(cls, factor_names: list[str]) -> FactorInjector:
        """从 FactorService 加载自定义因子表达式，创建 FactorInjector。"""
        # ponytail: 延迟 import 避免循环依赖；FactorService 从 DB 拿自定义表达式
        from factor.service import FactorService

        svc = FactorService()
        # 只加载 factor_names 中存在的自定义因子，避免全量加载
        custom = {k: v for k, v in svc.factors.items() if k in factor_names and k not in svc._builtin}
        return cls(factor_names=factor_names, custom_factors=custom)

    def compute(self, bars: list[dict]) -> dict[str, float]:
        """根据历史 K 线计算所有因子的最新值。

        Args:
            bars: KlineBuffer.bars() 返回的 list[dict]，每个含
                  timestamp/open/high/low/close/volume。

        Returns:
            {factor_name: 最新值}；因子计算失败或数据不足时跳过该因子。
        """
        if not self._factor_names or not bars:
            return {}

        # 转 DataFrame：补齐 evaluate_factor 所需的 quote_volume 列
        # （KlineBuffer 无 quote_volume，用 volume * close 估算）
        df = pd.DataFrame(
            [
                {
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                    "quote_volume": b["volume"] * b["close"],
                }
                for b in bars
            ]
        )

        # ponytail: 延迟 import 避免循环依赖
        from factor.engine import evaluate_factor

        features: dict[str, float] = {}
        for name in self._factor_names:
            try:
                series = evaluate_factor(name, df, self._custom)
                if series is not None and len(series) > 0:
                    val = series.iloc[-1]
                    if pd.notna(val):
                        features[name] = float(val)
            except Exception as e:
                # 单个因子失败不阻断其他因子和策略循环
                logger.debug(f"因子 {name} 计算失败: {e}")
        return features
