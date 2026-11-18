"""RL Training Pipeline Service.

Unified entry point for RL training, HPO, Walk-Forward, and model registry.
"""

from __future__ import annotations

import contextlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from axon_quant.rl import run_kernel_backtest

from backtest.hpo_runner import HPORunner
from backtest.walk_forward import WalkForwardService
from services.ensemble_aggregator import make_ensemble_predict_fn
from services.rl_task_runner import NullReporter, ScaledReporter, learn_in_chunks
from services.slippage import SlippageCurve
from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    import pandas as pd

logger = get_logger(__name__, LogType.APPLICATION)

MODELS_DIR = Path(__file__).parent.parent / "data" / "models"

# 内核 RL 口径：与训练环境 `PyTradingEnv` 的默认观测空间一致
# （close Z-Score + volume 不归一化，window=1），保证模型输入维度对齐。
#
# 训练期观测归一化统计量（RunningStats）随模型落盘：训练结束时写进
# `<model>.meta.json` 的 `observation_stats`，内核路径用 `stats=` 灌回，
# 让内核侧 Z-Score 与训练分布一致。meta 缺该字段时内核统计量全空（Z-Score
# 恒为 0），加载处会告警 —— 那种情况下内核结果不能当作与训练等价的评估口径。
KERNEL_SPEC_VERSION = "v1"
KERNEL_WINDOW_SIZE = 1
KERNEL_FEATURES = [
    {"name": "close", "source": {"PriceField": "close"}, "normalizer": "ZScore", "clip_range": None},
    {"name": "volume", "source": {"VolumeField": "volume"}, "normalizer": "None", "clip_range": None},
]
# 内核 RL host 的动作空间必须是覆盖 [-1, 1] 的连续空间，
# 这样 `ratio -> Action -> decode_target_ratio` 才是恒等映射
KERNEL_ACTION_SPACE = {"type": "continuous", "min": -1.0, "max": 1.0}

#: obs 编码模式。`features` = 原生 `TradingEnv` 的指标向量（窗口 1，
#: close Z-Score + volume），旧模型都是这个口径；`ohlcv_window` = 原始 OHLCV
#: 归一化窗口（P3 opt-in，Python 侧变换层，见 `ObsWindowEnv`）。
OBS_MODE_FEATURES = "features"
OBS_MODE_OHLCV_WINDOW = "ohlcv_window"
OBS_MODES = (OBS_MODE_FEATURES, OBS_MODE_OHLCV_WINDOW)
#: OHLCV 窗口模式的默认窗口长度（bar）
OBS_WINDOW_DEFAULT = 64
#: 视为「常量通道」的 std 阈值。浮点累加残差（如 1.4e-17）若不当 0，
#: z-score 会把常量通道放大成 ±1e17 的垃圾特征。
OBS_STD_EPS = 1e-12
#: OHLCV 窗口模式的通道顺序（摊平顺序 = 时间窗内逐 bar 按此顺序）
OBS_CHANNELS = ("open", "high", "low", "close", "volume")

#: 派生微结构通道 → 适配器实际产出列（`backend/backtest/data_adapters/`）。
#:
#: 来源核实（P3-2）：
#: - `orderbook_adapter.py:72-73` bookTicker 产 `feature_mid_price` / `feature_spread`；
#: - `orderbook_adapter.py:119` bookDepth 只产 `feature_mid_price`（无 spread）；
#: - `tick_adapter.py:81-85` aggTrades/trades 只产 OHLCV，原始 `isBuyerMaker` 等方向列
#:   在聚合时被丢弃，故没有买卖不平衡通道可接（升级项：adapter 透传方向列后加）。
#:
#: 语义红线（`backtest/engine_service.py` 顶部）：bookDepth/bookTicker 的价是
#: **mid-price 合成价**，只作特征，绝不当作可撮合价。
OBS_EXTRA_CHANNELS: dict[str, dict[str, str]] = {
    "mid_price": {
        "column": "feature_mid_price",
        "note": "bookDepth/bookTicker 聚合的 mid 价（合成价，仅特征）",
    },
    "spread": {
        "column": "feature_spread",
        "note": "bookTicker 聚合的最优买卖价差均值（quote 单位）",
    },
}

# RL 成本口径的唯一来源：训练环境（`TradingEnv`）与内核评估（`worker.Kernel`）
# 都从这里取，改这一处即两边同步。任何一边自己写数字都会让
# `attribute_engine_diff` 报「成本模型不一致」。
RL_TRANSACTION_COST = 0.0001
RL_SLIPPAGE = 0.00001

#: 复合 reward 的 term 键域（`RLTrainConfig.reward_terms` 只接受这些键）
REWARD_TERM_KEYS = ("pnl", "sharpe", "downside", "turnover", "mdd")

#: 现行 reward（原生 `TradingEnv` 的 `reward="pnl"`）固化为默认配比：pnl=1，其余 0。
#: 因此不传 `reward_terms` 时行为与改造前完全一致（零漂移）。
DEFAULT_REWARD_TERMS: dict[str, float] = {"pnl": 1.0, "sharpe": 0.0, "downside": 0.0, "turnover": 0.0, "mdd": 0.0}

#: 部署策略行名前缀：`rl_paper_<model_id>`（`build_deploy_spec` 幂等 upsert 的键）
DEPLOY_STRATEGY_PREFIX = "rl_paper_"


@dataclass(frozen=True)
class CostProfile:
    """成本口径 profile：默认费率 + 按交易对 / 数据类型（candle_type）覆盖。

    缺省实例等价于改造前的单一常量 `RL_TRANSACTION_COST`（所有查询落到
    `default`，数值完全一致）。优先级：交易对 → 数据类型 → 默认。

    可选的 `slippage_curve`（P4-1）是「名义额 → 总成本」的查表曲线，**优先于
    标量**：给了 `notional` 且有曲线时返回曲线插值，否则走标量查表（零漂移）。
    曲线是总成本口径（费率 + 滑点），标定时用 `fee_bps` 把费率并进去，否则替换
    标量费率会丢掉手续费。

    ponytail: v1 一条全局曲线（不按交易对拆分）；拆分时把 curve 塞进
    `by_symbol` 同构映射即可，不必新建类。
    """

    default: float = RL_TRANSACTION_COST
    by_symbol: dict[str, float] = field(default_factory=dict)
    by_candle_type: dict[str, float] = field(default_factory=dict)
    #: 量分档成本曲线；None = 纯标量口径（现行为）
    slippage_curve: SlippageCurve | None = None

    def __post_init__(self) -> None:
        for rate in (self.default, *self.by_symbol.values(), *self.by_candle_type.values()):
            if not np.isfinite(rate) or rate < 0:
                msg = f"cost_profile 费率必须是有限非负数: {rate}"
                raise ValueError(msg)
        if self.slippage_curve is not None and not isinstance(self.slippage_curve, SlippageCurve):
            msg = f"slippage_curve 必须是 SlippageCurve: {type(self.slippage_curve).__name__}"
            raise ValueError(msg)

    def _scalar_rate(self, *, symbol: str | None = None, candle_type: str | None = None) -> float:
        """标量查表：交易对 → 数据类型 → 默认。"""
        if symbol:
            rate = self.by_symbol.get(symbol)
            if rate is None:
                rate = self.by_symbol.get(symbol.upper())
            if rate is not None:
                return float(rate)
        if candle_type:
            rate = self.by_candle_type.get(candle_type)
            if rate is not None:
                return float(rate)
        return float(self.default)

    def rate_for(
        self,
        *,
        symbol: str | None = None,
        candle_type: str | None = None,
        notional: float | None = None,
    ) -> float:
        """按优先级取费率（小数口径）。

        `notional` 给了且配了曲线 → 曲线插值（曲线优先，标量覆盖被忽略）；
        `notional` 缺省或没配曲线 → 标量查表（与 P2 完全一致）。
        """
        if notional is not None and self.slippage_curve is not None:
            return self.slippage_curve.cost_rate(float(notional))
        return self._scalar_rate(symbol=symbol, candle_type=candle_type)

    def kernel_rate(self, *, symbol: str | None = None, candle_type: str | None = None) -> float:
        """内核 / 训练环境只吃标量 `fee_rate`，曲线场景取首档代表值。

        近似语义：等于假设每笔名义额都不超过首档（`curve.notionals[0]`）。实际
        大单更贵，标量口径会低估成本；曲线只在 `rate_for(notional=...)` 的
        调用点（有名义额的地方）才是精确的。这是 v1 的已知天花板，不是 L2 撮合。
        """
        if self.slippage_curve is not None:
            return self.slippage_curve.representative_rate()
        return self._scalar_rate(symbol=symbol, candle_type=candle_type)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> CostProfile:
        """从 JSON 友好的 dict 构造：
        `{"default": x, "by_symbol": {...}, "by_candle_type": {...}, "slippage_curve": {"tiers": [...]}}`。
        """
        unknown = set(raw) - {"default", "by_symbol", "by_candle_type", "slippage_curve"}
        if unknown:
            msg = f"未知 cost_profile 字段: {sorted(unknown)}"
            raise ValueError(msg)
        curve_raw = raw.get("slippage_curve")
        if curve_raw is not None and not isinstance(curve_raw, SlippageCurve):
            curve_raw = SlippageCurve.from_mapping(curve_raw)
        return cls(
            default=float(raw.get("default", RL_TRANSACTION_COST)),
            by_symbol={str(k): float(v) for k, v in (raw.get("by_symbol") or {}).items()},
            by_candle_type={str(k): float(v) for k, v in (raw.get("by_candle_type") or {}).items()},
            slippage_curve=curve_raw,
        )

    def to_mapping(self) -> dict[str, Any]:
        """序列化（meta 回写 / API 回显）；无曲线时不落 `slippage_curve` 键。"""
        raw: dict[str, Any] = {
            "default": float(self.default),
            "by_symbol": dict(self.by_symbol),
            "by_candle_type": dict(self.by_candle_type),
        }
        if self.slippage_curve is not None:
            raw["slippage_curve"] = self.slippage_curve.to_mapping()
        return raw


class RLDeployError(Exception):
    """部署 spec 生成失败。

    `status` 是建议的 HTTP 状态码（service 层不 import fastapi，路由按此透传）：
    404 产物缺失 / 409 状态冲突 / 422 产物与运行时口径不兼容。
    """

    def __init__(self, message: str, *, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def rl_meta_path(model_path: str) -> Path:
    """模型观测规格元数据旁车文件路径（训练时写入，启动时校验口径）。"""
    return Path(f"{model_path}.meta.json")


def export_observation_stats(env: Any) -> list[dict[str, Any]] | None:
    """从训练环境导出观测归一化统计量（写进模型旁车用）。

    `TradingEnv.observation_stats()` 返回 JSON 字符串（`"null"` 表示没有归一化
    状态）。这里直接落成 JSON 数组，读侧不用再 parse 一遍字符串。

    取不到统计量时返回 `None` 并告警，交给 meta 写成 `null`：埋一个假的空统计量
    比明说「没有」更危险。
    """
    getter = getattr(env, "observation_stats", None)
    if getter is None:
        logger.warning("[RLService] 训练环境没有 observation_stats()，模型元数据将不含归一化统计量")
        return None
    raw = getter()
    stats = json.loads(raw) if isinstance(raw, str) else raw
    if not stats:
        logger.warning("[RLService] 训练环境未产生归一化统计量，模型元数据 observation_stats 记为 null")
        return None
    # 条目全为 count=0 说明训练期从未预热（统计量信息量等于空），
    # 落成 null 比存一串假的 0 更有辨识度
    if all(not entry.get("count") for entry in stats):
        logger.warning("[RLService] 观测统计量全未预热（count=0），模型元数据 observation_stats 记为 null")
        return None
    return stats


def observation_stats_from_meta(meta: dict[str, Any], *, model_path: str) -> list[dict[str, Any]] | None:
    """从模型旁车元数据取观测归一化统计量。

    缺字段返回 `None` 并告警：内核侧统计量全空会让 Z-Score 恒为 0，特征分布与
    训练时不一致，不能静默当成「等价口径」。
    """
    stats = meta.get("observation_stats")
    if not stats:
        logger.warning(
            f"[RLService] {rl_meta_path(model_path)} 缺少 observation_stats，内核侧 Z-Score 恒为 0，与训练分布不一致"
        )
        return None
    return stats


def load_observation_stats(model_path: str) -> list[dict[str, Any]] | None:
    """读模型旁车里的观测归一化统计量（回测 / 推理侧灌回内核用）。"""
    meta_file = rl_meta_path(model_path)
    if not meta_file.is_file():
        logger.warning(f"[RLService] RL 模型缺少观测规格元数据，内核统计量全空: {meta_file}")
        return None
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    return observation_stats_from_meta(meta, model_path=model_path)


def load_rl_meta(model_path: str) -> dict[str, Any]:
    """读模型旁车元数据；文件缺失或损坏时返回空 dict（旧模型照常可用）。"""
    meta_file = rl_meta_path(model_path)
    if not meta_file.is_file():
        return {}
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"[RLService] 模型元数据不可读，按缺省口径处理: {meta_file} ({exc})")
        return {}
    return meta if isinstance(meta, dict) else {}


def transaction_cost_from_meta(
    meta: dict[str, Any] | None,
    default: float = RL_TRANSACTION_COST,
    *,
    notional: float | None = None,
) -> float:
    """取模型训练时实际使用的费率；旧 meta 无该字段时回落 `default`（零漂移）。

    `notional` 给了且 meta 的 `cost_profile` 带曲线时，按该笔名义额取曲线插值
    （曲线优先于标量）；否则一律读 meta 记录的训练标量费率。旧 meta 没有
    `cost_profile` 键，走标量分支，数值与 P2 完全一致。
    """
    if not meta:
        return default
    if notional is not None:
        raw_profile = meta.get("cost_profile")
        if isinstance(raw_profile, dict):
            try:
                profile = CostProfile.from_mapping(raw_profile)
            except ValueError as exc:
                logger.warning(f"[RLService] meta 里的 cost_profile 非法，按标量费率处理: {exc}")
            else:
                if profile.slippage_curve is not None:
                    return profile.rate_for(notional=float(notional))
    rate = meta.get("transaction_cost")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not np.isfinite(rate) or rate < 0:
        return default
    return float(rate)


def compute_obs_stats(frame: pd.DataFrame, channels: tuple[str, ...] = OBS_CHANNELS) -> list[dict[str, float]]:
    """按训练窗计算逐通道 mean / std（ddof=0），作为 obs 归一化统计量。

    统计量随模型落盘（meta 的 `obs_stats`），推理侧必须复用同一份 —— 用推理
    数据重算等于特征分布漂移。数据缺失列/非有限值时直接报错，不静默产出
    错误归一化。
    """
    missing = [ch for ch in channels if ch not in frame.columns]
    if missing:
        msg = f"obs 通道缺少列: {missing}，可用列: {sorted(frame.columns)}"
        raise ValueError(msg)
    stats: list[dict[str, float]] = []
    for channel in channels:
        values = np.asarray(frame[channel], dtype=np.float64)
        if values.size == 0:
            msg = f"obs 通道 {channel} 为空，无法计算统计量"
            raise ValueError(msg)
        if not np.isfinite(values).all():
            msg = f"obs 通道 {channel} 含非有限值（NaN/inf），请先清洗数据"
            raise ValueError(msg)
        std = float(values.std())
        stats.append({"mean": float(values.mean()), "std": std if std > OBS_STD_EPS else 0.0})
    return stats


def select_obs_channels(frame: pd.DataFrame, extra_channels: list[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """按通道清单从 bar 形状的 DataFrame 抽列，返回 (通道矩阵, 通道名顺序)。

    基座 = `OBS_CHANNELS`（OHLCV）；追加通道取自 `OBS_EXTRA_CHANNELS` 的实际
    适配器列。缺列/未知通道显式报错（不做静默降维）：列缺失通常意味着
    data_type 不对（如 kline 数据选了 `spread`）或适配器未产该特征。

    列名按小写匹配：适配器产出 `Open/High/...`，`load_klines` 也是大写，
    而通道名是小写。
    """
    import pandas as pd  # 仅 TYPE_CHECKING 导入，运行期需要真正的构造器

    extras = list(extra_channels or [])
    unknown = [name for name in extras if name not in OBS_EXTRA_CHANNELS]
    if unknown:
        msg = f"未知 obs_extra_channels: {unknown}（可选: {sorted(OBS_EXTRA_CHANNELS)}）"
        raise ValueError(msg)
    lookup = {str(col).lower(): col for col in frame.columns}
    names = list(OBS_CHANNELS) + extras
    selected: dict[str, Any] = {}
    for name in names:
        if name in OBS_CHANNELS:
            column = name
            note = "OHLCV"
        else:
            column = OBS_EXTRA_CHANNELS[name]["column"]
            note = OBS_EXTRA_CHANNELS[name]["note"]
        actual = lookup.get(column)
        if actual is None:
            msg = (
                f"obs 通道 {name} 需要列 {column}（{note}），当前数据缺该列；"
                f"请用对应 data_type 加载或从 obs_extra_channels 移除它。可用列: {sorted(frame.columns)}"
            )
            raise ValueError(msg)
        selected[name] = frame[actual]
    return pd.DataFrame(selected), names


def obs_spec_from_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """解析模型 meta 里的 obs 规格；缺键 = 旧模型 → 指标向量口径（零漂移）。

    返回 `{mode, window, features, stats, extra_channels}`。`ohlcv_window` 模式
    要求 `obs_window / obs_features / obs_stats` 三者齐备且统计量长度与特征
    一致，否则显式报错 —— 静默按默认统计量归一化比直接失败更危险。
    `extra_channels` 是 features 里超出基座 OHLCV 的部分（回测重建用）。
    """
    meta = meta or {}
    mode = str(meta.get("obs_mode") or OBS_MODE_FEATURES)
    if mode not in OBS_MODES:
        msg = f"未知 obs_mode: {mode}（可选: {list(OBS_MODES)}）"
        raise ValueError(msg)
    if mode == OBS_MODE_FEATURES:
        return {
            "mode": mode,
            "window": 1,
            "features": [feature["name"] for feature in KERNEL_FEATURES],
            "stats": None,
            "extra_channels": [],
        }

    window = meta.get("obs_window")
    features = meta.get("obs_features")
    stats = meta.get("obs_stats")
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        msg = f"obs_mode=ohlcv_window 的 obs_window 非法: {window!r}"
        raise ValueError(msg)
    if not isinstance(features, list) or not features:
        msg = f"obs_mode=ohlcv_window 缺少 obs_features: {features!r}"
        raise ValueError(msg)
    if not isinstance(stats, list) or len(stats) != len(features):
        msg = (
            "obs_mode=ohlcv_window 的 obs_stats 缺失或与 obs_features 长度不匹配："
            f"stats={None if not isinstance(stats, list) else len(stats)}, features={len(features)}"
        )
        raise ValueError(msg)
    for entry in stats:
        if not isinstance(entry, dict):
            msg = f"obs_stats 条目必须是 {{mean, std}}: {entry!r}"
            raise ValueError(msg)
        mean, std = entry.get("mean"), entry.get("std")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (mean, std)):
            msg = f"obs_stats 条目必须含数值 mean/std: {entry!r}"
            raise ValueError(msg)
        if not np.isfinite(mean) or not np.isfinite(std) or std < 0:
            msg = f"obs_stats 数值非法: {entry!r}"
            raise ValueError(msg)
    return {
        "mode": mode,
        "window": int(window),
        "features": [str(name) for name in features],
        "stats": [{"mean": float(entry["mean"]), "std": float(entry["std"])} for entry in stats],
        # 超出基座 OHLCV 的派生通道（回测按它重建同一 obs 编码）
        "extra_channels": [str(name) for name in features if str(name) not in OBS_CHANNELS],
    }


def require_kernel_obs(meta: dict[str, Any] | None) -> dict[str, Any]:
    """内核推理路径（paper/live/kernel 回测）只支持指标向量 obs。

    `ohlcv_window` 模型的 obs 由 Python 侧编码，内核 host 只会喂 close/volume
    特征 —— 继续跑等于拿错维度静默推理，因此显式拒绝。升级路径：内核侧
    接 obs 编码器（P3 后续）后放开此处。
    """
    spec = obs_spec_from_meta(meta)
    if spec["mode"] != OBS_MODE_FEATURES:
        msg = (
            f"模型 obs_mode={spec['mode']} 暂不支持内核推理（paper/live/kernel 回测）；"
            "内核 host 只提供指标向量 obs，请用 engine='trading_env' 评估或等待内核侧 obs 编码接入"
        )
        raise ValueError(msg)
    return spec


def attribute_engine_diff(*, trading_env: dict[str, Any], kernel: dict[str, Any]) -> dict[str, Any]:
    """把两口径的收益差异拆成 成本 / 资金费 / 动作 / 撮合 四类。

    前提：两次运行使用同一动作序列（确定性策略）。**成本类比较的是费率口径
    （`fees / turnover`），不是绝对手续费**：两边成交笔数不同（内核逐 bar 重平衡、
    `TradingEnv` 有最小成交阈值）时绝对手续费必然不同，那属于「撮合」差异，
    不是成本模型不一致。费率不同才是 bug。

    输入是两次运行的汇总，两边同形、缺省为 0：

    - `total_pnl`：净收益，已扣成本、已加资金费；
    - `fees`：累计交易成本（正数 = 支出）；
    - `turnover`：成交名义总额（Σ|price×qty|），`cost` 用它把手续费折算成费率；
      缺失或为 0 时该侧费率记 0；
    - `funding`：累计资金费净额（正数 = 收入）；`TradingEnv` 不建模资金费，恒为 0；
    - `action_diff`：可选，由调用方单独测得的「目标仓位语义」收益贡献。

    口径：`net = gross - fees + funding`，因此

        total_diff = -fees_diff + funding + action_diff + 残差

    残差（`matching.residual`）来自撮合层：成交价、部分成交、保证金约束、重平衡
    阈值等。**不假装能把残差再拆细** —— 要细分就得逐笔成交对齐，那不在本函数的
    口径内；宁可把「说不清的部分」整体挂在 `matching` 上。

    Args:
        trading_env: `TradingEnv` 口径的汇总。
        kernel: 统一内核口径的汇总。

    Returns:
        `cost` / `funding` / `action` / `matching` / `total_pnl` 五类归因；
        两侧费率不一致时额外带 `error`。
    """
    env_pnl = float(trading_env.get("total_pnl", 0.0))
    kernel_pnl = float(kernel.get("total_pnl", 0.0))
    env_fees = float(trading_env.get("fees", 0.0))
    kernel_fees = float(kernel.get("fees", 0.0))

    # 费率 = 手续费 / 成交名义。turnover 缺失或为 0 时没有可比较的费率，记 0
    env_turnover = float(trading_env.get("turnover") or 0.0)
    kernel_turnover = float(kernel.get("turnover") or 0.0)
    env_rate = env_fees / env_turnover if env_turnover > 0.0 else 0.0
    kernel_rate = kernel_fees / kernel_turnover if kernel_turnover > 0.0 else 0.0
    rate_diff = kernel_rate - env_rate
    # 费率是浮点除法，按 1e-12 绝对容差判等（0.0001 量级的相对误差 ~1e-8 以内）
    rate_ok = abs(rate_diff) <= 1e-12

    # 残差口径不变：仍用绝对手续费把两边 net 拉回 gross
    fees_diff = kernel_fees - env_fees
    funding = float(kernel.get("funding", 0.0))
    action_diff = float(kernel.get("action_diff", 0.0)) - float(trading_env.get("action_diff", 0.0))
    total_diff = kernel_pnl - env_pnl
    # net = gross - fees + funding ⇒ 残差 = 总差 + 手续费差 - 资金费 - 动作差
    residual = total_diff + fees_diff - funding - action_diff

    report: dict[str, Any] = {
        "cost": {
            "trading_env_rate": env_rate,
            "kernel_rate": kernel_rate,
            "diff": rate_diff,
            "ok": rate_ok,
        },
        "funding": {"kernel": funding},
        "action": {"diff": action_diff},
        "matching": {"residual": residual},
        "total_pnl": {"trading_env": env_pnl, "kernel": kernel_pnl, "diff": total_diff},
    }
    if not rate_ok:
        report["error"] = "成本模型不一致"
    return report


def make_predict_fn(model: Any):
    """把 SB3 模型包装成内核 RL host 需要的 `obs -> target_ratio` 回调。

    训练时用的是 `GymnasiumWrapper` 的 `Box(0, 1)` 动作空间（只做多），
    因此这里把模型输出裁剪到 `[0, 1]`；内核侧动作空间仍是 `[-1, 1]`，正值直接透传。
    """

    def predict(obs: list[float]) -> float:
        action, _ = model.predict(np.asarray(obs, dtype=np.float32), deterministic=True)
        return float(np.clip(np.asarray(action, dtype=np.float64).reshape(-1)[0], 0.0, 1.0))

    return predict


@dataclass
class RLTrainConfig:
    """RL training configuration."""

    algorithm: str = "ppo"
    data: pd.DataFrame | None = None
    symbol: str = ""
    interval: str = "1h"
    candle_type: str = "spot"
    start: str | None = None
    end: str | None = None
    features: list[str] = field(default_factory=lambda: ["close"])
    reward_type: str = "pnl"
    total_timesteps: int = 10_000
    model_name: str = "rl_model"
    walk_forward: bool = False
    wf_splits: int = 5
    #: 复合 reward 权重覆盖；None = 现行 pnl 单 term（零漂移）。
    #: 只写要覆盖的 term，未列出的沿用 `DEFAULT_REWARD_TERMS`。
    reward_terms: dict[str, float] | None = None
    #: 成本 profile（`CostProfile` 或 JSON dict）；None = `RL_TRANSACTION_COST`。
    cost_profile: CostProfile | dict[str, Any] | None = None
    #: obs 编码模式：`features` = 原生指标向量（默认，旧模型口径）；
    #: `ohlcv_window` = 原始 OHLCV 归一化窗口（P3 opt-in）。
    obs_mode: str = OBS_MODE_FEATURES
    #: `ohlcv_window` 模式的窗口长度（bar 数）；`features` 模式忽略。
    obs_window: int = OBS_WINDOW_DEFAULT
    #: 额外派生微结构通道（opt-in，None = 只吃基座 OHLCV，零漂移）。
    #: 取值见 `OBS_EXTRA_CHANNELS`，需要数据里有对应适配器列（如 bookTicker 的 spread）。
    obs_extra_channels: list[str] | None = None
    #: 数据适配器类型（`kline` 走 `load_klines`，其余走 data_adapters，如 aggTrades/bookDepth）。
    data_type: str = "kline"

    def __post_init__(self) -> None:
        if self.obs_mode not in OBS_MODES:
            msg = f"未知 obs_mode: {self.obs_mode}（可选: {list(OBS_MODES)}）"
            raise ValueError(msg)
        if int(self.obs_window) < 1:
            msg = f"obs_window 必须 >= 1: {self.obs_window}"
            raise ValueError(msg)
        if self.obs_extra_channels:
            unknown = sorted(set(self.obs_extra_channels) - set(OBS_EXTRA_CHANNELS))
            if unknown:
                msg = f"未知 obs_extra_channels: {unknown}（可选: {sorted(OBS_EXTRA_CHANNELS)}）"
                raise ValueError(msg)
            if len(set(self.obs_extra_channels)) != len(self.obs_extra_channels):
                msg = f"obs_extra_channels 存在重复项: {self.obs_extra_channels}"
                raise ValueError(msg)
            if self.obs_mode != OBS_MODE_OHLCV_WINDOW:
                msg = "obs_extra_channels 只在 obs_mode=ohlcv_window 下生效，请同时开启窗口模式"
                raise ValueError(msg)
        if self.reward_terms is not None:
            unknown = set(self.reward_terms) - set(REWARD_TERM_KEYS)
            if unknown:
                msg = f"未知 reward term: {sorted(unknown)}（可选: {list(REWARD_TERM_KEYS)}）"
                raise ValueError(msg)
            weights = {term: float(self.reward_terms[term]) for term in REWARD_TERM_KEYS if term in self.reward_terms}
            if not all(np.isfinite(w) for w in weights.values()):
                msg = f"reward_terms 权重必须是有限数: {self.reward_terms}"
                raise ValueError(msg)
            self.reward_terms = weights
        if self.cost_profile is not None and not isinstance(self.cost_profile, CostProfile):
            self.cost_profile = CostProfile.from_mapping(self.cost_profile)

    def effective_reward_terms(self) -> dict[str, float]:
        """实际生效的 term 权重（缺省 = 现行 pnl 单 term）。"""
        return {**DEFAULT_REWARD_TERMS, **(self.reward_terms or {})}


@dataclass
class RLTrainResult:
    """RL training result."""

    model_id: str | None = None
    model_path: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    walk_forward: dict[str, Any] | None = None


def _make_env_config(
    initial_capital: float = 100_000.0,
    max_steps: int = 500,
    seed: int = 42,
    symbol: str = "BTCUSDT",
    transaction_cost: float = RL_TRANSACTION_COST,
) -> dict[str, Any]:
    """Create default environment config."""
    return {
        "initial_capital": initial_capital,
        "transaction_cost": transaction_cost,
        "slippage": RL_SLIPPAGE,
        "max_steps": max_steps,
        "seed": seed,
        "symbol": symbol,
        "return_window": 50,
    }


try:
    import gymnasium as gym

    class GymnasiumWrapper(gym.Env):
        """Wrap axon_quant TradingEnv to be Gymnasium-compatible for SB3."""

        def __init__(self, env, max_steps: int = 0, n_features: int | None = None):
            super().__init__()
            self._env = env
            self._done = False
            self._current_step = 0
            if max_steps > 0:
                self._max_steps = max_steps
            elif hasattr(env, "info") and isinstance(env.info, dict):
                self._max_steps = 999_999_999
            else:
                self._max_steps = 50000

            # 动态确定 observation_space 维度：
            # 1) 调用方显式指定 → 直接采用
            # 2) 否则探测一次 env.reset() 拿到首帧 obs 推断维度
            if n_features is not None and n_features > 0:
                inferred = n_features
            else:
                probe_obs = self._probe_obs(env)
                inferred = self._infer_n_features(probe_obs)
            self.observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=(inferred,), dtype=np.float32)
            self.action_space = gym.spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)

        @staticmethod
        def _probe_obs(env):
            """探测性地调用一次 env.reset() 推断 obs 维度，复位后再 reset 一次保证初始状态干净。"""
            try:
                probe = env.reset()
            except Exception:
                # 探测失败时用占位单维 obs，避免构造阶段崩溃
                return np.zeros(1, dtype=np.float32)
            # 复位 env 到探测前的状态
            with contextlib.suppress(Exception):
                env.reset()
            return probe

        @staticmethod
        def _infer_n_features(obs) -> int:
            """从 obs 推断特征维度：dict 走 'features' 键，其他走 len()。"""
            if isinstance(obs, dict) and "features" in obs:
                features = obs["features"]
                return len(features) if features is not None and len(features) > 0 else 1
            if hasattr(obs, "__len__"):
                length = len(obs)
                return length if length > 0 else 1
            return 1

        @staticmethod
        def _coerce_obs(obs, observation_space) -> np.ndarray:
            """统一 obs 转换：dict 取 'features'，array-like 直接转 ndarray，并按 space 形状校验。"""
            if isinstance(obs, dict) and "features" in obs:
                arr = np.asarray(obs["features"], dtype=np.float32)
            else:
                arr = np.asarray(obs, dtype=np.float32)
            expected = observation_space.shape[0]
            if arr.shape[0] != expected:
                # 维度不匹配时截断或零填充到正确形状，避免 SB3 训练时抛 shape 错误
                flat = arr.flatten()
                if flat.size >= expected:
                    arr = flat[:expected]
                else:
                    padded = np.zeros(expected, dtype=np.float32)
                    padded[: flat.size] = flat
                    arr = padded
            return arr

        def reset(self, seed=None, options=None):
            """Reset environment."""
            obs = self._env.reset()
            self._done = False
            self._current_step = 0
            info = self._env.info if hasattr(self._env, "info") and isinstance(self._env.info, dict) else {}
            obs_arr = self._coerce_obs(obs, self.observation_space)
            return obs_arr, info

        def step(self, action):
            """Take a step in the environment."""
            if isinstance(action, np.ndarray):
                action = action.tolist()
            # axon_quant TradingEnv only accepts positive actions (buy quantity)
            action = [max(0.0, min(1.0, a)) for a in action]

            result = self._env.step(action)
            self._current_step += 1

            if isinstance(result, tuple) and len(result) >= 4:
                obs = result[0]
                reward = result[1]
                done = result[2]
                if len(result) >= 5:
                    info = result[4] if isinstance(result[4], dict) else {}
                else:
                    info = result[3] if isinstance(result[3], dict) else {}
            else:
                obs = result
                reward = 0.0
                done = False
                info = {}

            obs = self._coerce_obs(obs, self.observation_space)
            truncated = self._current_step >= self._max_steps
            self._done = done or truncated

            return obs, float(reward), done, truncated, info or {}

        def close(self):
            """Close environment."""
            pass

except ImportError:
    GymnasiumWrapper = None


class RewardShapingEnv:
    """多 term 加权 reward 环境包装（只在显式配置 `reward_terms` 时启用）。

    原生 `TradingEnv` 的 reward 是 pnl/sharpe/sortino 三选一，表达不了
    「pnl - λ·回撤 - μ·换手」这类目标。这层把观测/成交原样透传给原生 env，
    只按 `info` 的权益曲线重算 reward：

    - `pnl`：本步权益变动（净，已扣手续费/滑点）
    - `sharpe`：最近 `window` 步权益收益率的滚动 Sharpe（样本不足记 0）
    - `downside`：`min(pnl, 0)`，只罚亏损步
    - `turnover`：本步成交名义额 = 手续费增量 / 费率
    - `mdd`：当前回撤 `(peak - equity) / peak`

    term 量纲不同（pnl 是货币、mdd 是比例），权重由调用方标定。
    ponytail: 只读 `info` 公开字段，不复制原生撮合逻辑；原生 env 若日后
    直接支持 term 权重，这层整体删除。
    """

    def __init__(
        self, env: Any, weights: dict[str, float], *, cost_rate: float = RL_TRANSACTION_COST, window: int = 50
    ):
        self._env = env
        self._weights = {term: float(weights.get(term, 0.0)) for term in REWARD_TERM_KEYS}
        self._cost_rate = float(cost_rate)
        self._window = max(2, int(window))
        self._reset_state()

    def _reset_state(self) -> None:
        self._equity: float | None = None
        self._peak = 0.0
        self._fees = 0.0
        self._returns: list[float] = []

    @property
    def info(self) -> dict[str, Any]:
        info = getattr(self._env, "info", {})
        return info if isinstance(info, dict) else {}

    @property
    def portfolio_value(self) -> float:
        return float(getattr(self._env, "portfolio_value", 0.0))

    def observation_stats(self) -> str:
        getter = getattr(self._env, "observation_stats", None)
        return getter() if getter is not None else "null"

    def reset(self, *args, **kwargs) -> Any:
        self._reset_state()
        obs = self._env.reset(*args, **kwargs)
        info = self.info
        equity = info.get("portfolio_value")
        if equity is not None:
            self._equity = float(equity)
            self._peak = self._equity
        self._fees = float(info.get("transaction_costs") or 0.0)
        return obs

    def step(self, action: Any) -> Any:
        result = self._env.step(action)
        obs, raw_reward, terminated, truncated = result[0], result[1], result[2], result[3]
        info = result[4] if len(result) > 4 else {}
        reward = self._shape_reward(raw_reward, info)
        return obs, reward, terminated, truncated, info

    def close(self) -> None:
        closer = getattr(self._env, "close", None)
        if closer is not None:
            closer()

    def _shape_reward(self, raw_reward: Any, info: Any) -> float:
        info = info if isinstance(info, dict) else {}
        equity_raw = info.get("portfolio_value")
        if equity_raw is None or self._equity is None:
            # 没有权益曲线就没有拆 term 的依据，退回原生 reward（不臆造指标）
            return float(raw_reward)

        equity = float(equity_raw)
        prev_equity = self._equity
        pnl = equity - prev_equity
        self._equity = equity
        self._peak = max(self._peak, equity)

        fees = float(info.get("transaction_costs") or 0.0)
        turnover = (fees - self._fees) / self._cost_rate if self._cost_rate > 0 else 0.0
        self._fees = fees

        if prev_equity > 0:
            self._returns.append(pnl / prev_equity)
            del self._returns[: max(0, len(self._returns) - self._window)]

        terms = {
            "pnl": pnl,
            "sharpe": self._rolling_sharpe(),
            "downside": min(pnl, 0.0),
            "turnover": turnover,
            "mdd": (self._peak - equity) / self._peak if self._peak > 0 else 0.0,
        }
        # term 明细随 info 出参，便于训练后诊断（不影响 SB3）
        info["reward_terms"] = terms
        return float(sum(self._weights[term] * value for term, value in terms.items()))

    def _rolling_sharpe(self) -> float:
        """滚动窗口内权益收益率的 Sharpe（mean/std × √n）；样本不足或零波动记 0。"""
        if len(self._returns) < 2:
            return 0.0
        returns = np.asarray(self._returns, dtype=np.float64)
        std = float(returns.std())
        if std <= 0.0:
            return 0.0
        return float(returns.mean() / std * np.sqrt(returns.size))


class ObsWindowEnv:
    """把原生 env 的指标 obs 换成归一化滚动窗口（P3 opt-in，不碰撮合）。

    原生 `TradingEnv` 的 obs 固定为 close Z-Score + volume（窗口 1，不可配）。
    这层按训练数据重建观测：第 t 步取最近 `window` 根 bar 的通道矩阵，
    用 `stats`（训练窗逐通道 mean/std）z-score 后摊平，obs 维度 =
    `window × 通道数`（默认 64×5=320）。

    通道 = 基座 `OBS_CHANNELS`（OHLCV）+ `extra_channels`（`OBS_EXTRA_CHANNELS`
    注册的派生微结构通道，如 bookTicker 的 `spread`）；缺列显式报错。

    归一化统计量必须来自训练窗并冻结进 meta：推理侧传入的 `stats` 与训练
    不一致等于特征分布漂移。这层不做兜底猜测，缺/不匹配由
    `obs_spec_from_meta` 显式拒绝。

    `stats=None` 时按 `frame` 现算（训练窗），因此 WF 折内务必显式传入
    首折训练窗统计量，别让验证窗重算造成特征泄漏。

    ponytail: v1 只做逐通道 z-score（无 log/差分/多尺度）；升级路径是
    encoder 抽象 + 可配置变换，`obs_spec_from_meta` 的 meta 契约可原样承载。
    """

    def __init__(
        self,
        env: Any,
        frame: pd.DataFrame,
        *,
        window: int = OBS_WINDOW_DEFAULT,
        stats: list[dict[str, float]] | None = None,
        extra_channels: list[str] | None = None,
    ) -> None:
        self._env = env
        self._window = int(window)
        if self._window < 1:
            msg = f"obs_window 必须 >= 1: {window}"
            raise ValueError(msg)
        channel_frame, self._channels = select_obs_channels(frame, extra_channels)
        self._frames = np.asarray(channel_frame, dtype=np.float64)
        if self._frames.shape[0] == 0:
            msg = "obs_mode=ohlcv_window 需要非空行情数据"
            raise ValueError(msg)
        self._stats = list(stats) if stats is not None else compute_obs_stats(channel_frame, tuple(self._channels))
        if len(self._stats) != len(self._channels):
            msg = f"obs_stats 长度 {len(self._stats)} 与通道数 {len(self._channels)} 不匹配"
            raise ValueError(msg)
        stds = np.asarray([entry["std"] for entry in self._stats], dtype=np.float64)
        # std≈0（常量通道）→ 除以 1，归一化结果恒为 0，避免 0/0 造 NaN 或残差放大
        self._std = np.where(stds > OBS_STD_EPS, stds, 1.0)
        self._mean = np.asarray([entry["mean"] for entry in self._stats], dtype=np.float64)
        self._idx = 0

    @property
    def info(self) -> dict[str, Any]:
        info = getattr(self._env, "info", {})
        return info if isinstance(info, dict) else {}

    @property
    def portfolio_value(self) -> float:
        return float(getattr(self._env, "portfolio_value", 0.0))

    def observation_stats(self) -> str:
        getter = getattr(self._env, "observation_stats", None)
        return getter() if getter is not None else "null"

    def obs_encoder_meta(self) -> dict[str, Any]:
        """训练落盘用：模式 / 窗口 / 通道清单 / 冻结统计量。"""
        return {
            "obs_mode": OBS_MODE_OHLCV_WINDOW,
            "obs_window": self._window,
            "obs_features": list(self._channels),
            "obs_stats": self._stats,
        }

    def reset(self, *args, **kwargs) -> Any:
        self._env.reset(*args, **kwargs)
        self._idx = 0
        return self._obs(self._idx)

    def step(self, action: Any) -> Any:
        _obs, reward, terminated, truncated, info = self._env.step(action)
        self._idx = min(self._idx + 1, self._frames.shape[0] - 1)
        return self._obs(self._idx), reward, terminated, truncated, info

    def close(self) -> None:
        closer = getattr(self._env, "close", None)
        if closer is not None:
            closer()

    def _obs(self, idx: int) -> np.ndarray:
        start = idx - self._window + 1
        if start < 0:
            # 序列头部不足一个窗口：用首根 bar 补齐（保持窗口形状恒定）
            pad = np.repeat(self._frames[:1], -start, axis=0)
            window_frames = np.vstack([pad, self._frames[: idx + 1]])
        else:
            window_frames = self._frames[start : idx + 1]
        return ((window_frames - self._mean) / self._std).reshape(-1).astype(np.float32)


class RLService:
    """RL training pipeline service."""

    def __init__(self):
        self._hpo = HPORunner()
        self._wf = WalkForwardService()
        self._models_dir = MODELS_DIR
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_data(self, config: RLTrainConfig) -> pd.DataFrame:
        """Load data from config.data or BacktestDataProvider.

        `data_type != "kline"` 走 data_adapters（aggTrades/trades/bookDepth/bookTicker
        等），产出 bar 形状 + 该类型的派生特征列；适配器的 `market` 由
        `candle_type` 推导（spot→spot，其余→um 本位永续）。
        """
        if config.data is not None:
            return config.data
        if config.symbol:
            from backtest.data_provider import BacktestDataProvider

            provider = BacktestDataProvider()
            if config.data_type and config.data_type != "kline":
                market = "spot" if config.candle_type == "spot" else "um"
                return provider.load_data(
                    config.symbol,
                    config.interval,
                    data_type=config.data_type,
                    market=market,
                    start=config.start,
                    end=config.end,
                ).data
            return provider.load_klines(
                config.symbol,
                config.interval,
                config.candle_type,
                config.start,
                config.end,
            )
        msg = "需要 config.data 或 config.symbol"
        raise ValueError(msg)

    def create_env(
        self,
        data: pd.DataFrame,
        features: list[str] | None = None,
        reward_type: str = "pnl",
        initial_capital: float = 100_000.0,
        transaction_cost: float = RL_TRANSACTION_COST,
        obs_mode: str = OBS_MODE_FEATURES,
        obs_window: int = OBS_WINDOW_DEFAULT,
        obs_stats: list[dict[str, float]] | None = None,
        obs_extra_channels: list[str] | None = None,
    ) -> Any:
        """Create an RL training environment.

        `obs_mode=ohlcv_window` 时在原生 env 外套 `ObsWindowEnv`（原始 OHLCV
        归一化窗口，可追加 `OBS_EXTRA_CHANNELS` 派生微结构通道）；缺省
        `features` 原样返回原生 env（零漂移）。

        Requires axon_quant. Raises RuntimeError if not available.
        """
        # 走适配层检查可用性,避免业务代码直连 axon_quant
        from axon_bridge import rl as _rl_bridge

        if not hasattr(_rl_bridge, "TradingEnv"):
            msg = "axon_quant.rl.TradingEnv 不可用，请安装 axon_quant: pip install axon_quant"
            raise RuntimeError(msg)

        df = data.copy()
        df.columns = [c.lower() for c in df.columns]
        if "timestamp" not in df.columns:
            df["timestamp"] = range(len(df))

        market_data = df.to_dict("records")
        config = _make_env_config(initial_capital=initial_capital, max_steps=len(df), transaction_cost=transaction_cost)
        env = _rl_bridge.TradingEnv(config=config, market_data=market_data, reward=reward_type)
        if obs_mode == OBS_MODE_OHLCV_WINDOW:
            return ObsWindowEnv(env, df, window=obs_window, stats=obs_stats, extra_channels=obs_extra_channels)
        return env

    @staticmethod
    def _cost_rate(config: RLTrainConfig) -> float:
        """训练实际使用的费率：有 profile 按 symbol/candle_type 查表，否则沿用常量。

        曲线场景的近似语义：训练环境（`TradingEnv`）与内核都只接受标量费率，
        没有逐笔名义额可查，因此取曲线**首档代表值**（`CostProfile.kernel_rate`），
        相当于假设每笔成交名义额都不超过首档。真实大单更贵 —— 这个偏差是 v1
        的已知天花板（不做 L2 撮合/逐档吃单），不在训练回路里假装精确。
        """
        profile = config.cost_profile
        if not isinstance(profile, CostProfile):
            return RL_TRANSACTION_COST
        return profile.kernel_rate(symbol=config.symbol, candle_type=config.candle_type)

    @staticmethod
    def _obs_stats(frame: pd.DataFrame, extra_channels: list[str] | None) -> list[dict[str, float]]:
        """训练窗逐通道统计量（基座 OHLCV + 派生微结构通道）。"""
        channel_frame, names = select_obs_channels(frame, extra_channels)
        return compute_obs_stats(channel_frame, tuple(names))

    def _build_train_env(
        self,
        data: pd.DataFrame,
        config: RLTrainConfig,
        *,
        cost_rate: float,
        obs_stats: list[dict[str, float]] | None = None,
    ) -> Any:
        """训练环境：obs 变换层按 config 装配，reward 组合层只在显式配置时套。

        不配置新模式/新 reward 时逐字节等价于改造前（原生 env 直出）。
        """
        env = self.create_env(
            data,
            config.features,
            config.reward_type,
            transaction_cost=cost_rate,
            obs_mode=config.obs_mode,
            obs_window=config.obs_window,
            obs_stats=obs_stats,
            obs_extra_channels=config.obs_extra_channels,
        )
        if config.reward_terms is None:
            return env
        return RewardShapingEnv(env, config.effective_reward_terms(), cost_rate=cost_rate)

    def train(self, config: RLTrainConfig, reporter: Any = None) -> RLTrainResult:
        """Execute RL training with stable-baselines3 and save model.

        When config.walk_forward=True, runs Walk-Forward validation first,
        then trains final model on full data with OOS evaluation.

        Args:
            reporter: 可选任务上报器（`status` 协议见 `services.rl_task_runner`）。
                缺省 `NullReporter`，同步 `/train`（ModelHub）行为不变。

        progress 语义（对前端单一数值）：walk-forward 占前 50%，最终训练
        50%→95%，保存 95%→100%；stage 取 `loading_data` / `wf_fold_i` /
        `wf_eval` / `learning` / `saving` 五个取值。
        """
        reporter = reporter if reporter is not None else NullReporter()
        reporter.state(stage="loading_data", progress=0.0, message="加载行情数据")
        data = self._load_data(config)
        cost_rate = self._cost_rate(config)
        # 原始序列模式的归一化统计量来自训练窗；WF 折内冻结首折训练窗（避免
        # 用验证窗重算 = 特征泄漏），最终模型用全量训练数据重算
        final_obs_stats = (
            self._obs_stats(data, config.obs_extra_channels) if config.obs_mode == OBS_MODE_OHLCV_WINDOW else None
        )
        reporter.check_cancel()

        logger.info(
            f"[RLService] 开始训练: algorithm={config.algorithm}, timesteps={config.total_timesteps}, reward={config.reward_type}"
        )
        reporter.log(
            f"开始训练: algorithm={config.algorithm}, timesteps={config.total_timesteps}, reward={config.reward_type}"
        )
        start_time = time.time()

        wf_share = 0.5 if config.walk_forward else 0.0
        wf_result = None
        if config.walk_forward:
            from rl.walk_forward_rl import RLWalkForwardService

            wf_svc = RLWalkForwardService()
            wf_obs_stats: dict[str, list[dict[str, float]]] = {}

            def env_factory(d: pd.DataFrame):
                stats = None
                if config.obs_mode == OBS_MODE_OHLCV_WINDOW:
                    # 首折训练窗统计量冻结后复用：验证窗不重算，杜绝特征泄漏
                    if "stats" not in wf_obs_stats:
                        wf_obs_stats["stats"] = self._obs_stats(d, config.obs_extra_channels)
                    stats = wf_obs_stats["stats"]
                env = self._build_train_env(d, config, cost_rate=cost_rate, obs_stats=stats)
                return GymnasiumWrapper(env)

            try:
                from stable_baselines3 import DQN, PPO, SAC
            except ImportError:
                msg = "缺少RL训练依赖，请安装: pip install stable-baselines3 gymnasium torch"
                raise RuntimeError(msg)

            algo_map = {"ppo": PPO, "sac": SAC, "dqn": DQN}
            algo_cls = algo_map.get(config.algorithm)
            if algo_cls is None:
                msg = f"Unknown algorithm: {config.algorithm}"
                raise ValueError(msg)

            wf_result = wf_svc.validate(
                data=data,
                env_factory=env_factory,
                algo_cls=algo_cls,
                n_splits=config.wf_splits,
                total_timesteps=config.total_timesteps,
                reporter=ScaledReporter(reporter, base=0.0, span=wf_share),
            )

        reporter.check_cancel()
        reporter.state(stage="learning", progress=wf_share, message="构建训练环境")
        env = self._build_train_env(data, config, cost_rate=cost_rate, obs_stats=final_obs_stats)

        try:
            from stable_baselines3 import DQN, PPO, SAC
        except ImportError:
            msg = "缺少RL训练依赖，请安装: pip install stable-baselines3 gymnasium torch"
            raise RuntimeError(msg)

        algo_map = {"ppo": PPO, "sac": SAC, "dqn": DQN}
        algo_cls = algo_map.get(config.algorithm)
        if algo_cls is None:
            msg = f"Unknown algorithm: {config.algorithm}"
            raise ValueError(msg)

        logger.info(f"[RLService] 使用 {algo_cls.__name__} 训练...")
        reporter.log(f"使用 {algo_cls.__name__} 训练 {config.total_timesteps} steps")

        wrapped_env = GymnasiumWrapper(env)
        model = algo_cls("MlpPolicy", wrapped_env, verbose=0)
        # 分块 learn：块间检查取消，块内 BaseCallback 逐 step 报进度
        learn_in_chunks(
            model,
            config.total_timesteps,
            ScaledReporter(reporter, base=wf_share, span=0.95 - wf_share),
            stage="learning",
        )

        reporter.check_cancel()
        reporter.state(stage="saving", progress=0.95, message="保存模型与观测规格")
        # 统计量必须在训练循环跑完后再取：每次 step 都会在线更新 RunningStats
        observation_stats = export_observation_stats(env)

        model_id = f"{config.model_name}_{config.algorithm}_{int(time.time())}"
        model_path = str(MODELS_DIR / f"{model_id}.zip")
        model.save(model_path)

        # elapsed 计算前移到 meta 写入之前:elapsed_seconds 要随训练上下文落盘
        elapsed = time.time() - start_time

        # 观测规格元数据:RL 策略启动时据此校验 spec_version / 窗口 / 特征是否
        # 与本机内核口径一致,避免拿旧口径模型去跑新内核;
        # algorithm/total_timesteps/elapsed_seconds/reward_type/created_at/
        # walk_forward 是模型卡的训练上下文,注册表 seed 时并入 metadata
        rl_meta_path(model_path).write_text(
            json.dumps(
                {
                    "model_id": model_id,
                    "spec_version": KERNEL_SPEC_VERSION,
                    "window_size": KERNEL_WINDOW_SIZE,
                    "features": KERNEL_FEATURES,
                    # 训练期归一化统计量:内核路径据此还原 Z-Score 分布,
                    # 取不到时写 null(不伪造空统计量)
                    "observation_stats": observation_stats,
                    "algorithm": config.algorithm,
                    "total_timesteps": config.total_timesteps,
                    "elapsed_seconds": round(elapsed, 2),
                    "reward_type": config.reward_type,
                    # 实际生效的 term 权重（缺省 = pnl 单 term）；OOS 明细归 `walk_forward`
                    "reward_terms": config.effective_reward_terms(),
                    # 训练实际费率，供回测/归因与训练同源（旧 meta 无此字段时回落常量）
                    "transaction_cost": cost_rate,
                    # 成本 profile 原样落盘（含 slippage_curve）：回测侧据此按名义额
                    # 查曲线；旧 meta 无此键 = 纯标量口径
                    **(
                        {"cost_profile": config.cost_profile.to_mapping()}
                        if isinstance(config.cost_profile, CostProfile)
                        else {}
                    ),
                    # obs 编码口径（模型卡摘要依据）：缺键 = 旧模型的指标向量口径；
                    # ohlcv_window 的统计量必须随模型冻结，推理侧不许重算
                    "obs_mode": config.obs_mode,
                    "obs_window": config.obs_window if config.obs_mode == OBS_MODE_OHLCV_WINDOW else 1,
                    "obs_features": (
                        list(OBS_CHANNELS) + list(config.obs_extra_channels or [])
                        if config.obs_mode == OBS_MODE_OHLCV_WINDOW
                        else [feature["name"] for feature in KERNEL_FEATURES]
                    ),
                    "obs_stats": final_obs_stats,
                    # 训练取数口径：回测按它取同一份数据源（旧 meta 无此键 → kline）
                    "data_type": config.data_type,
                    # ISO 8601 毫秒精度(项目时间戳规范)
                    "created_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                    # walk-forward 完整结果(OOS 折明细 + 汇总);seed 并入注册表时只取 aggregate
                    "walk_forward": wf_result,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        logger.info(f"[RLService] 模型已保存: {model_path}")
        reporter.log(f"模型已保存: {model_path}")

        wrapped_env.close()

        logger.info(f"[RLService] 训练完成: elapsed={elapsed:.1f}s")
        reporter.log(f"训练完成: elapsed={elapsed:.1f}s")
        reporter.state(progress=1.0, message="训练完成")

        return RLTrainResult(
            model_id=model_id,
            model_path=model_path,
            metrics={
                "steps": config.total_timesteps,
                "algorithm": config.algorithm,
                "elapsed_seconds": round(elapsed, 2),
                "model_path": model_path,
            },
            walk_forward=wf_result,
        )

    def load_model(self, model_path: str) -> Any:
        """Load a trained model from path."""
        try:
            from stable_baselines3 import DQN, PPO, SAC

            if "ppo" in model_path.lower():
                return PPO.load(model_path)
            elif "sac" in model_path.lower():
                return SAC.load(model_path)
            elif "dqn" in model_path.lower():
                return DQN.load(model_path)
            else:
                return PPO.load(model_path)
        except Exception as e:
            logger.error(f"[RLService] 加载模型失败: {e}")
            return None

    def list_saved_models(self) -> list[dict[str, Any]]:
        """List all saved models in the models directory."""
        models = []
        if MODELS_DIR.exists():
            for f in MODELS_DIR.glob("*.zip"):
                models.append(
                    {
                        "name": f.stem,
                        "path": str(f),
                        "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                        "created": f.stat().st_ctime,
                    }
                )
        return models

    def resolve_saved_model_path(self, model_id: str) -> Path:
        """将模型 ID（文件 stem）安全解析为 MODELS_DIR 下的 .zip 路径。

        白名单字符集杜绝路径分隔符；`.`/`..` 虽过正则但无业务意义，显式排除；
        resolve 后再校验父目录双保险，防止 Windows 保留名 / 软链接等绕过正则。
        """
        if model_id in {".", ".."} or not re.fullmatch(r"[\w.\-]+", model_id or ""):
            raise ValueError(f"非法的模型 ID: {model_id!r}")
        target = (MODELS_DIR / f"{model_id}.zip").resolve()
        if target.parent != MODELS_DIR.resolve():
            raise ValueError(f"非法的模型路径: {model_id!r}")
        return target

    def delete_saved_model(self, model_id: str) -> None:
        """删除指定模型文件（文件即模型存在的唯一事实）。

        ponytail: Rust registry（model_registry）无 delete API，注册条目删除后
        会成为孤立记录；列表展示一律以 MODELS_DIR 下 .zip 文件为准，孤立条目
        无副作用。若未来 Rust 侧补 delete，再在此同步调用。

        部署侧连带关系：本方法**不回收** `build_deploy_spec` 生成的 `rl_paper_*`
        策略行（孤儿行无副作用——RL 启动时会因模型文件缺失直接报错，策略列表以
        文件为事实源）。级联删除留待策略库有「RL 行」语义后再做。
        """
        target = self.resolve_saved_model_path(model_id)
        if not target.is_file():
            raise FileNotFoundError(f"模型不存在: {model_id}")
        target.unlink()
        # 观测规格旁车文件一并清理，避免残留陈旧 meta
        with contextlib.suppress(FileNotFoundError):
            rl_meta_path(str(target)).unlink()
        logger.info(f"[RLService] 模型已删除: {model_id}")

    def build_deploy_spec(self, model_path: str, *, symbol: str | None = None) -> dict[str, Any]:
        """把训练产物登记成可部署的 RL 策略行，返回可直接 POST /workers 的 payload。

        为什么要 upsert 策略行：worker 创建只认 `strategy_id`，而 RL 启动要求该行
        `strategy_type='rl'` 且 `parameters` 是 **JSON object**（含 model_path，
        见 `worker/strategy_manager.py::_load_rl_spec`）。策略库唯一的写入口
        `/strategy/upload` 写的是数组形态的 schema 描述、且不落 strategy_type，
        不能用于 RL —— 所以部署必须先在这里物化一行。

        校验全部在写库前完成（不落半截数据）：模型文件 → meta 旁车 → spec_version。
        `file_name` / `file_path` 留空：RL 分支直接注册模型到内核 RL host，不走
        StrategyLoaderService（不加载源码）。

        Args:
            model_path: 训练产物 .zip 路径（任务快照的 `model_path`）。
            symbol: 部署 worker 的交易对（训练产物不记录标的，缺省留空由前端填）。

        Returns:
            `{"strategy": {id,name,strategy_type,parameters}, "worker": {...}}`。

        Raises:
            RLDeployError: 产物缺失（404）/ spec_version 不匹配（422）/ 同名非 RL
                策略冲突（409）；HTTP 状态码由路由按 `exc.status` 透传。
        """
        raw_path = str(model_path or "").strip()
        if not raw_path:
            raise RLDeployError("缺少 model_path", status=404)
        path = Path(raw_path)
        if not path.is_file():
            raise RLDeployError(f"模型文件不存在: {raw_path}", status=404)

        meta_file = rl_meta_path(raw_path)
        if not meta_file.is_file():
            raise RLDeployError(f"模型缺少观测规格元数据（训练产物不完整或已被清理）: {meta_file}", status=404)
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RLDeployError(f"模型元数据不可读: {meta_file} ({exc})", status=422) from exc
        spec_version = str(meta.get("spec_version") or "")
        if spec_version != KERNEL_SPEC_VERSION:
            raise RLDeployError(
                f"模型 spec_version 不匹配: 模型={spec_version or '缺失'} 期望={KERNEL_SPEC_VERSION}", status=422
            )

        model_id = path.stem
        strategy_name = f"{DEPLOY_STRATEGY_PREFIX}{model_id}"
        # 契约里 model_path 必须能被 worker 进程直接 isfile：存绝对路径，不依赖 CWD
        deploy_params = {"model_path": str(path.resolve()), "spec_version": spec_version}

        # 函数内 import：ORM / DB 会话只在部署路径拉起，与 rl_service 其余轻量场景隔离
        from strategy.models import Strategy
        from utils.db_session import get_db_session

        with get_db_session() as db:
            row = db.query(Strategy).filter(Strategy.name == strategy_name).first()
            if row is not None and (row.strategy_type or "rule") != "rl" and (row.code or row.file_name):
                # 同名但不是我们生成的 RL 部署行：拒绝覆盖，避免把用户源码策略改成 RL
                raise RLDeployError(f"同名策略已存在且不是 RL 部署行: {strategy_name}", status=409)

            if row is not None:
                # 幂等更新：保留 id 与用户改过的其它参数键（如 initial_capital）
                effective = dict(self._deploy_params_of(row)) | deploy_params
                row.strategy_type = "rl"
                row.parameters = json.dumps(effective, ensure_ascii=False)
            else:
                effective = deploy_params
                row = Strategy(
                    name=strategy_name,
                    description=f"RL 模型 {model_id}（训练产物部署行，由训练任务自动登记）",
                    strategy_type="rl",
                    parameters=json.dumps(effective, ensure_ascii=False),
                    tags=json.dumps(["rl", "deploy"], ensure_ascii=False),
                    # RL 不加载源码：file_name/file_path/code 留空（两列均 nullable）
                    version="1.0.0",
                )
                db.add(row)
            db.commit()
            db.refresh(row)
            strategy_id = row.id
            strategy_name = row.name

        symbol_norm = str(symbol or "").strip().upper()
        initial_capital = float(effective.get("initial_capital") or 100_000.0)
        worker_body = {
            "name": f"rl-{model_id}",
            "description": f"RL model {model_id} (paper)",
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "strategy_file_name": None,
            # RL paper v1 边界（strategy_manager.start_rl_paper）：binance + 永续 + 这些周期
            "trading_config": {
                "exchange": "binance",
                "symbols_config": {"type": "symbols", "symbols": [symbol_norm] if symbol_norm else []},
                "interval": "1h",
                "market_type": "futures",
                "trading_mode": "paper",
            },
            "config": {"initial_capital": initial_capital},
        }
        logger.info(f"[RLService] 部署 spec 已生成: strategy_id={strategy_id}, name={strategy_name}, model={model_id}")
        return {
            "strategy": {
                "id": strategy_id,
                "name": strategy_name,
                "strategy_type": "rl",
                "parameters": effective,
            },
            "worker": worker_body,
        }

    @staticmethod
    def _deploy_params_of(row: Any) -> dict[str, Any]:
        """读已有部署行的 parameters（仅 object 形态有效；数组/垃圾值当作空）。"""
        if not row.parameters:
            return {}
        try:
            raw = json.loads(row.parameters)
        except json.JSONDecodeError, TypeError:
            return {}
        return raw if isinstance(raw, dict) else {}

    def optimize_hyperparameters(
        self,
        objective_fn: Any,
        param_space: dict[str, Any],
        n_trials: int = 10,
    ) -> dict[str, Any]:
        """Execute hyperparameter optimization."""
        return self._hpo.optimize(objective_fn, param_space, n_trials)

    def walk_forward_validate(
        self,
        data: pd.DataFrame,
        n_splits: int = 5,
        mode: str = "rolling",
    ) -> dict[str, Any]:
        """Execute Walk-Forward validation."""
        return self._wf.validate(strategy_fn=None, data=data, n_splits=n_splits, mode=mode)

    def run_backtest(
        self,
        model_path: str,
        symbol: str,
        interval: str = "1h",
        candle_type: str = "spot",
        initial_capital: float = 100_000.0,
        reward_type: str = "pnl",
        engine: str = "trading_env",
        ensemble_id: str | None = None,
    ) -> dict[str, Any]:
        """用已训练模型回测，返回评估指标。

        Args:
            engine: 评估口径。
                - `"trading_env"`（默认）：SB3 + `axon_quant TradingEnv` 逐 step 评估；
                - `"kernel"`：统一内核 `worker.Kernel` + RL host，撮合与实盘同一主回路。
            ensemble_id: 非空时按模型集成加载成员（Python 侧聚合），仅 engine="kernel"
                有效，此时 `model_path` 忽略。
            响应体固定带 `engine` 字段，调用方据此区分两条口径。

        Uses TradingEnv as the simulation engine and the SB3 model for inference.
        Returns evaluation metrics (PnL, Sharpe, drawdown, etc.).
        """
        # backtest.data_provider 顶层 import pandas 栈；保持调用点导入，
        # rl_service 被轻量场景引用时（测试收集 / CLI）不为此拉起数据链路
        from backtest.data_provider import BacktestDataProvider

        if engine not in ("trading_env", "kernel"):
            msg = f"未知 engine: {engine}（可选 'trading_env' / 'kernel'）"
            raise ValueError(msg)

        if ensemble_id and engine != "kernel":
            msg = "ensemble_id 仅支持 kernel 引擎回测(trading_env 口径按单模型加载)"
            raise ValueError(msg)

        provider = BacktestDataProvider()
        meta = load_rl_meta(model_path)
        data_type = str(meta.get("data_type") or "kline")
        if data_type != "kline":
            # 与训练同源取数：适配器训练（aggTrades/bookTicker 等）的 obs 通道
            # 来自这些数据，回测拿 kline 会缺列（旧 meta 无 data_type → kline）
            data = provider.load_data(
                symbol,
                interval,
                data_type=data_type,
                market="spot" if candle_type == "spot" else "um",
            ).data
        else:
            data = provider.load_klines(symbol, interval, candle_type)
        if data.empty:
            msg = f"无法加载 {symbol} {interval} 数据"
            raise ValueError(msg)

        if engine == "kernel":
            return self._run_kernel_backtest(
                model_path, data, symbol, interval, initial_capital, ensemble_id=ensemble_id
            )

        # 不能提升到模块顶部：rl/__init__ 反向 import 本模块（GymnasiumWrapper 等），
        # rl_service 模块期 import rl.* 会撞上半初始化的 rl 包成环
        from rl.evaluation import evaluate_model

        cost_rate = transaction_cost_from_meta(meta)
        obs = obs_spec_from_meta(meta)
        env = self.create_env(
            data,
            reward_type=reward_type,
            initial_capital=initial_capital,
            transaction_cost=cost_rate,
            obs_mode=obs["mode"],
            obs_window=obs["window"],
            obs_stats=obs["stats"],
            obs_extra_channels=obs["extra_channels"],
        )
        wrapped_env = GymnasiumWrapper(env)

        model = self.load_model(model_path)
        if model is None:
            msg = f"无法加载模型: {model_path}"
            raise RuntimeError(msg)

        metrics = evaluate_model(model, wrapped_env, transaction_cost=cost_rate)
        wrapped_env.close()

        return {
            "symbol": symbol,
            "interval": interval,
            "data_bars": len(data),
            "initial_capital": initial_capital,
            "total_pnl": metrics.total_pnl,
            "total_return_pct": metrics.total_return_pct,
            "sharpe_ratio": metrics.sharpe_ratio,
            "max_drawdown_pct": metrics.max_drawdown_pct,
            "win_rate": metrics.win_rate,
            "num_trades": metrics.num_trades,
            "profit_factor": metrics.profit_factor,
            # 成交名义总额：`attribute_engine_diff` 用它把手续费折算成费率口径
            "turnover": metrics.turnover,
            "engine": "trading_env",
        }

    def _run_kernel_backtest(
        self,
        model_path: str,
        data: pd.DataFrame,
        symbol: str,
        interval: str,
        initial_capital: float,
        ensemble_id: str | None = None,
    ) -> dict[str, Any]:
        """统一内核路径：backend 编排（模型 IO / 数据清洗 / symbol 归一化）→ 执行设施。

        执行段（worker.Kernel 装配 + 15 字段结果拼装）已下沉
        `axon_quant.rl.kernel_backtest::run_kernel_backtest`（2026-11-11），
        与 `trading_env` 口径的差别只在编排层：成交、资金费、保证金与统计
        全部由 Rust 内核完成（与实盘同一条主回路）。`ensemble_id` 非空时走
        集成员聚合，不再加载单模型。
        """
        from backtest.backtest_loop import clean_ohlcv_df
        from backtest.engine_service import EventDrivenBacktestService
        from vocab import expand_symbol

        if ensemble_id:
            # 集成:成员 ratio predict_fn 组合,spec 以基准成员 meta 为准(spec §4.4)
            # 函数内 import:ensemble_service 顶层依赖本模块(rl_service),顶部 import 会成环
            from services.ensemble_service import load_ensemble_spec

            member_specs = load_ensemble_spec(ensemble_id, spec_version=KERNEL_SPEC_VERSION)
            predict_fn = make_ensemble_predict_fn(member_specs.member_predict_fns)
            model_id = ensemble_id
            window_size = int(member_specs.meta.get("window_size") or KERNEL_WINDOW_SIZE)
            features = member_specs.meta.get("features") or KERNEL_FEATURES
            stats = observation_stats_from_meta(member_specs.meta, model_path=member_specs.representative_path)
            cost_rate = transaction_cost_from_meta(member_specs.meta)
            meta = member_specs.meta
            # 内核 host 只喂指标向量 obs：原始序列模型在这里显式拒绝，不静默错维推理
            require_kernel_obs(meta)
        else:
            meta = load_rl_meta(model_path)
            cost_rate = transaction_cost_from_meta(meta)
            require_kernel_obs(meta)
            model = self.load_model(model_path)
            if model is None:
                msg = f"无法加载模型: {model_path}"
                raise RuntimeError(msg)
            predict_fn = make_predict_fn(model)
            model_id = Path(model_path).stem
            window_size = KERNEL_WINDOW_SIZE
            features = KERNEL_FEATURES
            stats = load_observation_stats(model_path)

        # 内核按 BASE/QUOTE 建 instrument；直接用交易所原始 symbol 会退化成默认品种
        rust_symbol = expand_symbol(symbol)
        bars = EventDrivenBacktestService._df_to_rust_bars(clean_ohlcv_df(data))

        # 费率与训练环境同源：取模型 meta 记录的训练费率（旧 meta 回落 `RL_TRANSACTION_COST`），
        # 否则训练用了自定义 cost profile 时归因会误报「成本模型不一致」。
        # 曲线场景：内核只吃标量 `fee_rate`，meta 的 transaction_cost 已是曲线首档
        # 代表值（见 `RLService._cost_rate`），训练/回测口径一致；真实大单成本更高，
        # 该口径会低估 —— v1 已知近似，不承诺 L2 撮合。
        result = run_kernel_backtest(
            bars,
            predict_fn,
            rust_symbol,
            interval,
            {
                "spec_version": KERNEL_SPEC_VERSION,
                "window_size": window_size,
                "features": features,
                "action_space": KERNEL_ACTION_SPACE,
            },
            initial_capital=initial_capital,
            fee_rate=cost_rate,
            stats=stats,
            model_id=model_id,
        )
        # 设施回显内核 symbol 与 len(bars)；对外契约沿用原始 symbol 与清洗前行数
        result["symbol"] = symbol
        result["data_bars"] = len(data)
        return result

    def run_backtest_task(
        self,
        model_id: str,
        symbol: str,
        interval: str = "1h",
        candle_type: str = "spot",
        initial_capital: float = 100_000.0,
        ensemble_id: str | None = None,
    ) -> dict[str, Any]:
        """RL 模型回测任务化：跑统一内核 → 结果落盘 → 复用策略回测列表/详情链路。

        与 `run_backtest`（同步自查、结果不落盘）的分工：本方法面向前端任务流，
        结果按策略回测同一份契约写入 backtest_service 的结果/任务目录，
        列表页按 strategy_name 前缀 `rl_model:`（集成 `rl_ensemble:`）识别来源，
        详情页 / 回放页零感知复用。引擎口径固定 kernel（与实盘同一条主回路）。

        ponytail: 同步执行——RL kernel 回测为秒级；若未来模型/数据规模放大到
        分钟级，升级路径是线程 + progress_tracker 轮询（与策略 /backtest/run 同模式）。
        """
        from backtest.backtest_loop import BacktestLoop, clean_ohlcv_df
        from backtest.engine_service import EventDrivenBacktestService
        from backtest.result_formatter_service import ResultFormatterService
        from backtest.service import BacktestService

        model_path = self.resolve_saved_model_path(model_id)
        if ensemble_id:
            strategy_name = f"rl_ensemble:{ensemble_id}"
        else:
            strategy_name = f"rl_model:{model_id}"

        # 函数内 import 同 run_backtest：pandas 数据链路按需拉起，轻量场景（测试收集）不受累
        from backtest.data_provider import BacktestDataProvider

        data = BacktestDataProvider().load_klines(symbol, interval, candle_type)
        if data.empty:
            msg = f"无法加载 {symbol} {interval} 数据"
            raise ValueError(msg)

        kernel_result = self._run_kernel_backtest(
            str(model_path), data, symbol, interval, initial_capital, ensemble_id=ensemble_id
        )

        # 引擎逐 bar 产物适配策略回测格式化契约（ms 时间戳 / 前端 Trade 契约 / kline records）
        nav_curve = kernel_result["bar_nav_curve"]
        equity_curve = EventDrivenBacktestService.nav_curves_to_equity(nav_curve, kernel_result["bar_balance_curve"])
        trade_records = BacktestLoop._format_round_trip_trades(
            kernel_result["trades"], symbol, kernel_result["fills_detail"]
        )
        # RL 目标仓位策略持仓可长期不归零，round-trip trades 天然稀疏甚至为空
        # （同名指标 total_trades 数的是 fills，配对口径数的是 round-trip）。
        # 逐笔成交是恒有的事实粒度，转成前端展示契约透传，详情页在 trades
        # 为空时用兜底展示；时间口径与 _format_round_trip_trades 一致（UTC 秒）。
        fill_rows = [
            {
                "fill_id": int(f.get("fill_id", 0)),
                "timestamp": int(f.get("timestamp_ns", 0)) // 1_000_000_000,
                "formatted_time": datetime.fromtimestamp(int(f.get("timestamp_ns", 0)) / 1e9, tz=UTC).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "side": str(f.get("taker_side", "Buy")).lower(),
                "price": float(f.get("price", 0.0)),
                "quantity": float(f.get("quantity", 0.0)),
            }
            for f in (kernel_result["fills_detail"] or [])
        ]
        cleaned = clean_ohlcv_df(data)
        adapted = {
            "initial_capital": kernel_result["initial_capital"],
            "final_nav": nav_curve[-1][1] if nav_curve else initial_capital,
            "total_pnl": kernel_result["total_pnl"],
            "trade_count": len(trade_records),
            "fills": kernel_result["num_trades"],
            "max_drawdown_pct": kernel_result["max_drawdown_pct"],
            # kernel 设施的 win_rate 为 0~1 小数；格式化器口径是百分数
            "win_rate": kernel_result["win_rate"] * 100.0,
            "sharpe_ratio": kernel_result["sharpe_ratio"],
            "total_fees": kernel_result["total_fees"],
            "nav_peak": max((nav for _, nav in nav_curve), default=initial_capital),
            "trades": trade_records,
            "fills_detail": fill_rows,
            "equity_curve": equity_curve,
            "klines": EventDrivenBacktestService._klines_to_records(cleaned),
            # 清洗后时间戳在 DatetimeIndex（clean_ohlcv_df 口径），统一转 ns 整数
            "data_start_ns": int(cleaned.index.as_unit("ns").asi8[0]) if len(cleaned) else 0,
            "data_end_ns": int(cleaned.index.as_unit("ns").asi8[-1]) if len(cleaned) else 0,
        }
        formatted = ResultFormatterService.format_axon_results(adapted, symbol, interval, strategy_name)

        # 落盘契约与策略回测 service.run_backtest 的顶层结构对齐（列表/详情共用读取口）
        result = {
            "status": "completed",
            "message": "RL 模型回测完成",
            "successful_currencies": [symbol],
            "failed_currencies": [],
            "results": formatted,
        }

        backtest_service = BacktestService()
        task_id = backtest_service.create_task(
            strategy_name=strategy_name,
            strategy_params={
                "model_id": model_id,
                "ensemble_id": ensemble_id,
                "interval": interval,
                "candle_type": candle_type,
                "engine": "kernel",
                "spec_version": KERNEL_SPEC_VERSION,
            },
            symbols=[symbol],
            timeframes=[interval],
            engine_type="axon",
            config={
                "symbols": [symbol],
                "interval": interval,
                "market": "spot" if candle_type == "spot" else "um",
                "initial_capital": initial_capital,
                "engine_type": "axon",
                "data_type": "kline",
                "trading_mode": "spot" if candle_type == "spot" else "futures",
            },
        )
        backtest_service.complete_task(task_id, result)

        return {
            "task_id": task_id,
            "strategy_name": strategy_name,
            "symbol": symbol,
            "interval": interval,
            "total_pnl": kernel_result["total_pnl"],
            "total_return_pct": kernel_result["total_return_pct"],
            "sharpe_ratio": kernel_result["sharpe_ratio"],
            "max_drawdown_pct": kernel_result["max_drawdown_pct"],
            "win_rate": kernel_result["win_rate"],
            "num_trades": kernel_result["num_trades"],
            "engine": "kernel",
            "data_bars": kernel_result["data_bars"],
        }
