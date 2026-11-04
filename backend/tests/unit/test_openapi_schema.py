"""环境级回归：OpenAPI 必须可生成（Swagger 可用），且研究路由在 schema 内。"""

from __future__ import annotations

from main import app


def test_openapi_schema_generation_includes_research():
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/research/sessions" in paths
    # 历史失败的根因模型必须能完整解析（曾经因 datetime 只在 TYPE_CHECKING 导入而失败）
    assert "ScheduledTaskCreate" in schema["components"]["schemas"]
