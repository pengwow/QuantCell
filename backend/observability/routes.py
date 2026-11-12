"""指标查询端点（P2-01）：GET /api/v1/metrics

返回 Prometheus 文本格式，供 prometheus/兼容抓取端拉取。
开关 observability.metrics_enabled 关闭（默认）时返回 404——不暴露端点存在性
之外的任何信息，回滚=关开关。
"""

from fastapi import APIRouter, HTTPException
from starlette.responses import Response

from observability.metrics import metrics_enabled, render_metrics

router = APIRouter(tags=["observability"])


@router.get(
    "/api/v1/metrics",
    summary="Prometheus 指标查询",
    description="返回 Prometheus 文本格式的指标数据；开关 observability.metrics_enabled "
    "关闭时 404（P2-01 指标埋点默认关闭）",
)
async def get_metrics() -> Response:
    if not metrics_enabled():
        raise HTTPException(status_code=404, detail="metrics disabled (observability.metrics_enabled=false)")
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
