"""B3 pre-trade 风控装配：worker_risk_control 人工开关三态优先，params.risk 直通兜底。

QuantCell 的金额/比例口径 → axon-risk 引擎 RiskConfig 的映射在这里收口，
四处驱动装配点（RL/规则 × paper/live）共用。
三态语义（spec §4.6，人工开关优先）：
- 表行 enabled=True → 人工配置赢过 params.risk（字段全空 → 装配引擎默认档）
- 表行 enabled=False → 强制停用（返回 None，人工取消优先）
- 无表行 → params.risk 直通（零行为变化；都未配置仍返回 None，opt-in 不变）

另含当日盈亏回灌器 `RiskPnlFeeder`：axon-risk 的 `update_daily_pnl` 是累加语义、
无内部日切，增量换算与跨日清零由 Python 侧驱动。
"""

from datetime import date
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


def _local_today() -> date:
    """风控「当日」口径：服务端本地日期（引擎本身无时区概念，日切由这里决定）。

    ponytail: 单一服务端时区，未按交易所时区分品种切日；多时区部署的
    升级路径是把时区作为配置传入并按品种维护独立基线。
    """
    return date.today()


def resolve_risk_settings(
    params: dict[str, Any],
    worker_id: int,
    initial_cash: float,
) -> tuple[dict[str, Any], float | None] | None:
    """三态装配（spec §4.6）：

    - 有表行且 enabled=True → 人工配置赢过 params.risk；
      字段全空返回 ({}, None)，装配引擎默认档（推翻旧「空行视为未配置」）
    - 有表行且 enabled=False → 强制停用（返回 None），人工取消优先
    - 无表行 → params.risk 直通（零行为变化）：键原样传给 Rust set_risk_config，
      未知键由 Rust 侧报错（统一单点校验，防拼错键名静默走默认值）；
      额外支持 "max_position_value"（目标净仓名义额上限，独立参数）。
    """
    row = _load_risk_control_row(worker_id)
    if row is not None:
        if not row["enabled"]:
            return None
        return _map_row_to_settings(row, initial_cash)

    risk = params.get("risk")
    if isinstance(risk, dict) and risk:
        config = dict(risk)
        max_position_value = config.pop("max_position_value", None)
        return config, max_position_value
    return None


def _map_row_to_settings(row: dict[str, Any], initial_cash: float) -> tuple[dict[str, Any], float | None]:
    """表行 → (引擎 config, max_position_value)。enabled=True 的行才会走到这里。

    「金额 = 比例 × 资金」转换，绝对金额字段优先于比例字段。
    """
    config: dict[str, Any] = {}
    max_position_value: float | None = None
    if row["max_position_pct"] and row["max_position_pct"] > 0:
        max_position_value = float(row["max_position_pct"]) * initial_cash
    if row["max_position_size"] and row["max_position_size"] > 0:
        # 绝对金额与比例换算值并存时取更严（更小）者
        size_value = float(row["max_position_size"])
        max_position_value = size_value if max_position_value is None else min(max_position_value, size_value)
    if row["daily_loss_amount"] and row["daily_loss_amount"] > 0:
        config["max_daily_loss"] = float(row["daily_loss_amount"])
    elif row["daily_loss_limit"] and row["daily_loss_limit"] > 0:
        config["max_daily_loss"] = float(row["daily_loss_limit"]) * initial_cash
    # 引擎白名单新键（risk_config_from_dict 五键之内）
    if row["max_drawdown"] and row["max_drawdown"] > 0:
        config["max_drawdown"] = float(row["max_drawdown"])
    if row["max_leverage"] and row["max_leverage"] > 0:
        config["max_leverage"] = float(row["max_leverage"])
    if row["circuit_breaker_cooldown_secs"] is not None:
        # 0 是合法值（禁用冷却等待），必须用 is not None 而非 truthy 判断
        config["circuit_breaker_cooldown_secs"] = int(row["circuit_breaker_cooldown_secs"])
    if max_position_value:
        # 单笔订单名义额上限对齐仓位上限：超出仓位上限的单笔必然被仓位检查拒，
        # 不需要更严的独立单笔限额（引擎默认 5 万元对大账户会误拒正常开仓）
        config["max_order_value"] = max_position_value
    return config, max_position_value


def apply_risk_config(
    driver: Any,
    params: dict[str, Any],
    worker_id: int,
    initial_cash: float,
) -> bool:
    """装配 pre-trade 风控到驱动（未配置 = 不调用 = 驱动行为不变）。

    配置错误（未知键 / 非法值等）由 Rust 侧抛 ValueError → 启动失败公开暴露，
    规避「以为有风控实际裸奔」的静默降级。

    Returns:
        是否实际装配（泵线程据此决定是否启用当日盈亏回灌）
    """
    settings = resolve_risk_settings(params, worker_id, initial_cash)
    if settings is None:
        return False
    config, max_position_value = settings
    driver.set_risk_config(config, max_position_value=max_position_value)
    logger.info(
        f"[risk_config] 风控已装配: worker_id={worker_id}, config={config}, max_position_value={max_position_value}"
    )
    return True


class RiskPnlFeeder:
    """当日盈亏回灌器：把累计口径观测值换算成增量喂给引擎，并负责跨日清零。

    引擎 `update_daily_pnl` 是累加语义且没有内部日切，Python 侧必须
    自己算增量、自己跨日 `reset_daily`（否则昨日亏损会一直压着今日额度）。

    Args:
        driver: PaperDriver / LiveDriver（绑定层方法在未配置风控时 no-op）
        daily_scoped: 观测值是否本身就是「当日」口径
            - True（live）：DB 当日已实现盈亏汇总，跨日天然从 0 起算；
              首次回灌即灌入全量当日值，重启不丢当日亏损额度
            - False（paper）：运行期权益快照，跨日基线取当日首个观测权益
    """

    def __init__(self, driver: Any, *, daily_scoped: bool) -> None:
        self._driver = driver
        self._daily_scoped = daily_scoped
        self._day = _local_today()
        # 当日盈亏基线（观测值口径下的「零点」）；None = 待当日首个观测确定
        self._day_start: float | None = None
        # 上一次已回灌的当日盈亏，用于换算增量
        self._last_pnl = 0.0

    def feed(self, value: float) -> None:
        """回灌一次累计口径观测值（delta 为 0 时不调引擎）。"""
        self.reset_if_new_day()
        if self._day_start is None:
            # daily_scoped 的观测值本身就是当日累计（从 0 起算），基线取 0；
            # 权益口径则以当日首个观测为基线，当日盈亏从 0 开始
            self._day_start = 0.0 if self._daily_scoped else value
        today_pnl = value - self._day_start
        delta = today_pnl - self._last_pnl
        self._last_pnl = today_pnl
        if delta:
            self._driver.update_risk_pnl(delta)

    def reset_if_new_day(self) -> bool:
        """日期变化时清零引擎当日盈亏与熔断器，返回是否发生日切。

        无新成交也要调用（live 泵每轮调）：否则昨日触发的熔断会一直挂到
        下一笔成交才有机会解除，空仓账户甚至永远等不到（熔断只拦扩仓，
        没有持仓也就没有减仓可放行）。
        """
        today = _local_today()
        if today == self._day:
            return False
        self._day = today
        self._day_start = None
        self._last_pnl = 0.0
        self._driver.reset_risk_daily()
        logger.info(f"[risk_config] 风控跨日清零（当日盈亏与熔断器归零）: day={today}")
        return True


def _load_risk_control_row(worker_id: int) -> dict[str, Any] | None:
    """读 worker_risk_control 单行 → 平铺 dict（无行 / 查询失败返回 None）。

    fallback 是尽力而为：查询失败只 warn（视为未配置），不阻断启动——
    正式风控配置请走 params.risk 直通口，它失败会直接抛错。
    返回平铺 dict 而非 ORM 对象：session 关闭后仍可安全访问。
    """
    try:
        # 函数内 import：沿项目惯例（dependencies.py / event_handler.py），
        # 避免模块加载期初始化数据库配置
        from utils.db_session import get_db_session

        from .models import WorkerRiskControl

        with get_db_session() as db:
            row = db.query(WorkerRiskControl).filter(WorkerRiskControl.worker_id == worker_id).first()
            if row is None:
                return None
            return {
                "enabled": bool(row.enabled),
                "max_position_pct": row.max_position_pct,
                "max_position_size": row.max_position_size,
                "daily_loss_amount": row.daily_loss_amount,
                "daily_loss_limit": row.daily_loss_limit,
                "max_drawdown": row.max_drawdown,
                "max_leverage": row.max_leverage,
                "circuit_breaker_cooldown_secs": row.circuit_breaker_cooldown_secs,
            }
    except Exception as e:
        logger.warning(f"[risk_config] worker_risk_control 查询失败（视为未配置）: worker_id={worker_id}, error={e}")
        return None


def push_risk_control(worker_id: int, driver: Any | None, params: dict, initial_cash: float) -> str:
    """把人工风控配置实时推送到运行中的 driver（不重启），返回 applied。

    - "hot": 已推送到运行中引擎（或人工停用已生效）
    - "on_start": 走启动前暂存/降级（driver 未启动、引擎未装配、旧 .so、推送异常）

    签名说明：params / initial_cash 由调用方（core_service）查询后传入，
    本模块不 import strategy 模型——避免 worker→strategy 循环依赖。
    """
    if driver is None:
        return "on_start"
    try:
        # 旧 .so（<0.22.5）无这三个方法：hasattr 探测，缺一个都降级回旧装配语义
        if not (
            hasattr(driver, "set_risk_enabled")
            and hasattr(driver, "update_risk_config")
            and hasattr(driver, "risk_assembled")
        ):
            return "on_start"
        resolved = resolve_risk_settings(params, worker_id, initial_cash)
        if resolved is None:
            # 人工取消/停用：bypass 全放行（引擎保留，不再检查）
            driver.set_risk_enabled(False)
            return "hot"
        config, max_position_value = resolved
        if not driver.risk_assembled():
            # 引擎未装配：走启动前暂存，等价 apply_risk_config 的旧路径
            driver.set_risk_config(config, max_position_value=max_position_value)
            return "on_start"
        # 顺序关键：先 set_enabled(True) 清 bypass，再换配置；
        # 顺序颠倒会把旧 bypass 残留到新配置上（换档后仍全放行）
        driver.set_risk_enabled(True)
        driver.update_risk_config(config, max_position_value)
        return "hot"
    except Exception as exc:
        logger.error(f"[risk_config] 风控配置推送失败 worker_id={worker_id}: {exc}")
        return "on_start"
