"""
验证案例模块
包含各种策略的验证案例
"""

from .base_case import ValidationCase, CaseResult
from .sma_cross_case import SmaCrossValidationCase
from .buy_hold_case import BuyHoldValidationCase

__all__ = [
    "ValidationCase",
    "CaseResult",
    "SmaCrossValidationCase",
    "BuyHoldValidationCase",
]
