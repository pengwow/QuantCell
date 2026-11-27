"""banned 词条 lint 门禁（命名审计 P2-6 / A-7）。

词条事实源 = vocab.py 的 VOCAB_DOMAINS（kind="banned"）；本脚本的词法规则表
TERM_RULES 必须覆盖全部 banned 词条（缺一即 abort），防止词条与词法规则漂移。

三种模式（同 frontend i18n-audit 的基线交互）：
  python scripts/vocab_lint.py                  # 探测：输出明细排行
  python scripts/vocab_lint.py --check          # 门禁：任一 (file, term) 计数超基线即 exit 1
  python scripts/vocab_lint.py --update-baseline

基线文件 backend/scripts/vocab_lint_baseline.json，只降不升：
新代码出现 banned 词条会让 CI / pre-commit 变红；清理存量后主动 --update-baseline 收紧。

豁免分两层：
1. 路径豁免：词汇事实源自身（vocab.py / vocab.generated.ts / export_vocab_types.py）
   与归档代码（decision_py_archive_v2_202610 / .trae_deleted）。
2. 行级豁免：注释行不扫；CONTEXT_ALLOW 上下文正则豁免 exchange adapter 边界的
   交易所原生参数（同 side 域「BINANCE BUY 原则」——原生语境合法，跨模块即禁）。

ponytail: 行级正则扫描，字符串内出现的词（如 K线类型 "LONG"）与代码标识符无法
静态区分，统一计入基线由人工清理；升级路径：换 AST 解析 + 语境判定。
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 脚本直跑时 sys.path[0] 是 scripts/，把 backend 根提入 path 以 import vocab 事实源
BACKEND_ROOT = Path(__file__).resolve().parent.parent  # backend/
sys.path.insert(0, str(BACKEND_ROOT))

from vocab import VOCAB_DOMAINS

REPO_ROOT = BACKEND_ROOT.parent
BASELINE_PATH = BACKEND_ROOT / "scripts" / "vocab_lint_baseline.json"

# 路径豁免（相对 repo 根）：词汇事实源自身、归档/运行时数据目录
PATH_ALLOW = {
    "backend/vocab.py",
    "backend/worker/vocab.py",
    "backend/scripts/export_vocab_types.py",
    "backend/scripts/vocab_lint.py",
    "frontend/src/types/vocab.generated.ts",  # 生成产物，与事实源同步
    "backend/.archive/",  # 历史归档（含 .trash）
    "backend/data/",  # 运行时数据目录（用户安装插件等），非代码库
}

# 注释行（整行豁免）与行内注释剥离（# 前须空白，避免误伤 URL/字符串内容）
COMMENT_LINE_RE = re.compile(r"^\s*(#|//|/?\*|\{/\*)")
INLINE_COMMENT_RE = [re.compile(r"\s+#.*$"), re.compile(r"\s+//.*$")]

# 词法规则表：词条事实源 → 词正则 + 大小写口径 + 边界豁免。
# erase：先抹掉的合法组合词（canonical / reserved），抹完再数命中；
# context_allow：行内命中任一正则则该行豁免（adapter 边界原生语境）；
# file_allow：整文件豁免（文件级原生语境，相对 repo 根）。
TERM_RULES: dict[str, dict] = {
    # direction 域：LONG/SHORT 仅交易所原生大写值（adapter 边界），canonical 是
    # 小写 position_side="long"，故只拦大写整词
    "LONG/SHORT": {
        "regex": r"\b(LONG|SHORT)\b",
        "case_sensitive": True,
        "context_allow": [
            r"PositionSide\.",
            r"position_side",
            # 测试守护情境（P2-13 定性）：词汇归一收口后，必须持续验证「大写入参被
            # 兼容归一 / 被 Schema 拒绝」，以下非 canonical 字面量是测试本体，故意保留：
            r"side\s*=?\s*[\"']?(?:LONG|SHORT)\b",  # side="LONG" / ?side=LONG / event.side = "LONG"
            r"[\"'](?:LONG|SHORT)[\"']\s*,\s*[\"'](?:long|short)[\"']",  # 参数化归一对 ("LONG", "long")
            r"VALUES\s*\(\s*[\"'](?:LONG|SHORT)[\"']\s*\)",  # 迁移测试的遗留大写脏数据
        ],
    },
    # account 域：裸 wallet 禁用（wallet_balance canonical 有 _ 续接，\bwallet\b 天然不命中）
    "wallet": {"regex": r"\bwallet\b", "case_sensitive": False},
    # account 域：margin 组合仅保留 canonical margin_used 与 reserved 配置语境。
    # erase 含引擎边界词（usd_margin / coin_margin 结算口径、margin_equity 强平判定）
    # 与 CSS 样式语境（margin: 8 / marginBottom —— 样式边距非账域）
    "margin": {
        "regex": r"\bmargin\w*",
        "case_sensitive": False,
        # erase：词形本身合法的 term（snake canonical/reserved + TS camel 镜像），扫描前从违规检查层挖掉
        "erase": r"\bmargin(?:_used|_mode|_applied|_ratio|_specs\w*|_asset|_equity|(?:(?:usd|coin)_)?margin|(?:(?:initial|maint)_margin))\b|[Mm]argin(?:Used|Mode|Applied|Ratio|Specs?\w*|Asset|Equity|Initial|Maint|Balance)\b",
        "context_allow": [
            r"margin(?:[A-Z]\w*)?\s*[:=]\s*[\"'0-9(.\[-]",  # CSS：margin: 8 / marginBottom: 16
            r"\.margins\(",  # matplotlib/empyrical 的_ax.margins 轴边距 API
            r"margin-(?:top|bottom|left|right)",  # template literal 内的 CSS 连字符属性
            r"MARGIN\s*=\s*[\"']",  # 交易所协议枚举值 MARGIN = "margin"
            r"==\s*[\"']margin[\"']|return\s+[\"']margin[\"']",  # 杠杆账户类型值域判断/透传（ccxt defaultType）
            r"\bspot\s*/\s*(?:future\(s\)?|futures)\s*/\s*margin\b",  # AccountType 三档枚举的文档串（杠杆账户语境），
            r"\bspot\s*/\s*margin\b",  # market_type 值域组合文档串（spot/margin 共用现货 ticker / spot / margin / futures）
            r"AccountType\s*\.|account_type|accountType",  # 账户类型：account_type / 拼接词 BinanceAccountType.MARGIN
            r"trading_mode|tradingMode|TradingMode",  # trading_mode 值域含 "margin"，键本身合法
            r"margin_type|marginType",  # set_margin_type 是交易所接口命名
            r"value:\s*[\"']margin[\"']",  # 下拉选项 { value: 'margin' }，UI 值域
            r"[\"']margin[\"']\s*:",  # market_type 值域 dict 键（spot/margin/futures 行情分类契约）
            r"margin\.rs",  # axon-quant 源文件名的文档引用
            r"asset_type, base, quote, margin",  # axon_bridge instrument 元组的文档注释
            r"Column\([\"']margin_ratio",  # alembic 历史迁移里的 DB 列（列保留，ORM 层已删）
            r"\.get\([\"']margin_(?:shortfall_count|settings)[\"']\)",  # 旧结果 JSON/任务行的兼容回退键
        ],
    },
    # interval 域：period 禁用于 K线频率；_period 后缀参数（bb_period 等）天然不命中
    "period": {
        "regex": r"\bperiod\b",
        "case_sensitive": False,
        "context_allow": [
            r"_PERIOD_MAP",
            r"rate_limit\(",  # 限流窗口参数（秒），freq 无关
            r'Column\("period"',  # 历史 alembic 迁移文件（历史 DDL 记录不可改）
            r'"period"\s*:\s*\d',  # 指标参数 JSON 回看窗口根数（rsi.period=14 同 taBuiltins 例外）
        ],
        "file_allow": (
            "backend/backtest/baseline.py",  # report.period：报表覆盖日期区间
            "backend/collector/services/deriv_collector.py",  # 交易所 OpenInterest 原生参数
            "backend/collector/services/",  # deriv/quality 交易所原生参数语境（tests 同语境）
            "backend/strategy/templates/mean_reversion.py",  # _rsi(closes, period) 回看窗口（note 例外）
            "backend/collector/db/migrations.py",  # 历史列名 rename 迁移（features.freq → interval）
            "backend/alembic/versions/46_rename_indicator_alert_rules_period_to_interval.py",  # rename 迁移
            "backend/tests/unit/collector/test_kline_interval_rename_migration.py",  # 迁移自检测试：须书写历史列名验证 rename
            "backend/exchange/decorators.py",  # rate_limit(calls, period) 限流窗口秒数（vocab note 例外）
            "backend/tests/unit/collector/services/",  # 交易所原生参数语境的适配层测试
            "frontend/src/components/chart/",  # 图表 UI 展示层遗留词（vocab note 明文豁免）
            "frontend/src/utils/taBuiltins.ts",  # TA 指标回看窗口参数（note 例外：指标窗口根数）
        ),
    },
    # interval 域：freq 禁用于 K线频率；pandas 参数名语境豁免
    "freq": {
        "regex": r"\bfreq\b",
        "case_sensitive": False,
        "context_allow": [r"date_range", r"resample\("],
        "file_allow": (
            "backend/collector/db/migrations.py",  # 历史列名 rename 迁移（features.freq → interval）
            "backend/alembic/versions/46_rename_indicator_alert_rules_period_to_interval.py",  # 同上
            "backend/tests/unit/collector/test_kline_interval_rename_migration.py",  # 迁移自检测试：同上语境
        ),
    },
    # position 域：holdings 禁用于持仓语义（hold 是策略输出枚举，不命中）
    "holdings": {"regex": r"\bholdings\b", "case_sensitive": False},
    # kline_volume 域：禁止 volume 的 String/双列伴生形态
    "volume_decimal": {"regex": r"volume_decimal", "case_sensitive": False},
}


def _check_term_rules_cover_banned() -> None:
    """TERM_RULES 必须覆盖 VOCAB_DOMAINS 全部 banned 词条，缺一 abort（防漂移）。"""
    banned = {t.term for d in VOCAB_DOMAINS for t in d.terms if t.kind == "banned"}
    missing = banned - set(TERM_RULES)
    if missing:
        raise SystemExit(f"vocab_lint.py 的 TERM_RULES 缺少 banned 词条的词法规则: {sorted(missing)}")


def _is_file_allowed(rel: str, prefixes: tuple[str, ...]) -> bool:
    """文件级豁免匹配：精确路径，或以 / 结尾的目录前缀。"""
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in prefixes)


def _path_allowed(rel: str) -> bool:
    """路径豁免匹配：精确相等或目录前缀（以 / 结尾的条目）。"""
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in PATH_ALLOW)


def iter_target_files():
    """收集扫描目标：backend/**/*.py + frontend/src/**/*.{ts,tsx}（排除归档/venv/测试/生成物）。"""
    py_files = [p for p in BACKEND_ROOT.rglob("*.py")]
    fe_src = REPO_ROOT / "frontend" / "src"
    ts_files = [p for p in fe_src.rglob("*") if p.suffix in (".ts", ".tsx")] if fe_src.exists() else []
    for f in sorted(py_files + ts_files):
        rel = f.relative_to(REPO_ROOT).as_posix()
        s = str(f)
        if any(seg in s for seg in (".trae_deleted", "decision_py_archive", ".venv")):
            continue
        if f.suffix in (".ts", ".tsx") and (".test." in f.name or ".d.ts" in f.name):
            continue
        if _path_allowed(rel):
            continue
        yield rel, f


def scan_file(rel: str, path: Path) -> dict[str, list[int]]:
    """单文件扫描：返回 {词条: [行号]}。"""
    hits: dict[str, list[int]] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return hits
    for lineno, raw in enumerate(lines, 1):
        if COMMENT_LINE_RE.match(raw):
            continue
        line = raw
        for inline_re in INLINE_COMMENT_RE:
            line = inline_re.sub("", line)
        for term, rule in TERM_RULES.items():
            if _is_file_allowed(rel, rule.get("file_allow", ())):
                continue
            if any(re.search(rx, line) for rx in rule.get("context_allow", [])):
                continue
            cleaned = line
            if rule.get("erase"):
                cleaned = re.sub(rule["erase"], " ", cleaned)
            flags = 0 if rule.get("case_sensitive") else re.IGNORECASE
            if re.search(rule["regex"], cleaned, flags):
                hits.setdefault(term, []).append(lineno)
    return hits


def run_scan() -> dict[str, dict[str, int]]:
    """全量扫描：{file: {term: count}}，仅含命中文件。"""
    results: dict[str, dict[str, int]] = {}
    for rel, f in iter_target_files():
        hits = scan_file(rel, f)
        if hits:
            results[rel] = {t: len(ns) for t, ns in hits.items()}
    return results


def _relative_hits_by_lineno(results: dict[str, dict[str, int]]) -> dict[str, dict[str, list[int]]]:
    """探测模式用：重新扫描拿到行号明细（避免改变基线协议结构）。"""
    detail: dict[str, dict[str, list[int]]] = {}
    for rel, f in iter_target_files():
        hits = scan_file(rel, f)
        if rel in results and hits:
            detail[rel] = hits
    return detail


def main() -> int:
    parser = argparse.ArgumentParser(description="banned 词条 lint 门禁（命名审计 P2-6）")
    parser.add_argument("--check", action="store_true", help="门禁模式：与基线比对，超基线 exit 1")
    parser.add_argument("--update-baseline", action="store_true", help="以当前扫描结果重写基线")
    parser.add_argument("--detail", action="store_true", help="输出每处命中的行号")
    args = parser.parse_args()

    _check_term_rules_cover_banned()
    results = run_scan()
    total = sum(sum(v.values()) for v in results.values())

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        print(f"基线已更新：{total} 处命中（{BASELINE_PATH}）")
        return 0

    print(f"\nvocab banned-terms 扫描：共 {total} 处（backend/**/*.py + frontend/src/**）\n")
    for rel in sorted(results, key=lambda r: -sum(results[r].values())):
        terms = results[rel]
        print(f"{sum(terms.values()):5d}  {rel}  " + " ".join(f"{t}:{n}" for t, n in sorted(terms.items())))
    if args.detail:
        for rel, hits in _relative_hits_by_lineno(results).items():
            for term, linenos in hits.items():
                for ln in linenos:
                    print(f"  {rel}:{ln}: {term}")
        print()

    if not args.check:
        print("（探测模式；--check 走门禁，--update-baseline 收紧基线）")
        return 0

    if not BASELINE_PATH.exists():
        print("未找到基线，请先执行: uv run python scripts/vocab_lint.py --update-baseline", file=sys.stderr)
        return 1
    baseline = json.loads(BASELINE_PATH.read_text())
    violations = []
    for rel, terms in results.items():
        allowed = baseline.get(rel, {})
        for t, n in terms.items():
            if n > allowed.get(t, 0):
                violations.append(f"{rel}: {t} {n} 处（基线 {allowed.get(t, 0)}）")
    if violations:
        print("\nvocab lint 失败：以下 (file, term) 超出基线（只许迁出减少，不许新增）：\n", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\n处理：改用 canonical 词（词条裁决见 vocab.py VOCAB_DOMAINS / GET /api/v1/vocab）；"
            "确属 adapter 原生语境可在 vocab_lint.py 的 TERM_RULES 挂 context_allow / file_allow。",
            file=sys.stderr,
        )
        return 1
    print(f"vocab lint 通过：{total} 处，均在基线内（迁移清理后用 --update-baseline 收紧）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
