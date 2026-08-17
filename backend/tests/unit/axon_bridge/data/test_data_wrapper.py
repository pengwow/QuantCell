"""axon_quant.data 适配层测试。"""
from datetime import datetime


def test_data_service_importable():
    """DataService 应从适配层可导入。"""
    from backend.axon_bridge import DataService
    assert DataService is not None


def test_data_request_creation():
    """DataRequest 应可用,字段完整。"""
    from backend.axon_bridge import DataRequest, Frequency
    req = DataRequest(
        symbol="BTCUSDT",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 31),
        frequency=Frequency.Hour1,
    )
    assert req.symbol == "BTCUSDT"
    assert req.frequency == Frequency.Hour1


def test_frequency_enum_exposed():
    """Frequency 枚举应从适配层可导入,且包含 Hour1/Min1 等。"""
    from backend.axon_bridge import Frequency
    members = [m for m in dir(Frequency) if not m.startswith("_")]
    # 必须包含常用频率
    assert "Hour1" in members
    assert "Min1" in members
    assert "Day1" in members
