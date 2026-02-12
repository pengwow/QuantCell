"""
因子计算业务服务

实现因子计算的核心业务逻辑。

主要功能：
    - 因子管理：获取、添加、删除因子
    - 因子计算：单因子、多因子、所有因子计算
    - 因子分析：IC分析、IR分析、分组分析、单调性检验、稳定性检验
    - 因子验证：验证因子表达式有效性

类说明：
    FactorService: 因子服务类
        - get_factor_list(): 获取因子列表
        - get_factor_expression(): 获取因子表达式
        - add_factor(): 添加自定义因子
        - delete_factor(): 删除自定义因子
        - calculate_factor(): 计算单因子
        - calculate_factors(): 计算多因子
        - calculate_all_factors(): 计算所有因子
        - validate_factor_expression(): 验证因子表达式
        - get_factor_correlation(): 计算因子相关性
        - get_factor_descriptive_stats(): 获取因子统计
        - calculate_ic(): 计算IC
        - calculate_ir(): 计算IR
        - group_analysis(): 分组分析
        - factor_monotonicity_test(): 单调性检验
        - factor_stability_test(): 稳定性检验

异常：
    FactorError: 因子模块基础异常
    FactorNotFoundError: 因子不存在异常
    FactorExpressionError: 因子表达式错误异常

作者: QuantCell Team
创建日期: 2024-01-01
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

# 导入QLib相关模块
try:
    from qlib.data import D
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.data.ops import *

    QLIB_AVAILABLE = True
except ImportError:
    QLIB_AVAILABLE = False
    logger.warning("QLib未安装，因子计算功能将受限")


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

    def _load_builtin_factors(self) -> Dict[str, str]:
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

    def get_factor_list(self) -> List[str]:
        """
        获取所有支持的因子列表

        Returns:
            因子名称列表
        """
        return list(self.factors.keys())

    def get_factor_expression(self, factor_name: str) -> Optional[str]:
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
            raise FactorNotFoundError(f"因子不存在: {factor_name}")
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
            raise FactorExpressionError("因子名称不能为空")

        if not factor_expression or not factor_expression.strip():
            raise FactorExpressionError("因子表达式不能为空")

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
            raise FactorNotFoundError(f"因子不存在: {factor_name}")

        del self.factors[factor_name]
        logger.info(f"成功删除因子: {factor_name}")
        return True

    def calculate_factor(
        self,
        factor_name: str,
        instruments: List[str],
        start_time: str,
        end_time: str,
        freq: str = "day",
    ) -> Optional[pd.DataFrame]:
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
            raise FactorError("QLib未安装，无法计算因子")

        try:
            factor_expr = self.get_factor_expression(factor_name)

            logger.info(
                f"开始计算因子 {factor_name}，"
                f"标的数量: {len(instruments)}, "
                f"时间范围: {start_time} 至 {end_time}"
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
            raise FactorError(f"计算因子失败: {e}")

    def calculate_factors(
        self,
        factor_names: List[str],
        instruments: List[str],
        start_time: str,
        end_time: str,
        freq: str = "day",
    ) -> Optional[pd.DataFrame]:
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
            raise FactorError("QLib未安装，无法计算因子")

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
                raise FactorError("没有有效的因子表达式")

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
            raise FactorError(f"计算多个因子失败: {e}")

    def calculate_all_factors(
        self,
        instruments: List[str],
        start_time: str,
        end_time: str,
        freq: str = "day",
    ) -> Optional[pd.DataFrame]:
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

    def get_factor_correlation(self, factor_data: pd.DataFrame) -> Optional[pd.DataFrame]:
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

    def get_factor_descriptive_stats(self, factor_data: pd.DataFrame) -> Optional[pd.DataFrame]:
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
        return_data: pd.DataFrame,
        method: str = "spearman",
    ) -> Optional[pd.Series]:
        """
        计算因子的信息系数(IC)

        Args:
            factor_data: 因子值DataFrame
            return_data: 收益率DataFrame
            method: 相关性计算方法，默认为spearman

        Returns:
            IC值序列，失败返回None
        """
        try:
            aligned_factor, aligned_return = factor_data.align(return_data, join="inner")
            ic = aligned_factor.corrwith(aligned_return, method=method)
            logger.info(f"成功计算IC值，方法: {method}")
            return ic
        except Exception as e:
            logger.error(f"计算IC值失败: {e}")
            return None

    def calculate_ir(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        method: str = "spearman",
    ) -> Optional[float]:
        """
        计算因子的信息比率(IR)

        Args:
            factor_data: 因子值DataFrame
            return_data: 收益率DataFrame
            method: 相关性计算方法，默认为spearman

        Returns:
            IR值，失败返回None
        """
        try:
            ic = self.calculate_ic(factor_data, return_data, method)
            if ic is not None:
                ir = ic.mean() / ic.std()
                logger.info(f"成功计算IR值，方法: {method}, IR: {ir:.4f}")
                return ir
            return None
        except Exception as e:
            logger.error(f"计算IR值失败: {e}")
            return None

    def group_analysis(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        n_groups: int = 5,
    ) -> Optional[Dict[str, Any]]:
        """
        因子分组回测分析

        Args:
            factor_data: 因子值DataFrame
            return_data: 收益率DataFrame
            n_groups: 分组数量，默认为5

        Returns:
            分组回测结果，失败返回None
        """
        try:
            aligned_factor, aligned_return = factor_data.align(return_data, join="inner")

            groups = aligned_factor.groupby(level=1).apply(
                lambda x: pd.qcut(x, n_groups, labels=False, duplicates="drop") + 1
            )

            group_returns = aligned_return.groupby(
                [groups, aligned_return.index.get_level_values(1)]
            ).mean()

            cumulative_returns = group_returns.groupby(level=0).cumsum()

            long_short_return = group_returns.loc[n_groups] - group_returns.loc[1]
            cumulative_long_short = long_short_return.cumsum()

            logger.info(f"成功完成分组回测分析，分组数量: {n_groups}")
            return {
                "group_returns": group_returns,
                "cumulative_returns": cumulative_returns,
                "long_short_return": long_short_return,
                "cumulative_long_short": cumulative_long_short,
            }
        except Exception as e:
            logger.error(f"分组回测分析失败: {e}")
            return None

    def factor_monotonicity_test(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        n_groups: int = 5,
    ) -> Optional[Dict[str, Any]]:
        """
        因子单调性检验

        Args:
            factor_data: 因子值DataFrame
            return_data: 收益率DataFrame
            n_groups: 分组数量，默认为5

        Returns:
            单调性检验结果，失败返回None
        """
        try:
            group_result = self.group_analysis(factor_data, return_data, n_groups)

            if group_result is not None:
                group_returns = group_result["group_returns"].groupby(level=0).mean()
                monotonicity_score = group_returns.loc[n_groups] - group_returns.loc[1]

                from scipy.stats import spearmanr

                groups = list(range(1, n_groups + 1))
                monotonicity_corr, _ = spearmanr(groups, group_returns.values)

                logger.info(
                    f"成功完成因子单调性检验，"
                    f"单调性得分: {monotonicity_score:.4f}, "
                    f"相关性: {monotonicity_corr:.4f}"
                )
                return {
                    "group_returns": group_returns.to_dict(),
                    "monotonicity_score": monotonicity_score,
                    "monotonicity_corr": monotonicity_corr,
                }
            return None
        except Exception as e:
            logger.error(f"因子单调性检验失败: {e}")
            return None

    def factor_stability_test(
        self,
        factor_data: pd.DataFrame,
        window: int = 20,
    ) -> Optional[Dict[str, Any]]:
        """
        因子稳定性检验

        Args:
            factor_data: 因子值DataFrame
            window: 滚动窗口大小，默认为20

        Returns:
            稳定性检验结果，失败返回None
        """
        try:
            rolling_autocorr = factor_data.rolling(window=window).corr(
                factor_data.shift(1)
            )
            cross_std = factor_data.groupby(level=1).std()

            logger.info(f"成功完成因子稳定性检验，窗口大小: {window}")
            return {
                "rolling_autocorr": rolling_autocorr,
                "cross_std": cross_std,
            }
        except Exception as e:
            logger.error(f"因子稳定性检验失败: {e}")
            return None
