"""每品种保证金规格构建：DB → 内置快照 → 默认档位（三级回退）。

对外只暴露 ``build_margin_specs``；DB / 快照读取拆成独立小函数，便于单测 monkeypatch。
输出的 key 使用 ``BASE/QUOTE``，与 Rust 引擎的 instrument key 对齐；档位字段名与
Rust ``Bracket`` 一一对应（见 axon-backtest/src/margin.rs）。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.BACKTEST)

_SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "binance_um_leverage_brackets.json"

# 档位超过这个天数只告警不阻断：档位漂移通常很慢，宁可用旧数据也不让回测跑不起来
_SNAPSHOT_MAX_AGE_DAYS = 30

# 兜底档位：MMR 0.5%、无 cum、强平费按 taker、最高 125x
DEFAULT_BRACKETS: list[dict[str, Any]] = [
    {
        "notional_floor": 0.0,
        "notional_cap": None,
        "mmr": 0.005,
        "cum": 0.0,
        "liquidation_fee_rate": 0.001,
        "max_leverage": 125.0,
    }
]


def _warn_if_stale(symbol: str, collected_at: datetime | None) -> None:
    """档位数据过期只告警：不阻断回测，但要让运维知道该刷快照了。"""
    if collected_at is None:
        return
    # SQLite 的 DateTime(timezone=True) 取回来可能是 naive，按 UTC 解释
    ts = collected_at if collected_at.tzinfo is not None else collected_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - ts > timedelta(days=_SNAPSHOT_MAX_AGE_DAYS):
        logger.warning(
            f"杠杆档位数据已超过 {_SNAPSHOT_MAX_AGE_DAYS} 天未更新",
            extra={"symbol": symbol, "collected_at": ts.isoformat()},
        )


def _load_from_db(symbol: str) -> list[dict] | None:
    """从 collector 的 leverage_brackets 表读档位；缺失或 DB 不可用返回 None。

    表未建好（未初始化 DB 的部署）、SQLite 锁冲突等异常都不应该让回测挂掉，
    统一降级到下一级数据源。
    """
    # 函数内导入：collector 依赖 SQLAlchemy 与 DB 配置链，回测进程未初始化 DB 时
    # 顶层导入会把这条可选依赖变成硬依赖
    try:
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import LeverageBracket
    except ImportError as exc:
        logger.debug("collector 模块不可用，跳过 DB 档位", extra={"symbol": symbol, "error": str(exc)})
        return None

    try:
        init_database_config()
        with SessionLocal() as session:
            row = (
                session.query(LeverageBracket)
                .filter_by(symbol=symbol.upper(), market="um")
                .order_by(LeverageBracket.collected_at.desc())
                .first()
            )
            if row is None:
                return None
            collected_at = row.collected_at
            brackets = json.loads(row.brackets_json)
    except Exception as exc:
        # 表未建好属于常见状态（尚未采集档位），由 build_margin_specs 的统一告警兜底，
        # 这里只留调试信息，避免同一品种每跑一次回测刷两条 warning
        logger.debug(
            "读取杠杆档位失败，降级到内置快照",
            extra={"symbol": symbol, "error": str(exc)},
        )
        return None

    _warn_if_stale(symbol, collected_at)
    return brackets or None


def _load_from_snapshot(symbol: str) -> list[dict] | None:
    """从内置快照读取档位；文件缺失或损坏返回 None。"""
    try:
        data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "杠杆档位快照不可用",
            extra={"symbol": symbol, "path": str(_SNAPSHOT_PATH), "error": str(exc)},
        )
        return None
    return data.get(symbol.upper()) or None


def normalize_symbol(symbol: str) -> str:
    """BTCUSDT → BTC/USDT（与 Rust 引擎 instrument key 对齐）。"""
    s = symbol.upper().replace("-", "").replace("_", "")
    # 计价货币按长度从长到短匹配，避免 USDC 被 USD 抢先截断
    for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
        if s.endswith(quote) and len(s) > len(quote):
            return f"{s[: -len(quote)]}/{quote}"
    return s


def build_margin_specs(settings: Iterable[tuple[str, float, str]]) -> dict[str, dict]:
    """[("BTCUSDT", 20.0, "cross")] → {"BTC/USDT": {"leverage": …, "mode": …, "brackets": […]}}。

    杠杆上限按该品种档位表首档（币安 ``initialLeverage``）校验，超限抛 ValueError，
    消息带品种名与上限，方便直接回给前端。
    """
    specs: dict[str, dict] = {}
    for symbol, leverage, mode in settings:
        lev = float(leverage)
        brackets = _load_from_db(symbol) or _load_from_snapshot(symbol)
        if brackets is None:
            logger.warning(
                "杠杆档位缺失，使用默认档位",
                extra={"symbol": symbol, "leverage": lev, "source": "default"},
            )
            brackets = DEFAULT_BRACKETS

        cap = float(brackets[0].get("max_leverage", 125.0))
        if lev > cap:
            raise ValueError(f"{symbol} 杠杆 {lev:g}x 超过该品种最高 {cap:g}x")

        specs[normalize_symbol(symbol)] = {
            "leverage": lev,
            "mode": mode,
            "brackets": brackets,
        }
    return specs
