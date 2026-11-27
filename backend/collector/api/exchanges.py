"""
交易所管理API路由

提供交易所配置、连接测试和账户快照查询功能
"""

import threading
import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

from collector.schemas import ApiResponse
from exchange import SUPPORTED_EXCHANGES

# 使用 exchange 模块的连通性测试服务（已从 collector 迁移）
from exchange.connection import create_exchange_instance, test_exchange_connection
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


router = APIRouter(prefix="/exchanges", tags=["exchanges"])


class TestConnectionRequest(BaseModel):
    """测试连接请求模型"""

    exchange_name: str = Field(..., description="交易所名称 (binance, okx)")
    api_key: str | None = Field(None, description="API密钥")
    secret_key: str | None = Field(None, description="API密钥")
    api_passphrase: str | None = Field(None, description="API密码（OKX需要）")
    proxy_url: str | None = Field(None, description="代理URL")
    trading_mode: str = Field("spot", description="交易模式 (spot, future)")
    testnet: bool = Field(False, description="是否使用测试网络")


class TestConnectionResponse(BaseModel):
    """测试连接响应模型"""

    success: bool = Field(..., description="测试是否成功")
    status: str = Field(..., description="连接状态")
    message: str = Field(..., description="结果消息")
    response_time_ms: float | None = Field(None, description="响应时间（毫秒）")
    details: dict = Field(default_factory=dict, description="详细测试信息")


@router.post("/test-connection", response_model=ApiResponse)
async def test_exchange_connection_route(request: TestConnectionRequest):
    """
    测试交易所连接

    验证交易所连接状态、API Key有效性及代理设置正确性

    - **exchange_name**: 交易所名称，支持 binance, okx
    - **api_key**: API密钥（可选，用于验证API认证）
    - **secret_key**: API密钥密钥（可选，用于验证API认证）
    - **api_passphrase**: API密码（OKX需要）
    - **proxy_url**: 代理URL（可选）
    - **trading_mode**: 交易模式，spot 或 future
    - **testnet**: 是否使用测试网络

    返回结果包含：
    - success: 测试是否成功
    - status: 连接状态 (success, network_error, auth_error, permission_error, proxy_error, timeout_error, unknown_error)
    - message: 详细结果消息
    - response_time_ms: 响应时间
    - details: 详细测试信息
    """
    logger.info(
        f"收到测试连接请求: exchange={request.exchange_name}, "
        f"mode={request.trading_mode}, testnet={request.testnet}, "
        f"has_api_key={bool(request.api_key)}, proxy={request.proxy_url or '无'}"
    )

    try:
        result = await test_exchange_connection(
            exchange_name=request.exchange_name,
            api_key=request.api_key,
            secret_key=request.secret_key,
            api_passphrase=request.api_passphrase,
            proxy_url=request.proxy_url,
            trading_mode=request.trading_mode,
            testnet=request.testnet,
        )

        logger.info(
            f"测试连接完成: exchange={request.exchange_name}, "
            f"status={result.status.value}, success={result.success}, "
            f"耗时={result.response_time_ms or 0:.0f}ms, "
            f"message={result.message}"
        )

        return ApiResponse(
            code=0,
            message=result.message,
            data={
                "success": result.success,
                "status": result.status.value,
                "message": result.message,
                "response_time_ms": result.response_time_ms,
                "details": result.details,
            },
        )

    except Exception as e:
        import traceback

        logger.error(f"测试连接接口异常: exchange={request.exchange_name}, error={e}\n{traceback.format_exc()}")
        return ApiResponse(code=500, message=f"测试连接时发生错误: {e!s}", data=None)


@router.get("/supported", response_model=ApiResponse)
async def get_supported_exchanges():
    """
    获取支持的交易所列表

    返回当前支持连接测试的交易所列表
    """
    return ApiResponse(
        code=0,
        message="获取支持的交易所列表成功",
        data={"exchanges": SUPPORTED_EXCHANGES},
    )


# ── 账户快照（/setting/exchange-account 页面数据源） ──────────────────────

_HISTORY_WINDOW_MS = 7 * 86_400_000  # 委托/成交流水回看窗口
_TOP_SYMBOLS = 5  # 历史按 symbol 拉取的上限（币安全市场历史必须逐 symbol）
_ROWS_LIMIT = 50  # 单 symbol 每类上限

# 交易所实例缓存：ccxt 实例内含 markets 等大块公共数据，重建要 10s+；
# TTL 内复用让页面自动刷新/手点刷新免于每轮重拉。ponytail: 无单飞锁，并发首请求会各建一份，够用
_EX_CACHE: dict[str, tuple[float, object]] = {}
_EX_TTL = 120.0


def _get_exchange(exchange_id: str, cfg: dict, env: str, mode: str) -> object:
    """按 (exchange, env, mode) 缓存构造好的 ccxt 实例；demo 模式在构造时接线"""
    ck = f"{exchange_id}:{env}:{mode}"
    hit = _EX_CACHE.get(ck)
    if hit and time.time() - hit[0] < _EX_TTL:
        return hit[1]

    api_key, secret_key = _resolve_credentials(cfg, env)
    proxy_url = cfg.get("proxy_url") if _truthy(cfg.get("proxy_enabled")) else None
    ex = create_exchange_instance(
        exchange_id,
        api_key=api_key or None,
        secret_key=secret_key or None,
        trading_mode=mode,
        proxy_url=proxy_url,
    )
    # 币安模拟盘：demo 端点族（demo-api / demo-fapi），密钥来自 demo.binance.com
    if exchange_id == "binance" and env == "testnet":
        ex.exchange.enable_demo_trading(True)
    # 经代理访问超大体量的 exchangeInfo 可能超过 ccxt 默认 10s，放宽到 30s
    ex.exchange.timeout = 30_000
    # 关闭 ccxt 对「无 symbol 拉全量挂单」的一次性告警异常（其实现为抛错且标志不复位）
    ex.exchange.options["warnOnFetchOpenOrdersWithoutSymbol"] = False
    _EX_CACHE[ck] = (time.time(), ex)
    return ex


def _truthy(v) -> bool:
    return v in (1, "1", True, "true", "True")


def _norm_trading_mode(mode: str) -> str:
    """spot / future(s) / margin 三档；margin 是杠杆钱包（ccxt defaultType 直接支持）"""
    m = str(mode).lower()
    if m in ("future", "futures"):
        return "future"
    if m == "margin":
        return "margin"
    return "spot"


def _resolve_credentials(cfg: dict, env: str) -> tuple[str, str]:
    """按环境取密钥：testnet/paper 用 testnet 通道密钥，live 用 live（含旧字段兼容）"""
    if env == "testnet":
        return str(cfg.get("testnet_api_key") or ""), str(cfg.get("testnet_api_secret") or "")
    return (
        str(cfg.get("live_api_key") or cfg.get("api_key") or ""),
        str(cfg.get("live_api_secret") or cfg.get("api_secret") or ""),
    )


def _strip_settle(symbol: str) -> str:
    """ "BTC/USDT:USDT" → "BTC/USDT"（展示用交易对）"""
    return symbol.partition(":")[0]


def _collect_prices(ex, quote: str, errors: dict) -> dict[str, float]:
    """一次公共行情拉全 ~*/QUOTE 的最新价，供非 quote 资产估值"""
    tickers = {}
    try:
        tickers = ex.exchange.fetch_tickers() or {}
    except Exception as e:
        errors["prices"] = f"{type(e).__name__}: {e}"[:240]
        return {}
    prices: dict[str, float] = {}
    for sym, t in tickers.items():
        if not sym or not isinstance(t, dict):
            continue
        last = t.get("last") or t.get("close")
        if last is None:
            continue
        base = sym.split("/")[0].partition(":")[0] if "/" in sym else None
        if base and (sym.endswith(f"/{quote}") or sym.endswith(f":{quote}")):
            prices.setdefault(base, float(last))
    return prices


def _balance_rows(balance: dict, quote: str, prices: dict[str, float]) -> list[dict]:
    rows = []
    for currency, totals in (balance.get("total") or {}).items():
        try:
            total = float(totals or 0)
        except TypeError, ValueError:
            continue
        if total <= 0:
            continue
        free = float((balance.get("free") or {}).get(currency) or 0)
        used = float((balance.get("used") or {}).get(currency) or 0)
        price = 1.0 if currency == quote else prices.get(currency)
        # ponytail: 主流稳定币互相锚定 1（币安无 USDT/USDC 反向行情对，quote≠USDT 时缺价按锚定估值；
        # 脱锚属黑天鹅场景，升级路径是 cross-rate 换算）
        if price is None and currency in ("USDT", "USDC", "FDUSD", "TUSD"):
            price = 1.0
        rows.append(
            {
                "currency": currency,
                "free": free,
                "used": used,
                "priceUsdt": price,
                "valueUsdt": total * price if price is not None else 0.0,
            }
        )
    rows.sort(key=lambda r: r["valueUsdt"], reverse=True)
    return rows


def _futures_account_totals(balance: dict) -> dict | None:
    """币安合约余额原始报文带账户级汇总，直接取用；缺席返回 None 由前端兜底求和"""
    info = balance.get("info") or {}
    if not isinstance(info, dict) or "totalWalletBalance" not in info:
        return None

    def f(key: str) -> float:
        try:
            return float(info.get(key) or 0)
        except TypeError, ValueError:
            return 0.0

    # ponytail: wallet_total 命名规避 vocab banned 裸 wallet（_ 续接不撞 \bwallet\b）；
    # totalWalletBalance/totalMarginBalance 为币安原生字段（vocab erase 有 camel 镜像）
    wallet_total = f("totalWalletBalance")
    unrealized = f("totalUnrealizedProfit")
    return {
        "walletUsdt": wallet_total,
        "unrealizedUsdt": unrealized,
        "equityUsdt": f("totalMarginBalance") or wallet_total + unrealized,
        "availableUsdt": f("availableBalance"),
        "usedUsdt": f("totalInitialMargin"),
    }


def _norm_position(p: dict, maint_share: float = 0.0) -> dict | None:
    """归一化持仓。币安 demo 走 v3 positionRisk：无 leverage/maintMargin 字段，
    分别用 保证金占用/名义价值 与 账户级维持保证金按名义分摊 推算。"""
    try:
        contracts = abs(float(p.get("contracts") or 0))
    except TypeError, ValueError:
        return None
    if contracts <= 0:
        return None
    entry = float(p.get("entryPrice") or 0)
    initial = float(p.get("initialMargin") or 0)
    pair = _strip_settle(p.get("symbol") or "")
    info = p.get("info") or {}
    notional = abs(float(p.get("notional") or 0))
    unset = p.get("unrealizedPnl")
    unrealized = float(unset) if isinstance(unset, (int, float)) else float(info.get("unRealizedProfit") or 0)
    try:
        liq = float(p.get("liquidationPrice") or 0)
    except TypeError, ValueError:
        liq = 0.0
    # 杠杆：ccxt → 币安原始 → 按保证金占用推算（demo v3 不回传 leverage）
    lev = p.get("leverage") or info.get("leverage")
    if not lev and initial > 0 and notional > 0:
        lev = round(notional / initial)
    leverage = float(lev or 1)
    # 损益两平价：ccxt 未解析，币安 info.breakEvenPrice 有（含费用口径）
    breakeven = float(info.get("breakEvenPrice") or 0)
    # 币安「保证金比率」= 维持保证金 / 保证金余额（positionRisk.marginRatio）
    margin_ratio = float(p.get("marginRatio") or 0) * 100
    # 维持保证金：ccxt → 调用方传入的账户级分摊份额
    maint = float(p.get("maintenanceMargin") or info.get("maintMargin") or 0) or maint_share
    return {
        "symbol": p.get("symbol"),
        "pair": pair,
        "side": p.get("side") or "long",
        "mode": p.get("marginMode") or "cross",
        "leverage": leverage,
        "qty": contracts,
        "entry": entry,
        "mark": float(p.get("markPrice") or 0),
        "notional": notional,
        "unrealized": unrealized,
        "initialMargin": initial,
        "maintMargin": maint,
        "liqPrice": liq,
        "breakeven": breakeven,
        "marginRatio": margin_ratio,
    }


def _norm_order(o: dict) -> dict:
    return {
        "id": o.get("id") or "",
        "time": int(o.get("timestamp") or 0),
        "pair": _strip_settle(o.get("symbol") or ""),
        "type": "market" if o.get("type") == "market" else "limit",
        "side": o.get("side") or "buy",
        "price": float(o.get("price") or 0),
        "qty": float(o.get("amount") or 0),
        "filled": float(o.get("filled") or 0),
        "status": o.get("status") or "open",
    }


def _norm_trade(t: dict) -> dict:
    fee = t.get("fee") if isinstance(t.get("fee"), dict) else {}
    return {
        "id": t.get("id") or "",
        "time": int(t.get("timestamp") or 0),
        "pair": _strip_settle(t.get("symbol") or ""),
        "side": t.get("side") or "buy",
        "price": float(t.get("price") or 0),
        "qty": float(t.get("amount") or 0),
        "fee": float(fee.get("cost") or 0),
    }


def _history_symbols(positions: list[dict], balance_rows: list[dict], quote: str, mode: str) -> list[str]:
    """历史委托/成交必须逐 symbol 拉取：优先持仓，其次按估值取头部余额资产"""
    symbols: list[str] = []
    for p in positions:
        if p.get("symbol"):
            symbols.append(p["symbol"])
    suffix = f"/{quote}:{quote}" if mode == "future" else f"/{quote}"
    for row in balance_rows:
        if len(symbols) >= _TOP_SYMBOLS:
            break
        sym = f"{row['currency']}{suffix}"
        if row["currency"] != quote and sym not in symbols:
            symbols.append(sym)
    return symbols[:_TOP_SYMBOLS]


def _collect_account(ex, mode: str, quote: str) -> dict:
    """逐段拉取并归一化；任何一段失败记入 errors 后继续其余段落"""
    errors: dict[str, str] = {}
    exx = ex.exchange

    def safe(name: str, fn, default):
        try:
            return fn()
        except Exception as e:
            errors[name] = f"{type(e).__name__}: {e}"[:240]
            return default

    prices = _collect_prices(ex, quote, errors)
    balance = safe("balance", lambda: exx.fetch_balance() or {}, {})
    is_futures = mode == "future"
    futures_totals = _futures_account_totals(balance) if is_futures else None

    if is_futures:
        # defaultType=future 时 fetch_balance 拿到的是合约钱包；现货账户需显式指定 type 单独拉
        fut_balance = balance
        spot_balance = safe("balance_spot", lambda: exx.fetch_balance({"type": "spot"}) or {}, {})
        spots = _balance_rows(spot_balance, quote, prices)
    else:
        fut_balance = None
        spots = _balance_rows(balance, quote, prices)

    # 维持保证金兜底：demo v3 positionRisk 无 per-position 值，用账户级 totalMaintMargin 按名义价值分摊
    acct_maint = float((fut_balance or {}).get("info", {}).get("totalMaintMargin") or 0)
    raw_positions = safe("positions", lambda: exx.fetch_positions() or [], [])
    total_notional = sum(abs(float(p.get("notional") or 0)) for p in raw_positions if p.get("contracts"))
    positions = []
    for p in raw_positions:
        share = acct_maint * (abs(float(p.get("notional") or 0)) / total_notional) if total_notional else 0.0
        pn = _norm_position(p, maint_share=share)
        if pn:
            positions.append(pn)

    open_orders = [_norm_order(o) for o in safe("openOrders", lambda: exx.fetch_open_orders() or [], [])]

    symbols = _history_symbols(positions, spots, quote, mode)
    since = int(time.time() * 1000) - _HISTORY_WINDOW_MS
    orders = {o["id"]: o for o in open_orders}  # 当前挂单并入委托列表（按 id 去重）
    trades: dict[str, dict] = {}
    ok_syms = 0
    for sym in symbols:
        try:
            for o in exx.fetch_orders(sym, since=since, limit=_ROWS_LIMIT) or []:
                orders[o.get("id") or sym] = _norm_order(o)
            for t in exx.fetch_my_trades(sym, since=since, limit=_ROWS_LIMIT) or []:
                trades[t.get("id") or sym] = _norm_trade(t)
            ok_syms += 1
        except Exception as e:
            errors.setdefault(f"history:{sym}", str(e)[:120])
    if symbols and ok_syms == 0:
        errors.setdefault("history", f"全部 {_TOP_SYMBOLS} 个 symbol 均拉取失败")

    order_rows = sorted(orders.values(), key=lambda o: o["time"], reverse=True)[:30]
    trade_rows = sorted(trades.values(), key=lambda t: t["time"], reverse=True)[:50]

    spot_total = sum(r["valueUsdt"] for r in spots)
    unrealized = (
        sum(p["unrealized"] for p in positions)
        if positions
        else (futures_totals["unrealizedUsdt"] if futures_totals else 0.0)
    )
    futures_equity = futures_totals["equityUsdt"] if futures_totals else None

    data = {
        "fetchedAt": int(time.time() * 1000),
        "spot": {"balances": spots, "totalUsdt": round(spot_total, 8)},
        "futures": {
            "totals": futures_totals,
            "equityUsdt": futures_equity,
            "unrealizedUsdt": unrealized,
            "positions": positions,
        },
        "orders": order_rows,
        "trades": trade_rows,
        "historySymbols": symbols,
        "errors": errors,
    }
    return data


# ── 快照缓存 + 访问激活的后台同步 ─────────────────────────────────────────
# 场景：拉一份快照经代理要 5-10s，页面进入不该白等。请求命中缓存立即返回
# （stale 数据 + 旧 fetchedAt），并把 key 记入 _ACTIVE_KEYS；后台线程每
# _SNAPSHOT_SYNC_INTERVAL 秒同步一次活跃 key，让缓存保持新鲜。
# `refresh=1`（手动刷新按钮）绕过缓存强制拉新。
_SNAPSHOT_CACHE: dict[tuple[str, str], dict] = {}
_ACTIVE_KEYS: set[tuple[str, str]] = set()
_SNAPSHOT_SYNC_INTERVAL = 300  # 定时同步间隔（s），新鲜度要求低，5 分钟足够
_SYNC_THREAD: threading.Thread | None = None


def _build_snapshot(exchange_id: str, eff_env: str) -> dict | None:
    """组装快照数据（端点与后台同步线程共用）。

    paper / 未配置密钥 → 返回 configured=false 前端空态载荷；真实拉取 → 完整快照。
    """
    # 函数内 import：settings/models.py 的 db 层反向 import collector 包，模块级
    # from settings.models import ... 会在加载 collector 时形成循环导入。
    from settings.models import SystemConfigBusiness

    cfg = SystemConfigBusiness.get_all_flattened_by_prefix("exchange").get(exchange_id) or {}
    mode = _norm_trading_mode(str(cfg.get("trading_mode") or "spot"))
    quote = str(cfg.get("quote_currency") or "USDT")

    def base(**extra: object) -> dict:
        return {
            "exchange": exchange_id,
            "configured": True,
            "env": eff_env,
            "mode": mode,
            "quote": quote,
            **extra,
        }

    if eff_env == "paper":
        return {"configured": False, "paper": True, "exchange": exchange_id, "env": eff_env, "mode": mode}
    if not all(_resolve_credentials(cfg, eff_env)):
        return {"configured": False, "exchange": exchange_id, "env": eff_env, "mode": mode}

    ex = _get_exchange(exchange_id, cfg, eff_env, mode)
    return base(**_collect_account(ex, mode, quote))


def _start_snapshot_sync() -> None:
    """启动（或复用）后台定时同步线程：仅刷新近期被页面访问过的环境。"""
    global _SYNC_THREAD
    if _SYNC_THREAD and _SYNC_THREAD.is_alive():
        return

    def loop() -> None:
        while True:
            time.sleep(_SNAPSHOT_SYNC_INTERVAL)
            for key in list(_ACTIVE_KEYS):
                try:
                    data = _build_snapshot(*key)
                    if data and data.get("configured"):
                        _SNAPSHOT_CACHE[key] = data
                except Exception as e:
                    logger.warning(f"账户快照后台同步失败: {key} error={e}")

    _SYNC_THREAD = threading.Thread(target=loop, daemon=True, name="exacct-snapshot-sync")
    _SYNC_THREAD.start()


@router.get("/account-snapshot", response_model=ApiResponse)
def get_exchange_account_snapshot(exchange_id: str = "binance", env: str = "", refresh: bool = False):
    """交易所账户快照（Balance/持仓/挂单/近期委托与成交）

    数据源为已保存的交易所配置（exchange.{id}.* 配置项）：
    - env 覆盖参数（来自设置页当前查看的环境，可不传）:
      live → 实盘端点 + live_api_key；testnet → 币安模拟盘 demo-api/demo-fapi（testnet_api_key）；
      paper → 本地模拟不产生交易所账户，返回 configured=false（前端展示专属空态）
    - 不传时沿用已保存的 trading_environment
    - 缓存：命中立即返回（数据可能为后台定时同步前的旧值，fetchedAt 字段如实反映）；
      refresh=true（页面手动刷新）强制拉新
    未配置密钥时返回 code=0 + configured=false（前端展示引导空态，而非报错）。
    """
    # 函数内 import：settings/models.py 的 db 层反向 import collector 包，模块级
    # from settings.models import ... 会在加载 collector 时形成循环导入。
    from settings.models import SystemConfigBusiness

    cfg = SystemConfigBusiness.get_all_flattened_by_prefix("exchange").get(exchange_id) or {}
    # env 覆盖：设置页可能正在查看未保存的环境，入口链接把 UI 状态显式带给本接口
    eff_env = str(cfg.get("trading_environment") or "live")
    if env in ("live", "testnet", "paper"):
        eff_env = env

    key = (exchange_id, eff_env)
    cached = _SNAPSHOT_CACHE.get(key)
    if cached is not None and not refresh:
        # 页面进入路径：秒回缓存，并激活后台定时同步
        _ACTIVE_KEYS.add(key)
        _start_snapshot_sync()
        return ApiResponse(code=0, message="获取账户快照成功（缓存）", data=cached)

    _start_snapshot_sync()  # 首次访问也要保证定时同步线程在场
    try:
        data = _build_snapshot(exchange_id, eff_env)
    except Exception as e:
        logger.error(f"构造交易所实例失败: {exchange_id} env={eff_env} error={e}")
        return ApiResponse(code=500, message=f"构造交易所客户端失败: {e}", data=None)
    if data and data.get("configured"):
        _SNAPSHOT_CACHE[key] = data
    msg = "获取账户快照成功"
    if data and not data.get("configured"):
        msg = (
            "本地模拟由 QuantCell 自行撮合，不产生交易所账户"
            if "paper" in data
            else "该交易所未配置可用于读取账户的 API 密钥"
        )
    return ApiResponse(code=0, message=msg, data=data)
