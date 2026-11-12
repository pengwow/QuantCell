"""能力开关只读端点 — P2-02

GET /api/v1/capabilities：输出当前部署的能力集（布尔字典）。
前端登录后据此过滤菜单、渲染能力降级页；无敏感信息，不挂鉴权。
"""

from fastapi import APIRouter

from common.schemas import ApiResponse
from config.capabilities import get_capabilities

router = APIRouter(prefix="/api/v1/capabilities", tags=["Capabilities"])


@router.get(
    "",
    summary="获取能力开关集",
    description="按部署形态裁剪的功能域开关（live_trading/agent_gateway/mcp_server），env 与 config.toml 可覆盖",
)
async def read_capabilities() -> ApiResponse:
    return ApiResponse(code=0, message="ok", data=get_capabilities())
