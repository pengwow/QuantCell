"""
能力开关（capability flags）— P2-02

按部署形态裁剪功能域：桌面版可关闭实盘交易，团队版可关闭 Agent 网关。
纯读取、无迁移，读取优先级：
  env（QUANTCELL_CAPABILITY_<NAME>）> config.toml [capabilities] > 内置默认值。

默认值与现状兼容：live_trading / agent_gateway 开启（单机全功能）；
mcp_server 能力域尚未实现（P2-04 预留），默认关闭。
"""

import os
from enum import StrEnum

from fastapi import HTTPException

from utils.config_manager import get_flag
from utils.logger import get_logger

logger = get_logger(__name__)

# 实盘域交易模式：live / testnet 都走真实下单链路（strategy_manager 中 testnet 映射为
# run_mode="live"），仅 paper 是纯模拟。能力关闭时这三种之外的模式不受影响。
TRADING_LIVE_MODES = frozenset({"live", "testnet"})


class Capability(StrEnum):
    """能力域标识。值为 API / 配置中的小写下划线形式。"""

    LIVE_TRADING = "live_trading"
    AGENT_GATEWAY = "agent_gateway"
    MCP_SERVER = "mcp_server"


# 内置默认值：与单机版现状兼容；新增能力域时必须在此登记，
# 否则 get_capabilities 不会输出、get_flag 也查不到对应键
_DEFAULTS: dict[Capability, bool] = {
    Capability.LIVE_TRADING: True,
    Capability.AGENT_GATEWAY: True,
    Capability.MCP_SERVER: False,
}

_ENV_PREFIX = "QUANTCELL_CAPABILITY_"
_FALSE_STRINGS = frozenset({"0", "false", "no", "off"})
_TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})


def _from_env(cap: Capability) -> bool | None:
    """读环境变量覆盖值；未设置或值非法返回 None（继续走配置通道）。"""
    raw = os.environ.get(_ENV_PREFIX + cap.name)
    if raw is None:
        return None
    normalized = raw.strip().lower()
    if normalized in _FALSE_STRINGS:
        return False
    if normalized in _TRUE_STRINGS:
        return True
    logger.warning(f"能力开关环境变量值非法，已忽略: {_ENV_PREFIX + cap.name}={raw!r}")
    return None


def is_enabled(cap: Capability) -> bool:
    """能力是否开启。env 覆盖优先，其次 config.toml [capabilities] 分组，最后内置默认值。"""
    env_value = _from_env(cap)
    if env_value is not None:
        return env_value
    return bool(get_flag(f"capabilities.{cap.value}", _DEFAULTS[cap]))


def get_capabilities() -> dict[str, bool]:
    """输出全量能力集（供 /api/v1/capabilities 端点与前端能力菜单使用）。"""
    return {cap.value: is_enabled(cap) for cap in Capability}


def _forbidden(cap: Capability, reason: str) -> HTTPException:
    """统一 403 结构：detail.code 供机器判定，capability 名供前端定位降级文案。"""
    return HTTPException(
        status_code=403,
        detail={
            "code": 403,
            "message": f"能力未开启（{cap.value}）：{reason}",
            "data": {"capability": cap.value, "enabled": False},
        },
    )


def require_capability(cap: Capability):
    """FastAPI 依赖工厂：能力关闭时整组路由 403（用于 agent_gateway 等整域能力）。"""

    def dependency() -> None:
        if not is_enabled(cap):
            raise _forbidden(cap, "该功能域已在当前部署中关闭")

    return dependency


def require_live_trading(trading_mode: str) -> None:
    """实盘域校验：live/testnet 模式需要 live_trading 能力，paper 恒放行。

    挂点是交易闸门（创建含实盘配置的 worker / 启动 / 批量启动），update/clone 等
    配置搬运路径不拦——最终仍需经过启动端点才会产生交易行为。
    """
    if trading_mode in TRADING_LIVE_MODES and not is_enabled(Capability.LIVE_TRADING):
        raise _forbidden(Capability.LIVE_TRADING, f"trading_mode={trading_mode} 受实盘开关限制，请改用 paper")
