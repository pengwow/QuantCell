"""deep 闭环的 LLM 智能体（假设生成 / 实验规划 / 代码生成 / 结构化反馈）。

借鉴 RD-Agent 的三段式上下文（§7）：全量历史压缩表 + 上一轮明细 + SOTA 代码,
prompt 模板在本仓库重新编写，只借鉴结构不 vendor 其框架。
所有 LLM 输出都用 Pydantic 校验；解析失败先重试一次，仍失败则返回安全兜底，
不让单次坏输出把整个会话判死（PRD §11 #1）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from factor.llm_miner import SYSTEM_PROMPT as CODE_SYSTEM_PROMPT
from factor.llm_miner import extract_code

# (system, user) -> (content, usage)
LLMCall = Callable[[str, str], tuple[str, dict[str, Any]]]


class HypothesisOut(BaseModel):
    hypothesis: str = Field(min_length=1)
    reason: str = ""
    prediction: str = ""


class FactorTask(BaseModel):
    name: str = ""
    description: str = Field(min_length=1)
    formulation: str = ""


class PlanOut(BaseModel):
    tasks: list[FactorTask] = Field(default_factory=list)


class FeedbackOut(BaseModel):
    observations: str = ""
    evaluation: str = ""
    new_hypothesis: str = ""
    reason: str = ""


HYPOTHESIS_SYSTEM = """你是量化因子研究员。基于给定的研究历史与当前 SOTA，
提出一个新的、可验证的因子假设。要求：
- 与历史尝试不重复，优先做增量改进而不是从零发明；
- 只输出 JSON：{"hypothesis": "...", "reason": "...", "prediction": "..."}，不要其它文字。"""

PLAN_SYSTEM = """你是量化实验规划员。把因子假设拆解为 1~3 个可独立编码的因子任务。
要求：
- 每个任务给出 name、description（含公式/逻辑）、formulation（可执行表达式）；
- 只输出 JSON：{"tasks": [{"name": "...", "description": "...", "formulation": "..."}]}。"""

FEEDBACK_SYSTEM = """你是量化因子评审员。对刚完成的试验给出结构化反馈，供下一轮参考。
要求：
- 只输出 JSON：{"observations": "...", "evaluation": "...", "new_hypothesis": "...", "reason": "..."}；
- evaluation 明确说明样本内/样本外表现是否一致、可能的过拟合风险。"""


def _extract_json(text: str) -> str:
    """从可能带 ```json 围栏的输出里截取第一个 JSON 对象。"""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return ""
    return text[start : end + 1]


def usage_tokens(usage: dict[str, Any] | None) -> int:
    """token 统计：优先 total_tokens，缺失时用 prompt + completion 兜底。"""
    if not usage:
        return 0
    total = usage.get("total_tokens")
    if total is not None:
        return int(total)
    return int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)


def prompt_fingerprint(system: str, user: str) -> str:
    """prompt 指纹（16 位十六进制），用于复现实验时核对输入。"""
    return hashlib.sha256(f"{system}\n{user}".encode()).hexdigest()[:16]


def _call_json(
    llm_call: LLMCall,
    system: str,
    user: str,
    model_cls: type[BaseModel],
    fallback: BaseModel,
) -> tuple[BaseModel, dict[str, Any]]:
    """带一次重试的结构化调用；两次都失败返回兜底对象。

    usage 按真实调用次数累计（重试也计一次调用），token 用 usage 或
    prompt+completion 兜底，避免成本统计只算第一次调用。
    """
    usage_total: dict[str, Any] = {"total_tokens": 0, "llm_calls": 0}
    last_content = ""
    for attempt in range(2):
        prompt = user if attempt == 0 else f"{user}\n\n上次输出无法解析，请严格只输出 JSON。"
        content, usage = llm_call(system, prompt)
        usage_total["llm_calls"] += 1
        usage_total["total_tokens"] += usage_tokens(usage)
        last_content = content
        try:
            return model_cls.model_validate_json(_extract_json(content)), usage_total
        except Exception:
            continue
    _ = last_content
    return fallback, usage_total


def generate_hypothesis(
    llm_call: LLMCall, context: str, seed_factor: str | None
) -> tuple[HypothesisOut, dict[str, Any]]:
    """生成假设；解析失败时用确定性兜底，保证 loop 能继续。"""
    extra = f"\n\n种子因子：{seed_factor}" if seed_factor else ""
    fallback = HypothesisOut(
        hypothesis=f"在 {seed_factor} 基础上做条件化改进" if seed_factor else "探索新的量价组合因子",
        reason="LLM 输出不可解析，使用兜底假设",
    )
    return _call_json(llm_call, HYPOTHESIS_SYSTEM, context + extra, HypothesisOut, fallback)


def plan_tasks(llm_call: LLMCall, hypothesis: str, context: str) -> tuple[list[FactorTask], dict[str, Any]]:
    """规划任务；空列表/解析失败返回 []，由 loop 记 failed。"""
    user = f"{context}\n\n本轮假设：{hypothesis}\n请拆分因子任务。"
    out, usage = _call_json(llm_call, PLAN_SYSTEM, user, PlanOut, PlanOut())
    return out.tasks[:3], usage


def code_prompt(task: FactorTask) -> tuple[str, str]:
    """代码生成的 (system, user)，loop 用它算 prompt 指纹，供复现核对。"""
    user = f"任务名称：{task.name}\n任务描述：{task.description}\n公式：{task.formulation}\n请只输出 Python 代码块。"
    return CODE_SYSTEM_PROMPT, user


def generate_code(llm_call: LLMCall, task: FactorTask) -> tuple[str, dict[str, Any]]:
    """按任务生成因子代码；提取失败返回空串。"""
    system, user = code_prompt(task)
    content, usage = llm_call(system, user)
    return extract_code(content), usage


def repair_prompt(task: FactorTask, code: str, kind: str, error: str) -> tuple[str, str]:
    """自修复提示：把分类后的错误摘要回灌，要求重写完整代码。"""
    user = (
        f"任务名称：{task.name}\n任务描述：{task.description}\n公式：{task.formulation}\n\n"
        f"上一版代码执行失败（{kind}）：{error[:300]}\n\n"
        f"上一版代码：\n```python\n{code[:4000]}\n```\n"
        "请修复上述问题并只输出完整的 Python 代码块。"
    )
    return CODE_SYSTEM_PROMPT, user


def repair_code(llm_call: LLMCall, task: FactorTask, code: str, kind: str, error: str) -> tuple[str, dict[str, Any]]:
    """按错误摘要重写代码；提取失败返回空串。"""
    system, user = repair_prompt(task, code, kind, error)
    content, usage = llm_call(system, user)
    return extract_code(content), usage


def build_feedback(
    llm_call: LLMCall, context: str, metrics: dict[str, Any], sota_metrics: dict[str, Any] | None
) -> tuple[FeedbackOut, dict[str, Any]]:
    """结构化反馈；失败返回空反馈，不阻断决策。"""
    user = (
        f"{context}\n\n本轮指标：{json.dumps(metrics, ensure_ascii=False, default=str)}\n"
        f"当前 SOTA：{json.dumps(sota_metrics or {}, ensure_ascii=False, default=str)}"
    )
    return _call_json(llm_call, FEEDBACK_SYSTEM, user, FeedbackOut, FeedbackOut())


def render_context(
    trials: list[dict[str, Any]],
    sota_trial: dict[str, Any] | None,
    max_history: int = 20,
    knowledge: list[dict[str, Any]] | None = None,
) -> str:
    """三段式上下文：全量历史压缩 → 上一轮明细 → SOTA 代码（+ 已知失败模式）。"""

    def metric(trial: dict[str, Any], key: str) -> Any:
        return (trial.get("metrics") or {}).get(key)

    lines = ["## 研究历史（按时间倒序，最多 20 条）"]
    for t in trials[-max_history:][::-1]:
        lines.append(
            f"- L{t.get('loop_idx')}C{t.get('candidate_idx')} {t.get('status')} "
            f"IC_IR={metric(t, 'ic_ir')} IC={metric(t, 'ic_mean')} "
            f"fitness={metric(t, 'fitness')} decision={t.get('decision')} "
            f"假设={(t.get('hypothesis') or '')[:80]}"
        )
    if not trials:
        lines.append("- （暂无历史试验）")

    lines.append("\n## 上一轮明细")
    if trials:
        last = trials[-1]
        lines.append(f"- 假设：{last.get('hypothesis') or ''}")
        lines.append(f"- 指标：{json.dumps(last.get('metrics') or {}, ensure_ascii=False, default=str)}")
        lines.append(f"- 反馈：{json.dumps(last.get('feedback') or {}, ensure_ascii=False, default=str)}")
    else:
        lines.append("- （无）")

    lines.append("\n## 当前 SOTA")
    if sota_trial:
        lines.append(f"- 指标：{json.dumps(sota_trial.get('metrics') or {}, ensure_ascii=False, default=str)}")
        lines.append(f"- 代码：\n```python\n{(sota_trial.get('code') or '')[:1200]}\n```")
    else:
        lines.append("- （暂无，尚未有 trial 通过三道硬门）")

    if knowledge:
        # 失败签名来自 research_knowledge：让 LLM 在提假设/拆任务时避开已知的坑
        lines.append("\n## 已知失败模式（历史知识库，命中越多越要避开）")
        for item in knowledge[:5]:
            lines.append(
                f"- {item.get('signature')}（命中 {item.get('hit_count')} 次）"
                f"{'：' + item['hint'] if item.get('hint') else ''}"
            )

    lines.append("\n要求：新假设必须与上述历史尝试有明确差异，禁止重复已失败的实现。")
    return "\n".join(lines)
