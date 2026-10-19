"""
因子计算模块

提供量化交易因子计算和管理功能。

主要功能：
    - 因子列表管理：获取支持的因子列表
    - 因子计算：计算单因子或多因子值
    - 因子分析：IC分析、IR分析、单调性分析等
    - 因子验证：验证因子有效性

数据来源：
    - 本地 parquet K 线（quality.parquet_provider）+ pandas 自有表达式引擎，无外部量化框架依赖

使用示例：
    >>> from factor import FactorService
    >>> service = FactorService()
    >>> factors = service.get_factor_list()
    >>> result = service.calculate_factor("momentum_5d", ["BTCUSDT"], None, None, interval="1h")

作者: QuantCell Team
创建日期: 2024-01-01
最后修改: 2024-01-01

版本: 1.0.0
"""

# 版本信息
__version__ = "1.0.0"
__author__ = "QuantCell Team"

# 惰性导出：factor.routes 在模块级构造 FactorService() 并立刻查询 factor_catalog 表，
# 若在 init_db() 建表（Base.metadata.create_all）之前触发导入，新库上必报
# "no such table: factor_catalog"，导致全新环境无法完成首次初始化。
# 改为首次访问属性时才导入，保证 `import factor.models` 只注册模型、不碰数据库。
# 与 backtest/__init__.py 的写法保持一致。
_LAZY_EXPORTS: dict[str, str] = {
    "router": ".routes",
    "FactorService": ".service",
    # 请求/响应模型
    "FactorAddRequest": ".schemas",
    "FactorAnalyzeRequest": ".schemas",
    "FactorCalculateBase": ".schemas",
    "FactorCalculateMultiRequest": ".schemas",
    "FactorCalculateRequest": ".schemas",
    "FactorCorrelationRequest": ".schemas",
    "FactorDetail": ".schemas",
    "FactorGroupAnalysisRequest": ".schemas",
    "FactorICRequest": ".schemas",
    "FactorIRRequest": ".schemas",
    "FactorMonotonicityRequest": ".schemas",
    "FactorStabilityRequest": ".schemas",
    "FactorStatsRequest": ".schemas",
    "FactorValidateRequest": ".schemas",
}


def __getattr__(name: str):
    """按需导入导出项（PEP 562）。"""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        msg = f"module '{__name__}' has no attribute '{name}'"
        raise AttributeError(msg)
    from importlib import import_module

    value = getattr(import_module(module_path, __name__), name)
    globals()[name] = value  # 缓存，后续访问走模块 __dict__
    return value


__all__ = [
    # 请求模型
    "FactorAddRequest",
    "FactorAnalyzeRequest",
    "FactorCalculateBase",
    "FactorCalculateMultiRequest",
    "FactorCalculateRequest",
    "FactorCorrelationRequest",
    "FactorDetail",
    "FactorGroupAnalysisRequest",
    "FactorICRequest",
    "FactorIRRequest",
    "FactorMonotonicityRequest",
    # 服务
    "FactorService",
    "FactorStabilityRequest",
    "FactorStatsRequest",
    "FactorValidateRequest",
    # 路由
    "router",
]
