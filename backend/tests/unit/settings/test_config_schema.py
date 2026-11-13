"""settings.schema（P2-05 设置 schema 化）单元测试。

覆盖：
- GET /schema：分组/字段定义完整暴露、order 排序、advanced 标记
- GET /values：未配置项 default 兜底、存储值类型还原（bool/number）
- PUT /values：合法写入 + 回读一致、bool 的 "1"/"0" 存储口径与旧入口互通
- 校验拦截：未知 key 400、select 越界 400、类型不符 400（两阶段：校验失败不落库）
- 与旧接口兼容：PUT 写入后旧 GET /api/v1/config（按 name 分组）可见同一 key

策略：直接调用路由函数（无需走 HTTP 层），访客判定 monkeypatch 为 False。
存储走 conftest 的 DB_FILE 临时副本库，真实读写、零污染。
"""

import json

import pytest
from fastapi import HTTPException

from settings import routes
from settings.models import SystemConfigBusiness
from settings.schema import SETTINGS_SCHEMA, FieldType, find_field, restore_value
from settings.schemas import ConfigValuesUpdateRequest


@pytest.fixture(autouse=True)
def _not_guest(monkeypatch):
    """路由层访客判定统一视为已登录，鉴权矩阵由 integration/api/test_auth.py 覆盖"""
    monkeypatch.setattr(routes, "is_guest_user", lambda request: False)


def _update(values: dict):
    """PUT /values 路由函数的直调包装，返回 updated_count"""
    payload = ConfigValuesUpdateRequest(values=values)
    return routes.update_config_values(request=None, payload=payload).data["updated_count"]


# ---------------------------------------------------------------------------
# GET /schema
# ---------------------------------------------------------------------------


def test_schema_exposes_groups_and_fields():
    data = routes.get_config_schema().data
    groups = {g["key"]: g for g in data["groups"]}

    # order 排序生效
    orders = [g["order"] for g in data["groups"]]
    assert orders == sorted(orders)

    assert "general" in groups
    keys = [f["key"] for f in groups["general"]["fields"]]
    assert "theme" in keys and "language" in keys and "defaultPerPage" in keys


def test_schema_advanced_flag_present():
    fields = {f.key: f for f in SETTINGS_SCHEMA["general"].fields}
    assert fields["showTips"].advanced is True
    assert fields["theme"].advanced is False


# ---------------------------------------------------------------------------
# GET /values
# ---------------------------------------------------------------------------


def test_values_default_fallback_and_clean_state():
    # 先清掉 schema 字段的存量，保证从 default 起步
    for field_key in ("theme", "showTips", "defaultPerPage"):
        SystemConfigBusiness.delete(field_key)

    values = routes.get_config_values().data
    assert values["theme"] == "light"
    assert values["showTips"] is True  # bool default 还原为原生 bool
    assert values["defaultPerPage"] == 12


def test_restore_value_type_conversion():
    _, field = find_field("theme")
    assert restore_value(field, "dark") == "dark"
    assert restore_value(field, None) == "light"

    _, bool_field = find_field("showTips")
    assert restore_value(bool_field, "1") is True
    assert restore_value(bool_field, "0") is False


# ---------------------------------------------------------------------------
# PUT /values
# ---------------------------------------------------------------------------


def test_values_roundtrip_and_legacy_compat():
    updated = _update({"theme": "dark", "showTips": True, "defaultPerPage": 24})
    assert updated == 3

    # 回读：类型已还原
    values = routes.get_config_values().data
    assert values["theme"] == "dark"
    assert values["showTips"] is True
    assert values["defaultPerPage"] == 24

    # 存储口径：bool 落 "1"/"0"（SystemConfig.set 旧口径）
    assert SystemConfigBusiness.get("theme") == "dark"
    assert SystemConfigBusiness.get("showTips") == "1"
    assert SystemConfigBusiness.get("defaultPerPage") == "24"

    # name 分组 = 挂靠 group.key，旧接口 getConfig 按 'general' 分组可见
    details = SystemConfigBusiness.get_with_details("theme")
    assert details["name"] == "general"


def test_put_rejects_unknown_key_without_partial_write():
    # 清掉前序测试可能写入的值，保证"未写入"断言可信
    SystemConfigBusiness.delete("theme")
    with pytest.raises(HTTPException) as err:
        _update({"theme": "dark", "not_in_schema": "x"})
    assert err.value.status_code == 400
    assert "not_in_schema" in err.value.detail
    # 两阶段写入：非法批次一个 key 都不落
    assert SystemConfigBusiness.get("theme") != "dark"


def test_put_rejects_select_out_of_range_and_bad_number():
    from settings.schema import store_value

    _, theme_field = find_field("theme")
    with pytest.raises(ValueError, match="合法取值"):
        store_value(theme_field, "solarized")

    _, showtips_field = find_field("showTips")
    with pytest.raises(ValueError, match="bool"):
        store_value(showtips_field, "definitely-not-bool")

    num_field = find_field("defaultPerPage")[1]
    assert num_field.type == FieldType.NUMBER
    with pytest.raises(ValueError, match="数字"):
        store_value(num_field, "not-a-number")
    # 整值不带 ".0"
    assert store_value(num_field, 24) == "24"
    assert store_value(num_field, 24.5) == "24.5"


def test_bool_accepts_string_form():
    """部分前端表单提交字符串布尔，兼容 "true"/"false" 文本形态"""
    from settings.schema import store_value

    _, bool_field = find_field("showTips")
    assert store_value(bool_field, "true") == "1"
    assert store_value(bool_field, "false") == "0"
    with pytest.raises(ValueError):
        store_value(bool_field, "yes")


# ---------------------------------------------------------------------------
# chart 组（图表页偏好持久化：priceStyle/uiPrefs 以 JSON 字符串存储，解析归前端）
# ---------------------------------------------------------------------------


def test_schema_contains_chart_group():
    data = routes.get_config_schema().data
    groups = {g["key"]: g for g in data["groups"]}
    assert "chart" in groups
    keys = [f["key"] for f in groups["chart"]["fields"]]
    assert "priceStyle" in keys and "uiPrefs" in keys


def test_chart_price_style_roundtrip():
    SystemConfigBusiness.delete("priceStyle")
    raw = json.dumps({"candle.type": "renko", "yAxis.reverse": True})
    assert _update({"priceStyle": raw}) == 1
    # STRING 类型原样返回，不做 JSON 解析（解析归前端）
    values = routes.get_config_values().data
    assert values["priceStyle"] == raw
    assert SystemConfigBusiness.get("priceStyle") == raw
    # name 分组挂 chart，旧接口 GET /api/v1/config/ 按 chart 组可见
    assert SystemConfigBusiness.get_with_details("priceStyle")["name"] == "chart"


def test_chart_ui_prefs_roundtrip():
    SystemConfigBusiness.delete("uiPrefs")
    raw = json.dumps({"period": "4h", "symbol": "ETHUSDT", "timezone": "UTC"})
    assert _update({"uiPrefs": raw}) == 1
    assert json.loads(routes.get_config_values().data["uiPrefs"])["period"] == "4h"
