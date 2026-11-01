"""
本地 System 2 代理：OpenAI 兼容入口 → ollama 原生 `/api/chat`，并注入 think 开关。

为什么不直连 ollama 的 `/v1/chat/completions`：
  MiniCPM5-2B 是推理模型，默认输出全落在 reasoning、content 恒为空。
  ollama 的 OpenAI 兼容层对 think 处理不稳（实测 3~9s 且偶发 reasoning 挤占 token
  导致 content 被截断 → axon-llm Parse 失败）；原生 `/api/chat` + think 开关更可控。

axon-llm 的请求体固定为 `{model, messages, max_tokens, temperature}`，不带思考开关，
故由本代理补上并转换响应。

环境变量：
     OLLAMA_BASE   ollama 地址（默认 http://127.0.0.1:11434）
     S2_THINK      1（默认）保留推理段，判断质量更好（实测 2.7~9.5s）
                   0 跳过推理，0.2~0.5s 极快但判断保守（实测几乎恒 hold）
     S2_HOST / S2_PORT  监听地址 / 端口（默认 127.0.0.1:8020）

启动：
    OLLAMA_MODELS=... ollama serve          # 先起 ollama (:11434)
    python s2_proxy.py                      # 再起代理 (:8020)
QuantCell 设置页 System 2 的 api_host 填 http://127.0.0.1:8020
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

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434")
THINK_ON = os.getenv("S2_THINK", "1") != "0"
# 决策器需要确定性：axon-llm 的 OllamaBackend 默认传 temperature=0.7，
# 实测同一 state 会在 buy/sell/hold 之间跳变（0.1 仍不稳定，0 才完全一致），故强制贪心
S2_TEMPERATURE = float(os.getenv("S2_TEMPERATURE", "0"))

logger = logging.getLogger("s2_proxy")

app = FastAPI(title="ollama think proxy")


def _post(url: str, payload: bytes) -> bytes:
    req = urllib.request.Request(
        url, data=payload, method="POST", headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()

    # axon-llm 的 complete() 只走非流式；静默降级会让 SSE 客户端解析失败，故显式拒绝
    if body.get("stream"):
        raise HTTPException(
            status_code=400, detail="streaming is not supported by this proxy"
        )

    raw_max = body.get("max_tokens")
    try:
        max_tokens = int(raw_max) if raw_max is not None else 1024
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=422, detail="max_tokens must be an integer"
        ) from e

    payload = {
        "model": body.get("model"),
        "messages": body.get("messages", []),
        "stream": False,
        "think": THINK_ON,
        "options": {
            "temperature": S2_TEMPERATURE,
            # 放宽到 2048：推理段长度波动大（实测 166~566 tokens），
            # 按 axon-llm 传入的 1024 容易让 content 被截断
            "num_predict": max(max_tokens, 2048),
        },
    }

    started = time.perf_counter()
    try:
        raw = await run_in_threadpool(
            _post, f"{OLLAMA_BASE}/api/chat", json.dumps(payload).encode()
        )
    except urllib.error.HTTPError as e:
        raise HTTPException(
            status_code=e.code, detail=e.read().decode("utf-8", "replace")
        ) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ollama unreachable: {e}") from e

    resp = json.loads(raw)
    msg = resp.get("message") or {}
    prompt_tokens = int(resp.get("prompt_eval_count") or 0)
    completion_tokens = int(resp.get("eval_count") or 0)

    logger.info(
        "chat ok %.0fms prompt=%s completion=%s think=%s",
        (time.perf_counter() - started) * 1000,
        prompt_tokens,
        completion_tokens,
        THINK_ON,
    )

    # 转成 OpenAI 形状：axon-llm 只读 choices[0].message.content
    return JSONResponse(
        {
            "id": "chatcmpl-ollama",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": resp.get("model") or body.get("model") or "",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": msg.get("content", "")},
                    "finish_reason": "stop" if resp.get("done") else "length",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
    )


@app.get("/v1/models")
def models():
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=30) as resp:
            tags = json.loads(resp.read())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ollama unreachable: {e}") from e
    return JSONResponse(
        {
            "object": "list",
            "data": [
                {"id": m.get("name"), "object": "model", "owned_by": "ollama"}
                for m in tags.get("models", [])
            ],
        }
    )


@app.get("/health")
def health():
    return {"status": "ok", "upstream": OLLAMA_BASE, "think": THINK_ON}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    host = os.getenv("S2_HOST", "127.0.0.1")
    port = int(os.getenv("S2_PORT", "8020"))
    logger.info("proxy ready at http://%s:%s -> %s", host, port, OLLAMA_BASE)
    uvicorn.run(app, host=host, port=port, workers=1)
