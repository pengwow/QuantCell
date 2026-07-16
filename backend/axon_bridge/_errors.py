"""axon_quant 异常 → QuantCell 异常的映射规范。

所有 QuantCell 业务代码抛出的 axon_quant 异常,经 map_error 包装后
统一提供 http_status + code + to_http() 三件套。

包名说明:本目录命名为 axon_bridge 而非 axon_quant,避免与
site-packages 的 axon_quant 同名导致循环导入。
"""
from typing import Any
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


# axon_quant 0.4.0 错误类(顶层 + risk 子模块)
# 延迟导入避免循环依赖
def _build_mapping() -> dict[type, tuple[int, str]]:
    from axon_quant import (
        DataError, OmsError, ExchangeError,
        BacktestError, ComplianceError, InferenceError, DefiError,
    )
    from axon_quant.risk import RiskError
    return {
        DataError:        (400, "data_error"),
        OmsError:         (409, "oms_conflict"),
        ExchangeError:    (502, "exchange_error"),
        BacktestError:    (500, "backtest_error"),
        ComplianceError:  (500, "compliance_error"),
        InferenceError:   (500, "inference_error"),
        DefiError:        (500, "defi_error"),
        RiskError:        (403, "risk_rejected"),
    }


def map_error(e: Exception) -> AxonQuantError:
    """axon_quant 异常 → QuantCell AxonQuantError。

    已知异常类型用 ERROR_MAPPING 映射;未知类型回退到 500 通用错误。
    """
    mapping = _build_mapping()
    for src_type, (status, code) in mapping.items():
        if isinstance(e, src_type):
            exc: Any = AxonQuantError(e)
            exc.http_status = status
            exc.code = code
            return exc
    return AxonQuantError(e)
