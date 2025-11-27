# 因子计算服务模块
# 用于计算和管理量化交易因子

from .routes import router as factor_router
from .service import FactorService

__all__ = [
    "factor_router",
    "FactorService"
]
