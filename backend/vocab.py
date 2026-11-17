"""方向词汇 canonical 契约与归一层（single source of truth，设计文档 §3）。

包级唯一实现：原位于 worker/vocab.py，现提升为根级模块供 exchange/backtest
等域直接引用；worker/vocab.py 保留为向后兼容 re-export 壳。

三条铁律：
1. 落库/传输/类型/日志只允许 canonical 小写；交易所原生大小写（BINANCE 返回的
   "BUY"、"LONG" 等）只存在于 exchange adapter 边界内，跨越本模块即被归一。
2. Side 不携带仓位信息；PositionSide 是「下单时声明的仓位归属」，不从 side 推导。
   成交/订单行上的 position_side 是声明值透传（回报直取或固定 both），不是算出来的。
3. 展示一律 i18n，任何文案/翻译逻辑不得进入本模块。
"""

from typing import Literal, cast

Side = Literal["buy", "sell"]
PositionSide = Literal["long", "short", "both"]

_SIDES = frozenset({"buy", "sell"})
_POSITION_SIDES = frozenset({"long", "short", "both"})


def normalize_side(value: str) -> Side:
    """任意大小写的 side（含两侧空白）归一为 canonical 小写；非法值抛 ValueError。"""
    v = str(value or "").strip().lower()
    if v in _SIDES:
        return cast(Side, v)
    raise ValueError(f"invalid side: {value!r}（期望 buy/sell，大小写均可）")


def normalize_position_side(value: str) -> PositionSide:
    """任意大小写的 position_side 归一为 canonical 小写；非法值抛 ValueError。"""
    v = str(value or "").strip().lower()
    if v in _POSITION_SIDES:
        return cast(PositionSide, v)
    raise ValueError(f"invalid position_side: {value!r}（期望 long/short/both，大小写均可）")


# ---------------------------------------------------------------------------
# 账户域（命名审计 P2-1）：资金口径 5 词边界，禁止混用
# ---------------------------------------------------------------------------

# canonical 与分界（审计报告 §10.4 裁决）：
#   equity           账户总价值（cash + 持仓市值，含浮盈）——总量口径的唯一词。
#   balance          不含浮盈的余额口径，两个注册子语义：
#                      (a) 回测 MT4 存款曲线：本金 + 已实现盈亏 − 费用（equity − balance 即浮盈）；
#                      (b) 交易所钱包余额快照（adapter 的 get_balance，各币种 dict，ccxt 惯例）。
#   cash             纯现金余额（账户/现货语境）。
#   nav              份额制净值（factor 域 cumprod 曲线）+ Rust 内核边界词（序列化产物
#                      bar_nav_curve / final_nav / nav_peak）。Python/TS 新代码禁止再引入
#                      nav 表示账户绝对总值；消费内核产物时应立即映射为 equity。
#   wallet_balance   交易所单币种钱包余额；裸 wallet 禁用。
#   available        仅允许"可用性布尔"语义；资金语义必须是 available_balance。
#   margin_used      已用保证金（曲线/字段）。margin 前缀仅保留于保证金配置语境
#                      （margin_mode / margin_applied / margin_specs_effective）。
# Rust 内核内部保留自有词汇（Portfolio::cash / Portfolio::nav()），属引擎域内实现，
# 跨到 Python/TS 即按上表映射。

# ---------------------------------------------------------------------------
# symbol 域（命名审计 P1-5）：canonical = 紧缩大写 "BTCUSDT"
# ---------------------------------------------------------------------------

# 展开格式（"BASE/QUOTE"，Rust 引擎 instrument key / leverage 键 / 前端展示）的
# 计价币后缀表，按长度从长到短匹配，避免 USDC 被 USD 抢先截断
_SYMBOL_QUOTES = ("USDT", "USDC", "USD", "BTC", "ETH")


def normalize_symbol(symbol: str) -> str:
    """任意分隔格式（BTCUSDT / BTC-USDT / BTC_USDT / BTC/USDT 等）归一为
    canonical 紧缩大写 "BTCUSDT"。落库/文件名/键查询一律使用本格式。"""
    s = str(symbol or "").upper()
    return s.replace("/", "").replace("\\", "").replace("-", "").replace("_", "").replace(" ", "")


# ---------------------------------------------------------------------------
# K线周期域（命名审计 P2-3）：K线频率 canonical = interval，禁止 period/freq
# ---------------------------------------------------------------------------

# interval      K线/数据采样周期（"1h"/"15m"）。锚：Rust 内核 Kernel(interval=...)、
#               DataService.get_kline_data(interval=...) 既有口径。
# period 例外清单（语义独立，非 K线频率，允许保留）：
#   - 策略/指标回看窗口参数（bb_period / rsi_period 等，整数根数）；
#   - exchange/decorators.rate_limit(calls, period) —— 限流窗口（秒）；
#   - collector/services/deriv_collector.py 的 _PERIOD_MAP / self.period ——
#     交易所 OpenInterest API 原生参数名，adapter 边界内允许（同 side 域的
#     "BINANCE BUY 原则"：交易所原生词汇只存在于 adapter 边界内）；
#   - backtest/baseline.py 报表的 report.period —— 报告覆盖的日期区间；
#   - indicator_alert_rules / features 表的 DB 列 period / freq —— 历史列名，
#     ORM 属性与传输面已改 interval，列名不动避免迁移。
# freq 例外清单：
#   - pandas date_range(freq=…) —— 第三方库参数名；
#   - collector quality 服务内部 freq 局部变量——同上第三方参数语境。
# frequency 语义独立，不属于本域：
#   - IndicatorAlertRule.frequency —— 通知去重窗口（分钟）；
#   - frequency_type —— 采集调度频率（hourly/daily）。
# 前端图表 UI 与 chartPreferences 的 period 是展示层/本地遗留词；新增传输/API
# 字段一律 interval。

# ---------------------------------------------------------------------------
# position / holding 域（命名审计 P2-3）：持仓 canonical = position
# ---------------------------------------------------------------------------

# position      仓位/持仓唯一词：position_events（逐笔成交重建的事件流）、
#               position_prices（回测 replay 响应键，{symbol: [[t, close], ...]}
#               仅净持仓非零的网格点，供前端算浮盈）。二者数据形态不同，不合并。
#               原响应键 holding_prices 已改名 position_prices。
# hold/holdings 禁止新用于持仓语义；"hold" 仅允许出现在「持有期间」的自然语言
#               注释里。

# ---------------------------------------------------------------------------
# stage / phase 域（命名审计 P2-3）：两词自洽分界，只定边界不改代码
# ---------------------------------------------------------------------------

# stage         业务工作流阶段：research 编排流水线、backtest 的
#               data_prep/execution/analysis、factor 计算阶段；
#               model_registry 的 stage 是 MLflow 术语（development/production），
#               按引擎记录值透传，不改名。
# phase         进程/流程时序阶段：graceful_shutdown 的 ShutdownPhase、内存构建
#               的 phase1/phase2 提示词。跨进程时序说 phase，跨工作流水线说
#               stage，两词不得混用。


def expand_symbol(symbol: str) -> str:
    """紧缩格式展开为 "BASE/QUOTE"（Rust 引擎可解析的 instrument key）。

    关键约束：已带 "/" 的 symbol 直接透传，避免 BTC/USDT → BTC//USDT 这种
    双斜杠污染（会导致 leverage 键查询永远 miss，回退到 1x）。识别不出的
    计价币原样返回紧缩大写，不做猜测。
    """
    s = str(symbol or "").upper()
    if "/" in s:
        return s
    s = s.replace("-", "").replace("_", "")
    for quote in _SYMBOL_QUOTES:
        if s.endswith(quote) and len(s) > len(quote):
            return f"{s[: -len(quote)]}/{quote}"
    return s
