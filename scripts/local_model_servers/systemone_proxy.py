"""
System One 通用代理：把 Jev 兼容服务（`POST {upstream}/v1/systemone`）暴露成
axon-llm 期望的 `POST /v1/decide` 契约。

适用对象（均为 Jev 协议，数据来源 laya-ai.com/zh/jev-alternatives）：
    Jev（TypeSafe 托管）、Kev、Von、Decider、Rizzo Flow、OpenThai-SystemOne，
    以及 laya-serve / ollaya / sys1 / Arbiter 等兼容 Jev API 的服务。

与 laya_serve_local.py 的区别：
    - laya_serve_local 是**进程内**用 laya_mlx 跑 Laya checkpoint（Apple Silicon）；
    - 本代理**只做协议转换**，上游必须是已经起好的 HTTP 服务。

**不做 confidence 映射**：不同决策模型的 confidence 语义与分布各不相同
（官方明示「不同模型给出的概率不能直接换用，要重新设定阈值」），
cascade 门限需按实际模型在留出数据上标定。仅补 axon-llm 必填的 usage.cost_usd。

环境变量：
    SYSTEMONE_BASE   上游地址（默认 http://127.0.0.1:8080）
    SYSTEMONE_MODEL  模型标识（转发时填给上游，用于 checkpoint 路由；默认 jev-1）
    SYSTEMONE_API_KEY  上游鉴权（可空）
    S1_HOST / S1_PORT  监听地址 / 端口（默认 127.0.0.1:8030）

启动：
    python systemone_proxy.py
QuantCell 设置页 System 1 的 api_host 填 http://127.0.0.1:8030
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

SYSTEMONE_BASE = os.getenv("SYSTEMONE_BASE", "http://127.0.0.1:8080").rstrip("/")
SYSTEMONE_MODEL = os.getenv("SYSTEMONE_MODEL", "jev-1")
SYSTEMONE_API_KEY = os.getenv("SYSTEMONE_API_KEY", "")

logger = logging.getLogger("systemone_proxy")

app = FastAPI(title="Jev systemone -> decide proxy")


def _systemone_url() -> str:
    return (
        f"{SYSTEMONE_BASE}/systemone"
        if SYSTEMONE_BASE.endswith("/v1")
        else f"{SYSTEMONE_BASE}/v1/systemone"
    )


def _post(url: str, payload: bytes) -> bytes:
    headers = {"content-type": "application/json"}
    if SYSTEMONE_API_KEY:
        headers["authorization"] = f"Bearer {SYSTEMONE_API_KEY}"
    req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


@app.post("/v1/decide")
async def decide(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        # 默认会抛 500；畸形请求体属于客户端问题，按 400 返回便于排查
        raise HTTPException(status_code=400, detail=f"invalid json body: {e}") from e
    # model 透传：laya-serve 等用它选 checkpoint；不传则用环境变量兜底
    payload = {
        "state": body.get("state"),
        "questions": body.get("questions"),
        "model": body.get("model") or SYSTEMONE_MODEL,
    }

    started = time.perf_counter()
    try:
        raw = await run_in_threadpool(
            _post, _systemone_url(), json.dumps(payload).encode()
        )
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        # 上游 4xx 原样透传（非法 questions 等），其余统一 502
        code = e.code if 400 <= e.code < 500 else 502
        raise HTTPException(status_code=code, detail=detail) from e
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"systemone upstream unreachable: {e}"
        ) from e

    out = json.loads(raw)
    usage = dict(out.get("usage") or {})
    usage["input_tokens"] = int(usage.get("input_tokens") or 0)
    usage["cost_usd"] = (
        0.0  # 自托管无单次计费；托管 API 的真实成本需按供应商单价自行换算
    )
    out["usage"] = usage
    out.setdefault("model", payload["model"])

    logger.info(
        "decide ok %.0fms input_tokens=%s",
        (time.perf_counter() - started) * 1000,
        usage["input_tokens"],
    )
    return JSONResponse(out)


@app.get("/v1/models")
def models():
    """探活/模型列表：上游不提供时返回配置的模型名，避免设置页判定不可用。"""
    url = (
        f"{SYSTEMONE_BASE}/models"
        if SYSTEMONE_BASE.endswith("/v1")
        else f"{SYSTEMONE_BASE}/v1/models"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        if isinstance(data.get("data"), list):
            return JSONResponse(data)
    except Exception:
        pass
    return JSONResponse(
        {
            "object": "list",
            "data": [
                {"id": SYSTEMONE_MODEL, "object": "model", "owned_by": "systemone"}
            ],
        }
    )


@app.get("/health")
def health():
    return {"status": "ok", "upstream": SYSTEMONE_BASE, "model": SYSTEMONE_MODEL}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    host = os.getenv("S1_HOST", "127.0.0.1")
    port = int(os.getenv("S1_PORT", "8030"))
    logger.info("proxy ready at http://%s:%s -> %s", host, port, _systemone_url())
    uvicorn.run(app, host=host, port=port, workers=1)
