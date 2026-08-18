"""自定义指标代码静态质量分析

对用户编写的指标 Python 代码进行启发式规则检查，
不执行代码，仅通过正则/AST 分析检测潜在问题。
与策略代码质量分析不同，指标代码关注点在于：
- output 字典结构（plots/signals）
- 数据长度一致性
- NaN 处理最佳实践
- 信号标记格式
"""

from __future__ import annotations

import re
from typing import Any


def _has_my_indicator_meta(code: str) -> tuple[bool, bool]:
    """检查是否声明了 my_indicator_name 和 my_indicator_description"""
    c = code or ""
    name = bool(re.search(r"^\s*my_indicator_name\s*=", c, re.MULTILINE))
    desc = bool(re.search(r"^\s*my_indicator_description\s*=", c, re.MULTILINE))
    return name, desc


def _has_output_dict(code: str) -> bool:
    """检查是否定义了 output 变量"""
    return bool(re.search(r"\boutput\s*=\s*\{", code or ""))


def _has_df_copy(code: str) -> bool:
    """检查是否有 df = df.copy()"""
    return bool(re.search(r"df\s*=\s*df\.copy\s*\(\s*\)", code or ""))


def _declared_param_names(code: str) -> list[str]:
    """提取 # @param 声明的参数名"""
    names: list[str] = []
    for m in re.finditer(
        r"^\s*#\s*@param\s+(\w+)\s+(int|float|bool|str|string)\s+\S+",
        code or "",
        re.MULTILINE | re.IGNORECASE,
    ):
        names.append(m.group(1))
    return names


def _uses_params_get(code: str, name: str) -> bool:
    """检查参数是否通过 params.get() 读取"""
    pattern = rf'params\s*\.?\s*get\s*\(\s*[\'"]{re.escape(name)}[\'"]\s*,?'
    return bool(re.search(pattern, code or ""))


def _uses_where_none_for_markers(code: str) -> bool:
    """检查信号标记是否使用了 .where(None).tolist()（可能产生 NaN 问题）"""
    return bool(re.search(r"\.where\s*\([^)]*,\s*None\s*\)\s*\.tolist\s*\(", code or ""))


def _check_plots_structure(code: str) -> list[dict[str, Any]]:
    """检查 plots 定义的结构问题"""
    hints: list[dict[str, Any]] = []
    if not (code or "").strip():
        return hints

    if not re.search(r"['\"]plots['\"]", code):
        hints.append(
            {
                "severity": "error",
                "code": "MISSING_PLOTS_KEY",
                "message": "output 字典中缺少 'plots' 键",
            }
        )
    elif re.search(r"['\"]plots['\"]\s*:\s*\[\s*\]", code):
        hints.append(
            {
                "severity": "warn",
                "code": "EMPTY_PLOTS",
                "message": "plots 列表为空，K线图上将无任何内容显示",
            }
        )

    for m in re.finditer(r"['\"]name['\"]\s*:\s*", code):
        start = m.end()
        end_quote = code.find("'", start)
        if end_quote == -1:
            end_quote = code.find('"', start)
        if end_quote == -1:
            hints.append(
                {
                    "severity": "error",
                    "code": "INVALID_PLOT_NAME",
                    "message": "plot 的 name 值格式错误",
                }
            )

    for m in re.finditer(r"['\"]data['\"]\s*:\s*", code):
        pass

    if not re.search(r"['\"]overlay['\"]", code):
        hints.append(
            {
                "severity": "info",
                "code": "MISSING_OVERLAY_HINT",
                "message": "建议为每个 plot 指定 overlay 属性(True=主图叠加, False=副图)",
            }
        )

    return hints


def _check_signals_structure(code: str) -> list[dict[str, Any]]:
    """检查 signals 定义的结构问题"""
    hints: list[dict[str, Any]] = []
    if not (code or "").strip():
        return hints

    has_signals_key = bool(re.search(r"['\"]signals['\"]", code))
    if has_signals_key and re.search(r"['\"]signals['\"]\s*:\s*\[\s*\]", code):
        hints.append(
            {
                "severity": "info",
                "code": "EMPTY_SIGNALS",
                "message": "signals 列表为空，不会有买卖信号标记",
            }
        )

    for m in re.finditer(r"['\"]type['\"]\s*:\s*['\"](buy|sell)['\"]", code):
        m.group(1)

    unknown_types = set()
    for m in re.finditer(r"['\"]type['\"]\s*:\s*['\"](\w+)['']", code):
        t = m.group(1)
        if t not in ("buy", "sell"):
            unknown_types.add(t)
    for t in unknown_types:
        hints.append(
            {
                "severity": "warn",
                "code": "UNKNOWN_SIGNAL_TYPE",
                "message": f"未知的信号类型 '{t}'，仅支持 'buy' 和 'sell'",
                "params": {"type": t},
            }
        )

    return hints


def _check_nan_handling(code: str) -> list[dict[str, Any]]:
    """检查 NaN 处理最佳实践"""
    hints: list[dict[str, Any]] = []
    c = code or ""

    has_rolling = bool(re.search(r"\.rolling\s*\(", c))
    has_ewm = bool(re.search(r"\.ewm\s*\(", c))
    bool(re.search(r"\.shift\s*\(", c))
    bool(re.search(r"\.mean\s*\(", c))

    if (has_rolling or has_ewm) and not re.search(r"\.fillna\s*\(", c) and not re.search(r"\.dropna\s*\(", c):
        hints.append(
            {
                "severity": "warn",
                "code": "NO_NAN_HANDLING_AFTER_ROLLING",
                "message": "使用了 rolling/ewm 计算会产生前导 NaN，建议添加 .fillna() 处理",
            }
        )

    if re.search(r"np\.(nan|inf|NaN)", c) or re.search(r"math\.(nan|inf)", c):
        hints.append(
            {
                "severity": "warn",
                "code": "LITERAL_NAN_IN_CODE",
                "message": "代码中包含显式的 nan/inf 字面量，可能导致渲染异常",
            }
        )

    if re.search(r'output\s*=\s*\{[^}]*["\']data["\']', c) and not re.search(r"\.tolist\s*\(\s*\)", c[:500]):
        hints.append(
            {
                "severity": "info",
                "code": "DATA_NOT_CONVERTED_TO_LIST",
                "message": "plot/signal 的 data 建议使用 .tolist() 转换为 Python list",
            }
        )

    return hints


def _check_import_safety(code: str) -> list[dict[str, Any]]:
    """检查导入安全性"""
    hints: list[dict[str, Any]] = []
    c = code or ""
    dangerous_imports = [
        ("os", "禁止导入 os 模块"),
        ("sys", "禁止导入 sys 模块"),
        ("requests", "禁止导入 requests 模块"),
        ("subprocess", "禁止导入 subprocess 模块"),
        ("socket", "禁止导入 socket 模块"),
        ("threading", "禁止导入 threading 模块"),
        ("multiprocessing", "禁止导入 multiprocessing 模块"),
        ("sqlite3", "禁止导入 sqlite3 模块"),
    ]

    for mod, reason in dangerous_imports:
        pattern = rf"(?:^|[\s;])import\s+{re.escape(mod)}(?:\s|$|[,])|from\s+{re.escape(mod)}\s+import"
        if re.search(pattern, c, re.MULTILINE):
            hints.append(
                {
                    "severity": "error",
                    "code": f"DANGEROUS_IMPORT_{mod.upper()}",
                    "message": reason,
                }
            )

    dangerous_funcs = ["eval(", "exec(", "compile(", "__import__("]
    for func in dangerous_funcs:
        if func in c:
            hints.append(
                {
                    "severity": "error",
                    "code": "DANGEROUS_FUNC",
                    "message": f"使用了危险函数 {func.strip('(')}",
                }
            )

    return hints


def analyze_indicator_code_quality(code: str) -> list[dict[str, Any]]:
    """
    分析指标代码质量，返回提示列表

    每个 hint 包含:
      - severity: "error" | "warn" | "info"
      - code: 规则码（英文标识）
      - message: 中文描述
      - params: 可选的额外信息

    Args:
        code: 用户编写的指标 Python 代码字符串

    Returns:
        提示字典列表，空列表表示无问题
    """
    hints: list[dict[str, Any]] = []
    raw = (code or "").strip()
    if not raw:
        return [{"severity": "error", "code": "EMPTY_CODE", "message": "代码为空"}]

    if len(raw) > 10000:
        hints.append(
            {
                "severity": "warn",
                "code": "CODE_TOO_LONG",
                "message": f"代码过长({len(raw)}字符)，可能影响执行性能",
            }
        )

    name_ok, desc_ok = _has_my_indicator_meta(raw)
    if not name_ok:
        hints.append(
            {
                "severity": "warn",
                "code": "MISSING_INDICATOR_NAME",
                "message": "缺少 my_indicator_name 变量声明",
            }
        )
    if not desc_ok:
        hints.append(
            {
                "severity": "info",
                "code": "MISSING_INDICATOR_DESCRIPTION",
                "message": "缺少 my_indicator_description 变量声明",
            }
        )

    if not _has_df_copy(raw):
        hints.append(
            {
                "severity": "info",
                "code": "MISSING_DF_COPY",
                "message": "建议在开头添加 df = df.copy() 以避免修改原始数据",
            }
        )

    if not _has_output_dict(raw):
        hints.append(
            {
                "severity": "error",
                "code": "MISSING_OUTPUT",
                "message": "缺少 output 字典变量定义",
            }
        )
    else:
        hints.extend(_check_plots_structure(raw))
        hints.extend(_check_signals_structure(raw))

    declared_params = _declared_param_names(raw)
    if declared_params:
        unread = [n for n in declared_params if not _uses_params_get(raw, n)]
        if unread:
            joined = "、".join(unread)
            hints.append(
                {
                    "severity": "warn",
                    "code": "DECLARED_PARAMS_NOT_READ_VIA_PARAMS_GET",
                    "message": f"已声明的参数未通过 params.get() 读取：{joined}",
                    "params": {"names": unread},
                }
            )

    if _uses_where_none_for_markers(raw):
        hints.append(
            {
                "severity": "info",
                "code": "SIGNAL_MARKERS_USE_WHERE_NONE",
                "message": "信号标记使用了 .where(..., None).tolist()，建议改用显式 None 列表以避免 NaN 渲染问题",
            }
        )

    hints.extend(_check_nan_handling(raw))
    hints.extend(_check_import_safety(raw))

    if not re.search(r"pd\.|numpy|np\.", raw):
        hints.append(
            {
                "severity": "info",
                "code": "NO_PANDAS_USAGE",
                "message": "未检测到 pandas/numpy 使用，指标计算通常需要这些库",
            }
        )

    return hints


def get_quality_score(hints: list[dict[str, Any]]) -> tuple[int, str]:
    """
    根据提示列表计算质量分数

    Returns:
        (score, level): score 为 0-100 整数，level 为 "excellent"|"good"|"fair"|"poor"
    """
    if not hints:
        return 100, "excellent"

    error_count = sum(1 for h in hints if h.get("severity") == "error")
    warn_count = sum(1 for h in hints if h.get("severity") == "warn")
    info_count = sum(1 for h in hints if h.get("severity") == "info")

    score = max(0, 100 - error_count * 30 - warn_count * 10 - info_count * 2)

    if score >= 90:
        level = "excellent"
    elif score >= 70:
        level = "good"
    elif score >= 50:
        level = "fair"
    else:
        level = "poor"

    return score, level
