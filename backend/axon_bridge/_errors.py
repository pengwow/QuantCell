"""axon_quant 异常 → QuantCell 异常的映射规范。

所有 QuantCell 业务代码抛出的 axon_quant 异常,经 map_error 包装后
统一提供 http_status + code + to_http() 三件套。

包名说明:本目录命名为 axon_bridge 而非 axon_quant,避免与
site-packages 的 axon_quant 同名导致循环导入。
"""

from __future__ import annotations

from fastapi import HTTPException


class AxonQuantError(Exception):
    """axon_quant 异常的 QuantCell 包装基类。"""

    http_status: int = 500
    code: str = "axon_quant_error"

    def __init__(self, original: Exception):
        self.original = original
        self.message = str(original)
        super().__init__(self.message)

    def to_http(self) -> HTTPException:
        return HTTPException(
            status_code=self.http_status,
            detail={"code": self.code, "message": self.message},
        )


# axon_quant 0.11.x 错误类映射(缓存为模块级常量,避免每次重建)
# 如 axon_quant 未安装,映射为空使 map_error 回退到通用 500
try:
    from axon_quant import (
        AxonError,
        BacktestError,
        ComplianceError,
        DataError,
        DefiError,
        ExchangeError,
        InferenceError,
        OmsError,
    )
    from axon_quant.risk import RiskError

    _ERROR_MAPPING: dict[type, tuple[int, str]] = {
        DataError: (400, "data_error"),
        OmsError: (409, "oms_conflict"),
        ExchangeError: (502, "exchange_error"),
        BacktestError: (500, "backtest_error"),
        ComplianceError: (500, "compliance_error"),
        InferenceError: (500, "inference_error"),
        DefiError: (500, "defi_error"),
        RiskError: (403, "risk_rejected"),
    }
    _AXON_ERROR_BASE = AxonError  # 基类兜底用
except ImportError:
    _ERROR_MAPPING = {}
    _AXON_ERROR_BASE = None


def map_error(e: Exception) -> AxonQuantError:
    """axon_quant 异常 → QuantCell AxonQuantError。

    已知异常类型用 _ERROR_MAPPING 映射;AxonError 基类兜底;
    未知类型(非 axon_quant)回退到 500 通用错误。
    """
    # 先匹配最具体的子类(如 DataError → 400)
    for src_type, (status, code) in _ERROR_MAPPING.items():
        if isinstance(e, src_type):
            exc = AxonQuantError(e)
            exc.http_status = status
            exc.code = code
            return exc

    # AxonError 基类兜底:所有 axon_quant 未分类异常 → 500
    if _AXON_ERROR_BASE is not None and isinstance(e, _AXON_ERROR_BASE):
        exc = AxonQuantError(e)
        exc.http_status = 500
        exc.code = "axon_error"
        return exc

    # 非 axon_quant 异常:通用 500
    return AxonQuantError(e)
