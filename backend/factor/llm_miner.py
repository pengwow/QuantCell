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
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from axon_bridge.llm import chat_to_dict
from factor.code_store import code_hash
from factor.engine import load_raw_ohlcv
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
                wf = analysis.get("wf")
                if wf is not None:
                    # walk-forward：oos_flag/note 已在 service 层按多折汇总算好，直接透传
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
                    flag, note = wf["oos_flag"], wf["oos_note"]
                else:
                    metrics_oos = _metrics_from_analysis(analysis["test"]) if analysis["test"] else None
                    if metrics_oos is not None:
                        flag, note = oos_flag(metrics, metrics_oos)
                    elif params.test_ratio > 0:
                        # test 段因样本不足在 service 层被吞：候选仍成功，标注未复核
                        flag, note = None, "样本外数据不足，未做复核"
                    else:
                        flag, note = None, None
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

    successful = [r for r in candidates if r["status"] == "success"]
    best = sorted(successful, key=lambda r: r["metrics"]["fitness"], reverse=True)[: params.top_k]
    report(100.0, "completed", f"完成：有效候选 {len(successful)}，Top {len(best)}")

    return {
        "candidates": candidates,
        "best": best,
        "stats": {
            "requested_per_round": params.n_candidates,
            "rounds": params.n_rounds,
            "generated": generated_total,
            "unique": unique_total,
            "succeeded": len(successful),
            "failed": len(candidates) - len(successful),
            "symbols": list(raw_map),
            "interval": params.interval,
            "model_name": params.model_name,
            "test_ratio": params.test_ratio,
            "wf_folds": params.wf_folds,
        },
    }
