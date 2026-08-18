"""因子计算业务服务 — 因子管理/计算/分析"""

from __future__ import annotations

from typing import Any

import pandas as pd

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# QLib 仅用于因子计算（D.features），分析方法不依赖它
try:
    import qlib.data.ops as _qlib_ops
    from qlib.data import D

    QLIB_AVAILABLE = True
except ImportError:
    QLIB_AVAILABLE = False
    logger.debug("QLib 未安装，因子计算（calculate_factor）将不可用，分析功能不受影响")


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

    提供因子计算和管理的核心业务逻辑。

    Attributes:
        factors: 因子字典，存储所有可用因子

    Example:
        >>> service = FactorService()
        >>> factors = service.get_factor_list()
        >>> result = service.calculate_factor("momentum_5d", ["BTCUSDT"], "2023-01-01", "2023-12-31")
    """

    def __init__(self) -> None:
        """
        初始化因子计算服务

        加载内置因子并初始化服务状态。
        """
        self.factors = self._load_builtin_factors()
        logger.info(f"FactorService初始化完成，共加载 {len(self.factors)} 个因子")

    def _load_builtin_factors(self) -> dict[str, str]:
        """
        加载内置因子

        Returns:
            内置因子字典
        """
        return {
            # 价格相关因子
            "close": "$close",
            "open": "$open",
            "high": "$high",
            "low": "$low",
            "volume": "$volume",
            "vwap": "$vwap",
            "amount": "$volume * $close",
            # 动量因子
            "momentum_5d": "$close / $Ref($close, 5) - 1",
            "momentum_10d": "$close / $Ref($close, 10) - 1",
            "momentum_20d": "$close / $Ref($close, 20) - 1",
            "momentum_60d": "$close / $Ref($close, 60) - 1",
            # 波动率因子
            "volatility_5d": "$Std($close, 5)",
            "volatility_10d": "$Std($close, 10)",
            "volatility_20d": "$Std($close, 20)",
            "volatility_60d": "$Std($close, 60)",
            # 量价因子
            "turnover_rate": "$volume / $Ref($volume, 20)",
            "volume_change": "$volume / $Ref($volume, 1) - 1",
            "price_volume": "($close - $open) * $volume",
            # 技术指标因子
            "ma_5d": "$MA($close, 5)",
            "ma_10d": "$MA($close, 10)",
            "ma_20d": "$MA($close, 20)",
            "ma_60d": "$MA($close, 60)",
            "macd": "$MACD($close, 12, 26, 9)",
            "rsi_14d": "$RSI($close, 14)",
            "kdj": "$KDJ($high, $low, $close, 9, 3, 3)",
            "bollinger": "$BBANDS($close, 20, 2)",
            # 财务因子（需要财务数据支持）
            "pe": "$close / $Ref($eps, 1)",
            "pb": "$close / $Ref($bvps, 1)",
            "roe": "$Ref($net_profit, 1) / $Ref($equity, 1)",
            "roa": "$Ref($net_profit, 1) / $Ref($assets, 1)",
            "profit_growth": "$Ref($net_profit, 1) / $Ref($net_profit, 2) - 1",
        }

    def get_factor_list(self) -> list[str]:
        """
        获取所有支持的因子列表

        Returns:
            因子名称列表
        """
        return list(self.factors.keys())

    def get_factor_expression(self, factor_name: str) -> str | None:
        """
        获取因子的表达式

        Args:
            factor_name: 因子名称

        Returns:
            因子表达式，不存在返回None

        Raises:
            FactorNotFoundError: 因子不存在时抛出
        """
        expression = self.factors.get(factor_name)
        if expression is None:
            msg = f"因子不存在: {factor_name}"
            raise FactorNotFoundError(msg)
        return expression

    def add_factor(self, factor_name: str, factor_expression: str) -> bool:
        """
        添加自定义因子

        Args:
            factor_name: 因子名称
            factor_expression: 因子表达式

        Returns:
            是否添加成功

        Raises:
            FactorExpressionError: 表达式无效时抛出
        """
        if not factor_name or not factor_name.strip():
            msg = "因子名称不能为空"
            raise FactorExpressionError(msg)

        if not factor_expression or not factor_expression.strip():
            msg = "因子表达式不能为空"
            raise FactorExpressionError(msg)

        if factor_name in self.factors:
            logger.warning(f"因子 {factor_name} 已存在，将覆盖现有因子")

        self.factors[factor_name] = factor_expression.strip()
        logger.info(f"成功添加因子: {factor_name}")
        return True

    def delete_factor(self, factor_name: str) -> bool:
        """
        删除自定义因子

        Args:
            factor_name: 因子名称

        Returns:
            是否删除成功

        Raises:
            FactorNotFoundError: 因子不存在时抛出
        """
        if factor_name not in self.factors:
            msg = f"因子不存在: {factor_name}"
            raise FactorNotFoundError(msg)

        del self.factors[factor_name]
        logger.info(f"成功删除因子: {factor_name}")
        return True

    def calculate_factor(
        self,
        factor_name: str,
        instruments: list[str],
        start_time: str,
        end_time: str,
        freq: str = "day",
    ) -> pd.DataFrame | None:
        """
        计算指定因子的值

        Args:
            factor_name: 因子名称
            instruments: 标的列表
            start_time: 开始时间，格式：YYYY-MM-DD
            end_time: 结束时间，格式：YYYY-MM-DD
            freq: 频率，默认为日线

        Returns:
            因子值DataFrame，失败返回None

        Raises:
            FactorNotFoundError: 因子不存在时抛出
            FactorError: 计算失败时抛出
        """
        if not QLIB_AVAILABLE:
            msg = "QLib未安装，无法计算因子"
            raise FactorError(msg)

        try:
            factor_expr = self.get_factor_expression(factor_name)

            logger.info(
                f"开始计算因子 {factor_name}，标的数量: {len(instruments)}, 时间范围: {start_time} 至 {end_time}"
            )

            factor_data = D.features(
                instruments=instruments,
                fields=[factor_expr],
                start_time=start_time,
                end_time=end_time,
                freq=freq,
            )

            factor_data.columns = [factor_name]

            logger.info(f"因子 {factor_name} 计算完成，数据形状: {factor_data.shape}")
            return factor_data

        except FactorNotFoundError:
            raise
        except Exception as e:
            logger.error(f"计算因子 {factor_name} 失败: {e}")
            msg = f"计算因子失败: {e}"
            raise FactorError(msg)

    def calculate_factors(
        self,
        factor_names: list[str],
        instruments: list[str],
        start_time: str,
        end_time: str,
        freq: str = "day",
    ) -> pd.DataFrame | None:
        """
        计算多个因子的值

        Args:
            factor_names: 因子名称列表
            instruments: 标的列表
            start_time: 开始时间，格式：YYYY-MM-DD
            end_time: 结束时间，格式：YYYY-MM-DD
            freq: 频率，默认为日线

        Returns:
            因子值DataFrame，失败返回None

        Raises:
            FactorError: 计算失败时抛出
        """
        if not QLIB_AVAILABLE:
            msg = "QLib未安装，无法计算因子"
            raise FactorError(msg)

        try:
            factor_exprs = []
            valid_factor_names = []

            for factor_name in factor_names:
                try:
                    expr = self.get_factor_expression(factor_name)
                    factor_exprs.append(expr)
                    valid_factor_names.append(factor_name)
                except FactorNotFoundError:
                    logger.warning(f"因子 {factor_name} 不存在，将跳过")

            if not factor_exprs:
                msg = "没有有效的因子表达式"
                raise FactorError(msg)

            logger.info(
                f"开始计算多个因子，"
                f"因子数量: {len(factor_exprs)}, "
                f"标的数量: {len(instruments)}, "
                f"时间范围: {start_time} 至 {end_time}"
            )

            factor_data = D.features(
                instruments=instruments,
                fields=factor_exprs,
                start_time=start_time,
                end_time=end_time,
                freq=freq,
            )

            factor_data.columns = valid_factor_names

            logger.info(f"多个因子计算完成，数据形状: {factor_data.shape}")
            return factor_data

        except Exception as e:
            logger.error(f"计算多个因子失败: {e}")
            msg = f"计算多个因子失败: {e}"
            raise FactorError(msg)

    def calculate_all_factors(
        self,
        instruments: list[str],
        start_time: str,
        end_time: str,
        freq: str = "day",
    ) -> pd.DataFrame | None:
        """
        计算所有因子的值

        Args:
            instruments: 标的列表
            start_time: 开始时间，格式：YYYY-MM-DD
            end_time: 结束时间，格式：YYYY-MM-DD
            freq: 频率，默认为日线

        Returns:
            因子值DataFrame，失败返回None
        """
        return self.calculate_factors(
            factor_names=list(self.factors.keys()),
            instruments=instruments,
            start_time=start_time,
            end_time=end_time,
            freq=freq,
        )

    def validate_factor_expression(self, factor_expression: str) -> bool:
        """
        验证因子表达式是否有效

        Args:
            factor_expression: 因子表达式

        Returns:
            是否有效
        """
        try:
            if not factor_expression or not factor_expression.strip():
                return False

            # TODO: 实现更复杂的表达式验证逻辑
            return True
        except Exception as e:
            logger.error(f"因子表达式验证失败: {e}")
            return False

    def get_factor_correlation(self, factor_data: pd.DataFrame) -> pd.DataFrame | None:
        """
        计算因子之间的相关性

        Args:
            factor_data: 因子值DataFrame

        Returns:
            因子相关性矩阵，失败返回None
        """
        try:
            return factor_data.corr()
        except Exception as e:
            logger.error(f"计算因子相关性失败: {e}")
            return None

    def get_factor_descriptive_stats(self, factor_data: pd.DataFrame) -> pd.DataFrame | None:
        """
        获取因子的描述性统计信息

        Args:
            factor_data: 因子值DataFrame

        Returns:
            描述性统计信息，失败返回None
        """
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
        兼容 MultiIndex（QLib 格式：datetime×instrument）和普通 DataFrame/Series。
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

            from scipy.stats import spearmanr

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
            rolling_autocorr = factor_series.rolling(window=window).apply(
                lambda x: x.autocorr() if len(x.dropna()) > 1 else float("nan"),
                raw=False,
            )
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
