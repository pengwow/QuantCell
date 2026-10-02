"""LLM 因子挖掘闭环：生成 pandas 代码 → 沙箱执行 → 复用 FactorService 指标 → 反思迭代。

- LLM 统一走 axon_bridge（create_llm_backend/chat_to_dict），不直连 openai SDK；
- 每轮并发生成 n_candidates 个候选，AST 静态失败不启动子进程（便宜地失败）；
- 成功候选的 fitness = |RankIC 均值| * 100 * 覆盖率惩罚（coverage<0.2 时二次惩罚），
  与 FactorMiner 默认口径对齐；
- 反思：把上一轮失败原因与最佳候选摘要拼进下一轮 prompt。
- 候选内存去重复用 factor.code_store.code_hash（规范化口径的单一真相源，
  入库 hash 去重共用同一函数；口径必须一致，改动需同步两处并回归去重用例）。
- train/test 时间切分 + 样本外复核：raw_map 按行序（时间升序）切后段做 OOS，
  两段独立沙箱执行（防 rolling warmup 泄漏）；fitness/排序只看 train，
  oos_flag 标记样本外符号反转/衰减，过拟合风险在结果行与反思中可见。
- wf_folds>=2 时改走滚动 walk-forward：OOS 区间等分 k 个连续窗口，因子在各
  递增历史前缀上独立执行（1+k 次沙箱），按折 bar_count 加权 IC/符号一致性汇总。
- 相关性去重：全部轮次完成后，成功候选按 fitness 降序贪心比较 train 段因子
  （各品种内部 pct-rank 后求 pearson，即尺度无关的 spearman 秩相关），
  |corr|>=dedup_corr 的低 fitness 候选标记 redundant 且不进 best；只用
  train 段，去重是选择动作，禁止用 OOS。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from axon_bridge.llm import chat_to_dict
from factor.code_store import code_hash
from factor.engine import _timestamps_to_datetime, load_raw_ohlcv
from factor.sandbox import (
    SandboxError,
    SandboxOutputError,
    SandboxResourceError,
    SandboxSecurityError,
    SandboxTimeoutError,
)
from factor.service import FactorError, FactorService
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

ProgressCb = Callable[[float, str, str], None]

_FENCE_RE = re.compile(r"```(?:[a-zA-Z]*)?\s*(.*?)```", re.DOTALL)

SYSTEM_PROMPT = """你是顶级加密量化研究员，任务是发明有预测力的 Alpha 因子。

输入数据：变量 df 是 pandas.DataFrame，按时间升序排列，列包括：
- open/high/low/close：开高低收价格
- volume：成交量；quote_volume：成交额；vwap=quote_volume/volume（成交均价）；amount=volume*close

输出契约：
- 只输出 Python 代码，不要任何解释文字；最终结果必须赋值给 factor（与 df 等长、逐行对齐的 pandas.Series）
- 环境只注入了 pandas as pd、numpy as np；禁止 import、文件、网络、递归、列表推导、逐行循环，全部用向量化写法
- 前若干行允许产生 NaN（warmup），但不允许整列 NaN 或 inf

优秀示例：
factor = (df["close"] - df["vwap"]) / df["close"].rolling(20).std()
factor = df["volume"].pct_change() * df["close"].pct_change()
factor = (df["high"] - df["low"]) / df["close"].rolling(20).mean()

目标是预测未来 1 根 K 线收益，追求稳定的截面 RankIC；避免与「close/Ref(close,n)-1」这类裸动量雷同。"""


@dataclass
class LLMMineParams:
    symbols: list[str]
    interval: str = "1h"
    candle_type: str = "spot"
    start: str | None = None
    end: str | None = None
    n_candidates: int = 4
    n_rounds: int = 2
    top_k: int = 5
    temperature: float = 0.8
    model_id: str | None = None
    model_name: str = ""
    # 评估固定参数（挖掘场景不需要让用户调）
    method: str = field(default="spearman")
    n_groups: int = field(default=5)
    window: int = field(default=20)
    forward: int = field(default=1)
    # 样本外切分比例（取后段时间）：0=不切分；范围校验在 Pydantic schema 层
    test_ratio: float = 0.3
    # 滚动 walk-forward 折数：0=关闭（走单次 test_ratio 切分）；2-6=多窗口滚动复核
    wf_folds: int = 0
    # 候选 train 段因子相关性去重阈值：|秩相关|≥该值且 fitness 更低者标记冗余；
    # <=0 关闭；只用 train 段（去重是选择动作，禁止用 OOS 造成样本外泄漏）
    dedup_corr: float = 0.9
    # 去重选定 best 后，是否对其中 train IC 非 None 的非冗余候选自动做
    # IC 加权 zscore 合成（权重/时序统计冻结在 train；失败不阻断挖掘）
    compose: bool = True


def extract_code(text: str) -> str:
    """从 LLM 响应中抽取代码：优先取 ```python 围栏，否则整体去空白。"""
    if not text:
        return ""
    match = _FENCE_RE.search(text)
    return (match.group(1) if match else text).strip()


def _user_prompt(round_idx: int, n_rounds: int, candidate_idx: int, n_candidates: int, reflection: str) -> str:
    parts = [
        f"第 {round_idx + 1}/{n_rounds} 轮挖掘，候选编号 {candidate_idx + 1}/{n_candidates}。",
        "请给出一个与简单价量动量不同的新因子（可从波动结构、量价背离、高低价区间、成交额分布等角度切入）。",
    ]
    if reflection:
        parts.append("以下是前序轮次的反思材料，请避开已知失败、借鉴有效结构：\n" + reflection)
    return "\n".join(parts)


def _reflection_text(rows: list[dict[str, Any]], best_global: dict[str, Any] | None) -> str:
    lines = []
    failures = [r for r in rows if r["status"] != "success"][:5]
    seen_msg = set()
    for row in failures:
        msg = (row.get("error") or "")[:120]
        if msg in seen_msg:
            continue
        seen_msg.add(msg)
        lines.append(f"- 失败({row['status']}): {msg}")
    if best_global is not None:
        m = best_global["metrics"]
        lines.append(
            f"- 当前最佳因子 fitness={m['fitness']:.2f}, IC={m['ic_mean']}, "
            f"覆盖率={m['coverage']}，代码：{best_global['code'].splitlines()[-1][:100]}"
        )
        if best_global.get("oos_flag") == "sign_flip" and best_global.get("metrics_oos"):
            lines.append(
                "- 警告：当前最佳因子样本外 IC 符号反转"
                f"（train={m['ic_mean']} → oos={best_global['metrics_oos']['ic_mean']}），"
                "疑似过拟合，请优先探索方向稳定的结构"
            )
    return "\n".join(lines)


def _metrics_from_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    ic = analysis["ic"].get("mean")
    coverage = (analysis.get("inspection") or {}).get("coverage")
    # 覆盖率惩罚：coverage<20% 时按平方比例压缩 fitness（与 FactorMiner 对齐）
    penalty = (coverage / 0.20) ** 2 if coverage is not None and coverage < 0.20 else 1.0
    fitness = abs(ic) * 100.0 * penalty if ic is not None else 0.0
    return {
        "fitness": round(float(fitness), 4),
        "ic_mean": ic,
        "ic_ir": analysis["ic"].get("ir"),
        "coverage": coverage,
        "turnover": (analysis.get("inspection") or {}).get("turnover"),
        "long_short_return": analysis.get("long_short_return"),
        "monotonicity_spearman": (analysis.get("monotonicity") or {}).get("spearman"),
        "nw_t_stat": ((analysis.get("inspection") or {}).get("ic_stats") or {}).get("nw_t_stat"),
        "bar_count": analysis.get("bar_count"),
    }


def _oos_metrics(
    analysis: dict[str, Any], train_metrics: dict[str, Any], test_ratio: float
) -> tuple[dict[str, Any] | None, str | None, str | None, list[dict[str, Any]] | None]:
    """从 analyze_code_panel/analyze_composite 的结果组装样本外块。

    返回 (metrics_oos, oos_flag, oos_note, folds)：wf 路径 folds 为各折列表；
    单次路径 test 不足且 test_ratio>0 时给「未做复核」说明；test_ratio=0 全 None。
    候选行与合成因子共用同一口径，禁止两处分叉。
    """
    wf = analysis.get("wf")
    if wf is not None:
        metrics_oos = {
            # 与单次 metrics_oos 行结构对齐（wf 不产出的全指标填 None）
            "fitness": None,
            "turnover": None,
            "long_short_return": None,
            "monotonicity_spearman": None,
            "nw_t_stat": None,
            "ic_mean": wf["ic_mean"],
            "ic_std": wf["ic_std"],
            "ic_ir": wf["ic_ir"],
            "coverage": wf["coverage"],
            "bar_count": wf["bar_count"],
            "sign_consistency": wf["sign_consistency"],
            "n_folds": wf["n_folds"],
            "valid_folds": wf["valid_folds"],
            "folds": wf["folds"],
        }
        return metrics_oos, wf["oos_flag"], wf["oos_note"], wf["folds"]
    if analysis["test"]:
        metrics_oos = _metrics_from_analysis(analysis["test"])
        flag, note = oos_flag(train_metrics, metrics_oos)
        return metrics_oos, flag, note, None
    if test_ratio > 0:
        # test 段因样本不足在 service 层被吞：候选仍成功，标注未复核
        return None, None, "样本外数据不足，未做复核", None
    return None, None, None, None


def oos_flag(
    train_metrics: dict[str, Any] | None, test_metrics: dict[str, Any] | None
) -> tuple[str | None, str | None]:
    """样本外复核判定（纯函数）：基于两段 ic_mean。

    - 任一段缺失或任一 ic_mean 为 None → (None, None)；
    - 符号相反 → ('sign_flip', 提示文案)；
    - |test_ic| < 0.5*|train_ic| → ('weak', 提示文案)；
    - 否则 ('ok', '')。
    """
    if not train_metrics or not test_metrics:
        return None, None
    train_ic = train_metrics.get("ic_mean")
    test_ic = test_metrics.get("ic_mean")
    if train_ic is None or test_ic is None:
        return None, None
    if train_ic * test_ic < 0:
        return (
            "sign_flip",
            f"样本外 IC 符号反转（train={train_ic:.4f}，oos={test_ic:.4f}），疑似过拟合",
        )
    if abs(test_ic) < 0.5 * abs(train_ic):
        return (
            "weak",
            f"样本外 IC 衰减过半（train={train_ic:.4f}，oos={test_ic:.4f}），样本外减弱",
        )
    return "ok", ""


def _factor_corr(s1: pd.Series, s2: pd.Series, min_pairs: int = 30) -> float | None:
    """两个 MultiIndex(datetime,symbol) 因子面板的「各品种内部秩次一致度」。

    对齐后双侧 dropna，先在每个 symbol 组内 rank(pct=True)，再对两条百分位秩
    序列整体求 pearson 相关：组内秩变换消除跨品种量纲/尺度差异（如不同币种
    价格量级差千倍、或 x 与 100x+3 这种单调仿射变换），因此结果等价于
    spearman 口径的因子相关性。有效配对 < min_pairs（或常数列导致相关不可
    估计）时返回 None，调用方按「无法判定重复」处理。
    """
    joined = pd.concat([s1.rename("a"), s2.rename("b")], axis=1).dropna()
    if len(joined) < min_pairs:
        return None
    rank_a = joined["a"].groupby(level=1).rank(pct=True)
    rank_b = joined["b"].groupby(level=1).rank(pct=True)
    corr = rank_a.corr(rank_b, method="pearson")
    if corr is None or pd.isna(corr):
        return None
    return float(corr)


def correlation_dedup(rows: list[dict[str, Any]], threshold: float, min_pairs: int = 30) -> None:
    """成功候选按 fitness 降序做贪心相关性去重（原地更新）。

    1. 仅处理 status=='success' 行（依赖内部键 ``_factor``：train 段因子面板）；
    2. 按 metrics.fitness 降序（fitness 高者优先保留，同 fitness 保持原顺序）；
    3. 每个候选与已保留行逐个算 :func:`_factor_corr`，首次 ``|corr| >= threshold``
       命中即写 redundant=True/redundant_with=命中行 code_hash/redundant_corr 并
       停止比较；未命中则保留；配对不足（None）视为不重复；
    4. 非 success 行不触碰（默认字段由调用方预先补齐）。
    """
    success_rows = [r for r in rows if r.get("status") == "success"]
    success_rows.sort(key=lambda r: r["metrics"]["fitness"], reverse=True)
    kept: list[dict[str, Any]] = []
    for row in success_rows:
        for anchor in kept:
            corr = _factor_corr(anchor["_factor"], row["_factor"], min_pairs=min_pairs)
            if corr is not None and abs(corr) >= threshold:
                row["redundant"] = True
                row["redundant_with"] = anchor["code_hash"]
                row["redundant_corr"] = round(corr, 4)
                break
        else:
            kept.append(row)


def _classify_exc(exc: Exception) -> tuple[str, str]:
    # Sandbox 子类判断必须在前：FactorError 与 SandboxError 是两条独立异常链
    if isinstance(exc, SandboxSecurityError):
        return "security_error", str(exc)
    if isinstance(exc, SandboxOutputError):
        return "output_error", str(exc)
    if isinstance(exc, SandboxTimeoutError):
        return "timeout", str(exc)
    if isinstance(exc, SandboxResourceError):
        return "resource_error", str(exc)
    if isinstance(exc, FactorError):
        return "runtime_error", str(exc)
    if isinstance(exc, SandboxError):
        return "runtime_error", str(exc)
    return "runtime_error", f"{type(exc).__name__}: {exc}"


async def _generate_batch(backend: Any, system_prompt: str, user_prompts: list[str]) -> list[dict[str, Any]]:
    """并发请求 LLM，返回归一化响应（content + finish_reason）。

    reasoning 模型可能把全部预算花在思考链上：finish_reason='length' 且
    content 为空，调用方需与真正的空响应区分（提示加轮次而非当成无回复）。
    """

    async def one(prompt: str) -> dict[str, Any]:
        resp = await chat_to_dict(
            backend,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        return {"content": resp.get("content") or "", "finish_reason": resp.get("finish_reason")}

    return await asyncio.gather(*(one(p) for p in user_prompts))


def run_llm_mining(
    params: LLMMineParams,
    *,
    backend: Any,
    provider: Any = None,
    service: FactorService | None = None,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """同步挖掘入口（运行于 factor job 工作线程；内部 asyncio.run 驱动并发 LLM 调用）。"""
    service = service or FactorService()
    raw_map = load_raw_ohlcv(
        params.symbols,
        params.interval,
        params.candle_type,
        params.start,
        params.end,
        provider,
    )

    def report(p: float, stage: str, msg: str) -> None:
        logger.info(f"[LLM挖掘] {p:.0f}% {stage} {msg}")
        if progress:
            progress(p, stage, msg)

    candidates: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    reflection = ""
    generated_total = unique_total = 0

    # 轮间进度区间 5→95
    for round_idx in range(params.n_rounds):
        report(
            5 + round_idx / params.n_rounds * 80,
            "generating",
            f"第 {round_idx + 1}/{params.n_rounds} 轮：请求 LLM 生成 {params.n_candidates} 个候选",
        )
        prompts = [
            _user_prompt(round_idx, params.n_rounds, i, params.n_candidates, reflection)
            for i in range(params.n_candidates)
        ]
        responses = asyncio.run(_generate_batch(backend, SYSTEM_PROMPT, prompts))
        round_rows: list[dict[str, Any]] = []

        for i, resp in enumerate(responses):
            text = resp["content"]
            finish_reason = resp.get("finish_reason")
            code = extract_code(text)
            generated_total += 1
            base = {"round": round_idx + 1, "candidate": i + 1}
            if not code:
                # reasoning 模型思考链耗尽 token 预算（finish=length）与真空响应区分：
                # 前者提示用户增加轮次/候选，后者只表明本轮该次调用无产出
                if finish_reason == "length":
                    status, error_type, error = (
                        "llm_truncated",
                        "llm_truncated",
                        "LLM 思考链超过 token 预算、未产出代码（finish=length）；请增加反思轮数后重试",
                    )
                else:
                    status, error_type, error = "empty", "empty", "LLM 返回为空"
                row = {
                    **base,
                    "code": "",
                    "code_hash": "",
                    "status": status,
                    "error_type": error_type,
                    "error": error,
                    "metrics": None,
                    "metrics_oos": None,
                    "oos_flag": None,
                    "oos_note": None,
                }
                candidates.append(row)
                round_rows.append(row)
                continue

            h = code_hash(code)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            unique_total += 1

            pct = 5 + (round_idx + (i + 1) / len(responses)) / params.n_rounds * 80
            report(pct, "evaluating", f"沙箱执行 + 指标评估（候选 {i + 1}/{len(responses)}）")
            try:
                analysis = service.analyze_code_panel(
                    code,
                    raw_map,
                    interval=params.interval,
                    method=params.method,
                    n_groups=params.n_groups,
                    window=params.window,
                    forward=params.forward,
                    label=f"llm_r{round_idx + 1}_{h[:8]}",
                    test_ratio=params.test_ratio,
                    wf_folds=params.wf_folds,
                )
                metrics = _metrics_from_analysis(analysis["train"])
                metrics_oos, flag, note, _folds = _oos_metrics(analysis, metrics, params.test_ratio)
                row = {
                    **base,
                    "code": code,
                    "code_hash": h,
                    "status": "success",
                    "error_type": None,
                    "error": None,
                    "metrics": metrics,
                    "metrics_oos": metrics_oos,
                    "oos_flag": flag,
                    "oos_note": note,
                    # 内部键：train 段因子面板，仅供跨候选相关性去重，返回前必须剥离
                    "_factor": analysis["train_factor"],
                }
            except Exception as exc:  # 每个候选独立失败，不影响整轮
                status, message = _classify_exc(exc)
                logger.info(f"[LLM挖掘] 候选失败 {status}: {message[:150]}")
                row = {
                    **base,
                    "code": code,
                    "code_hash": h,
                    "status": status,
                    "error_type": status,
                    "error": message[:500],
                    "metrics": None,
                    "metrics_oos": None,
                    "oos_flag": None,
                    "oos_note": None,
                }
            candidates.append(row)
            round_rows.append(row)

        successes = [r for r in round_rows if r["status"] == "success"]
        best_global = max(
            (r for r in candidates if r["status"] == "success"),
            key=lambda r: r["metrics"]["fitness"],
            default=None,
        )
        reflection = _reflection_text(round_rows, best_global)
        report(
            5 + (round_idx + 1) / params.n_rounds * 80,
            "reflect",
            f"第 {round_idx + 1} 轮完成：成功 {len(successes)}/{len(round_rows)}",
        )

    # 所有行统一补冗余默认字段（非 success 行 correlation_dedup 不会触碰）
    for row in candidates:
        row.setdefault("redundant", False)
        row.setdefault("redundant_with", None)
        row.setdefault("redundant_corr", None)

    # 跨轮统一贪心相关性去重：只用 train 段因子，fitness 高者优先保留
    if params.dedup_corr > 0:
        correlation_dedup(candidates, params.dedup_corr)

    successful = [r for r in candidates if r["status"] == "success"]
    non_redundant = [r for r in successful if not r["redundant"]]
    redundant_count = len(successful) - len(non_redundant)
    best = sorted(non_redundant, key=lambda r: r["metrics"]["fitness"], reverse=True)[: params.top_k]

    # 自动合成（best 行仍持有 _factor train 面板，必须在剥离之前完成）
    composite = _build_composite(params, best, raw_map, service) if params.compose else None
    composed = composite is not None and "error" not in composite

    report(
        100.0,
        "completed",
        f"完成：有效候选 {len(successful)}（重复 {redundant_count}），Top {len(best)}"
        + ("，已合成" if composed else ""),
    )

    # 剥离内部键：pd.Series 不能进 JSON，train_factor 也不允许透出到 HTTP 结果
    for row in candidates:
        row.pop("_factor", None)
    for row in best:
        row.pop("_factor", None)
    assert all("_factor" not in r and "train_factor" not in r for r in candidates)
    assert all("_factor" not in r and "train_factor" not in r for r in best)

    return {
        "candidates": candidates,
        "best": best,
        "composite": composite,
        "stats": {
            "requested_per_round": params.n_candidates,
            "rounds": params.n_rounds,
            "generated": generated_total,
            "unique": unique_total,
            "succeeded": len(successful),
            "failed": len(candidates) - len(successful),
            "redundant": redundant_count,
            "composed": composed,
            "symbols": list(raw_map),
            "interval": params.interval,
            "model_name": params.model_name,
            "test_ratio": params.test_ratio,
            "wf_folds": params.wf_folds,
        },
    }


def _build_composite(
    params: LLMMineParams,
    best: list[dict[str, Any]],
    raw_map: dict[str, pd.DataFrame],
    service: FactorService,
) -> dict[str, Any] | None:
    """对去重后 best 中 train IC 非 None 的候选做 IC 加权 zscore 合成。

    - 非 None 成分 <2 或权重拟合失败（分母 0）→ None（不合成）；
    - 权重在 train 段 IC 拟合冻结，ts_stats 由各 best 行的 train 面板（_factor）
      拟合冻结；OOS 评估复用 analyze_composite（raw_map 为挖掘已加载的同一份）；
    - 合成是派生动作：任何异常都不阻断挖掘，返回 {"error": msg}（调用方记统计）；
    - 返回 dict 全部为 JSON 原生类型（无 Series/numpy，weights/ts_stats 显式转 float）。
    """
    comp_rows = [r for r in best if r.get("metrics") and r["metrics"].get("ic_mean") is not None]
    if len(comp_rows) < 2:
        return None
    codes = [r["code"] for r in comp_rows]
    ics = [r["metrics"]["ic_mean"] for r in comp_rows]
    weights = FactorService.fit_ic_weights(ics)
    if weights is None:
        return None
    ts_stats_list = [FactorService._fit_ts_stats(r["_factor"]) for r in comp_rows]

    wf_on = params.wf_folds >= 2 and params.test_ratio > 0
    n_runs = len(codes) * (1 + params.wf_folds) if wf_on else len(codes) * (2 if params.test_ratio > 0 else 1)
    logger.info(f"[LLM挖掘] 合成因子：{len(codes)} 个成分，预计沙箱执行 {n_runs} 次")
    try:
        analysis = service.analyze_composite(
            codes,
            weights,
            ts_stats_list,
            raw_map,
            interval=params.interval,
            method=params.method,
            n_groups=params.n_groups,
            window=params.window,
            forward=params.forward,
            label="llm_composite",
            test_ratio=params.test_ratio,
            wf_folds=params.wf_folds,
        )
    except Exception as exc:
        logger.warning(f"[LLM挖掘] 因子合成失败（不阻断挖掘）: {type(exc).__name__}: {exc}")
        return {"error": f"{type(exc).__name__}: {exc}"}

    train_metrics = _metrics_from_analysis(analysis["train"])
    metrics_oos, flag, note, folds = _oos_metrics(analysis, train_metrics, params.test_ratio)

    # train_window：start=train 段全局最小时间；end=OOS 切点（_wf_bounds 首折起点；
    # 单次路径也用同一切点，test_ratio=0 时即数据末端时间戳）
    train_map, _ = FactorService._split_raw_map(raw_map, params.test_ratio)
    start_ts = min(_timestamps_to_datetime(df["timestamp"]).min() for df in train_map.values())
    oos_start = FactorService._wf_bounds(raw_map, params.test_ratio, 2)[0][0]
    composite: dict[str, Any] = {
        "n": len(codes),
        "constituents": [
            {"code_hash": r["code_hash"], "weight": float(w), "ts_stats": ts_stats_list[i]}
            for i, (r, w) in enumerate(zip(comp_rows, weights, strict=True))
        ],
        "train_window": {
            "start": pd.Timestamp(start_ts).isoformat(),
            "end": pd.Timestamp(oos_start).isoformat(),
            "interval": params.interval,
            "candle_type": params.candle_type,
        },
        "metrics": train_metrics,
        "metrics_oos": metrics_oos,
        "oos_flag": flag,
        "oos_note": note,
    }
    if folds is not None:
        composite["folds"] = folds
    return composite
