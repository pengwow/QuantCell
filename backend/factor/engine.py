"""因子求值引擎 — 基于本地 parquet K 线 + pandas 的自有实现。

- 内置/自定义因子统一由「表达式安全求值器」计算，表达式语法为本模块自有：
  列 open/high/low/close/volume/quote_volume/vwap/amount；
  函数 Ref/MA/Std/RSI/MACD/KDJ/BBANDS；四则运算 + 括号。
- 求值走 AST 白名单：禁止属性访问、导入、任意函数调用与未授权列。
- 财务因子（pe/pb/roe/roa/profit_growth）无行情数据来源，标记 supported=False。
"""

from __future__ import annotations

import ast
import operator as _op

import pandas as pd

from quality.parquet_provider import ParquetDataProvider
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


class FactorExpressionError(Exception):
    """因子不存在 / 表达式非法 / 无法求值"""


UNSUPPORTED_FACTORS: set[str] = {"pe", "pb", "roe", "roa", "profit_growth"}

# 因子求值实际需要的 K 线列（vwap/amount 由 quote_volume 派生，故必须含 quote_volume）
_KLINE_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]

# name -> 分类 / 展示名 / 自有表达式 / 是否可计算
FACTOR_META: dict[str, dict] = {
    "close": {"category": "price", "label": "收盘价", "expression": "close", "supported": True},
    "open": {"category": "price", "label": "开盘价", "expression": "open", "supported": True},
    "high": {"category": "price", "label": "最高价", "expression": "high", "supported": True},
    "low": {"category": "price", "label": "最低价", "expression": "low", "supported": True},
    "volume": {"category": "price", "label": "成交量", "expression": "volume", "supported": True},
    "vwap": {"category": "price", "label": "成交均价(VWAP)", "expression": "vwap", "supported": True},
    "amount": {"category": "price", "label": "成交额", "expression": "volume * close", "supported": True},
    "momentum_5d": {
        "category": "momentum",
        "label": "动量(5)",
        "expression": "close / Ref(close, 5) - 1",
        "supported": True,
    },
    "momentum_10d": {
        "category": "momentum",
        "label": "动量(10)",
        "expression": "close / Ref(close, 10) - 1",
        "supported": True,
    },
    "momentum_20d": {
        "category": "momentum",
        "label": "动量(20)",
        "expression": "close / Ref(close, 20) - 1",
        "supported": True,
    },
    "momentum_60d": {
        "category": "momentum",
        "label": "动量(60)",
        "expression": "close / Ref(close, 60) - 1",
        "supported": True,
    },
    "volatility_5d": {"category": "volatility", "label": "波动率(5)", "expression": "Std(close, 5)", "supported": True},
    "volatility_10d": {
        "category": "volatility",
        "label": "波动率(10)",
        "expression": "Std(close, 10)",
        "supported": True,
    },
    "volatility_20d": {
        "category": "volatility",
        "label": "波动率(20)",
        "expression": "Std(close, 20)",
        "supported": True,
    },
    "volatility_60d": {
        "category": "volatility",
        "label": "波动率(60)",
        "expression": "Std(close, 60)",
        "supported": True,
    },
    "turnover_rate": {
        "category": "volume_price",
        "label": "量比(20)",
        "expression": "volume / Ref(volume, 20)",
        "supported": True,
    },
    "volume_change": {
        "category": "volume_price",
        "label": "量变(1)",
        "expression": "volume / Ref(volume, 1) - 1",
        "supported": True,
    },
    "price_volume": {
        "category": "volume_price",
        "label": "价量相关",
        "expression": "(close - open) * volume",
        "supported": True,
    },
    "ma_5d": {"category": "technical", "label": "MA(5)", "expression": "MA(close, 5)", "supported": True},
    "ma_10d": {"category": "technical", "label": "MA(10)", "expression": "MA(close, 10)", "supported": True},
    "ma_20d": {"category": "technical", "label": "MA(20)", "expression": "MA(close, 20)", "supported": True},
    "ma_60d": {"category": "technical", "label": "MA(60)", "expression": "MA(close, 60)", "supported": True},
    "macd": {"category": "technical", "label": "MACD(DIF)", "expression": "MACD(close, 12, 26)", "supported": True},
    "rsi_14d": {"category": "technical", "label": "RSI(14)", "expression": "RSI(close, 14)", "supported": True},
    "kdj": {"category": "technical", "label": "KDJ-K(9)", "expression": "KDJ(high, low, close, 9)", "supported": True},
    "bollinger": {
        "category": "technical",
        "label": "布林%B(20,2)",
        "expression": "BBANDS(close, 20, 2)",
        "supported": True,
    },
    "pe": {"category": "fundamental", "label": "市盈率", "expression": "", "supported": False},
    "pb": {"category": "fundamental", "label": "市净率", "expression": "", "supported": False},
    "roe": {"category": "fundamental", "label": "净资产收益率", "expression": "", "supported": False},
    "roa": {"category": "fundamental", "label": "总资产收益率", "expression": "", "supported": False},
    "profit_growth": {"category": "fundamental", "label": "净利润增速", "expression": "", "supported": False},
}


# ---------------- 技术指标（纯 pandas） ----------------


def _rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + gain / loss)


def _macd(close: pd.Series, fast: int, slow: int) -> pd.Series:
    return close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()


def _kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    rsv = (close - low.rolling(n).min()) / (high.rolling(n).max() - low.rolling(n).min()) * 100
    return rsv.ewm(alpha=1 / 3, adjust=False).mean()


def _boll_pctb(close: pd.Series, n: int, k: float) -> pd.Series:
    return (close - close.rolling(n).mean()) / (k * close.rolling(n).std())


# ---------------- AST 白名单求值 ----------------

_BINOPS = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.Pow: _op.pow,
    ast.Mod: _op.mod,
}
_UNARY = {ast.UAdd: _op.pos, ast.USub: _op.neg}
_ALLOWED_COLS = {"open", "high", "low", "close", "volume", "quote_volume", "vwap", "amount"}
# 每个函数允许的 (序列参数个数, 整数窗口参数个数)
_FUNC_ARITY = {
    "Ref": (1, 1),
    "MA": (1, 1),
    "Std": (1, 1),
    "RSI": (1, 1),
    "MACD": (1, 2),
    "KDJ": (3, 1),
    "BBANDS": (1, 2),
}


def _const_int(node: ast.AST) -> int:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        return -int(node.operand.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return int(node.value)
    raise FactorExpressionError("函数窗口参数必须是整数常量")


def _eval(node: ast.AST, env: dict) -> pd.Series | float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, env))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNC_ARITY:
        fname = node.func.id
        n_series, n_int = _FUNC_ARITY[fname]
        if len(node.args) != n_series + n_int:
            raise FactorExpressionError(f"{fname} 参数个数错误")
        series_args = [_eval(a, env) for a in node.args[:n_series]]
        if not all(isinstance(a, pd.Series) for a in series_args):
            raise FactorExpressionError(f"{fname} 的序列参数必须是列字段")
        int_args = [_const_int(a) for a in node.args[n_series:]]
        if fname == "Ref":
            return series_args[0].shift(int_args[0])
        if fname == "MA":
            return series_args[0].rolling(int_args[0]).mean()
        if fname == "Std":
            return series_args[0].rolling(int_args[0]).std()
        if fname == "RSI":
            return _rsi(series_args[0], int_args[0])
        if fname == "MACD":
            return _macd(series_args[0], int_args[0], int_args[1])
        if fname == "KDJ":
            return _kdj(series_args[0], series_args[1], series_args[2], int_args[0])
        return _boll_pctb(series_args[0], int_args[0], float(int_args[1]))
    raise FactorExpressionError("表达式含不被允许的语法（仅支持列字段、Ref/MA/Std/RSI/MACD/KDJ/BBANDS、四则运算）")


def _column_env(df: pd.DataFrame) -> dict:
    return {
        "open": df["open"],
        "high": df["high"],
        "low": df["low"],
        "close": df["close"],
        "volume": df["volume"],
        "quote_volume": df["quote_volume"],
        "vwap": df["quote_volume"] / df["volume"],
        "amount": df["volume"] * df["close"],
    }


def evaluate_expression(expression: str, df: pd.DataFrame) -> pd.Series:
    """安全求值一个因子表达式。"""
    if not expression or not expression.strip():
        raise FactorExpressionError("表达式为空")
    expr = expression.strip()
    if "$" in expr:
        raise FactorExpressionError("不支持 $ 前缀，请直接使用列名（如 close）")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise FactorExpressionError(f"表达式语法错误: {e}") from e
    result = _eval(tree, _column_env(df))
    if not isinstance(result, pd.Series):
        raise FactorExpressionError("表达式必须返回按时间对齐的序列，而非标量")
    result.name = None
    return result


def evaluate_factor(name: str, df: pd.DataFrame, custom: dict[str, str] | None = None) -> pd.Series:
    """按因子名计算内置或自定义因子（输入单品种原始 K 线 DataFrame）。"""
    meta = FACTOR_META.get(name)
    if meta is not None:
        if not meta["supported"]:
            raise FactorExpressionError(f"因子 {name} 依赖财务数据，当前加密行情数据源不支持")
        return evaluate_expression(meta["expression"], df)
    custom = custom or {}
    if name in custom:
        return evaluate_expression(custom[name], df)
    raise FactorExpressionError(f"未知因子: {name}")


# ---------------- parquet 取数与面板 ----------------


def _timestamps_to_datetime(ts: pd.Series) -> pd.Series:
    """把整数时间戳列转为 datetime64[ns] Series，按数值量级自适应 ns/us/ms/s。

    Binance 等源落盘的 K 线时间戳实测为微秒（int64），而 pd.to_datetime 对
    整数默认按纳秒解析，会把日期错位到 1970 年。不同下载源单位不一，故用整列
    最大绝对值的量级推断单位，再统一转回纳秒；列本身已是日期类型时走默认解析。
    """
    numeric = pd.to_numeric(ts, errors="coerce")
    if numeric.notna().any():
        magnitude = float(numeric.abs().max())
        if magnitude >= 1e17:
            unit = "ns"
        elif magnitude >= 1e14:
            unit = "us"
        elif magnitude >= 1e11:
            unit = "ms"
        else:
            unit = "s"
        return pd.to_datetime(numeric, unit=unit, errors="coerce").astype("datetime64[ns]")
    return pd.to_datetime(ts, errors="coerce").astype("datetime64[ns]")


def load_raw_ohlcv(
    symbols: list[str],
    interval: str,
    candle_type: str,
    start: str | None,
    end: str | None,
    provider: ParquetDataProvider | None = None,
) -> dict[str, pd.DataFrame]:
    """读取多品种原始 K 线（每个 symbol 读盘一次，供多因子复用）。"""
    provider = provider or ParquetDataProvider()
    raw_map: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        raw = provider.get_kline_data(symbol, interval, candle_type, start, end, columns=_KLINE_COLUMNS)
        if not raw.empty:
            raw_map[symbol] = raw
    if not raw_map:
        raise FactorExpressionError("所选品种在该周期/时间范围内无可用数据")
    return raw_map


def factor_panel_from_raw(
    name: str, raw_map: dict[str, pd.DataFrame], custom: dict[str, str] | None = None
) -> pd.Series:
    """从已读入的多品种 K 线计算因子，返回 MultiIndex(datetime, symbol) Series。"""
    series_list = []
    for symbol, raw in raw_map.items():
        s = evaluate_factor(name, raw, custom)
        s.index = pd.MultiIndex.from_arrays(
            [_timestamps_to_datetime(raw["timestamp"]).values, [symbol] * len(raw)],
            names=["datetime", "symbol"],
        )
        series_list.append(s)
    panel = pd.concat(series_list).sort_index()
    panel.name = name
    return panel


def load_factor_panel(
    symbols: list[str],
    interval: str,
    candle_type: str,
    start: str | None,
    end: str | None,
    factor_name: str,
    custom_expressions: dict[str, str] | None = None,
    provider: ParquetDataProvider | None = None,
) -> pd.Series:
    """读盘 + 计算单因子面板。"""
    raw_map = load_raw_ohlcv(symbols, interval, candle_type, start, end, provider)
    return factor_panel_from_raw(factor_name, raw_map, custom_expressions)


def close_panel_from_raw(raw_map: dict[str, pd.DataFrame]) -> pd.Series:
    """从已读入的多品种 K 线构造收盘价 MultiIndex(datetime, symbol) 面板。"""
    series_list = []
    for symbol, raw in raw_map.items():
        s = raw["close"].copy()
        s.index = pd.MultiIndex.from_arrays(
            [_timestamps_to_datetime(raw["timestamp"]).values, [symbol] * len(raw)],
            names=["datetime", "symbol"],
        )
        series_list.append(s)
    panel = pd.concat(series_list).sort_index()
    panel.name = "close"
    return panel


def load_close_panel(
    symbols: list[str],
    interval: str,
    candle_type: str,
    start: str | None,
    end: str | None,
    provider: ParquetDataProvider | None = None,
) -> pd.Series:
    """读取多品种收盘价面板（与因子面板同索引约定）。"""
    raw_map = load_raw_ohlcv(symbols, interval, candle_type, start, end, provider)
    return close_panel_from_raw(raw_map)
