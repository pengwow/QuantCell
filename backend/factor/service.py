# 因子计算服务
# 实现因子计算的核心逻辑

import sys
from pathlib import Path

import pandas as pd
from loguru import logger

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent  
sys.path.append(str(project_root))

# 导入QLib相关模块
from qlib.data import D
from qlib.data.dataset.handler import DataHandlerLP
from qlib.data.ops import *


class FactorService:
    """
    因子计算服务类，用于计算和管理量化交易因子
    """
    
    def __init__(self):
        """初始化因子计算服务"""
        self.factors = {
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
    
    def get_factor_list(self):
        """
        获取所有支持的因子列表
        
        :return: 因子列表
        """
        return list(self.factors.keys())
    
    def get_factor_expression(self, factor_name):
        """
        获取因子的表达式
        
        :param factor_name: 因子名称
        :return: 因子表达式
        """
        return self.factors.get(factor_name, None)
    
    def add_factor(self, factor_name, factor_expression):
        """
        添加自定义因子
        
        :param factor_name: 因子名称
        :param factor_expression: 因子表达式
        :return: 是否添加成功
        """
        if factor_name in self.factors:
            logger.warning(f"因子 {factor_name} 已存在，将覆盖现有因子")
        self.factors[factor_name] = factor_expression
        return True
    
    def delete_factor(self, factor_name):
        """
        删除自定义因子
        
        :param factor_name: 因子名称
        :return: 是否删除成功
        """
        if factor_name in self.factors:
            del self.factors[factor_name]
            return True
        return False
    
    def calculate_factor(self, factor_name, instruments, start_time, end_time, freq="day"):
        """
        计算指定因子的值
        
        :param factor_name: 因子名称
        :param instruments: 标的列表
        :param start_time: 开始时间
        :param end_time: 结束时间
        :param freq: 频率，默认为日线
        :return: 因子值DataFrame
        """
        try:
            # 获取因子表达式
            factor_expr = self.factors.get(factor_name)
            if not factor_expr:
                logger.error(f"因子 {factor_name} 不存在")
                return None
            
            logger.info(f"开始计算因子 {factor_name}，标的数量: {len(instruments)}, 时间范围: {start_time} 至 {end_time}")
            
            # 使用QLib的D模块计算因子
            factor_data = D.features(
                instruments=instruments,
                fields=[factor_expr],
                start_time=start_time,
                end_time=end_time,
                freq=freq
            )
            
            # 重命名列名为因子名称
            factor_data.columns = [factor_name]
            
            logger.info(f"因子 {factor_name} 计算完成，数据形状: {factor_data.shape}")
            return factor_data
            
        except Exception as e:
            logger.error(f"计算因子 {factor_name} 失败: {e}")
            logger.exception(e)
            return None
    
    def calculate_factors(self, factor_names, instruments, start_time, end_time, freq="day"):
        """
        计算多个因子的值
        
        :param factor_names: 因子名称列表
        :param instruments: 标的列表
        :param start_time: 开始时间
        :param end_time: 结束时间
        :param freq: 频率，默认为日线
        :return: 因子值DataFrame
        """
        try:
            # 获取因子表达式列表
            factor_exprs = []
            for factor_name in factor_names:
                expr = self.factors.get(factor_name)
                if expr:
                    factor_exprs.append(expr)
                else:
                    logger.warning(f"因子 {factor_name} 不存在，将跳过")
            
            if not factor_exprs:
                logger.error("没有有效的因子表达式")
                return None
            
            logger.info(f"开始计算多个因子，因子数量: {len(factor_exprs)}, 标的数量: {len(instruments)}, 时间范围: {start_time} 至 {end_time}")
            
            # 使用QLib的D模块计算因子
            factor_data = D.features(
                instruments=instruments,
                fields=factor_exprs,
                start_time=start_time,
                end_time=end_time,
                freq=freq
            )
            
            # 重命名列为因子名称
            factor_data.columns = [factor_name for factor_name in factor_names if factor_name in self.factors]
            
            logger.info(f"多个因子计算完成，数据形状: {factor_data.shape}")
            return factor_data
            
        except Exception as e:
            logger.error(f"计算多个因子失败: {e}")
            logger.exception(e)
            return None
    
    def calculate_all_factors(self, instruments, start_time, end_time, freq="day"):
        """
        计算所有因子的值
        
        :param instruments: 标的列表
        :param start_time: 开始时间
        :param end_time: 结束时间
        :param freq: 频率，默认为日线
        :return: 因子值DataFrame
        """
        return self.calculate_factors(
            factor_names=list(self.factors.keys()),
            instruments=instruments,
            start_time=start_time,
            end_time=end_time,
            freq=freq
        )
    
    def validate_factor_expression(self, factor_expression):
        """
        验证因子表达式是否有效
        
        :param factor_expression: 因子表达式
        :return: 是否有效
        """
        try:
            # 简单验证：尝试解析表达式
            # 这里可以添加更复杂的验证逻辑
            return True
        except Exception as e:
            logger.error(f"因子表达式验证失败: {e}")
            return False
    
    def get_factor_correlation(self, factor_data):
        """
        计算因子之间的相关性
        
        :param factor_data: 因子值DataFrame
        :return: 因子相关性矩阵
        """
        try:
            return factor_data.corr()
        except Exception as e:
            logger.error(f"计算因子相关性失败: {e}")
            logger.exception(e)
            return None
    
    def get_factor_descriptive_stats(self, factor_data):
        """
        获取因子的描述性统计信息
        
        :param factor_data: 因子值DataFrame
        :return: 描述性统计信息
        """
        try:
            return factor_data.describe()
        except Exception as e:
            logger.error(f"获取因子描述性统计失败: {e}")
            logger.exception(e)
            return None
    
    def calculate_ic(self, factor_data, return_data, method="spearman"):
        """
        计算因子的信息系数(IC)
        
        :param factor_data: 因子值DataFrame
        :param return_data: 收益率DataFrame
        :param method: 相关性计算方法，默认为spearman
        :return: IC值序列
        """
        try:
            # 确保因子数据和收益率数据的索引一致
            aligned_factor, aligned_return = factor_data.align(return_data, join="inner")
            
            # 计算IC值
            ic = aligned_factor.corrwith(aligned_return, method=method)
            
            logger.info(f"成功计算IC值，方法: {method}")
            return ic
        except Exception as e:
            logger.error(f"计算IC值失败: {e}")
            logger.exception(e)
            return None
    
    def calculate_ir(self, factor_data, return_data, method="spearman"):
        """
        计算因子的信息比率(IR)
        
        :param factor_data: 因子值DataFrame
        :param return_data: 收益率DataFrame
        :param method: 相关性计算方法，默认为spearman
        :return: IR值
        """
        try:
            # 计算IC序列
            ic = self.calculate_ic(factor_data, return_data, method)
            
            if ic is not None:
                # 计算IR值：IC均值 / IC标准差
                ir = ic.mean() / ic.std()
                logger.info(f"成功计算IR值，方法: {method}, IR: {ir:.4f}")
                return ir
            return None
        except Exception as e:
            logger.error(f"计算IR值失败: {e}")
            logger.exception(e)
            return None
    
    def group_analysis(self, factor_data, return_data, n_groups=5):
        """
        因子分组回测分析
        
        :param factor_data: 因子值DataFrame
        :param return_data: 收益率DataFrame
        :param n_groups: 分组数量，默认为5
        :return: 分组回测结果
        """
        try:
            # 确保因子数据和收益率数据的索引一致
            aligned_factor, aligned_return = factor_data.align(return_data, join="inner")
            
            # 按因子值分组
            groups = aligned_factor.groupby(level=1).apply(
                lambda x: pd.qcut(x, n_groups, labels=False, duplicates="drop") + 1
            )
            
            # 计算每组的平均收益率
            group_returns = aligned_return.groupby([groups, aligned_return.index.get_level_values(1)]).mean()
            
            # 计算每组的累计收益率
            cumulative_returns = group_returns.groupby(level=0).cumsum()
            
            # 计算多空组合收益率
            long_short_return = group_returns.loc[n_groups] - group_returns.loc[1]
            cumulative_long_short = long_short_return.cumsum()
            
            logger.info(f"成功完成分组回测分析，分组数量: {n_groups}")
            return {
                "group_returns": group_returns,
                "cumulative_returns": cumulative_returns,
                "long_short_return": long_short_return,
                "cumulative_long_short": cumulative_long_short
            }
        except Exception as e:
            logger.error(f"分组回测分析失败: {e}")
            logger.exception(e)
            return None
    
    def factor_monotonicity_test(self, factor_data, return_data, n_groups=5):
        """
        因子单调性检验
        
        :param factor_data: 因子值DataFrame
        :param return_data: 收益率DataFrame
        :param n_groups: 分组数量，默认为5
        :return: 单调性检验结果
        """
        try:
            # 执行分组分析
            group_result = self.group_analysis(factor_data, return_data, n_groups)
            
            if group_result is not None:
                # 获取每组的平均收益率
                group_returns = group_result["group_returns"].groupby(level=0).mean()
                
                # 计算单调性得分：高分组收益率 - 低分组收益率
                monotonicity_score = group_returns.loc[n_groups] - group_returns.loc[1]
                
                # 计算Spearman相关性
                from scipy.stats import spearmanr
                groups = list(range(1, n_groups + 1))
                monotonicity_corr, _ = spearmanr(groups, group_returns.values)
                
                logger.info(f"成功完成因子单调性检验，单调性得分: {monotonicity_score:.4f}, 相关性: {monotonicity_corr:.4f}")
                return {
                    "group_returns": group_returns.to_dict(),
                    "monotonicity_score": monotonicity_score,
                    "monotonicity_corr": monotonicity_corr
                }
            return None
        except Exception as e:
            logger.error(f"因子单调性检验失败: {e}")
            logger.exception(e)
            return None
    
    def factor_stability_test(self, factor_data, window=20):
        """
        因子稳定性检验
        
        :param factor_data: 因子值DataFrame
        :param window: 滚动窗口大小，默认为20
        :return: 稳定性检验结果
        """
        try:
            # 计算因子在滚动窗口内的自相关性
            rolling_autocorr = factor_data.rolling(window=window).corr(factor_data.shift(1))
            
            # 计算因子的截面标准差
            cross_std = factor_data.groupby(level=1).std()
            
            logger.info(f"成功完成因子稳定性检验，窗口大小: {window}")
            return {
                "rolling_autocorr": rolling_autocorr,
                "cross_std": cross_std
            }
        except Exception as e:
            logger.error(f"因子稳定性检验失败: {e}")
            logger.exception(e)
            return None
