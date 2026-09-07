"""collector.schemas.system 单元测试。

覆盖 VersionInfo / RunningStatus / ResourceUsage / SystemInfoResponse 四个纯 Pydantic 模型：
- 字段必填校验
- 字段别名与序列化 round-trip
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from collector.schemas.system import ResourceUsage, RunningStatus, SystemInfoResponse, VersionInfo


def test_version_info_basic():
    v = VersionInfo(system_version="0.1.0", python_version="3.14.0", build_date="2026-09-07")
    assert v.system_version == "0.1.0"
    assert v.python_version == "3.14.0"
    assert v.build_date == "2026-09-07"


def test_version_info_missing_field_raises():
    with pytest.raises(ValidationError):
        VersionInfo(system_version="0.1.0")


def test_running_status_with_datetime():
    ts = datetime(2026, 9, 7, 10, 30, 0)
    rs = RunningStatus(uptime="3 天 2 小时", status="running", status_color="green", last_check=ts)
    assert rs.status == "running"
    assert rs.status_color == "green"
    # datetime 字段应保留为 datetime 对象
    assert rs.last_check == ts


def test_running_status_io_roundtrip():
    rs = RunningStatus(
        uptime="1 天 0 小时",
        status="running",
        status_color="green",
        last_check="2026-09-07T10:30:00",
    )
    data = rs.model_dump()
    assert data["status"] == "running"
    # 反序列化后仍可重建
    rs2 = RunningStatus.model_validate(data)
    assert rs2 == rs


def test_resource_usage():
    ru = ResourceUsage(cpu_usage=12.5, memory_usage="4.2GB / 16GB", disk_space="120GB / 512GB")
    assert ru.cpu_usage == 12.5
    assert ru.memory_usage == "4.2GB / 16GB".replace("4.2GB / 16GB", "4.2GB / 16GB")


def test_system_info_response_nested():
    v = VersionInfo(system_version="1.2.3", python_version="3.14", build_date="2026-01-01")
    rs = RunningStatus(
        uptime="0 天 0 小时",
        status="running",
        status_color="green",
        last_check=datetime(2026, 9, 7),
    )
    ru = ResourceUsage(cpu_usage=1.0, memory_usage="1GB / 8GB", disk_space="10GB / 100GB")
    resp = SystemInfoResponse(version=v, running_status=rs, resource_usage=ru)
    dumped = resp.model_dump()
    assert dumped["version"]["system_version"] == "1.2.3"
    assert dumped["running_status"]["status"] == "running"
    assert dumped["resource_usage"]["cpu_usage"] == 1.0
