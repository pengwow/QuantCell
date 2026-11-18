"""方向词汇 canonical 契约与归一层（single source of truth，设计文档 §3）。

包级唯一实现：原位于 worker/vocab.py，现提升为根级模块供 exchange/backtest
等域直接引用；worker/vocab.py 保留为向后兼容 re-export 壳。

三条铁律：
1. 落库/传输/类型/日志只允许 canonical 小写；交易所原生大小写（BINANCE 返回的
   "BUY"、"LONG" 等）只存在于 exchange adapter 边界内，跨越本模块即被归一。
2. Side 不携带仓位信息；PositionSide 是「下单时声明的仓位归属」，不从 side 推导。
   成交/订单行上的 position_side 是声明值透传（回报直取或固定 both），不是算出来的。
3. 展示一律 i18n，任何文案/翻译逻辑不得进入本模块。

命名契约的机器可读事实源 = VOCAB_ENUMS / VOCAB_DOMAINS（命名审计 P2-5 / A-4）：
GET /api/v1/vocab 与前端类型生成脚本（backend/scripts/export_vocab_types.py）
都消费这两个结构；词条 note 承载裁决全文，注释不再另行定档（单一事实源）。
"""

from typing import Literal, NamedTuple, cast

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
# 命名契约结构化事实源（命名审计 P2-5 / A-4）
# kind 语义：canonical = 该概念唯一正确用词；banned = 误用词（新代码出现即告警，
# P2-6 lint 门禁消费）；reserved = 限定语境内合法的词。
# ---------------------------------------------------------------------------

# 枚举值域（与上方 Literal / 归一 frozenset 必须一致，由测试守护）
VOCAB_ENUMS: dict[str, tuple[str, ...]] = {
    "side": ("buy", "sell"),
    "position_side": ("long", "short", "both"),
}


class VocabTerm(NamedTuple):
    """单个词条：词 + 类别 + 边界裁决（人类可读全文）。"""

    term: str
    kind: Literal["canonical", "banned", "reserved"]
    note: str


class VocabDomain(NamedTuple):
    """一个词汇域：概念分组 + 词条集。"""

    name: str
    terms: tuple[VocabTerm, ...]


VOCAB_DOMAINS: tuple[VocabDomain, ...] = (
    VocabDomain(
        "direction",
        (
            VocabTerm(
                "side",
                "canonical",
                "下单方向唯一词（buy/sell 二值，见 enums.side）。铁律1：落库/传输/类型/"
                "日志只允许 canonical 小写，交易所原生大小写仅在 exchange adapter 边界内；"
                "铁律2：side 不携带仓位信息，不从 side 推导仓位归属。",
            ),
            VocabTerm(
                "position_side",
                "canonical",
                "下单时声明的仓位归属（long/short/both，见 enums.position_side）。"
                "成交/订单行上的 position_side 是声明值透传（回报直取或固定 both），"
                "不是算出来的。",
            ),
            VocabTerm(
                "LONG/SHORT",
                "banned",
                "long/short 只许表达仓位归属（position_side），下单方向一律 buy/sell；"
                "交易所返回的 LONG/SHORT 原生大写值仅在 adapter 边界内出现，跨模块即归一。",
            ),
        ),
    ),
    VocabDomain(
        "account",
        (
            VocabTerm(
                "equity",
                "canonical",
                "账户总价值（cash + 持仓市值，含浮盈）——总量口径的唯一词。",
            ),
            VocabTerm(
                "balance",
                "canonical",
                "不含浮盈的余额口径，两个注册子语义：(a) 回测 MT4 存款曲线：本金 + "
                "已实现盈亏 − 费用（equity − balance 即浮盈）；(b) 交易所钱包余额快照"
                "（adapter 的 get_balance，各币种 dict，ccxt 惯例）。",
            ),
            VocabTerm("cash", "canonical", "纯现金余额（账户/现货语境）。"),
            VocabTerm(
                "nav",
                "canonical",
                "份额制净值（factor 域 cumprod 曲线）+ Rust 内核边界词（序列化产物 "
                "bar_nav_curve / final_nav / nav_peak）。Python/TS 新代码禁止再用 nav "
                "表示账户绝对总值，消费内核产物时应立即映射为 equity；Rust 内核内部保留"
                "自有词汇（Portfolio::cash / Portfolio::nav()），属引擎域内实现，跨到 "
                "Python/TS 即按本表映射。",
            ),
            VocabTerm(
                "wallet_balance",
                "canonical",
                "交易所单币种钱包余额（wallet_balance 与 balance 子语义 (b) 同义，哪个词以所在模型既有口径为准）。",
            ),
            VocabTerm("wallet", "banned", "裸 wallet 禁用，钱包余额语义一律 wallet_balance。"),
            VocabTerm("available", "reserved", "仅允许『可用性布尔』语义。"),
            VocabTerm("available_balance", "canonical", "资金语义必须用 available_balance。"),
            VocabTerm("margin_used", "canonical", "已用保证金（曲线/字段）。"),
            VocabTerm("margin_mode", "reserved", "保证金配置语境专用词。"),
            VocabTerm("margin_applied", "reserved", "保证金配置语境专用词。"),
            VocabTerm("margin_specs_effective", "reserved", "保证金配置语境专用词。"),
            VocabTerm("margin", "banned", "裸 margin 前缀仅保留上列保证金配置语境，其余组合禁止。"),
        ),
    ),
    VocabDomain(
        "symbol",
        (
            VocabTerm(
                "BTCUSDT",
                "canonical",
                "紧缩大写格式（normalize_symbol 归一）。落库/文件名/键查询一律使用本格式；"
                "分隔变体（BTC-USDT / BTC_USDT / 带斜杠、空格）只能出现在输入边界，"
                "进入系统即被归一。",
            ),
            VocabTerm(
                "BASE/QUOTE",
                "reserved",
                "展开格式（expand_symbol），仅用于 Rust 引擎 instrument key、leverage 键"
                "与前端展示；计价币后缀表按长度匹配（_SYMBOL_QUOTES：USDT/USDC/USD/BTC/ETH），"
                "识别不出时原样返回不做猜测。",
            ),
        ),
    ),
    VocabDomain(
        "interval",
        (
            VocabTerm(
                "interval",
                "canonical",
                'K线/数据采样周期唯一词（"1h"/"15m"）。锚：Rust 内核 Kernel(interval=...)、'
                "DataService.get_kline_data(interval=...)。前端 chartPreferences / localStorage "
                "wire 字段已统一 interval（P2-10 切断式改名，无旧读兼容）；"
                "indicator_alert_rules / features 表历史列名 period / freq 已由迁移"
                "（alembic 46 / collector rename_kline_interval_columns）统一改名 interval。",
            ),
            VocabTerm(
                "period",
                "banned",
                "禁止用于 K线频率。例外（语义独立，允许保留）：策略/指标回看窗口参数"
                "（bb_period / rsi_period 等，整数根数）；exchange/decorators.rate_limit"
                "(calls, period) 限流窗口（秒）；collector/services/deriv_collector.py 的 "
                "_PERIOD_MAP / self.period（交易所 OpenInterest API 原生参数名，adapter "
                "边界内，同 side 域的『BINANCE BUY 原则』）；backtest/baseline.py 报表的 "
                "report.period（报告覆盖的日期区间）；列名 rename 迁移文件（历史 DDL 记录）。",
            ),
            VocabTerm(
                "freq",
                "banned",
                "禁止用于 K线频率。例外：pandas date_range(freq=…) 第三方库参数名；"
                "collector quality 服务内部 freq 局部变量（同第三方参数语境）。",
            ),
            VocabTerm(
                "frequency",
                "reserved",
                "语义独立，不属于 K线频率域：IndicatorAlertRule.frequency 是通知去重窗口"
                "（分钟）；frequency_type 是采集调度频率（hourly/daily）。",
            ),
        ),
    ),
    VocabDomain(
        "position",
        (
            VocabTerm(
                "position",
                "canonical",
                "仓位/持仓唯一词：position_events（逐笔成交重建的事件流）、position_prices"
                "（回测 replay 响应键 {symbol: [[t, close], ...]}，仅净持仓非零的网格点，"
                "供前端算浮盈）。二者数据形态不同，不合并。",
            ),
            VocabTerm(
                "holdings",
                "banned",
                "禁止用于持仓语义；原响应键 holding_prices 已改名 position_prices。"
                "hold 仅允许策略输出枚举（ActionType.Hold）与「持有期间」的自然语言语境。",
            ),
        ),
    ),
    VocabDomain(
        "stage_phase",
        (
            VocabTerm(
                "stage",
                "canonical",
                "业务工作流阶段：research 编排流水线、backtest 的 data_prep/execution/"
                "analysis、factor 计算阶段；model_registry 的 stage 是 MLflow 术语"
                "（development/production），按引擎记录值透传，不改名。",
            ),
            VocabTerm(
                "phase",
                "canonical",
                "进程/流程时序阶段：graceful_shutdown 的 ShutdownPhase、内存构建的 "
                "phase1/phase2 提示词。跨进程时序说 phase，跨工作流水线说 stage，"
                "两词不得混用。",
            ),
        ),
    ),
    VocabDomain(
        "kline_volume",
        (
            VocabTerm(
                "volume",
                "canonical",
                "K线三表（crypto_spot_klines / crypto_future_klines / stock_klines）的 "
                "volume 列 canonical 类型为 DECIMAL(40, 8) 单列（迁移 "
                "update_kline_volume_to_decimal，旧数据丢弃可重拉）。写入统一 "
                "collector.db.models.decimal_or_zero，读出统一 float()（Decimal 可直接转）。",
            ),
            VocabTerm(
                "volume_decimal",
                "banned",
                "禁止再为 volume 引入 String/双列形态（含 volume_decimal 伴生列）。",
            ),
            VocabTerm(
                "ohlc",
                "canonical",
                "K线三表 OHLC 四列 canonical 类型为 DECIMAL(40, 8)（P2-11 价格域收口，"
                "迁移 update_kline_ohlc_to_decimal DROP+create，存量K线可重拉）。写入统一 "
                "decimal_or_zero，读出统一 float()，API/前端零感知；timestamp 列 P2-14 "
                "起为 BigInteger 纳秒整型（迁移 update_kline_timestamp_to_bigint），"
                "不在价格域范围。",
            ),
        ),
    ),
)


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
