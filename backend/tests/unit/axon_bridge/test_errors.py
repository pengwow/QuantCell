"""适配层错误规范测试。"""
import pytest
from fastapi import HTTPException

# axon_quant 0.4.0 实际错误类(顶层)
from axon_quant import DataError, OmsError, ExchangeError


def test_data_error_maps_to_400():
    """DataError 应映射为 HTTP 400。"""
    from backend.axon_bridge._errors import map_error

    err = map_error(DataError("test"))
    assert err.http_status == 400
    assert err.code == "data_error"


def test_map_error_returns_axon_quant_error():
    """未知错误应包装为 AxonQuantError(500)。"""
    from backend.axon_bridge._errors import map_error, AxonQuantError

    err = map_error(ValueError("xxx"))
    assert isinstance(err, AxonQuantError)
    assert err.http_status == 500
    assert err.code == "axon_quant_error"


def test_to_http_creates_http_exception():
    """to_http() 应返回 FastAPI HTTPException。"""
    from backend.axon_bridge._errors import map_error

    err = map_error(DataError("bad request"))
    http = err.to_http()
    assert isinstance(http, HTTPException)
    assert http.status_code == 400
    assert http.detail["code"] == "data_error"


def test_oms_error_maps_to_409():
    """OmsError 应映射为 HTTP 409。"""
    from backend.axon_bridge._errors import map_error

    err = map_error(OmsError("conflict"))
    assert err.http_status == 409
    assert err.code == "oms_conflict"


def test_exchange_error_maps_to_502():
    """ExchangeError 应映射为 HTTP 502。"""
    from backend.axon_bridge._errors import map_error

    err = map_error(ExchangeError("binance down"))
    assert err.http_status == 502
    assert err.code == "exchange_error"
