"""因子计算业务服务 — 因子管理 / 计算 / 分析（基于本地 parquet + pandas 自有引擎）。"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from factor.engine import (
    FACTOR_META,
    UNSUPPORTED_FACTORS,
    close_panel_from_raw,
    evaluate_expression,
    factor_panel_from_raw,
    load_factor_panel,
    load_raw_ohlcv,
)
from factor.engine import (
    FactorExpressionError as _EngineExprError,
)
from factor.factor_store import FactorStore
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


class FactorError(Exception):
    """因子模块基础异常"""

    pass


class FactorNotFoundError(FactorError):
    """因子不存在异常"""

    pass


class FactorExpressionError(FactorError):
    """因子表达式错误异常"""

    pass


class FactorService:
    """
    因子计算服务类

    提供因子计算和管理的核心业务逻辑。内置因子元数据来自 factor.engine，
    自定义因子通过 FactorStore 持久化到 JSON，二者在初始化时合并。

    Attributes:
        factors: 因子名 -> 表达式，内置 + 自定义
    """

    def __init__(self) -> None:
        self._custom_store = FactorStore()
        self._builtin = {name: meta["expression"] for name, meta in FACTOR_META.items()}
        # 内置表达式（含不支持财务因子的空表达式）+ 自定义表达式
        self.factors: dict[str, str] = {**self._builtin, **self._custom_store.all()}
        logger.info(f"FactorService初始化完成，内置 {len(self._builtin)} 个，自定义 {len(self._custom_store.all())} 个")

    def _load_builtin_factors(self) -> dict[str, str]:
        return dict(self._builtin)

    def get_factor_list(self) -> list[str]:
        """获取所有支持的因子列表。"""
        return list(self.factors.keys())

    def get_factor_expression(self, factor_name: str) -> str | None:
        """获取因子表达式，不存在抛 FactorNotFoundError。"""
        expression = self.factors.get(factor_name)
        if expression is None:
            msg = f"因子不存在: {factor_name}"
            raise FactorNotFoundError(msg)
        return expression

    def add_factor(self, factor_name: str, factor_expression: str) -> bool:
        """添加自定义因子：非空校验 + 内置因子保护 + 持久化落盘。"""
        if not factor_name or not factor_name.strip():
            msg = "因子名称不能为空"
            raise FactorExpressionError(msg)

        if not factor_expression or not factor_expression.strip():
            msg = "因子表达式不能为空"
            raise FactorExpressionError(msg)

        if factor_name in self._builtin:
            raise FactorExpressionError(f"内置因子 {factor_name} 不允许覆盖")
        expr = factor_expression.strip()
        self.factors[factor_name] = expr
        self._custom_store.upsert(factor_name, expr)
        logger.info(f"成功添加自定义因子: {factor_name}")
        return True

    def delete_factor(self, factor_name: str) -> bool:
        """删除自定义因子：内置因子受保护，不存在抛 FactorNotFoundError。"""
        if factor_name in self._builtin:
            raise FactorExpressionError(f"内置因子 {factor_name} 不允许删除")
        if factor_name not in self.factors:
            raise FactorNotFoundError(f"因子不存在: {factor_name}")
        del self.factors[factor_name]
        self._custom_store.delete(factor_name)
        logger.info(f"成功删除自定义因子: {factor_name}")
        return True

    def validate_factor_expression(self, factor_expression: str) -> bool:
        """用 3 行最小合成 K 线对表达式做真实 AST 求值校验（不依赖真实行情）。"""
        if not factor_expression or not factor_expression.strip():
            return False
        probe = pd.DataFrame(
            {
                "open": [1.0, 2, 3],
                "high": [1.5, 2.5, 3.5],
                "low": [0.5, 1.5, 2.5],
                "close": [1.0, 2.0, 3.0],
                "volume": [10.0, 20, 30],
                "quote_volume": [10.0, 40, 90],
            }
        )
        try:
            evaluate_expression(factor_expression, probe)
            return True
        except _EngineExprError:
            return False

    def calculate_factor(
        self,
        factor_name: str,
        instruments: list[str],
        start_time: str | None,
        end_time: str | None,
        interval: str = "1h",
        candle_type: str = "spot",
        provider=None,
    ) -> pd.DataFrame:
        """计算单因子，返回 MultiIndex(datetime, symbol)、单列=因子名 的 DataFrame。"""
        if factor_name not in self.factors:
            raise FactorNotFoundError(f"因子不存在: {factor_name}")
        try:
            panel = load_factor_panel(
                instruments,
                interval,
                candle_type,
                start_time,
                end_time,
                factor_name,
                self._custom_store.all(),
                provider,
            )
            logger.info(f"因子 {factor_name} 计算完成，点数: {len(panel)}")
            return panel.to_frame(factor_name)
        except _EngineExprError as e:
            raise FactorError(str(e)) from e

    def calculate_factors(
        self,
        factor_names: list[str],
        instruments: list[str],
        start_time: str | None,
        end_time: str | None,
        interval: str = "1h",
        candle_type: str = "spot",
        provider=None,
    ) -> pd.DataFrame:
        """计算多因子：原始 K 线只读盘一次，逐因子求值后按索引对齐拼接。"""
        missing = [n for n in factor_names if n not in self.factors]
        if missing:
            raise FactorNotFoundError(f"因子不存在: {missing}")
        try:
            # ponytail: 多因子复用同一份 raw_map 避免重复读盘；K 线级数据量，外连接对齐足够
            raw_map = load_raw_ohlcv(instruments, interval, candle_type, start_time, end_time, provider)
            cols = {
                name: factor_panel_from_raw(name, raw_map, self._custom_store.all())
                for name in factor_names
                if name not in UNSUPPORTED_FACTORS
            }
            if not cols:
                raise FactorError("所选因子均不可计算（财务因子无数据）")
            return pd.concat(cols, axis=1).sort_index()
        except _EngineExprError as e:
            raise FactorError(str(e)) from e

    def calculate_all_factors(
        self,
        instruments: list[str],
        start_time: str | None,
        end_time: str | None,
        interval: str = "1h",
        candle_type: str = "spot",
        provider=None,
    ) -> pd.DataFrame:
        """计算所有可计算因子（内置量价/技术 + 自定义），跳过财务因子。"""
        names = [n for n in self.factors if n not in UNSUPPORTED_FACTORS]
        return self.calculate_factors(names, instruments, start_time, end_time, interval, candle_type, provider)

    def get_factor_details(self) -> list[dict]:
        """内置+自定义因子明细，供因子库展示。"""
        details = []
        for name in self.factors:
            meta = FACTOR_META.get(name)
            details.append(
                {
                    "name": name,
                    "expression": self.factors[name],
                    "category": (meta or {}).get("category", "custom"),
                    "label": (meta or {}).get("label", name),
                    "builtin": meta is not None,
                    "supported": name not in UNSUPPORTED_FACTORS,
                }
            )
        return sorted(details, key=lambda d: (not d["builtin"], d["category"], d["name"]))

    @staticmethod
    def _ic_series(factor: pd.Series, forward_ret: pd.Series, method: str, window: int) -> pd.Series:
        """IC 时序：多品种走每日截面相关（向量化）；单品种退化为滚动窗口相关。"""
        joined = pd.concat([factor.rename("f"), forward_ret.rename("r")], axis=1).dropna()
        if joined.empty:
            return pd.Series(dtype=float)

        n_symbols = joined.index.get_level_values(1).nunique()
        n_dates = joined.index.get_level_values(0).nunique()
        if n_symbols >= 2 and n_dates >= 3:
            fw = joined["f"].unstack(level=1)
            rw = joined["r"].unstack(level=1)
            # 先统一成对有效掩码：两侧缺失位置不同时，若直接各自 rank，
            # 两边秩的池子大小不同，rank→pearson 会偏离逐日 spearman
            # （已在 pandas 3.0.3 实测验证）
            valid = fw.notna() & rw.notna()
            pair_counts = valid.sum(axis=1)
            if method == "spearman":
                # spearman = 成对掩码后逐行秩变换再做 pearson；rank(axis=1) 为 C 层向量化
                fw = fw.where(valid).rank(axis=1)
                rw = rw.where(valid).rank(axis=1)
            # pearson 分支 corrwith 自带成对 NaN 排除，无需 mask
            ic = fw.corrwith(rw, axis=1)
            # 与旧口径一致：当天至少 2 个品种有有效值才计入
            return ic[pair_counts >= 2].dropna()

        # 单品种退化为滚动窗口相关
        w = min(window, max(3, len(joined) // 4))
        idx = joined.index.get_level_values(0)
        f = pd.Series(joined["f"].values, index=idx)
        r = pd.Series(joined["r"].values, index=idx)
        return f.rolling(w).corr(r).dropna()

    # 加密 7×24 周期 → 年 bar 数
    _PERIODS_PER_YEAR = {
        "1d": 365,
        "1h": 365 * 24,
        "4h": 365 * 6,
        "15m": 365 * 24 * 4,
        "5m": 365 * 24 * 12,
        "1m": 365 * 24 * 60,
    }

    @classmethod
    def _periods_per_year(cls, interval: str) -> int:
        if interval in cls._PERIODS_PER_YEAR:
            return cls._PERIODS_PER_YEAR[interval]
        m = re.fullmatch(r"(\d+)(m|h|d)", interval.strip())
        if m:
            num, unit = int(m.group(1)), m.group(2)
            minutes = num if unit == "m" else num * 60 if unit == "h" else num * 1440
            if minutes:
                return int(365 * 24 * 60 / minutes)
        return 365 * 24

    @staticmethod
    def _coverage(factor, total_bars: int) -> float | None:
        """因子有效值占总 K 线 bar 比例。total_bars 必须是 shift 前的原始总行数。"""
        if total_bars <= 0:
            return None
        # to_numpy 后求和：宽表 DataFrame 直接 .sum() 会得到按列 Series（pandas 3 无法 float()）
        return float(pd.notna(factor).to_numpy().sum()) / float(total_bars)

    @staticmethod
    def _turnover(factor_wide: pd.DataFrame) -> float | None:
        """信号逐 bar 绝对变化（跨品种×时间平均，无量纲）；首日 NaN 自动排除。"""
        if factor_wide.size == 0:
            return None
        return float(factor_wide.diff().abs().mean().mean())

    @classmethod
    def _decay(cls, factor_long: pd.Series, close_long: pd.Series, n_symbols: int, window: int) -> list[dict]:
        """lag ∈ {1,2,3,5,10} 的因子-前瞻收益 IC（spearman+pearson）。

        factor_long/close_long: MultiIndex(datetime,symbol) 的 Series。
        多品种复用 _ic_series 截面口径（逐期 IC 后全期均值）；单品种时序整体相关。
        样本不足返回 null，不抛错。
        """
        out = []
        for lag in (1, 2, 3, 5, 10):
            ret = close_long.groupby(level=1).shift(-lag) / close_long - 1
            joined = pd.concat([factor_long.rename("f"), ret.rename("r")], axis=1).dropna()
            sp = pp = None
            if len(joined) >= max(lag + 2, 10):
                if n_symbols >= 2 and joined.index.get_level_values(0).nunique() >= 3:
                    ic_series = cls._ic_series(joined["f"], joined["r"], "spearman", window)
                    sp = float(ic_series.mean()) if len(ic_series) else None
                    ic_p = cls._ic_series(joined["f"], joined["r"], "pearson", window)
                    pp = float(ic_p.mean()) if len(ic_p) else None
                else:
                    sp = float(joined["f"].corr(joined["r"], method="spearman"))
                    pp = float(joined["f"].corr(joined["r"], method="pearson"))
            out.append({"lag": lag, "spearman": sp, "pearson": pp})
        return out

    @classmethod
    def _ic_stats(cls, ic_series: pd.Series, interval: str) -> dict:
        n = len(ic_series)
        mean = float(ic_series.mean()) if n else None
        std = float(ic_series.std()) if n > 1 else None
        ir = (mean / std) if (mean is not None and std) and not pd.isna(std) else None
        ppy = cls._periods_per_year(interval)
        annualized = (ir * np.sqrt(ppy)) if ir is not None else None
        t_stat = (mean / (std / np.sqrt(n))) if (mean is not None and std and n > 1) else None
        return {
            "n": n,
            "ic_mean": mean,
            "ic_std": std,
            "ic_ir": ir,
            "periods_per_year": ppy,
            "annualized_ir": annualized,
            "t_stat": t_stat,
        }

    @staticmethod
    def _cross_section_groups(factor: pd.Series, n_groups: int) -> pd.Series:
        """逐时间点把截面因子值按分位切为 n 组（向量化实现）。

        rank(pct=True) 后 ceil 切桶：最低档进 1、最高档进 n；品种数少于
        组数时高位桶自然为空，后续 groupby 自动缺失（等价 qcut + duplicates='drop'）。
        """
        wide = factor.unstack(level=1)
        ranks = wide.rank(axis=1, pct=True)
        buckets = np.ceil(ranks * n_groups).clip(lower=1.0, upper=float(n_groups))
        # stack 默认丢弃 NaN，reindex 恢复完整索引以保持与因子序列对齐
        return buckets.stack().reindex(factor.index)

    def analyze(
        self,
        factor_name: str,
        symbols: list[str],
        interval: str,
        candle_type: str,
        start: str | None,
        end: str | None,
        method: str = "spearman",
        n_groups: int = 5,
        window: int = 20,
        forward: int = 1,
        provider=None,
        return_frames: bool = False,
    ) -> dict:
        """一站式分析：取数→因子→前瞻收益→IC/IR/分组/单调性/稳定性/序列。

        return_frames: 为 True 时额外返回因子值/前瞻收益对齐长表（列 f/r，
        MultiIndex datetime×symbol），仅供服务端快照收藏，不经过 HTTP。
        """
        if factor_name in UNSUPPORTED_FACTORS:
            raise FactorError(f"因子 {factor_name} 依赖财务数据，当前数据源不支持")
        if factor_name not in self.factors:
            raise FactorNotFoundError(f"因子不存在: {factor_name}")

        # 因子面板与收盘价面板共用同一份 raw_map，避免每个品种重复读盘
        raw_map = load_raw_ohlcv(symbols, interval, candle_type, start, end, provider)
        factor = factor_panel_from_raw(factor_name, raw_map, self._custom_store.all())
        close = close_panel_from_raw(raw_map)
        aligned = pd.concat([factor.rename("f"), close.rename("c")], axis=1).dropna()
        if len(aligned) < max(n_groups * 2, window + 2, 10):
            raise FactorError(f"有效数据不足（{len(aligned)} 根），请扩大时间范围或减小分组/窗口")

        # 按品种分组取前瞻，避免跨品种错位
        forward_ret = (aligned["c"].groupby(level=1).shift(-forward) / aligned["c"] - 1).rename("r")
        df = pd.concat([aligned["f"], forward_ret], axis=1).dropna()

        ic_series = self._ic_series(df["f"], df["r"], method, window)
        ic_mean = float(ic_series.mean()) if len(ic_series) else None
        ic_std = float(ic_series.std()) if len(ic_series) > 1 else None
        ic_ir = (ic_mean / ic_std) if ic_mean is not None and ic_std and not pd.isna(ic_std) else None

        n_symbols = df.index.get_level_values(1).nunique()
        if n_symbols >= 2:
            # 多品种：逐时间点截面分组，避免把不同时期的因子值混在同一分位
            grp = self._cross_section_groups(df["f"], n_groups)
        else:
            # 单品种：全样本时序分位
            try:
                grp = pd.qcut(df["f"], n_groups, labels=False, duplicates="drop") + 1
            except ValueError:
                grp = pd.qcut(df["f"].rank(method="first"), n_groups, labels=False) + 1
        group_returns = df["r"].groupby(grp).mean().sort_index()
        long_short = float(group_returns.iloc[-1] - group_returns.iloc[0]) if len(group_returns) >= 2 else None

        mono_corr, p_value = spearmanr(group_returns.index.astype(float), group_returns.values)

        stab_window = min(window, max(5, len(df) // 4))
        # 宽表按列滚动：每个品种各自计算 lag-1 自相关，避免跨品种边界滚动
        f_wide = df["f"].unstack(level=1)
        stab_series = f_wide.rolling(stab_window).corr(f_wide.shift(1)).stack()
        stab_autocorr_value = float(stab_series.mean()) if len(stab_series.dropna()) else None
        desc = df["f"].describe()

        pivot = df["f"].unstack(level=1)
        factor_by_time = pivot.mean(axis=1) if pivot.shape[1] > 1 else pivot.iloc[:, 0]
        close_pivot = aligned["c"].unstack(level=1)
        close_by_time = close_pivot.mean(axis=1) if close_pivot.shape[1] > 1 else close_pivot.iloc[:, 0]
        idx = factor_by_time.dropna().index.intersection(close_by_time.dropna().index)

        result = {
            "factor_name": factor_name,
            "instruments": symbols,
            "interval": interval,
            "bar_count": len(df),
            "stats": {
                "mean": float(desc["mean"]),
                "std": float(desc["std"]),
                "min": float(desc["min"]),
                "max": float(desc["max"]),
            },
            "ic": {
                "method": method,
                "series": [
                    {"t": t.strftime("%Y-%m-%d %H:%M"), "ic": (None if pd.isna(v) else float(v))}
                    for t, v in ic_series.items()
                ],
                "mean": ic_mean,
                "std": ic_std,
                "ir": ic_ir,
                "positive_rate": float((ic_series > 0).mean()) if len(ic_series) else None,
            },
            "groups": [{"group": int(g), "mean_forward_return": float(v)} for g, v in group_returns.items()],
            "long_short_return": long_short,
            "monotonicity": {"spearman": float(mono_corr), "p_value": float(p_value), "score": long_short},
            "stability": {"window": stab_window, "mean_autocorr": stab_autocorr_value},
            "series": {
                "dates": [t.strftime("%Y-%m-%d %H:%M") for t in idx],
                "close": [float(close_by_time.loc[t]) for t in idx],
                "factor": {t.strftime("%Y-%m-%d %H:%M"): float(factor_by_time.loc[t]) for t in idx},
            },
        }
        if return_frames:
            return result, df
        return result

    # ---------------- 通用统计方法（与具体行情引擎无关，保留供直接调用） ----------------

    def get_factor_correlation(self, factor_data: pd.DataFrame) -> pd.DataFrame | None:
        """计算因子之间的相关性矩阵。"""
        try:
            return factor_data.corr()
        except Exception as e:
            logger.error(f"计算因子相关性失败: {e}")
            return None

    def get_factor_descriptive_stats(self, factor_data: pd.DataFrame) -> pd.DataFrame | None:
        """获取因子的描述性统计信息。"""
        try:
            return factor_data.describe()
        except Exception as e:
            logger.error(f"获取因子描述性统计失败: {e}")
            return None

    def calculate_ic(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame | pd.Series,
        method: str = "spearman",
    ) -> pd.Series | None:
        """计算因子的信息系数(IC) — 因子值与未来收益的秩相关。"""
        try:
            return_series = return_data.iloc[:, 0] if isinstance(return_data, pd.DataFrame) else return_data

            factor_df = factor_data.apply(pd.to_numeric, errors="coerce")
            aligned = pd.concat([factor_df, return_series.rename("__ret__")], axis=1).dropna()
            if len(aligned) < 3:
                logger.warning("有效数据不足，无法计算IC")
                return None

            ic = aligned.iloc[:, :-1].corrwith(aligned["__ret__"], method=method)
            logger.info(f"成功计算IC值，方法: {method}, IC均值: {ic.mean():.4f}")
            return ic
        except Exception as e:
            logger.error(f"计算IC值失败: {e}")
            return None

    def calculate_ir(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame | pd.Series,
        method: str = "spearman",
    ) -> float | None:
        """计算因子的信息比率(IR) = IC均值 / IC标准差。"""
        try:
            ic = self.calculate_ic(factor_data, return_data, method)
            if ic is None or len(ic) == 0:
                return None
            ic_std = ic.std()
            if ic_std is None or pd.isna(ic_std) or ic_std == 0:
                logger.warning("IC标准差为0或NaN，无法计算IR（IC样本太少）")
                return None
            ir = float(ic.mean() / ic_std)
            logger.info(f"成功计算IR值，方法: {method}, IR: {ir:.4f}")
            return ir
        except Exception as e:
            logger.error(f"计算IR值失败: {e}")
            return None

    def group_analysis(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame | pd.Series,
        n_groups: int = 5,
    ) -> dict[str, Any] | None:
        """因子分组回测分析。

        对因子值按分位数分组，计算每组平均收益，评估因子的区分能力。
        兼容 MultiIndex（多重索引 datetime×symbol）和普通 DataFrame/Series。
        """
        try:
            factor_series = factor_data.iloc[:, 0] if factor_data.ndim > 1 else factor_data
            return_series = return_data.iloc[:, 0] if isinstance(return_data, pd.DataFrame) else return_data

            factor_series = factor_series.reindex(return_series.index).dropna()
            return_series = return_series.reindex(factor_series.index)

            if len(factor_series) < n_groups * 2:
                logger.warning(f"数据量不足（{len(factor_series)} 条），分组数 {n_groups} 过大")
                return None

            # ponytail: 使用 qcut 做截面/时序分组，跨标的 MultiIndex 场景需要 level=1
            if isinstance(factor_series.index, pd.MultiIndex):
                groups = factor_series.groupby(level=1).apply(
                    lambda x: pd.qcut(x, n_groups, labels=False, duplicates="drop") + 1
                )
            else:
                groups = pd.qcut(factor_series, n_groups, labels=False, duplicates="drop") + 1

            group_returns = return_series.groupby(groups).mean()
            long_short_ret = group_returns.iloc[-1] - group_returns.iloc[0]

            logger.info(f"分组分析完成，分组数: {n_groups}, 多空收益: {long_short_ret:.4f}")
            return {
                "group_returns": group_returns,
                "long_short_return": pd.Series([long_short_ret] * len(group_returns), index=group_returns.index),
                "n_groups": n_groups,
            }
        except Exception as e:
            logger.error(f"分组回测分析失败: {e}")
            return None

    def factor_monotonicity_test(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame | pd.Series,
        n_groups: int = 5,
    ) -> dict[str, Any] | None:
        """因子单调性检验 — 检验分组收益是否随因子值单调递增/递减。"""
        try:
            group_result = self.group_analysis(factor_data, return_data, n_groups)
            if group_result is None:
                return None

            group_returns = group_result["group_returns"]

            groups = list(range(1, len(group_returns) + 1))
            monotonicity_corr, p_value = spearmanr(groups, group_returns.values)
            monotonicity_score = float(group_returns.iloc[-1] - group_returns.iloc[0])

            logger.info(
                f"单调性检验完成，得分: {monotonicity_score:.4f}, "
                f"spearman: {monotonicity_corr:.4f}, p-value: {p_value:.4f}"
            )
            return {
                "group_returns": group_returns.to_dict(),
                "monotonicity_score": monotonicity_score,
                "monotonicity_corr": float(monotonicity_corr),
                "p_value": float(p_value),
            }
        except Exception as e:
            logger.error(f"因子单调性检验失败: {e}")
            return None

    def factor_stability_test(
        self,
        factor_data: pd.DataFrame,
        window: int = 20,
    ) -> dict[str, Any] | None:
        """因子稳定性检验 — 基于滚动自相关衡量因子值的时序稳定性。"""
        try:
            if len(factor_data) < window + 1:
                logger.warning(f"数据量不足（{len(factor_data)} 条），窗口 {window} 过大")
                return None

            factor_series = factor_data.iloc[:, 0] if factor_data.ndim > 1 else factor_data
            # lag-1 滚动自相关：rolling.corr 与 shift(1) 按索引配对，C 层向量化
            rolling_autocorr = factor_series.rolling(window=window).corr(factor_series.shift(1))
            cross_std = factor_series.rolling(window=window).std()

            logger.info(f"稳定性检验完成，窗口: {window}, 平均自相关: {rolling_autocorr.mean():.4f}")
            return {
                "rolling_autocorr": rolling_autocorr,
                "cross_std": cross_std,
                "mean_autocorr": float(rolling_autocorr.dropna().mean()) if rolling_autocorr.dropna().any() else None,
            }
        except Exception as e:
            logger.error(f"因子稳定性检验失败: {e}")
            return None
