"""因子计算业务服务 — 因子管理 / 计算 / 分析（基于本地 parquet + pandas 自有引擎）。"""

from __future__ import annotations

import re as _re
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from factor.code_store import CodeFactorStore, code_hash
from factor.composite_store import COMPOSITE_METHOD, CompositeFactorStore
from factor.engine import (
    FACTOR_META,
    UNSUPPORTED_FACTORS,
    _timestamps_to_datetime,
    close_panel_from_raw,
    evaluate_expression,
    factor_panel_from_raw,
    load_raw_ohlcv,
)
from factor.engine import (
    FactorExpressionError as _EngineExprError,
)
from factor.factor_store import FactorStore
from factor.sandbox import FactorSandbox
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

    def __init__(
        self,
        code_store: CodeFactorStore | None = None,
        sandbox: FactorSandbox | None = None,
        composite_store: CompositeFactorStore | None = None,
        factor_store: FactorStore | None = None,
    ) -> None:
        self._custom_store = factor_store or FactorStore()
        self._code_store = code_store or CodeFactorStore()
        self._composite_store = composite_store or CompositeFactorStore()
        self._sandbox = sandbox or FactorSandbox()
        self._builtin = {name: meta["expression"] for name, meta in FACTOR_META.items()}
        # 内置表达式（含不支持财务因子的空表达式）+ 自定义表达式
        self.factors: dict[str, str] = {**self._builtin, **self._custom_store.all()}
        logger.info(
            f"FactorService初始化完成，内置 {len(self._builtin)} 个，"
            f"自定义表达式 {len(self._custom_store.all())} 个，代码因子 {len(self._code_store.all())} 个，"
            f"合成因子 {len(self._composite_store.all())} 个"
        )

    def _load_builtin_factors(self) -> dict[str, str]:
        return dict(self._builtin)

    def get_factor_list(self) -> list[str]:
        """获取所有支持的因子列表（表达式因子 + 代码因子 + 合成因子）。"""
        return list(self.factors.keys()) + list(self._code_store.all()) + self._composite_store.names()

    def _factor_exists(self, name: str) -> bool:
        return name in self.factors or bool(self._code_store.get(name)) or self._composite_store.exists(name)

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

        if self._code_store.get(factor_name) is not None:
            raise FactorExpressionError(f"代码因子 {factor_name} 已存在，请改名或在因子库中删除后重建")

        if self._composite_store.exists(factor_name):
            raise FactorExpressionError(f"合成因子 {factor_name} 已存在，名称不可复用")

        if factor_name in self._builtin:
            raise FactorExpressionError(f"内置因子 {factor_name} 不允许覆盖")
        expr = factor_expression.strip()
        self.factors[factor_name] = expr
        self._custom_store.upsert(factor_name, expr)
        logger.info(f"成功添加自定义因子: {factor_name}")
        return True

    def delete_factor(self, factor_name: str) -> bool:
        """删除因子：代码因子走代码库、合成因子走合成库；内置受保护，其余按表达式删除。"""
        if self._code_store.get(factor_name) is not None:
            return self.delete_code_factor(factor_name)
        if self._composite_store.exists(factor_name):
            return self.delete_composite(factor_name)
        if factor_name in self._builtin:
            raise FactorExpressionError(f"内置因子 {factor_name} 不允许删除")
        if factor_name not in self.factors:
            raise FactorNotFoundError(f"因子不存在: {factor_name}")
        del self.factors[factor_name]
        self._custom_store.delete(factor_name)
        logger.info(f"成功删除自定义表达式因子: {factor_name}")
        return True

    _CODE_NAME_RE = _re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,99}$")

    def save_code_factor(
        self,
        factor_name: str,
        code: str,
        description: str = "",
        provenance: dict[str, Any] | None = None,
    ) -> bool:
        """保存 LLM/手写代码因子：名称校验 + 内置/表达式互斥 + 沙箱真实执行 + 去重。"""
        if not self._CODE_NAME_RE.match(factor_name or ""):
            raise FactorExpressionError("代码因子名需以字母开头，仅含字母数字下划线，长度 1-100")
        if factor_name in self._builtin:
            raise FactorExpressionError(f"内置因子 {factor_name} 不允许覆盖")
        if factor_name in self._custom_store.all():
            raise FactorExpressionError(f"表达式因子 {factor_name} 已存在，名称不可复用")
        if self._composite_store.exists(factor_name):
            raise FactorExpressionError(f"合成因子 {factor_name} 已存在，名称不可复用")
        if not code or not code.strip():
            raise FactorExpressionError("因子代码不能为空")
        if len(code) > 20000:
            raise FactorExpressionError("因子代码过长（上限 20000 字符）")
        code = code.strip()
        # hash 去重是纯内存计算，放在昂贵的沙箱子进程校验之前：
        # exclude_name=factor_name 跳过自身（同名覆盖允许），命中别的因子名则拒绝
        h = code_hash(code)
        existing = self._code_store.find_by_hash(h, exclude_name=factor_name)
        if existing is not None:
            raise FactorExpressionError(f"相同代码已存在为因子 '{existing}'，无需重复保存")
        # 静态策略 + 合成数据执行，任何一层失败直接拒绝
        self._sandbox.validate(code)
        self._code_store.upsert(factor_name, code, description.strip(), provenance, code_hash=h)
        logger.info(f"成功保存代码因子: {factor_name}")
        return True

    def delete_code_factor(self, factor_name: str) -> bool:
        if self._code_store.delete(factor_name):
            logger.info(f"成功删除代码因子: {factor_name}")
            return True
        raise FactorNotFoundError(f"代码因子不存在: {factor_name}")

    # 合成因子成分数量上下限（与 Pydantic schema 同口径，服务层再兜底一次）
    _COMPOSITE_MIN_CONSTITUENTS = 2
    _COMPOSITE_MAX_CONSTITUENTS = 20

    def save_composite(
        self,
        factor_name: str,
        description: str,
        codes: list[str],
        weights: list[float],
        ts_stats_list: list[dict[str, Any]],
        train_window: dict[str, Any],
        provenance: dict[str, Any] | None = None,
    ) -> bool:
        """保存 IC 加权 zscore 合成因子：名称互斥 + 成分约束 + 每成分沙箱校验。

        - 名称规则与 save_code_factor 一致；与内置/表达式/代码/composite 互斥
          （同名 composite 覆盖允许，幂等）；
        - 成分 2-20 个；weights/ts_stats 与 codes 一一对应；权重不强制和为 1
          （按拟合一一下发），但全 0 无意义，拒绝；
        - 保存前每个成分代码过沙箱静态+合成执行校验，任一失败整单拒绝、不落库。
        """
        if not self._CODE_NAME_RE.match(factor_name or ""):
            raise FactorExpressionError("合成因子名需以字母开头，仅含字母数字下划线，长度 1-100")
        if factor_name in self._builtin:
            raise FactorExpressionError(f"内置因子 {factor_name} 不允许覆盖")
        if factor_name in self._custom_store.all():
            raise FactorExpressionError(f"表达式因子 {factor_name} 已存在，名称不可复用")
        if self._code_store.get(factor_name) is not None:
            raise FactorExpressionError(f"代码因子 {factor_name} 已存在，名称不可复用")
        if not self._COMPOSITE_MIN_CONSTITUENTS <= len(codes) <= self._COMPOSITE_MAX_CONSTITUENTS:
            raise FactorExpressionError(
                f"合成因子成分数需在 {self._COMPOSITE_MIN_CONSTITUENTS}-{self._COMPOSITE_MAX_CONSTITUENTS} 个之间"
            )
        if len(weights) != len(codes) or len(ts_stats_list) != len(codes):
            raise FactorExpressionError("weights/ts_stats 必须与成分代码一一对应（数量一致）")
        if not any(float(w) != 0.0 for w in weights):
            raise FactorExpressionError("合成权重不能全为 0")
        if not isinstance(train_window, dict) or not {
            "start",
            "end",
            "interval",
            "candle_type",
        } <= set(train_window):
            raise FactorExpressionError("train_window 需包含 start/end/interval/candle_type")

        clean_codes: list[str] = []
        for code in codes:
            if not code or not str(code).strip() or len(str(code)) > 20000:
                raise FactorExpressionError("成分因子代码为空或过长（上限 20000 字符）")
            code = str(code).strip()
            # 静态策略 + 合成数据执行，任何一层失败直接拒绝（不落库）
            self._sandbox.validate(code)
            clean_codes.append(code)

        constituents = [
            {"code": code, "weight": float(weights[i]), "ts_stats": ts_stats_list[i]}
            for i, code in enumerate(clean_codes)
        ]
        self._composite_store.upsert(
            factor_name,
            description=(description or "").strip(),
            train_window=train_window,
            constituents=constituents,
            provenance=provenance,
            method=COMPOSITE_METHOD,
        )
        logger.info(f"成功保存合成因子: {factor_name}（{len(constituents)} 个成分）")
        return True

    def delete_composite(self, factor_name: str) -> bool:
        if self._composite_store.delete(factor_name):
            logger.info(f"成功删除合成因子: {factor_name}")
            return True
        raise FactorNotFoundError(f"合成因子不存在: {factor_name}")

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
        if not self._factor_exists(factor_name):
            raise FactorNotFoundError(f"因子不存在: {factor_name}")
        try:
            raw_map = load_raw_ohlcv(instruments, interval, candle_type, start_time, end_time, provider)
            panel = self._panel_from_raw(factor_name, raw_map)
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
        missing = [n for n in factor_names if not self._factor_exists(n)]
        if missing:
            raise FactorNotFoundError(f"因子不存在: {missing}")
        try:
            # ponytail: 多因子复用同一份 raw_map 避免重复读盘；K 线级数据量，外连接对齐足够
            raw_map = load_raw_ohlcv(instruments, interval, candle_type, start_time, end_time, provider)
            cols = {
                name: self._panel_from_raw(name, raw_map) for name in factor_names if name not in UNSUPPORTED_FACTORS
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
        """计算所有可计算因子（内置量价/技术 + 自定义表达式 + 代码因子），跳过财务因子。"""
        names = [n for n in self.get_factor_list() if n not in UNSUPPORTED_FACTORS]
        return self.calculate_factors(names, instruments, start_time, end_time, interval, candle_type, provider)

    def assemble_code_panel(
        self,
        name: str,
        series_map: dict[str, pd.Series],
        raw_map: dict[str, pd.DataFrame],
    ) -> pd.Series:
        """把沙箱逐品种产出的 Series 拼成 MultiIndex(datetime,symbol) 面板（与表达式面板同约定）。"""
        pieces = []
        for symbol, raw in raw_map.items():
            s = series_map[symbol].copy()
            s.index = pd.MultiIndex.from_arrays(
                [_timestamps_to_datetime(raw["timestamp"]).values, [symbol] * len(s)],
                names=["datetime", "symbol"],
            )
            pieces.append(s)
        panel = pd.concat(pieces).sort_index()
        panel.name = name
        return panel

    def _run_code_panel(self, code: str, name: str, raw_map: dict[str, pd.DataFrame]) -> pd.Series:
        """单份代码走沙箱并拼装 MultiIndex(datetime,symbol) 面板。"""
        series_map = self._sandbox.run(code, raw_map)
        return self.assemble_code_panel(name, series_map, raw_map)

    def _composite_panel_from_spec(
        self, spec: dict[str, Any], raw_map: dict[str, pd.DataFrame], name: str = "composite"
    ) -> pd.Series:
        """按冻结 spec 逐成分沙箱执行 → build_composite（weights/ts_stats 全部冻结）。

        train_window 仅持久化记录，不参与重算；analyze/compare/save_snapshot 等
        所有经 _panel_from_raw 的链路因此自动支持合成因子。
        """
        constituents = spec["constituents"]
        panels = [self._run_code_panel(c["code"], f"{name}__c{i}", raw_map) for i, c in enumerate(constituents)]
        weights = [float(c["weight"]) for c in constituents]
        ts_stats_list = [c.get("ts_stats") or {} for c in constituents]
        return self.build_composite(panels, weights, ts_stats_list)

    def _panel_from_raw(self, name: str, raw_map: dict[str, pd.DataFrame]) -> pd.Series:
        """统一面板入口：合成因子组合多代码沙箱、代码因子走沙箱，其余走 AST 引擎。"""
        composite_spec = self._composite_store.get(name)
        if composite_spec is not None:
            return self._composite_panel_from_spec(composite_spec, raw_map, name)
        entry = self._code_store.get(name)
        if entry is not None:
            return self._run_code_panel(entry["code"], name, raw_map)
        return factor_panel_from_raw(name, raw_map, self._custom_store.all())

    def get_factor_details(self) -> list[dict]:
        """内置+自定义表达式因子+代码因子明细，供因子库展示。"""
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
                    "kind": "expression",
                }
            )
        for name, entry in self._code_store.all().items():
            details.append(
                {
                    "name": name,
                    "expression": entry["code"],
                    "category": "llm_code",
                    "label": entry.get("description") or name,
                    "builtin": False,
                    "supported": True,
                    "kind": "code",
                    "description": entry.get("description", ""),
                }
            )
        for name, entry in self._composite_store.all().items():
            n_constituents = len(entry.get("constituents") or [])
            details.append(
                {
                    "name": name,
                    # 合成因子无单一表达式：用方法标记占位，因子库表达式列展示该串
                    "expression": f"{entry.get('method', COMPOSITE_METHOD)}({n_constituents})",
                    "category": "llm_composite",
                    "label": entry.get("description") or name,
                    "builtin": False,
                    "supported": True,
                    "kind": "composite",
                    "description": entry.get("description", ""),
                    "constituents_count": n_constituents,
                }
            )
        return sorted(details, key=lambda d: (not d["builtin"], d["category"], d["name"]))

    # ------------------------------------------------------------------
    # 合成因子（ic_zscore_v1）纯函数：权重拟合 / 时序统计 / 标准化 / 组合
    # ------------------------------------------------------------------

    @staticmethod
    def fit_ic_weights(ics: list[float | None]) -> list[float | None] | None:
        """train 段 IC 加权：w_i = ic_i / Σ|ic_j|（带符号，绝对值和归一为 1）。

        仅取非 None 成分；非 None 成分 <2 或分母为 0（全 0 IC）→ None（不合成）。
        返回与入参等长、同位置对齐的列表（None 位置保留 None）。
        """
        if sum(x is not None for x in ics) < 2:
            return None
        denom = sum(abs(x) for x in ics if x is not None)
        if denom <= 0:
            return None
        return [None if x is None else float(x) / denom for x in ics]

    @staticmethod
    def _fit_ts_stats(panel: pd.Series) -> dict[str, dict[str, float]]:
        """train 面板按 symbol 拟合时序 mean/std（pandas ddof=1），std=0/不可估 → 1.0 兜底。

        返回 {symbol: {"mean": float, "std": float}} 普通 float，可直接 JSON 持久化。
        """
        stats: dict[str, dict[str, float]] = {}
        for symbol, grp in panel.groupby(level=1):
            vals = pd.to_numeric(grp, errors="coerce").dropna()
            if len(vals):
                mean = float(vals.mean())
                std = float(vals.std()) if len(vals) > 1 else 0.0
                if not np.isfinite(mean):
                    mean = 0.0
            else:
                mean, std = 0.0, 0.0
            if not np.isfinite(std) or std == 0.0:
                std = 1.0
            stats[str(symbol)] = {"mean": mean, "std": float(std)}
        return stats

    @classmethod
    def _normalize_panel(cls, panel: pd.Series, ts_stats: dict[str, Any]) -> pd.Series:
        """成分面板标准化（无前视：截面只用同一时刻，时序统计冻结自 train）。

        逐个时间点看截面品种数：
        - >=3：截面路径。品种数 >=10 时先 clip 到该时刻 1%/99% 分位（winsorize，
          小截面跳过），再做截面 zscore (x-mean)/std（总体 std ddof=0；std=0→0）；
        - <3：时序路径。用 train 冻结的该 symbol mean/std 做 (x-mean)/std
          （std=0→0）；symbol 不在 ts_stats 时（train 未见品种的罕见兜底），
          退化用该 symbol 在本面板的全历史 mean/std（同 _fit_ts_stats 口径）。
        输入 NaN 位置输出保持 NaN，由 build_composite 按 0 贡献处理。
        """
        wide = panel.unstack(level=1).sort_index()
        counts = wide.notna().sum(axis=1)
        xs_rows = counts >= 3
        fallback = cls._fit_ts_stats(panel)

        def _cross_section(row: pd.Series) -> pd.Series:
            valid = row.dropna()
            if len(valid) >= 10:
                # winsorize：clip 到截面 1%/99% 分位（品种 <10 的小截面不做）
                row = row.clip(lower=valid.quantile(0.01), upper=valid.quantile(0.99))
                valid = row.dropna()
            mean = float(valid.mean())
            std = float(valid.std(ddof=0))
            if std <= 0 or not np.isfinite(std):
                # 常数截面 → 0（乘 0 保留 NaN 位置）
                return (row - mean) * 0.0
            return (row - mean) / std

        def _time_series(row: pd.Series) -> pd.Series:
            out = pd.Series(np.nan, index=row.index, dtype=float)
            for symbol in row.index:
                value = row[symbol]
                if pd.isna(value):
                    continue
                st = ts_stats.get(str(symbol)) or fallback.get(str(symbol))
                if not st:
                    continue
                std = float(st.get("std") or 0.0)
                out[symbol] = 0.0 if std <= 0 else (float(value) - float(st["mean"])) / std
            return out

        norm = wide.copy()
        if xs_rows.any():
            norm.loc[xs_rows] = wide.loc[xs_rows].apply(_cross_section, axis=1)
        if (~xs_rows).any():
            norm.loc[~xs_rows] = wide.loc[~xs_rows].apply(_time_series, axis=1)
        # stack 丢弃 NaN，恢复 MultiIndex(datetime,symbol) Series
        series = norm.stack()
        series.name = panel.name
        return series

    @classmethod
    def build_composite(
        cls,
        panels: list[pd.Series],
        weights: list[float],
        ts_stats_list: list[dict[str, Any]],
    ) -> pd.Series:
        """多个成分面板各自归一化后加权求和：composite = Σ w_i · z_i。

        - 索引取所有面板并集（outer），逐面板 reindex；某成分缺失的
          (datetime,symbol) 位置记 0 贡献（fillna(0)），其余成分照常相加；
        - 每个成分用它自己的冻结 ts_stats 归一化（一一对应，不可串用）。
        """
        if not panels or len(panels) != len(weights) or len(panels) != len(ts_stats_list):
            msg = "composite 成分面板/权重/ts_stats 不能为空且数量必须一致"
            raise FactorError(msg)
        union = panels[0].index
        for panel in panels[1:]:
            union = union.union(panel.index)
        total = pd.Series(0.0, index=union, dtype=float)
        for panel, weight, ts_stats in zip(panels, weights, ts_stats_list, strict=True):
            z = cls._normalize_panel(panel, ts_stats).reindex(union)
            total = total + float(weight) * z.fillna(0.0)
        total = total.sort_index()
        total.name = "composite"
        return total

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
        m = _re.fullmatch(r"(\d+)(m|h|d)", interval.strip())
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

    DEFAULT_HORIZONS: tuple[int, ...] = (1, 2, 3, 5, 10)

    @classmethod
    def _decay(
        cls,
        factor_long: pd.Series,
        close_long: pd.Series,
        n_symbols: int,
        window: int,
        horizons: tuple[int, ...] | list[int] | None = None,
    ) -> list[dict]:
        """各 horizon（前瞻 lag 根数）的因子-前瞻收益 IC（spearman+pearson）。

        factor_long/close_long: MultiIndex(datetime,symbol) 的 Series。
        horizons: 自定义 lag 列表；None 用默认 (1,2,3,5,10)。
        多品种复用 _ic_series 截面口径（逐期 IC 后全期均值）；单品种时序整体相关。
        样本不足返回 null，不抛错。
        """
        lags = tuple(horizons) if horizons else cls.DEFAULT_HORIZONS
        out = []
        for lag in lags:
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
            out.append({"lag": int(lag), "spearman": sp, "pearson": pp})
        return out

    @staticmethod
    def _nw_tstat(ic_series: pd.Series) -> tuple[float | None, int]:
        """Newey-West HAC 调整 t 统计量（Bartlett kernel）。

        对 IC 序列的均值显著性做异方差+自相关一致（HAC）校正：当 IC 存在正自相关
        （如滚动窗口 IC）时，普通 t-stat 会高估显著性，NW 标准误把该因素扣除。
        滞后阶数按 Newey-West (1994) 自动选择 L=floor(4·(n/100)^(2/9))。
        返回 (nw_t_stat, L)；样本不足返回 (None, 0)。
        """
        x = ic_series.dropna().to_numpy(dtype=float)
        n = len(x)
        if n < 4:
            return None, 0
        lag = int(np.floor(4 * (n / 100) ** (2 / 9)))
        e = x - x.mean()
        gamma0 = float(np.dot(e, e) / n)
        nw_var = gamma0
        for ell in range(1, lag + 1):
            weight = 1 - ell / (lag + 1)
            gamma_l = float(np.dot(e[ell:], e[:-ell]) / n)
            nw_var += 2 * weight * gamma_l
        if nw_var <= 0:
            return None, lag
        se = float(np.sqrt(nw_var / n))
        return float(x.mean() / se), lag

    @classmethod
    def _ic_stats(cls, ic_series: pd.Series, interval: str) -> dict:
        n = len(ic_series)
        mean = float(ic_series.mean()) if n else None
        std = float(ic_series.std()) if n > 1 else None
        ir = (mean / std) if (mean is not None and std) and not pd.isna(std) else None
        ppy = cls._periods_per_year(interval)
        annualized = (ir * np.sqrt(ppy)) if ir is not None else None
        t_stat = (mean / (std / np.sqrt(n))) if (mean is not None and std and n > 1) else None
        nw_t, nw_lag = cls._nw_tstat(ic_series)
        return {
            "n": n,
            "ic_mean": mean,
            "ic_std": std,
            "ic_ir": ir,
            "periods_per_year": ppy,
            "annualized_ir": annualized,
            "t_stat": t_stat,
            "nw_t_stat": nw_t,
            "nw_lag": nw_lag,
        }

    @staticmethod
    def _quantile_nav(df: pd.DataFrame, grp: pd.Series, n_groups: int, fee_rate: float = 0.0) -> dict:
        """分位组合净值曲线（与 analyze 分组标签同源），含双边换手与费后净值。

        口径：
        - 每组、每时间点取组内品种等权平均前瞻收益（截面）；某组无品种 → NaN，累计时空仓 0 收益；
        - 组内等权权重 w=1/组内品种数；双边换手 turnover_t = Σ_i|w_t−w_{t−1}|（买+卖合计，
          整组全换时=2 即 200%/bar）；时间均值剔除首日；
        - 净收益 = 毛收益 − turnover·单边费率 fee_rate（turnover 已含买卖双边）；
        - 多空(Qn-Q1)：权重 w_long−w_short，仅两端组同时有持仓时计收益与换手。
        """
        grp_wide = grp.unstack(level=1)  # datetime × symbol → 组号
        grp_ret = (
            df["r"]
            .groupby([df.index.get_level_values(0), grp])
            .mean()
            .unstack()
            .reindex(columns=range(1, n_groups + 1))
        )
        dates = [t.strftime("%Y-%m-%d %H:%M") for t in grp_ret.index]

        weights: dict[int, pd.DataFrame] = {}
        groups = []
        for g in range(1, n_groups + 1):
            membership = (grp_wide == g).astype(float)
            w = membership.div(membership.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
            weights[g] = w
            turnover = (w - w.shift(1)).abs().sum(axis=1)
            turnover.iloc[0] = 0.0
            gross = grp_ret[g]
            net = gross.fillna(0.0) - turnover * fee_rate  # 空仓 bar：gross=0、无成员→turnover=0
            groups.append(
                {
                    "group": int(g),
                    "coverage": float(gross.notna().mean()) if len(gross) else 0.0,
                    "turnover": float(turnover.iloc[1:].mean()) if len(turnover) > 1 else 0.0,
                    "returns": [None if pd.isna(v) else float(v) for v in gross],
                    "nav": [None if pd.isna(v) else float(v) for v in (1 + gross.fillna(0.0)).cumprod()],
                    "returns_net": [float(v) for v in net],
                    "nav_net": [float(v) for v in (1 + net).cumprod()],
                }
            )

        ls_returns: list[float | None] = [None] * len(dates)
        ls_nav: list[float | None] = []
        ls_turnover = None
        if n_groups in weights and 1 in weights:
            w_ls = weights[n_groups] - weights[1]
            to_ls = (w_ls - w_ls.shift(1)).abs().sum(axis=1)
            to_ls.iloc[0] = 0.0
            ls_turnover = float(to_ls.iloc[1:].mean()) if len(to_ls) > 1 else 0.0
            long_ret, short_ret = grp_ret[n_groups], grp_ret[1]
            both = long_ret.notna() & short_ret.notna()
            gross_ls = (long_ret - short_ret).where(both)
            if gross_ls.notna().any():
                net_ls = gross_ls - to_ls * fee_rate
                gross_cum = (1 + gross_ls.dropna()).cumprod().reindex(grp_ret.index)
                net_cum = (1 + net_ls.fillna(0.0)).cumprod().where(both).reindex(grp_ret.index)
                ls_returns = [None if pd.isna(v) else float(v) for v in gross_ls]
                ls_nav = [None if pd.isna(v) else float(v) for v in gross_cum]
                ls_net_nav = [None if pd.isna(v) else float(v) for v in net_cum]
            else:
                ls_net_nav = None
        else:
            ls_net_nav = None

        return {
            "dates": dates,
            "fee_rate": fee_rate,
            "groups": groups,
            "long_short_returns": ls_returns,
            "long_short_nav": ls_nav or None,
            "long_short_turnover": ls_turnover,
            "long_short_nav_net": ls_net_nav or None,
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
        horizons: list[int] | tuple[int, ...] | None = None,
        cost_bps: float = 0.0,
    ) -> dict:
        """一站式分析：取数→因子→IC/IR/分组/单调性/稳定性/深度审查(inspection)。

        return_frames: 为 True 时额外返回因子值/前瞻收益对齐长表（列 f/r，
        MultiIndex datetime×symbol），仅供服务端快照收藏，不经过 HTTP。
        horizons: 自定义衰减 lag 列表（K 线根数），None 用默认 (1,2,3,5,10)。
        cost_bps: 单边交易成本（基点，1bp=0.0001），用于分位组合费后净值。
        """
        if factor_name in UNSUPPORTED_FACTORS:
            raise FactorError(f"因子 {factor_name} 依赖财务数据，当前数据源不支持")
        if not self._factor_exists(factor_name):
            raise FactorNotFoundError(f"因子不存在: {factor_name}")

        horizons = tuple(horizons) if horizons else self.DEFAULT_HORIZONS

        # 因子面板与收盘价面板共用同一份 raw_map，避免每个品种重复读盘
        raw_map = load_raw_ohlcv(symbols, interval, candle_type, start, end, provider)
        factor = self._panel_from_raw(factor_name, raw_map)
        close = close_panel_from_raw(raw_map)
        return self._analyze_core(
            factor_name=factor_name,
            symbols=symbols,
            interval=interval,
            raw_map=raw_map,
            factor=factor,
            close=close,
            method=method,
            n_groups=n_groups,
            window=window,
            forward=forward,
            return_frames=return_frames,
            horizons=horizons,
            cost_bps=cost_bps,
        )

    def _analyze_core(
        self,
        *,
        factor_name: str,
        symbols: list[str],
        interval: str,
        raw_map: dict[str, pd.DataFrame],
        factor: pd.Series,
        close: pd.Series,
        method: str = "spearman",
        n_groups: int = 5,
        window: int = 20,
        forward: int = 1,
        return_frames: bool = False,
        horizons: tuple[int, ...] | None = None,
        cost_bps: float = 0.0,
    ) -> dict:
        """analyze 指标主体：HTTP 分析链路与 LLM 挖掘链路共用同一口径，禁止在此处分叉。"""
        fee_rate = float(cost_bps) / 10000.0
        n_total_bars = sum(len(raw) for raw in raw_map.values())
        # coverage 在 dropna 前统计：收盘同源无缺失，因子 NaN 计入，前瞻 shift 尾部不计入
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

        inspection = {
            "coverage": self._coverage(factor, n_total_bars),
            "turnover": self._turnover(df["f"].unstack(level=1)),
            "decay": self._decay(
                factor,
                close,
                n_symbols=df.index.get_level_values(1).nunique(),
                window=stab_window,
                horizons=horizons,
            ),
            "ic_stats": self._ic_stats(ic_series, interval),
            "quantile_nav": self._quantile_nav(df, grp, n_groups, fee_rate=fee_rate),
        }

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
            "inspection": inspection,
            "series": {
                "dates": [t.strftime("%Y-%m-%d %H:%M") for t in idx],
                "close": [float(close_by_time.loc[t]) for t in idx],
                "factor": {t.strftime("%Y-%m-%d %H:%M"): float(factor_by_time.loc[t]) for t in idx},
            },
        }
        if return_frames:
            return result, df
        return result

    @staticmethod
    def _split_raw_map(
        raw_map: dict[str, pd.DataFrame], test_ratio: float
    ) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
        """按**全局时间切点**切 train/test（不能按各品种行数比例切）。

        各品种历史长度可能不同（起点不同、终点相近）：逐品种切 70% 行会让
        短历史品种的 test 窗口整体晚于长历史品种，两段窗口时间不重叠，
        截面 IC 因找不到同日配对而为空。故取全部品种时间戳池的 (1-r) 分位
        作为统一 cutoff，逐品种按 timestamp 归入 train(<)/test(>=)，保证
        各品种 test 窗口时间对齐，且 train/test 时间不交叉（无跨品种泄漏）。
        - test_ratio<=0：不切分，train 复用原对象，test 返回空 dict；
        - test_ratio>0：train/test 均 copy；test 段 0 行的品种不放入 test_map。
        """
        if test_ratio <= 0:
            return raw_map, {}
        pooled = pd.concat([_timestamps_to_datetime(df["timestamp"]) for df in raw_map.values()])
        cutoff = pooled.quantile(1.0 - test_ratio)
        train_map: dict[str, pd.DataFrame] = {}
        test_map: dict[str, pd.DataFrame] = {}
        for symbol, df in raw_map.items():
            dt_index = _timestamps_to_datetime(df["timestamp"])
            train_map[symbol] = df[dt_index.to_numpy() < cutoff.to_numpy()].copy()
            test_df = df[dt_index.to_numpy() >= cutoff.to_numpy()].copy()
            if len(test_df) > 0:
                test_map[symbol] = test_df
        return train_map, test_map

    @staticmethod
    def _wf_bounds(
        raw_map: dict[str, pd.DataFrame], test_ratio: float, wf_folds: int
    ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """滚动 walk-forward 的折边界：把 OOS 总跨度等分为 k 个左闭右开连续窗口。

        OOS 跨度沿用 _split_raw_map 的全局时间戳池（全部品种 timestamp 池的
        [1-test_ratio, 1] 分位区间），保证品种间窗口对齐；k-1 个内边界取 OOS
        区间时间戳的 j/k 分位，折为 [b_j, b_{j+1})，最后一折右端含 oos_end。
        返回 [(start, end), ...]，边界单调、无重叠、连续覆盖整个 OOS 区间。
        """
        pooled = pd.concat([_timestamps_to_datetime(df["timestamp"]) for df in raw_map.values()])
        oos_start = pooled.quantile(1.0 - test_ratio)
        oos_end = pooled.max()
        oos = pooled[pooled >= oos_start]
        edges = [oos_start]
        for j in range(1, wf_folds):
            edges.append(oos.quantile(j / wf_folds))
        edges.append(oos_end)
        return [(edges[j], edges[j + 1]) for j in range(wf_folds)]

    def _fold_metrics(
        self,
        code: str,
        raw_map: dict[str, pd.DataFrame],
        fold_start: pd.Timestamp,
        fold_end: pd.Timestamp,
        *,
        interval: str,
        method: str,
        forward: int,
        window: int,
        label: str,
        index: int = 0,
        last: bool = False,
    ) -> dict[str, Any]:
        """单个 walk-forward 折的轻量指标（不跑分组/decay/净值，小窗口无意义）。

        - **扩展前缀执行**：因子在「每品种 ts<=fold_end 的全部历史前缀」上独立
          沙箱执行（copy、独立子进程）——rolling/ewm 的 warmup 来自真实历史前缀，
          且不使用折结束之后的数据（无前视，禁止全量跑完再切片）；
        - 前瞻收益按品种 shift(-forward)，折末 forward 根收益为 NaN 被 dropna
          自然丢弃（属正常）；指标行只保留 fold 窗口内（左闭右开，last 折含右端）；
        - coverage 口径：折窗口内（所有品种的窗口时间点）factor 非空行数 / 窗口
          原始总行数，在**前瞻收益 dropna 之前**统计（前瞻尾部不算缺失，因子 NaN
          与品种无数据计入分母）；
        - 窗口内有效时间点 <3（多品种截面 IC 的最低要求）或无品种 → ic_* 为 None，
          bar_count/coverage 如实返回，不抛异常，由 _aggregate_wf 决定是否纳入汇总。
        """
        prefix_map, window_rows = self._fold_prefix(raw_map, fold_start, fold_end, last)
        if not prefix_map or window_rows <= 0:
            return self._empty_fold(index, fold_start, fold_end)
        series_map = self._sandbox.run(code, prefix_map)
        factor = self.assemble_code_panel(label, series_map, prefix_map)
        return self._score_fold_panel(
            factor,
            prefix_map,
            fold_start,
            fold_end,
            method=method,
            forward=forward,
            window=window,
            index=index,
            last=last,
            window_rows=window_rows,
        )

    @staticmethod
    def _fold_prefix(
        raw_map: dict[str, pd.DataFrame],
        fold_start: pd.Timestamp,
        fold_end: pd.Timestamp,
        last: bool,
    ) -> tuple[dict[str, pd.DataFrame], int]:
        """切出折前缀数据（代码因子/合成因子共用）：(prefix_map, window_rows)。

        - prefix_map：每品种 ts<=fold_end 的全部历史前缀（copy），rolling/ewm 的
          warmup 来自真实历史前缀，不用折结束之后的数据（无前视，禁止全量跑完再切）；
        - window_rows：折窗口 [fold_start, fold_end)（last 折含右端）内原始总行数，
          作为 coverage 分母。
        """
        prefix_map: dict[str, pd.DataFrame] = {}
        window_rows = 0
        for symbol, df in raw_map.items():
            dt = _timestamps_to_datetime(df["timestamp"])
            dt_np = dt.to_numpy()
            prefix = df[dt_np <= fold_end.to_numpy()].copy()
            in_window = dt_np >= fold_start.to_numpy()
            in_window &= dt_np <= fold_end.to_numpy() if last else dt_np < fold_end.to_numpy()
            window_rows += int(in_window.sum())
            if len(prefix) > 0:
                prefix_map[symbol] = prefix
        return prefix_map, window_rows

    @staticmethod
    def _empty_fold(index: int, fold_start: pd.Timestamp, fold_end: pd.Timestamp) -> dict[str, Any]:
        return {
            "index": index,
            "start": fold_start.isoformat(),
            "end": fold_end.isoformat(),
            "ic_mean": None,
            "ic_std": None,
            "positive_rate": None,
            "coverage": None,
            "bar_count": 0,
        }

    def _score_fold_panel(
        self,
        factor: pd.Series,
        prefix_map: dict[str, pd.DataFrame],
        fold_start: pd.Timestamp,
        fold_end: pd.Timestamp,
        *,
        method: str,
        forward: int,
        window: int,
        index: int = 0,
        last: bool = False,
        window_rows: int | None = None,
    ) -> dict[str, Any]:
        """折前缀上已算好的因子面板 → 单折轻量指标（不跑分组/decay/净值，小窗口无意义）。

        与因子如何执行（单代码沙箱 / 多代码合成）无关，_fold_metrics 与
        analyze_composite 的 wf 路径共用本函数，保证折口径不分叉：
        - 前瞻收益按品种 shift(-forward)，折末 forward 根 NaN 被 dropna 自然丢弃；
          指标行只保留 fold 窗口内（左闭右开，last 折含右端）；
        - coverage 为折窗口内 factor 非空行数 / 窗口原始总行数，在**前瞻收益
          dropna 之前**统计；window_rows 由 _fold_prefix 统一计算；
        - 窗口内有效时间点 <3（多品种截面 IC 最低要求）→ ic_* 为 None，
          bar_count/coverage 如实返回，不抛异常，由 _aggregate_wf 决定是否纳入。
        """
        if window_rows is None:
            _, window_rows = self._fold_prefix(prefix_map, fold_start, fold_end, last)
        fold = self._empty_fold(index, fold_start, fold_end)
        close = close_panel_from_raw(prefix_map)
        aligned = pd.concat([factor.rename("f"), close.rename("c")], axis=1).dropna()

        dt_aligned = aligned.index.get_level_values(0)
        win_mask = dt_aligned >= fold_start
        win_mask &= dt_aligned <= fold_end if last else dt_aligned < fold_end
        window_df = aligned[win_mask]
        fold["coverage"] = self._coverage(window_df["f"], window_rows)

        forward_ret = (aligned["c"].groupby(level=1).shift(-forward) / aligned["c"] - 1).rename("r")
        df = pd.concat([aligned["f"], forward_ret], axis=1).dropna()
        dt_df = df.index.get_level_values(0)
        fold_mask = dt_df >= fold_start
        fold_mask &= dt_df <= fold_end if last else dt_df < fold_end
        df = df[fold_mask]
        fold["bar_count"] = len(df)

        # 折窗口有效时间点 <3 → IC 不估计：_ic_series 在多品种但日期不足时会
        # 退化为时序滚动相关，小窗口下无意义，按计划直接置 None（bar_count 如实保留）
        n_points = df.index.get_level_values(0).nunique()
        if n_points < 3:
            return fold
        ic_series = self._ic_series(df["f"], df["r"], method, window)
        if len(ic_series):
            fold["ic_mean"] = float(ic_series.mean())
            fold["ic_std"] = float(ic_series.std()) if len(ic_series) > 1 else None
            fold["positive_rate"] = float((ic_series > 0).mean())
        return fold

    @staticmethod
    def _aggregate_wf(
        folds: list[dict[str, Any]], train_ic: float | None
    ) -> tuple[dict[str, Any], str | None, str | None]:
        """多折 walk-forward 汇总（纯函数），返回 (metrics_oos, oos_flag, oos_note)。

        加权口径：
        - ic_mean：各折 ic_mean 按该折 bar_count 加权；ic_mean 为 None 的折样本
          不足，跳过加权但仍计入 n_folds；
        - ic_std：各**非空折 ic_mean 的折间样本标准差**（ddof=1），不是折内 ic_std
          的平均；仅 1 个有效折时折间离散度不可估计 → None（ic_ir 随之 None）；
        - coverage：按各折 bar_count 加权（折 coverage 已按折窗口归一，权重取该折
          有效样本量；coverage 独立于 IC 有效性，IC 空折仍参与）；
        - sign_consistency：非空折 ic_mean 与加权 ic_mean 同号的比例；无有效折→None。
        oos_flag 与单次切分同口径（train_ic 与加权 wf ic：反号 sign_flip、
        |wf|<0.5|train| weak、否则 ok；任一缺失 → None）。
        """
        n_folds = len(folds)
        valid = [f for f in folds if f.get("ic_mean") is not None]
        n_valid = len(valid)
        bar_count = int(sum(int(f.get("bar_count") or 0) for f in folds))
        metrics: dict[str, Any] = {
            "ic_mean": None,
            "ic_std": None,
            "ic_ir": None,
            "coverage": None,
            "bar_count": bar_count,
            "sign_consistency": None,
            "n_folds": n_folds,
            "valid_folds": n_valid,
        }

        # coverage 不依赖 IC 有效性：只要折有 coverage 与正样本量即纳入加权
        cov_num = sum(
            (f.get("coverage") or 0.0) * max(int(f.get("bar_count") or 0), 0)
            for f in folds
            if f.get("coverage") is not None
        )
        cov_den = sum(max(int(f.get("bar_count") or 0), 0) for f in folds if f.get("coverage") is not None)
        if cov_den > 0:
            metrics["coverage"] = float(cov_num / cov_den)

        notes: list[str] = []
        if n_valid < n_folds:
            notes.append(f"{n_folds - n_valid}/{n_folds} 个窗口样本不足，未纳入汇总")

        flag: str | None = None
        if valid:
            ics = np.array([f["ic_mean"] for f in valid], dtype=float)
            weights = np.array([max(int(f.get("bar_count") or 0), 0) for f in valid], dtype=float)
            if weights.sum() > 0:
                w = weights / weights.sum()
            else:  # 防御：IC 非空通常 bar_count>0；全 0 时退化为等权
                w = np.full(n_valid, 1.0 / n_valid)
            ic_mean = float(np.dot(w, ics))
            metrics["ic_mean"] = ic_mean
            if n_valid >= 2:
                ic_std = float(ics.std(ddof=1))
                metrics["ic_std"] = ic_std
                metrics["ic_ir"] = (ic_mean / ic_std) if ic_std else None
            same = int(((ics > 0) & (ic_mean > 0) | (ics < 0) & (ic_mean < 0)).sum())
            metrics["sign_consistency"] = float(same / n_valid)

            if train_ic is not None:
                if train_ic * ic_mean < 0:
                    flag = "sign_flip"
                    notes.insert(
                        0,
                        f"样本外 IC 符号反转（train={train_ic:.4f}，wf={ic_mean:.4f}），疑似过拟合",
                    )
                elif abs(ic_mean) < 0.5 * abs(train_ic):
                    flag = "weak"
                    notes.insert(
                        0,
                        f"样本外 IC 衰减过半（train={train_ic:.4f}，wf={ic_mean:.4f}），样本外减弱",
                    )
                else:
                    flag = "ok"
        return metrics, flag, ("；".join(notes) if notes else None)

    def analyze_code_panel(
        self,
        code: str,
        raw_map: dict[str, pd.DataFrame],
        *,
        interval: str,
        method: str = "spearman",
        n_groups: int = 5,
        window: int = 20,
        forward: int = 1,
        horizons: tuple[int, ...] | None = None,
        cost_bps: float = 0.0,
        label: str = "llm_candidate",
        test_ratio: float = 0.0,
        wf_folds: int = 0,
    ) -> dict[str, Any]:
        """对尚未入库的代码走「沙箱执行 → 全指标分析」，供 LLM 挖掘闭环调用。

        两条样本外复核路径（均**独立沙箱执行**，不能在全量结果上切——rolling
        因子的 warmup 会把未来信息泄漏进复核段）：
        - wf_folds>=2 且 test_ratio>0：滚动 walk-forward。train 段仍为首个折起点
          之前（_split_raw_map 全局切点，fitness/排序口径不变），随后在 k 个递增
          历史前缀上逐折执行（共 1+k 次沙箱），折内只算截面 IC 轻量指标并加权汇总；
          返回 ``{"train", "test": None, "wf": {...}}``；
        - 否则（wf_folds=0/1 或 test_ratio=0）：单次 train/test 切分，返回
          ``{"train", "test": analysis|None, "wf": None}``；test 段因有效数据不足
          （FactorError「有效数据不足」）时 test=None，其余异常照常抛出。
        - 顶层额外透出 ``"train_factor"``：train_map 上的 MultiIndex(datetime,symbol)
          因子面板（wf/单次两条路径同一份），供 LLM 挖掘做候选间相关性去重；
          属内部字段，不允许出现在挖掘 HTTP 结果中（由 llm_miner 剥离）。
        """
        horizons = horizons or self.DEFAULT_HORIZONS

        def _run_segment(seg_map: dict[str, pd.DataFrame], seg_label: str) -> tuple[dict[str, Any], pd.Series]:
            series_map = self._sandbox.run(code, seg_map)
            factor = self.assemble_code_panel(seg_label, series_map, seg_map)
            close = close_panel_from_raw(seg_map)
            analysis = self._analyze_core(
                factor_name=seg_label,
                symbols=list(seg_map),
                interval=interval,
                raw_map=seg_map,
                factor=factor,
                close=close,
                method=method,
                n_groups=n_groups,
                window=window,
                forward=forward,
                horizons=horizons,
                cost_bps=cost_bps,
            )
            return analysis, factor

        train_map, test_map = self._split_raw_map(raw_map, test_ratio)
        train_analysis, train_factor = _run_segment(train_map, label)
        test_analysis: dict[str, Any] | None = None
        wf: dict[str, Any] | None = None

        if wf_folds >= 2 and test_ratio > 0:
            bounds = self._wf_bounds(raw_map, test_ratio, wf_folds)
            folds = [
                self._fold_metrics(
                    code,
                    raw_map,
                    fold_start,
                    fold_end,
                    interval=interval,
                    method=method,
                    forward=forward,
                    window=window,
                    label=f"{label}__wf{i}",
                    index=i,
                    last=(i == wf_folds - 1),
                )
                for i, (fold_start, fold_end) in enumerate(bounds)
            ]
            wf_metrics, wf_flag, wf_note = self._aggregate_wf(folds, train_analysis["ic"].get("mean"))
            wf = {"folds": folds, **wf_metrics, "oos_flag": wf_flag, "oos_note": wf_note}
        elif test_map:
            try:
                test_analysis, _test_factor = _run_segment(test_map, f"{label}__oos")
            except FactorError as exc:
                # 仅吞样本外段「有效数据不足」：候选本身有效，只是后段太短无法复核
                if "有效数据不足" not in str(exc):
                    raise
                test_analysis = None
        return {
            "train": train_analysis,
            "test": test_analysis,
            "wf": wf,
            "train_factor": train_factor,
        }

    def _composite_segment_panels(
        self,
        codes: list[str],
        weights: list[float],
        ts_stats_list: list[dict[str, Any]],
        seg_map: dict[str, pd.DataFrame],
        label: str,
    ) -> pd.Series:
        """段内逐成分独立沙箱执行后组合成单一合成面板（每成分 1 次沙箱）。"""
        panels = [self._run_code_panel(code, f"{label}__c{i}", seg_map) for i, code in enumerate(codes)]
        return self.build_composite(panels, weights, ts_stats_list)

    def analyze_composite(
        self,
        codes: list[str],
        weights: list[float],
        ts_stats_list: list[dict[str, Any]],
        raw_map: dict[str, pd.DataFrame],
        *,
        interval: str,
        method: str = "spearman",
        n_groups: int = 5,
        window: int = 20,
        forward: int = 1,
        horizons: tuple[int, ...] | None = None,
        cost_bps: float = 0.0,
        label: str = "composite",
        test_ratio: float = 0.0,
        wf_folds: int = 0,
    ) -> dict[str, Any]:
        """对尚未入库的多成分组合走「逐成分沙箱 → build_composite → 全指标分析」。

        返回结构与 analyze_code_panel 的 train/test/wf 完全相同（不含 train_factor）：
        ``{"train", "test", "wf"}``。weights/ts_stats 在 train 段冻结后由调用方
        （LLM 挖掘/持久化复算）下发，本方法不再拟合——组合方式对两条链路同一口径。

        沙箱成本（每成分独立子进程，禁止全量跑完再切）：
        - wf_folds>=2 且 test_ratio>0：每成分 1(train)+k(折前缀) 次，共 n*(1+k)；
        - 单次切分：train/test 各一次，共 2n（test_ratio=0 时仅 train，n 次）。
        """
        horizons = horizons or self.DEFAULT_HORIZONS

        def _core(seg_map: dict[str, pd.DataFrame], composite: pd.Series, seg_label: str) -> dict[str, Any]:
            close = close_panel_from_raw(seg_map)
            return self._analyze_core(
                factor_name=seg_label,
                symbols=list(seg_map),
                interval=interval,
                raw_map=seg_map,
                factor=composite,
                close=close,
                method=method,
                n_groups=n_groups,
                window=window,
                forward=forward,
                horizons=horizons,
                cost_bps=cost_bps,
            )

        train_map, test_map = self._split_raw_map(raw_map, test_ratio)
        train_composite = self._composite_segment_panels(codes, weights, ts_stats_list, train_map, label)
        train_analysis = _core(train_map, train_composite, label)
        test_analysis: dict[str, Any] | None = None
        wf: dict[str, Any] | None = None

        if wf_folds >= 2 and test_ratio > 0:
            bounds = self._wf_bounds(raw_map, test_ratio, wf_folds)
            folds: list[dict[str, Any]] = []
            for i, (fold_start, fold_end) in enumerate(bounds):
                last = i == wf_folds - 1
                prefix_map, window_rows = self._fold_prefix(raw_map, fold_start, fold_end, last)
                if not prefix_map or window_rows <= 0:
                    folds.append(self._empty_fold(i, fold_start, fold_end))
                    continue
                # 每成分在 ts<=fold_end 的真实历史前缀上独立沙箱执行 → 前缀内组合
                fold_panels = [
                    self._run_code_panel(code, f"{label}__c{j}__wf{i}", prefix_map) for j, code in enumerate(codes)
                ]
                fold_composite = self.build_composite(fold_panels, weights, ts_stats_list)
                folds.append(
                    self._score_fold_panel(
                        fold_composite,
                        prefix_map,
                        fold_start,
                        fold_end,
                        method=method,
                        forward=forward,
                        window=window,
                        index=i,
                        last=last,
                        window_rows=window_rows,
                    )
                )
            wf_metrics, wf_flag, wf_note = self._aggregate_wf(folds, train_analysis["ic"].get("mean"))
            wf = {"folds": folds, **wf_metrics, "oos_flag": wf_flag, "oos_note": wf_note}
        elif test_map:
            try:
                test_composite = self._composite_segment_panels(
                    codes, weights, ts_stats_list, test_map, f"{label}__oos"
                )
                test_analysis = _core(test_map, test_composite, f"{label}__oos")
            except FactorError as exc:
                # 与 analyze_code_panel 同口径：仅吞 test 段「有效数据不足」
                if "有效数据不足" not in str(exc):
                    raise
                test_analysis = None
        return {"train": train_analysis, "test": test_analysis, "wf": wf}

    def compare_factors(
        self,
        factor_names: list[str],
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
        horizons: list[int] | tuple[int, ...] | None = None,
        cost_bps: float = 0.0,
    ) -> dict:
        """2-5 个因子共用参数横向对比；逐因子 analyze（读盘缓存复用）+ IC 时序时间轴对齐。"""
        results = {
            name: self.analyze(
                name,
                symbols,
                interval,
                candle_type,
                start,
                end,
                method=method,
                n_groups=n_groups,
                window=window,
                forward=forward,
                provider=provider,
                horizons=horizons,
                cost_bps=cost_bps,
            )
            for name in factor_names
        }
        details = {d["name"]: d for d in self.get_factor_details()}
        labels = {name: details.get(name, {}).get("label", name) for name in factor_names}
        return self._assemble_compare(results, labels)

    @staticmethod
    def _assemble_compare(results: dict[str, dict], labels: dict[str, str] | None = None) -> dict:
        """把 {factor_name: analyze 结果} 组装成对比行 + 时间轴对齐的 IC 序列。

        同步 compare_factors 与异步 compare job 共用，保证两条链路口径一致。
        """
        labels = labels or {}
        rows = []
        ic_by_factor: dict[str, pd.Series] = {}
        for name, res in results.items():
            insp = res.get("inspection", {})
            rows.append(
                {
                    "factor_name": name,
                    "label": labels.get(name, name),
                    "coverage": insp.get("coverage"),
                    "turnover": insp.get("turnover"),
                    "ic_mean": res["ic"].get("mean"),
                    "ic_ir": res["ic"].get("ir"),
                    "annualized_ir": (insp.get("ic_stats") or {}).get("annualized_ir"),
                    "t_stat": (insp.get("ic_stats") or {}).get("t_stat"),
                    "nw_t_stat": (insp.get("ic_stats") or {}).get("nw_t_stat"),
                    "ic_positive_rate": res["ic"].get("positive_rate"),
                    "long_short_return": res.get("long_short_return"),
                    "monotonicity_spearman": res.get("monotonicity", {}).get("spearman"),
                    "stability_autocorr": res.get("stability", {}).get("mean_autocorr"),
                    "n_groups": len(res.get("groups", [])),
                    "bar_count": res.get("bar_count"),
                }
            )
            ic_by_factor[name] = pd.Series(
                {p["t"]: p["ic"] for p in res["ic"]["series"] if p["ic"] is not None},
                dtype=float,
            )

        # IC 时序按时间标签 outer 对齐，缺失补 None
        aligned_ic = pd.DataFrame(ic_by_factor).sort_index()
        return {
            "factors": rows,
            "ic_series": {
                "dates": aligned_ic.index.tolist(),
                "series": {
                    name: [None if pd.isna(v) else float(v) for v in aligned_ic[name]] for name in aligned_ic.columns
                },
            },
        }

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
