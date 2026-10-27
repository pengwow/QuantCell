"""B3 pre-trade 风控装配：params.risk 直通优先，fallback worker_risk_control 表。

QuantCell 的金额/比例口径 → axon-risk 引擎 RiskConfig 的映射在这里收口，
四处驱动装配点（RL/规则 × paper/live）共用。
语义是 opt-in：两者都没配置时返回 None，驱动保持默认无风控行为（B3 之前行为不变）。

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
    """解析风控配置 → (config, max_position_value)，未配置返回 None。

    - params["risk"] 优先（直通口）：键原样传给 Rust set_risk_config，
      未知键由 Rust 侧报错（统一单点校验，防拼错键名静默走默认值）；
      额外支持 "max_position_value"（目标净仓名义额上限，独立参数）。
    - fallback 查 worker_risk_control 表：无行视为未配置；行存在时按
      「金额 = 比例 × 资金」转换，绝对金额字段优先于比例字段。
    """
    risk = params.get("risk")
    if isinstance(risk, dict) and risk:
        config = dict(risk)
        max_position_value = config.pop("max_position_value", None)
        return config, max_position_value

    row = _load_risk_control_row(worker_id)
    if row is None:
        return None

    config: dict[str, Any] = {}
    max_position_value: float | None = None
    if row["max_position_pct"] and row["max_position_pct"] > 0:
        max_position_value = float(row["max_position_pct"]) * initial_cash
    if row["max_position_size"] and row["max_position_size"] > 0:
        # 绝对金额与比例换算值并存时取更严（更小）者
        size_value = float(row["max_position_size"])
        max_position_value = (
            size_value if max_position_value is None else min(max_position_value, size_value)
        )
    if row["daily_loss_amount"] and row["daily_loss_amount"] > 0:
        config["max_daily_loss"] = float(row["daily_loss_amount"])
    elif row["daily_loss_limit"] and row["daily_loss_limit"] > 0:
        config["max_daily_loss"] = float(row["daily_loss_limit"]) * initial_cash
    if max_position_value:
        # 单笔订单名义额上限对齐仓位上限：超出仓位上限的单笔必然被仓位检查拒，
        # 不需要更严的独立单笔限额（引擎默认 5 万元对大账户会误拒正常开仓）
        config["max_order_value"] = max_position_value
    if not config and max_position_value is None:
        return None
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
        f"[risk_config] 风控已装配: worker_id={worker_id}, config={config}, "
        f"max_position_value={max_position_value}"
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
            row = (
                db.query(WorkerRiskControl)
                .filter(WorkerRiskControl.worker_id == worker_id)
                .first()
            )
            if row is None:
                return None
            return {
                "max_position_pct": row.max_position_pct,
                "max_position_size": row.max_position_size,
                "daily_loss_amount": row.daily_loss_amount,
                "daily_loss_limit": row.daily_loss_limit,
            }
    except Exception as e:
        logger.warning(
            f"[risk_config] worker_risk_control 查询失败（视为未配置）: "
            f"worker_id={worker_id}, error={e}"
        )
        return None
