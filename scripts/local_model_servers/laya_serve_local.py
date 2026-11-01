"""
本地 Laya System 1 适配服务：把 laya_mlx 包装成 axon-llm 的 `POST /v1/decide` 契约。

axon-llm 请求: `{model, state, questions}`；本服务返回 `{model, answers, usage{input_tokens, cost_usd}}`。

依赖 laya_mlx（**不在 backend 依赖里**，必须用独立 venv）：
    python -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python laya_serve_local.py            # 默认 127.0.0.1:8010

环境变量：
    LAYA_MODEL    checkpoint（默认 aac6fef/laya-multilingual-mlx）
    LAYA_HOST / LAYA_PORT   监听地址 / 端口
    LAYA_API_KEY  设置后校验 `Authorization: Bearer <key>`

两项契约适配（详见设计文档 4.6）：
    1. 补 `usage.cost_usd`——laya 原生没有该字段，而 axon-llm 的 DecisionUsage 必填；
    2. `confidence` 覆盖为 `answer_confidence`——laya 的 confidence 是 1-归一化熵（分布集中度），
       cascade 门限按「答案正确概率」设计，直接用会让 S1 永不直出。
"""

from __future__ import annotations

import copy
import hmac
import logging
import os
import threading
import time

import laya_mlx as laya
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

MODEL = os.getenv("LAYA_MODEL", "aac6fef/laya-multilingual-mlx")
API_KEY = os.getenv("LAYA_API_KEY", "")

logger = logging.getLogger("laya_adapter")

app = FastAPI(title="Laya /v1/decide adapter")

# 两把锁分开：加载锁与推理锁若共用，decide 持锁再调 get_agent 会自锁死（Lock 不可重入）
_infer_lock = threading.Lock()
_load_lock = threading.Lock()
_agent = None


def get_agent():
    """懒加载 checkpoint（进程内只加载一次）。"""
    global _agent
    if _agent is not None:
        return _agent
    with _load_lock:
        if _agent is None:
            logger.info("loading checkpoint %s ...", MODEL)
            _agent = laya.load(MODEL)
            logger.info("checkpoint loaded")
    return _agent


class DecideRequest(BaseModel):
    model: str = Field(
        default="", description="checkpoint 名，本服务忽略（固定用 LAYA_MODEL）"
    )
    state: dict | str
    questions: dict


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "loaded": _agent is not None}


@app.post("/v1/decide")
def decide(req: DecideRequest, authorization: str | None = Header(default=None)):
    # 常量时间比较：避免 LAYA_HOST=0.0.0.0 时被逐字节探测 key
    if API_KEY and not hmac.compare_digest(authorization or "", f"Bearer {API_KEY}"):
        raise HTTPException(status_code=401, detail="invalid api key")

    started = time.perf_counter()
    agent = get_agent()  # 锁外取，避免与推理锁嵌套
    try:
        with _infer_lock:  # MLX forward pass 不能并发，串行化
            out = agent.predict(req.state, req.questions)
    except ValueError as e:
        # laya 对非法 questions（缺 criteria/instructions）抛 ValueError → 422 对齐后端语义
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.exception("inference failed")
        raise HTTPException(
            status_code=502, detail=f"laya inference failed: {e}"
        ) from e

    # 复制一份再改写：laya 若将来引入结果缓存，原地改会跨请求累积污染 raw_confidence
    out = copy.deepcopy(out)

    for ans in (out.get("answers") or {}).values():
        if isinstance(ans, dict) and "answer_confidence" in ans:
            ans["raw_confidence"] = ans.get("confidence")
            ans["confidence"] = ans["answer_confidence"]

    # 保留 laya 的 output_tokens / state_tokens / truncated 等字段（Rust serde 会忽略未知键），
    # 排查截断/丢 token 时这些信息很关键
    usage = dict(out.get("usage") or {})
    usage["input_tokens"] = int(usage.get("input_tokens") or 0)
    usage["cost_usd"] = 0.0  # 本地推理不计费
    out["usage"] = usage
    out.setdefault("model", MODEL)

    logger.info(
        "decide ok %.0fms input_tokens=%s",
        (time.perf_counter() - started) * 1000,
        usage["input_tokens"],
    )
    return out


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    host = os.getenv("LAYA_HOST", "127.0.0.1")
    port = int(os.getenv("LAYA_PORT", "8010"))
    logger.info("preloading %s ...", MODEL)
    get_agent()
    logger.info("ready at http://%s:%s/v1/decide", host, port)
    uvicorn.run(app, host=host, port=port, workers=1)
