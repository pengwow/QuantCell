"""系统内置指标的提醒支持定义。

信号提醒评估走 indicators/executor.py 的沙箱（受限 builtins + df/pd/np/math/params），
而系统内置指标原本只在前端 klinecharts 渲染、后端没有可执行代码，
导致内置指标无法创建提醒规则。这里以同一套沙箱契约（结尾赋值 output dict）
为每个内置指标提供 pandas 计算模板，随 GET /indicators/alerts/builtins 下发，
规则侧通过 indicator_alert_rules.builtin_id 引用。

plots 命名与前端 klinecharts 内置指标输出线对齐，便于弹窗里直接选线。
"""

from typing import Any

# 单个指标的沙箱模板：params.get(...) 带默认值，规则不传 params 也成立
_SMIMA = """
length = int(params.get("length", 20))
ma = df["close"].rolling(length).mean()
output = {
    "name": "SMA",
    "plots": [{"name": "sma", "data": ma.tolist()}],
    "signals": [],
}
"""

_EMA = """
length = int(params.get("length", 20))
ema = df["close"].ewm(span=length, adjust=False).mean()
output = {
    "name": "EMA",
    "plots": [{"name": "ema", "data": ema.tolist()}],
    "signals": [],
}
"""

_RSI = """
length = int(params.get("length", 14))
diff = df["close"].diff()
gain = diff.clip(lower=0).ewm(alpha=1.0 / length, adjust=False).mean()
loss = (-diff.clip(upper=0)).ewm(alpha=1.0 / length, adjust=False).mean()
rs = gain / loss.replace(0, np.nan)
rsi = 100 - 100 / (1 + rs)
output = {
    "name": "RSI",
    "plots": [{"name": "rsi", "data": rsi.tolist()}],
    "signals": [],
}
"""

_MACD = """
fast = int(params.get("fast", 12))
slow = int(params.get("slow", 26))
signal = int(params.get("signal", 9))
dif = df["close"].ewm(span=fast, adjust=False).mean() - df["close"].ewm(span=slow, adjust=False).mean()
dea = dif.ewm(span=signal, adjust=False).mean()
macd = 2 * (dif - dea)
output = {
    "name": "MACD",
    "plots": [
        {"name": "dif", "data": dif.tolist()},
        {"name": "dea", "data": dea.tolist()},
        {"name": "macd", "data": macd.tolist()},
    ],
    "signals": [],
}
"""

_BB = """
length = int(params.get("length", 20))
std_dev = float(params.get("std_dev", 2))
mid = df["close"].rolling(length).mean()
std = df["close"].rolling(length).std()
output = {
    "name": "BB",
    "plots": [
        {"name": "mid", "data": mid.tolist()},
        {"name": "up", "data": (mid + std_dev * std).tolist()},
        {"name": "down", "data": (mid - std_dev * std).tolist()},
    ],
    "signals": [],
}
"""

# TR / Wilder 平滑为 ATR、ADX 共用
_TR = """
prev_close = df["close"].shift(1)
tr = pd.concat(
    [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
    axis=1,
).max(axis=1)
"""

_ATR = (
    _TR
    + """
length = int(params.get("length", 14))
atr = tr.ewm(alpha=1.0 / length, adjust=False).mean()
output = {
    "name": "ATR",
    "plots": [{"name": "atr", "data": atr.tolist()}],
    "signals": [],
}
"""
)

_CCI = """
length = int(params.get("length", 20))
tp = (df["high"] + df["low"] + df["close"]) / 3
ma = tp.rolling(length).mean()
md = (tp - ma).abs().rolling(length).mean()
cci = (tp - ma) / (0.015 * md)
output = {
    "name": "CCI",
    "plots": [{"name": "cci", "data": cci.tolist()}],
    "signals": [],
}
"""

_WR = """
length = int(params.get("length", 14))
hh = df["high"].rolling(length).max()
ll = df["low"].rolling(length).min()
wr = -100 * (hh - df["close"]) / (hh - ll)
output = {
    "name": "WR",
    "plots": [{"name": "wr", "data": wr.tolist()}],
    "signals": [],
}
"""

_MFI = """
length = int(params.get("length", 14))
tp = (df["high"] + df["low"] + df["close"]) / 3
mf = tp * df["volume"]
diff = tp.diff()
pos = mf.where(diff > 0, 0.0).rolling(length).sum()
neg = mf.where(diff < 0, 0.0).rolling(length).sum()
mfi = 100 - 100 / (1 + pos / neg.replace(0, np.nan))
output = {
    "name": "MFI",
    "plots": [{"name": "mfi", "data": mfi.tolist()}],
    "signals": [],
}
"""

_ADX = (
    _TR
    + """
length = int(params.get("length", 14))
smooth = int(params.get("smooth", 6))
up = df["high"].diff()
down = -df["low"].diff()
plus_dm = up.where((up > down) & (up > 0), 0.0)
minus_dm = down.where((down > up) & (down > 0), 0.0)
atr = tr.ewm(alpha=1.0 / length, adjust=False).mean()
pdi = 100 * plus_dm.ewm(alpha=1.0 / length, adjust=False).mean() / atr
mdi = 100 * minus_dm.ewm(alpha=1.0 / length, adjust=False).mean() / atr
dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
adx = dx.ewm(alpha=2.0 / (smooth + 1), adjust=False).mean()
output = {
    "name": "ADX",
    "plots": [
        {"name": "adx", "data": adx.tolist()},
        {"name": "pdi", "data": pdi.tolist()},
        {"name": "mdi", "data": mdi.tolist()},
    ],
    "signals": [],
}
"""
)

_OBV = """
obv = (np.sign(df["close"].diff()).fillna(0.0) * df["volume"]).cumsum()
output = {
    "name": "OBV",
    "plots": [{"name": "obv", "data": obv.tolist()}],
    "signals": [],
}
"""

# CLV 落在 [-1, 1]，高低重合（一字板）时区间为 0，置 NaN 后由 clean_nan 清洗
_CLV = """
hl_range = (df["high"] - df["low"]).replace(0, np.nan)
clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl_range
adv = (clv * df["volume"]).fillna(0.0)
"""

_ADOSC = (
    _CLV
    + """
fast = int(params.get("fast", 3))
slow = int(params.get("slow", 10))
adosc = adv.ewm(span=fast, adjust=False).mean() - adv.ewm(span=slow, adjust=False).mean()
output = {
    "name": "ADOSC",
    "plots": [{"name": "adosc", "data": adosc.tolist()}],
    "signals": [],
}
"""
)

_AD = (
    _CLV
    + """
ad = adv.cumsum()
output = {
    "name": "AD",
    "plots": [{"name": "ad", "data": ad.tolist()}],
    "signals": [],
}
"""
)

_KDJ = """
n = int(params.get("k", 9))
m1 = int(params.get("d", 3))
m2 = int(params.get("j", 3))
hh = df["high"].rolling(n).max()
ll = df["low"].rolling(n).min()
rsv = 100 * (df["close"] - ll) / (hh - ll).replace(0, np.nan)
k = rsv.ewm(alpha=1.0 / m1, adjust=False).mean()
d = k.ewm(alpha=1.0 / m2, adjust=False).mean()
j = 3 * k - 2 * d
output = {
    "name": "KDJ",
    "plots": [
        {"name": "k", "data": k.tolist()},
        {"name": "d", "data": d.tolist()},
        {"name": "j", "data": j.tolist()},
    ],
    "signals": [],
}
"""

_VOL = """
ma1_len = int(params.get("ma1", 5))
ma2_len = int(params.get("ma2", 10))
volume = df["volume"].fillna(0.0)
ma1 = volume.rolling(ma1_len).mean()
ma2 = volume.rolling(ma2_len).mean()
output = {
    "name": "VOL",
    "plots": [
        {"name": "volume", "data": volume.tolist()},
        {"name": "ma1", "data": ma1.tolist()},
        {"name": "ma2", "data": ma2.tolist()},
    ],
    "signals": [],
}
"""

# key 即 builtin_id；顺序即前端下拉展示顺序（name/description 为中文兜底文案）
BUILTIN_ALERT_INDICATORS: dict[str, dict[str, Any]] = {
    "sma": {
        "name": "SMA 简单移动平均",
        "description": "收盘价 N 周期算术移动平均线",
        "plots": ["sma"],
        "params": {"length": 20},
        "code": _SMIMA,
    },
    "ema": {
        "name": "EMA 指数移动平均",
        "description": "对近期价格赋更高权重的移动平均线",
        "plots": ["ema"],
        "params": {"length": 20},
        "code": _EMA,
    },
    "rsi": {
        "name": "RSI 相对强弱指数",
        "description": "衡量涨跌动量强弱，70/30 为常见超买超卖参考线",
        "plots": ["rsi"],
        "params": {"length": 14},
        "code": _RSI,
    },
    "macd": {
        "name": "MACD 指数平滑异同平均",
        "description": "DIF/DEA/柱状线，常用于趋势与背离判断",
        "plots": ["dif", "dea", "macd"],
        "params": {"fast": 12, "slow": 26, "signal": 9},
        "code": _MACD,
    },
    "bb": {
        "name": "BB 布林带",
        "description": "中轨均线与上下标准差通道，衡量波动区间",
        "plots": ["mid", "up", "down"],
        "params": {"length": 20, "std_dev": 2},
        "code": _BB,
    },
    "atr": {
        "name": "ATR 平均真实波幅",
        "description": "衡量单根K线平均波动幅度，常用于止损参考",
        "plots": ["atr"],
        "params": {"length": 14},
        "code": _ATR,
    },
    "cci": {
        "name": "CCI 商品通道指数",
        "description": "偏离统计均值的程度，±100 为常见超买超卖参考",
        "plots": ["cci"],
        "params": {"length": 20},
        "code": _CCI,
    },
    "wr": {
        "name": "WR 威廉指标",
        "description": "收盘价在区间内的相对位置，-20/-80 为常见超买超卖参考",
        "plots": ["wr"],
        "params": {"length": 14},
        "code": _WR,
    },
    "mfi": {
        "name": "MFI 资金流量指标",
        "description": "结合价格与成交量的强弱指标，80/20 为常见超买超卖参考",
        "plots": ["mfi"],
        "params": {"length": 14},
        "code": _MFI,
    },
    "adx": {
        "name": "ADX 平均趋向指数",
        "description": "衡量趋势强度，+DI/-DI 反映多空方向",
        "plots": ["adx", "pdi", "mdi"],
        "params": {"length": 14, "smooth": 6},
        "code": _ADX,
    },
    "obv": {
        "name": "OBV 能量潮",
        "description": "按收盘涨跌累加成交量的动量指标",
        "plots": ["obv"],
        "params": {},
        "code": _OBV,
    },
    "adosc": {
        "name": "ADOSC 震荡指标",
        "description": "累积/派发线的快慢均线差，衡量资金进出",
        "plots": ["adosc"],
        "params": {"fast": 3, "slow": 10},
        "code": _ADOSC,
    },
    "ad": {
        "name": "AD 累积/派发线",
        "description": "按收盘位置加权累加成交量的资金流向指标",
        "plots": ["ad"],
        "params": {},
        "code": _AD,
    },
    "kdj": {
        "name": "KDJ 随机指标",
        "description": "K/D/J 三线，80/20 为常见超买超卖参考",
        "plots": ["k", "d", "j"],
        "params": {"k": 9, "d": 3, "j": 3},
        "code": _KDJ,
    },
    "vol": {
        "name": "VOL 成交量",
        "description": "成交量柱与其双均线",
        "plots": ["volume", "ma1", "ma2"],
        "params": {"ma1": 5, "ma2": 10},
        "code": _VOL,
    },
}


def builtin_definitions() -> list[dict[str, Any]]:
    """发送给前端的内置指标定义（不含沙箱代码）。"""
    return [
        {
            "key": key,
            "name": item["name"],
            "description": item["description"],
            "plots": item["plots"],
            "params": item["params"],
        }
        for key, item in BUILTIN_ALERT_INDICATORS.items()
    ]
