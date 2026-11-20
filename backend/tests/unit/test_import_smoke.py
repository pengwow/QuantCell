"""环境级冒烟：backend 主应用可导入，FastAPI 实例已挂载路由。

`main.py` 模块级只做路由装配（不启动 lifespan / 不写库 / 不发网络请求），
因此直接 `from main import app` 即可覆盖「全部 router 模块能被导入」这一契约；
一旦某个路由模块的 import 断裂（模型循环导入、缺失符号等），本用例会先红。

注意：本仓 FastAPI 的 include_router 是惰性的（app.routes 里是 _IncludedRouter），
所以用 openapi() 展开后的 paths 校验路由确实挂上，而不是数 app.routes 条数。
"""

from __future__ import annotations


def test_import_main_app_exposes_fastapi_with_routes():
    from fastapi import FastAPI

    from main import app

    assert isinstance(app, FastAPI)
    assert app.routes, "FastAPI 实例未挂载任何路由"

    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert any(p.startswith("/api/v1/agent") for p in paths), "agent 路由未挂载"
