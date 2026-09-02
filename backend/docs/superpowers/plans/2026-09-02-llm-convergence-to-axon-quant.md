# QuantCell LLM 收敛到 axon-quant 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 QuantCell 4 处直连 openai SDK 的 LLM 调用全部收敛到 axon-quant 0.14.1 原生 Rust 栈，删除 `agent/providers` 重复实现。

**Architecture:** 新增 `axon_bridge/llm.py` 桥接层（工厂 + 格式转换 + 响应归一化 + 错误分类），agent / strategy_generator / indicators 三个消费方直接调用桥接层。分 4 个 Stage 递进，每阶段独立 commit + 测试通过。

**Tech Stack:** Python 3.13+ / FastAPI / axon-quant 0.14.1（PyPI）/ pytest / asyncio

**Spec:** `backend/docs/superpowers/specs/2026-09-02-llm-convergence-to-axon-quant-design.md`

---

## 关键背景（执行者必读）

### axon-quant 0.14.1 LLMBackend API

```python
from axon_quant.llm import make_backend

backend = make_backend({"backends": [{
    "name": "primary",
    "base_url": "https://api.xxx.com/v1",  # 必须带 /v1
    "api_key": "sk-xxx",                    # 不能为空字符串(Rust 侧校验)
    "model": "gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 4096,
    "timeout_secs": 120,
}]})

# 同步(内部 block_on) / 异步(不阻塞事件循环)
resp = backend.chat(messages)                      # dict
resp = await backend.chat_async(messages)          # awaitable dict
resp = await backend.chat_with_tools_async(msgs, tools)  # 额外含 tool_calls
async for chunk in backend.stream_chat_async(msgs): ...  # 逐 chunk
```

**消息格式**：每条是 dict `{"role", "content", "tool_call_id"?, "tool_calls"?}`，
其中 `tool_calls` 是 **JSON 字符串** `[{"id","function_name","arguments"}]`。

**chat 返回 dict**：
```python
{"content": str, "reasoning_content": str, "finish_reason": "Stop",  # 注意:Rust Debug 格式,首字母大写!
 "prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
# chat_with_tools 额外含:
# "tool_calls": '[{"id":"call_1","function_name":"foo","arguments":"{...}"}]' 或 "null"
```

**stream chunk dict**（`type` 区分）：
```python
{"type": "content", "content": "增量文本"}
{"type": "reasoning", "content": "思考链增量"}
{"type": "tool_call_start", "id": "call_1", "name": "foo"}
{"type": "tool_call_delta", "id": "call_1", "arguments": "参数增量片段"}
{"type": "done", "finish_reason": "Stop"}
```

**工具定义**（扁平格式，不是 OpenAI 嵌套格式）：
```python
{"name": "foo", "description": "...", "parameters": {JSON Schema dict}}
```

**错误**：全部抛 `RuntimeError`，消息前缀：
`"network error: ..."` / `"auth error: ..."` / `"rate limited (retry_after=...)"` /
`"backend error: status 401: ..."`（非 429 的失败状态走 Backend 变体）/ `"parse error: ..."`。

### QuantCell 旧格式（消费方期望）

- `finish_reason`：小写 `"stop"` / `"tool_calls"` / `"length"` / `"content_filter"`
- `tool_calls`：`[{"id": str, "name": str, "arguments": dict}]`（arguments 已解析为 dict）
- 工具定义：OpenAI 嵌套格式 `{"type": "function", "function": {"name", "description", "parameters"}}`
  （来自 `agent/tools/base.py:95 to_schema()`）
- assistant 消息里的 `tool_calls`：OpenAI 格式 list
  `[{"id", "type": "function", "function": {"name", "arguments"(JSON str)}}]`
  （来自 `agent/core/loop.py` 的 `tool_call_dicts`）

### 项目规范

- 日志用 `from utils.logger import LogType, get_logger`，禁止 print
- 删除文件/目录用 `mv` 移到 `_dead_code/` 或 `_dead_tests/`，禁止 `rm`
- 测试命令：`cd backend && .venv/bin/python -m pytest <path> -v`
- commit 前 pre-commit 钩子自动 ruff 格式化

---

## 文件结构

| 文件 | 动作 | 职责 |
|------|------|------|
| `backend/axon_bridge/llm.py` | 新建 | 桥接层：工厂 + 格式转换 + 归一化 + 错误分类 |
| `backend/axon_bridge/__init__.py` | 修改 | 导出桥接层函数 |
| `backend/tests/unit/axon_bridge/test_llm.py` | 新建 | 桥接层单测 |
| `backend/agent/core/events.py` | 新建 | `StreamEvent` dataclass（从 providers/base.py 搬家） |
| `backend/agent/core/loop.py` | 修改 | `provider` → `llm_backend`，消费桥接层 |
| `backend/agent/core/memory.py` | 修改 | 同上（Consolidator / Dream） |
| `backend/agent/core/factory.py` | 修改 | `OpenAIProvider` → `create_llm_backend` |
| `backend/agent/providers/` | 删除(→`_dead_code/`) | 重复实现 |
| `backend/tests/agent/test_loop.py` | 修改 | MockProvider → FakeLLMBackend |
| `backend/tests/agent/test_providers.py` | 删除(→`_dead_tests/`) | 测已删除的 provider |
| `backend/tests/manual/test_logging_demo.py` | 删除(→`_dead_tests/`) | 依赖 OpenAIProvider |
| `backend/ai_model/strategy_generator.py` | 修改 | OpenAI client → LLMBackend |
| `backend/indicators/routes.py` | 修改 | 两处直连 → chat_async |

---

## Stage 1: axon_bridge/llm.py 桥接层（纯新增，不破旧）

### Task 1.1: 纯函数 — 格式转换与归一化

**Files:**
- Create: `backend/axon_bridge/llm.py`
- Test: `backend/tests/unit/axon_bridge/test_llm.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/axon_bridge/test_llm.py
"""axon_bridge.llm 桥接层测试"""

import json

import pytest

from axon_bridge.llm import (
    classify_llm_error,
    flatten_tools,
    normalize_finish_reason,
    parse_tool_calls,
    to_axon_messages,
)


class TestNormalizeFinishReason:
    def test_rust_debug_format_to_lower(self):
        assert normalize_finish_reason("Stop") == "stop"
        assert normalize_finish_reason("ToolCalls") == "tool_calls"
        assert normalize_finish_reason("Length") == "length"
        assert normalize_finish_reason("ContentFilter") == "content_filter"

    def test_empty_returns_none(self):
        assert normalize_finish_reason("") is None
        assert normalize_finish_reason(None) is None


class TestParseToolCalls:
    def test_null_and_empty(self):
        assert parse_tool_calls(None) == []
        assert parse_tool_calls("null") == []
        assert parse_tool_calls("") == []

    def test_parse_axon_format(self):
        raw = json.dumps(
            [{"id": "call_1", "function_name": "read_file", "arguments": '{"path": "a.txt"}'}]
        )
        result = parse_tool_calls(raw)
        assert result == [
            {"id": "call_1", "name": "read_file", "arguments": {"path": "a.txt"}}
        ]

    def test_invalid_arguments_json_fallback_to_empty_dict(self):
        raw = json.dumps(
            [{"id": "call_1", "function_name": "foo", "arguments": "not-json"}]
        )
        assert parse_tool_calls(raw)[0]["arguments"] == {}


class TestFlattenTools:
    def test_openai_nested_to_axon_flat(self):
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_price",
                    "description": "获取价格",
                    "parameters": {"type": "object"},
                },
            }
        ]
        assert flatten_tools(openai_tools) == [
            {"name": "get_price", "description": "获取价格", "parameters": {"type": "object"}}
        ]

    def test_empty(self):
        assert flatten_tools([]) == []
        assert flatten_tools(None) == []


class TestToAxonMessages:
    def test_plain_message(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert to_axon_messages(msgs) == [{"role": "user", "content": "hi"}]

    def test_none_content_becomes_empty_string(self):
        msgs = [{"role": "assistant", "content": None}]
        assert to_axon_messages(msgs)[0]["content"] == ""

    def test_openai_tool_calls_serialized_to_axon_json(self):
        msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "foo", "arguments": '{"x": 1}'},
                    }
                ],
            }
        ]
        result = to_axon_messages(msgs)[0]
        parsed = json.loads(result["tool_calls"])
        assert parsed == [{"id": "call_1", "function_name": "foo", "arguments": '{"x": 1}'}]

    def test_tool_call_id_passthrough(self):
        msgs = [{"role": "tool", "content": "ok", "tool_call_id": "call_1"}]
        assert to_axon_messages(msgs)[0]["tool_call_id"] == "call_1"


class TestClassifyLLMError:
    @pytest.mark.parametrize(
        ("msg", "expected"),
        [
            ("auth error: invalid key", "auth"),
            ("backend error: status 401: Unauthorized", "auth"),
            ("rate limited (retry_after=3s)", "rate_limit"),
            ("backend error: status 429: Too Many Requests", "rate_limit"),
            ("network error: request timeout", "timeout"),
            ("network error: connection reset", "network"),
            ("parse error: invalid json", "other"),
        ],
    )
    def test_classification(self, msg, expected):
        assert classify_llm_error(RuntimeError(msg)) == expected
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/axon_bridge/test_llm.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'axon_bridge.llm'`）

- [ ] **Step 3: 实现**

```python
# backend/axon_bridge/llm.py
"""axon_quant LLM 桥接层 — 全项目统一入口

所有 QuantCell 业务代码通过本模块调用 LLM,不直接 import openai SDK:
- create_llm_backend: 构造 axon_quant LLMBackend
- chat_to_dict / accumulate_stream: 归一化响应(格式对齐旧 OpenAI 语义)
- classify_llm_error: 错误分类(供路由层映射用户文案)

格式差异说明:
- axon 的 finish_reason 是 Rust Debug 格式("Stop"/"ToolCalls"),这里归一化为小写
- axon 的 tool_calls 是 JSON 字符串(function_name 字段),这里解析为
  [{"id", "name", "arguments"(dict)}]
- QuantCell 工具定义是 OpenAI 嵌套格式,axon 要扁平格式,flatten_tools 转换
"""

from __future__ import annotations

import json
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# Rust FinishReason Debug 格式 → OpenAI 风格小写
_FINISH_REASON_MAP = {
    "Stop": "stop",
    "Length": "length",
    "ToolCalls": "tool_calls",
    "ContentFilter": "content_filter",
}


def normalize_finish_reason(raw: str | None) -> str | None:
    """把 axon 的 finish_reason 归一化为小写 OpenAI 风格"""
    if not raw:
        return None
    return _FINISH_REASON_MAP.get(raw, raw.lower())


def parse_tool_calls(raw: str | None) -> list[dict[str, Any]]:
    """解析 axon tool_calls JSON 字符串为 [{id, name, arguments(dict)}]

    axon 格式: [{"id","function_name","arguments"(JSON str)}] 或 "null"
    """
    if not raw or raw == "null":
        return []
    try:
        calls = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"tool_calls JSON 解析失败: {raw[:200]}")
        return []
    result = []
    for tc in calls:
        args = tc.get("arguments", "")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args else {}
            except json.JSONDecodeError:
                args = {}
        result.append(
            {
                "id": tc.get("id", ""),
                "name": tc.get("function_name", ""),
                "arguments": args,
            }
        )
    return result


def flatten_tools(tools: list[dict] | None) -> list[dict]:
    """OpenAI 嵌套工具定义 → axon 扁平格式

    输入: [{"type":"function","function":{"name","description","parameters"}}]
    输出: [{"name","description","parameters"}]
    已是扁平格式的 dict(无 function 键)原样透传。
    """
    flat = []
    for t in tools or []:
        fn = t.get("function", t)
        flat.append(
            {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            }
        )
    return flat


def to_axon_messages(messages: list[dict]) -> list[dict]:
    """OpenAI 风格消息列表 → axon dict 消息格式

    - content None → ""(axon 要求 str)
    - assistant 消息的 OpenAI 格式 tool_calls(list) → axon JSON 字符串
    - tool_call_id 透传
    """
    out = []
    for m in messages:
        d: dict[str, Any] = {"role": m.get("role", "user"), "content": m.get("content") or ""}
        if m.get("tool_call_id"):
            d["tool_call_id"] = m["tool_call_id"]
        tcs = m.get("tool_calls")
        if tcs:
            if isinstance(tcs, str):
                d["tool_calls"] = tcs
            else:
                # OpenAI 格式 → axon ToolCall 格式后序列化
                flat = [
                    {
                        "id": tc.get("id", ""),
                        "function_name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", ""),
                    }
                    for tc in tcs
                ]
                d["tool_calls"] = json.dumps(flat, ensure_ascii=False)
        out.append(d)
    return out


def classify_llm_error(e: Exception) -> str:
    """把 axon RuntimeError 消息分类: auth / rate_limit / timeout / network / other"""
    msg = str(e).lower()
    if "auth" in msg or "status 401" in msg or "invalid_api_key" in msg:
        return "auth"
    if "rate limit" in msg or "status 429" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "network" in msg or "connection" in msg:
        return "network"
    return "other"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/axon_bridge/test_llm.py -v`
Expected: PASS（14 个用例）

- [ ] **Step 5: Commit**

```bash
git add backend/axon_bridge/llm.py backend/tests/unit/axon_bridge/test_llm.py
git commit -m "feat(axon_bridge): add LLM bridge pure functions (format conversion)"
```

---

### Task 1.2: 工厂 + 异步调用 + 流累积

**Files:**
- Modify: `backend/axon_bridge/llm.py`
- Test: `backend/tests/unit/axon_bridge/test_llm.py`

- [ ] **Step 1: 追加失败测试**

在 `test_llm.py` 末尾追加：

```python
from axon_bridge.llm import accumulate_stream, chat_to_dict, create_llm_backend


class TestCreateLLMBackend:
    def test_appends_v1_suffix(self):
        backend = create_llm_backend(
            api_key="sk-test", base_url="https://api.deepseek.com", model="deepseek-chat"
        )
        assert "LLMBackend" in repr(backend)

    def test_empty_api_key_uses_placeholder(self):
        # axon 拒绝空 api_key;本地 Ollama 等场景用占位符,失败延迟到请求时
        backend = create_llm_backend(api_key="", base_url="http://localhost:11434", model="llama3")
        assert "LLMBackend" in repr(backend)


class FakeBackend:
    """模拟 axon LLMBackend 的异步接口(返回原始 axon 格式)"""

    def __init__(self, chat_resp=None, stream_chunks=None):
        self.chat_resp = chat_resp or {}
        self.stream_chunks = stream_chunks or []
        self.last_tools = None

    async def chat_async(self, messages):
        return self.chat_resp

    async def chat_with_tools_async(self, messages, tools):
        self.last_tools = tools
        return self.chat_resp

    async def stream_chat_async(self, messages):
        for c in self.stream_chunks:
            yield c


class TestChatToDict:
    @pytest.mark.asyncio
    async def test_normalize_response(self):
        fake = FakeBackend(
            chat_resp={
                "content": "hello",
                "reasoning_content": "",
                "finish_reason": "Stop",
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
            }
        )
        resp = await chat_to_dict(fake, [{"role": "user", "content": "hi"}])
        assert resp["content"] == "hello"
        assert resp["finish_reason"] == "stop"
        assert resp["has_tool_calls"] is False
        assert resp["tool_calls"] == []
        assert resp["usage"]["total_tokens"] == 3

    @pytest.mark.asyncio
    async def test_tool_calls_parsed(self):
        fake = FakeBackend(
            chat_resp={
                "content": "",
                "reasoning_content": "",
                "finish_reason": "ToolCalls",
                "tool_calls": json.dumps(
                    [{"id": "c1", "function_name": "foo", "arguments": '{"x":1}'}]
                ),
            }
        )
        resp = await chat_to_dict(
            fake, [{"role": "user", "content": "hi"}], tools=[{"function": {"name": "foo"}}]
        )
        assert resp["has_tool_calls"] is True
        assert resp["tool_calls"][0]["name"] == "foo"
        assert resp["finish_reason"] == "tool_calls"
        # 工具定义已转扁平格式
        assert fake.last_tools == [{"name": "foo", "description": "", "parameters": {}}]


class TestAccumulateStream:
    @pytest.mark.asyncio
    async def test_content_and_done(self):
        fake = FakeBackend(
            stream_chunks=[
                {"type": "content", "content": "Hel"},
                {"type": "content", "content": "lo"},
                {"type": "done", "finish_reason": "Stop"},
            ]
        )
        chunks = [c async for c in accumulate_stream(fake, [{"role": "user", "content": "hi"}])]
        assert chunks[0] == {"delta": "Hel"}
        assert chunks[1] == {"delta": "lo"}
        assert chunks[2]["finish_reason"] == "stop"
        assert chunks[2]["is_tool_call"] is False

    @pytest.mark.asyncio
    async def test_tool_calls_accumulated(self):
        fake = FakeBackend(
            stream_chunks=[
                {"type": "tool_call_start", "id": "c1", "name": "foo"},
                {"type": "tool_call_delta", "id": "c1", "arguments": '{"x"'},
                {"type": "tool_call_delta", "id": "c1", "arguments": ":1}"},
                {"type": "done", "finish_reason": "ToolCalls"},
            ]
        )
        chunks = [c async for c in accumulate_stream(fake, [])]
        final = chunks[-1]
        assert final["is_tool_call"] is True
        assert final["tool_calls"] == [{"id": "c1", "name": "foo", "arguments": {"x": 1}}]
        assert final["finish_reason"] == "tool_calls"

    @pytest.mark.asyncio
    async def test_reasoning_passthrough(self):
        fake = FakeBackend(stream_chunks=[{"type": "reasoning", "content": "思考中"}])
        chunks = [c async for c in accumulate_stream(fake, [])]
        assert chunks[0] == {"reasoning_content": "思考中"}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/axon_bridge/test_llm.py -v`
Expected: FAIL（`ImportError: cannot import name 'create_llm_backend'`）

- [ ] **Step 3: 实现（追加到 `axon_bridge/llm.py` 末尾）**

```python
from collections.abc import AsyncIterator

from axon_quant.llm import make_backend

# axon 拒绝空 api_key;本地服务(Ollama)无需密钥时用占位符,
# 认证失败延迟到请求时暴露(与旧 openai SDK 行为一致)
_PLACEHOLDER_API_KEY = "ollama"


def create_llm_backend(
    api_key: str,
    base_url: str,
    model: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout_secs: int = 120,
):
    """构造 axon_quant LLMBackend(全项目统一工厂)

    base_url 自动补 /v1 后缀(与旧 OpenAICompatibleAdapter 行为一致)。
    """
    base = (base_url or "https://api.openai.com").rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return make_backend(
        {
            "backends": [
                {
                    "name": "primary",
                    "base_url": base,
                    "api_key": api_key or _PLACEHOLDER_API_KEY,
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "timeout_secs": timeout_secs,
                }
            ]
        }
    )


def normalize_chat_response(raw: dict) -> dict:
    """axon chat 原始 dict → QuantCell 归一化响应

    输出键与旧 LLMResponse dataclass 字段对齐:
    content / reasoning_content / finish_reason / has_tool_calls / tool_calls / usage
    """
    tool_calls = parse_tool_calls(raw.get("tool_calls"))
    return {
        "content": raw.get("content") or None,
        "reasoning_content": raw.get("reasoning_content") or None,
        "finish_reason": normalize_finish_reason(raw.get("finish_reason")),
        "has_tool_calls": bool(tool_calls),
        "tool_calls": tool_calls,
        "usage": {
            "prompt_tokens": raw.get("prompt_tokens", 0),
            "completion_tokens": raw.get("completion_tokens", 0),
            "total_tokens": raw.get("total_tokens", 0),
        },
    }


async def chat_to_dict(
    backend: Any,
    messages: list[dict],
    tools: list[dict] | None = None,
) -> dict:
    """异步 chat,返回归一化响应 dict

    有 tools 走 chat_with_tools_async,否则 chat_async。
    参数按构造时固定(temperature/max_tokens),不支持逐次覆盖
    (axon backend 无逐次参数,旧代码的逐次 max_tokens 差异被抹平)。
    """
    msgs = to_axon_messages(messages)
    if tools:
        raw = await backend.chat_with_tools_async(msgs, flatten_tools(tools))
    else:
        raw = await backend.chat_async(msgs)
    return normalize_chat_response(raw)


async def accumulate_stream(
    backend: Any,
    messages: list[dict],
) -> AsyncIterator[dict]:
    """异步流式 chat,产出归一化 chunk(对齐旧 StreamChunk 语义)

    - content 增量: {"delta": str}
    - reasoning 增量: {"reasoning_content": str}
    - 结束事件: {"finish_reason": str|None, "tool_calls": list|None, "is_tool_call": bool}
    工具调用参数跨 chunk 累积,结束时一次性解析为 dict。
    """
    msgs = to_axon_messages(messages)
    # 跨 chunk 累积工具调用: id -> {"id","name","arguments"(str)}
    acc: dict[str, dict] = {}
    async for chunk in backend.stream_chat_async(msgs):
        ctype = chunk.get("type")
        if ctype == "content":
            yield {"delta": chunk.get("content", "")}
        elif ctype == "reasoning":
            yield {"reasoning_content": chunk.get("content", "")}
        elif ctype == "tool_call_start":
            acc[chunk["id"]] = {
                "id": chunk["id"],
                "name": chunk.get("name", ""),
                "arguments": "",
            }
        elif ctype == "tool_call_delta":
            if chunk.get("id") in acc:
                acc[chunk["id"]]["arguments"] += chunk.get("arguments", "")
        elif ctype == "done":
            tool_calls = []
            for tc in acc.values():
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    {"id": tc["id"], "name": tc["name"], "arguments": args}
                )
            yield {
                "finish_reason": normalize_finish_reason(chunk.get("finish_reason")),
                "tool_calls": tool_calls or None,
                "is_tool_call": bool(tool_calls),
            }
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/axon_bridge/test_llm.py -v`
Expected: PASS（21 个用例）

- [ ] **Step 5: Commit**

```bash
git add backend/axon_bridge/llm.py backend/tests/unit/axon_bridge/test_llm.py
git commit -m "feat(axon_bridge): add LLM backend factory and async chat/stream bridge"
```

---

### Task 1.3: axon_bridge 顶层导出

**Files:**
- Modify: `backend/axon_bridge/__init__.py`

- [ ] **Step 1: 添加导出**

在 `backend/axon_bridge/__init__.py` 的 `from ._credentials import credentials` 之前插入：

```python
from .llm import (
    accumulate_stream,
    chat_to_dict,
    classify_llm_error,
    create_llm_backend,
    flatten_tools,
    normalize_chat_response,
    parse_tool_calls,
    to_axon_messages,
)
```

并在 `__all__` 列表开头（`"VERSION",` 之后）按字母序加入：

```python
    "accumulate_stream",
    "chat_to_dict",
    "classify_llm_error",
    "create_llm_backend",
    "flatten_tools",
    "normalize_chat_response",
    "parse_tool_calls",
    "to_axon_messages",
```

- [ ] **Step 2: 验证导入**

Run: `cd backend && .venv/bin/python -c "from axon_bridge import create_llm_backend, chat_to_dict, accumulate_stream, classify_llm_error; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/axon_bridge/__init__.py
git commit -m "feat(axon_bridge): export LLM bridge functions"
```

---

## Stage 2: agent 模块拆除 providers 抽象

### Task 2.1: StreamEvent 搬家 + loop.py 迁移

**Files:**
- Create: `backend/agent/core/events.py`
- Modify: `backend/agent/core/loop.py`

- [ ] **Step 1: 创建 events.py**

```python
# backend/agent/core/events.py
"""Agent 流式事件定义(原 agent/providers/base.py 的 StreamEvent 搬家)"""

from dataclasses import dataclass, field


@dataclass
class StreamEvent:
    """流式事件 - 用于 Agent Loop 向上层传递事件"""

    event_type: str  # start | content | reasoning | tool_calls | tool_start | tool_result | complete | error
    data: dict  # 事件数据
    timestamp: float = field(default_factory=lambda: __import__("time").time())
```

- [ ] **Step 2: 修改 loop.py 导入与构造**

`backend/agent/core/loop.py` 做以下替换：

1. 删除 `if TYPE_CHECKING:` 块中的 `from ..providers.base import LLMProvider`
2. 构造函数签名与初始化（第 41-61 行区域）：

```python
    def __init__(
        self,
        llm_backend,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        memory_window: int = 100,
        reasoning_effort: str | None = None,
        context_window_tokens: int = 128000,
    ):
        self.llm_backend = llm_backend
        self.workspace = workspace
        # 旧 provider.get_default_model() 的兜底逻辑内联到这里
        self.model = model or os.environ.get("DEFAULT_MODEL", "gpt-4o-mini")
```

（文件顶部补 `import os`；`temperature` / `max_tokens` / `reasoning_effort` 仍保留为实例属性——构造 backend 时已用，循环内不再逐次传递。）

3. `Consolidator(...)` / `Dream(...)` 的 `provider=provider` 改为 `llm_backend=llm_backend`

- [ ] **Step 3: 迁移非流式调用（`_run_agent_loop`）**

把第 147-154 行的：

```python
                response = await self.provider.chat(
                    messages=messages,
                    tools=self.tools.get_definitions(),
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    reasoning_effort=self.reasoning_effort,
                )
```

替换为：

```python
                response = await chat_to_dict(
                    self.llm_backend, messages, tools=self.tools.get_definitions()
                )
```

（顶部加 `from axon_bridge.llm import accumulate_stream, chat_to_dict`）

同函数内所有属性访问改 dict 访问：
- `response.finish_reason` → `response["finish_reason"]`
- `response.has_tool_calls` → `response["has_tool_calls"]`
- `response.content` → `response["content"]`
- `response.reasoning_content` → `response["reasoning_content"]`
- `response.tool_calls` → `response["tool_calls"]`

- [ ] **Step 4: 迁移流式调用（`_run_agent_loop_stream`）**

把第 295-333 行的 `async for chunk in self.provider.chat_stream(...)` 块替换为：

```python
                async for chunk in accumulate_stream(self.llm_backend, messages):
                    # 文本内容 - 立即推送给客户端
                    if chunk.get("delta"):
                        response_content += chunk["delta"]
                        if on_stream:
                            await on_stream(
                                StreamEvent(
                                    event_type="content",
                                    data={
                                        "content": chunk["delta"],
                                        "full_content": response_content,
                                    },
                                )
                            )

                    # 推理过程（DeepSeek-R1 等）
                    if chunk.get("reasoning_content"):
                        reasoning_parts.append(chunk["reasoning_content"])
                        if on_stream:
                            await on_stream(
                                StreamEvent(
                                    event_type="reasoning",
                                    data={"content": chunk["reasoning_content"]},
                                )
                            )

                    # 结束事件:捕获 finish_reason 与工具调用
                    if "finish_reason" in chunk:
                        finish_reason = chunk["finish_reason"]
                        if chunk.get("is_tool_call") and chunk.get("tool_calls"):
                            response_tool_calls = chunk["tool_calls"]
```

把两处函数内 `from ..providers.base import StreamEvent`（第 258、604 行）改为 `from .events import StreamEvent`。

- [ ] **Step 5: 运行 agent 循环测试（此时预期失败，测试还没改）**

Run: `cd backend && .venv/bin/python -m pytest tests/agent/test_loop.py -v`
Expected: FAIL（测试还在用旧 MockProvider）——这是预期的，Task 2.3 修测试。

- [ ] **Step 6: Commit（不含测试修复）**

```bash
git add backend/agent/core/events.py backend/agent/core/loop.py
git commit -m "refactor(agent): migrate AgentLoop to axon_bridge LLM backend"
```

---

### Task 2.2: memory.py + factory.py 迁移

**Files:**
- Modify: `backend/agent/core/memory.py`
- Modify: `backend/agent/core/factory.py`

- [ ] **Step 1: memory.py 迁移**

1. 删除 `if TYPE_CHECKING:` 中的 `from ..providers.base import LLMProvider`，顶部加
   `from axon_bridge.llm import chat_to_dict`
2. `Consolidator.__init__(self, store, provider, model, ...)`（第 207 行附近）：
   参数 `provider` → `llm_backend`，`self.provider = provider` → `self.llm_backend = llm_backend`
3. 第 304 行：

```python
            response = await chat_to_dict(
                self.llm_backend,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": formatted},
                ],
            )
            summary = response["content"] or "[no summary]"
```

（删除原调用的 `model=` / `temperature=` / `max_tokens=` 参数——backend 构造时已固定。）

4. `Dream.__init__`（第 530 行附近）同样 `provider` → `llm_backend`
5. 第 591、631 行的 `phase1_response = await self.provider.chat(...)` /
   `phase2_response = await self.provider.chat(...)` 同样改为
   `await chat_to_dict(self.llm_backend, messages列表)`，后续
   `response.content` → `response["content"]`

- [ ] **Step 2: factory.py 迁移**

替换第 9 行导入：

```python
from axon_bridge.llm import create_llm_backend
```

`get_agent()` 内（第 150-185 行区域）：

```python
        if ai_config:
            provider_config = ai_config["provider"]
            enabled_model = ai_config.get("enabled_model", {})
            if enabled_model:
                model_id = enabled_model.get("name") or enabled_model.get("id")
                logger.info(f"Agent使用模型: id={enabled_model.get('id')}, name={enabled_model.get('name')}")
            else:
                model_id = None

            model = model_id or os.environ.get("DEFAULT_MODEL", "gpt-4o-mini")
            llm_backend = create_llm_backend(
                api_key=provider_config.get("api_key") or "",
                base_url=provider_config.get("api_host") or "",
                model=model,
                temperature=0.1,
                max_tokens=4096,
            )
            logger.info(f"Agent使用系统配置: 提供商={provider_config['name']}, 模型={model}")
        else:
            model = os.environ.get("DEFAULT_MODEL", "gpt-4o-mini")
            llm_backend = create_llm_backend(
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                base_url=os.environ.get("OPENAI_BASE_URL") or "",
                model=model,
                temperature=0.1,
                max_tokens=4096,
            )
            logger.info("Agent使用环境变量配置")

        _agent_instance = AgentLoop(
            llm_backend=llm_backend,
            workspace=workspace,
            model=model,
            max_iterations=40,
            temperature=0.1,
            max_tokens=4096,
            memory_window=100,
        )
```

（顶部补 `import os`。）

- [ ] **Step 3: 验证导入链**

Run: `cd backend && .venv/bin/python -c "from agent.core.factory import get_ai_config; from agent.core.loop import AgentLoop; from agent.core.memory import Consolidator; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/agent/core/memory.py backend/agent/core/factory.py
git commit -m "refactor(agent): migrate memory and factory to axon_bridge LLM backend"
```

---

### Task 2.3: 删除 providers 包 + 测试迁移

**Files:**
- Delete(→`_dead_code/`): `backend/agent/providers/`
- Delete(→`_dead_tests/`): `backend/tests/agent/test_providers.py`、`backend/tests/manual/test_logging_demo.py`
- Modify: `backend/tests/agent/test_loop.py`

- [ ] **Step 1: 重写 test_loop.py 的 Mock**

把 `backend/tests/agent/test_loop.py` 第 1-39 行（导入 + MockProvider）替换为：

```python
"""Agent 循环测试"""

import json

import pytest

from agent.core.loop import AgentLoop


class FakeLLMBackend:
    """模拟 axon_quant LLMBackend(返回原始 axon 格式,桥接层负责归一化)"""

    def __init__(self, responses=None, stream_chunks=None):
        # responses: 依次返回的 chat 原始 dict 列表
        self.responses = responses or []
        self.stream_chunks = stream_chunks or []
        self.call_count = 0

    def _next(self):
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return {"content": "Mock response", "reasoning_content": "", "finish_reason": "Stop"}

    async def chat_async(self, messages):
        return self._next()

    async def chat_with_tools_async(self, messages, tools):
        return self._next()

    async def stream_chat_async(self, messages):
        for c in self.stream_chunks:
            yield c


def text_response(content: str) -> dict:
    """构造纯文本响应的原始 axon dict"""
    return {"content": content, "reasoning_content": "", "finish_reason": "Stop"}


def tool_call_response(tool_name: str, arguments: dict, call_id: str = "call_1") -> dict:
    """构造工具调用响应的原始 axon dict"""
    return {
        "content": "",
        "reasoning_content": "",
        "finish_reason": "ToolCalls",
        "tool_calls": json.dumps(
            [{"id": call_id, "function_name": tool_name, "arguments": json.dumps(arguments)}]
        ),
    }
```

然后把测试体中所有：
- `MockProvider([LLMResponse(content="Hello!", has_tool_calls=False, tool_calls=[])])`
  → `FakeLLMBackend([text_response("Hello!")])`
- 工具调用响应 `LLMResponse(content=None, has_tool_calls=True, tool_calls=[{"id": "call_1", "name": "read_file", "arguments": {"path": "test.txt"}}])`
  → `tool_call_response("read_file", {"path": "test.txt"})`
- `AgentLoop(provider=provider, ...)` → `AgentLoop(llm_backend=backend, ...)`
- 流式测试：`MockProvider([LLMResponse(content="Stream response", ...)])`
  → `FakeLLMBackend(stream_chunks=[{"type": "content", "content": "Stream response"}, {"type": "done", "finish_reason": "Stop"}])`

（逐个用例机械替换，保持断言不变。）

- [ ] **Step 2: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/agent/test_loop.py -v`
Expected: PASS

- [ ] **Step 3: 移除死代码（mv 到回收目录，禁止 rm）**

```bash
cd backend
mkdir -p _dead_code _dead_tests
mv agent/providers _dead_code/agent_providers_20260902
mv tests/agent/test_providers.py _dead_tests/
mv tests/manual/test_logging_demo.py _dead_tests/
```

- [ ] **Step 4: 全量回归 agent 测试**

Run: `cd backend && .venv/bin/python -m pytest tests/agent/ -v`
Expected: PASS（若 test_memory_system*.py 有引用 provider 的 fixture，同样按 FakeLLMBackend 模式替换）

- [ ] **Step 5: Commit**

```bash
git add -A backend/agent backend/tests backend/_dead_code backend/_dead_tests
git commit -m "refactor(agent): remove providers package, converge tests to FakeLLMBackend"
```

---

## Stage 3: strategy_generator 收敛

### Task 3.1: StrategyGenerator 改用 LLMBackend

**Files:**
- Modify: `backend/ai_model/strategy_generator.py`
- Test: `backend/tests/unit/ai_model/`

- [ ] **Step 1: 替换导入与构造**

1. 删除顶部 `from openai import APIConnectionError as OpenAIAPIConnectionError` 和
   `from openai import (...)` 整块 openai 导入，替换为：

```python
from axon_bridge.llm import classify_llm_error, create_llm_backend
```

2. `__init__` 中（第 140-146 行）把 `self._client = OpenAI(...)` 替换为：

```python
        # axon backend:temperature/max_tokens 构造时固定
        self._backend = create_llm_backend(
            api_key=api_key,
            base_url=self.api_host,
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            timeout_secs=int(self.DEFAULT_TIMEOUT),
        )
```

- [ ] **Step 2: 迁移同步生成 `generate()`**

把第 333-344 行的 API 调用替换为：

```python
            # 调用 axon backend(同步,内部 block_on)
            raw = self._backend.chat(
                [
                    {"role": "system", "content": "你是一个专业的量化交易策略生成专家。"},
                    {"role": "user", "content": prompt},
                ]
            )
            content = raw.get("content") or ""
```

第 348-364 行 usage 提取改为：

```python
            elapsed_time = time.time() - start_time
            logger.info(
                f"[{request_id}] API调用成功，耗时: {elapsed_time:.2f}s, "
                f"Token使用: {raw.get('total_tokens', 'N/A')}"
            )
            result = self._parse_response(content)
            result["metadata"] = {
                "request_id": request_id,
                "model": self.model_id,
                "elapsed_time": elapsed_time,
                "total_tokens": raw.get("total_tokens"),
                "prompt_tokens": raw.get("prompt_tokens"),
                "completion_tokens": raw.get("completion_tokens"),
            }
            total_tokens = raw.get("total_tokens")
```

异常处理（第 378-430 行区域）整块替换为：

```python
        except RuntimeError as e:
            elapsed_time = time.time() - start_time
            kind = classify_llm_error(e)
            error_code_map = {
                "auth": "api_authentication_error",
                "rate_limit": "api_rate_limit_error",
                "timeout": "api_timeout_error",
                "network": "api_connection_error",
            }
            logger.error(f"[{request_id}] API调用失败({kind}): {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code=error_code_map.get(kind, "api_error"),
            )
            if kind == "auth":
                raise APIAuthenticationError(f"API密钥无效或已过期: {e!s}") from e
            if kind == "rate_limit":
                raise APIRateLimitError(f"请求过于频繁，请稍后再试: {e!s}") from e
            if kind in ("timeout", "network"):
                raise APIConnectionError(f"API连接失败: {e!s}") from e
            raise StrategyGenerationError(f"API调用失败: {e!s}", "api_error") from e
```

（保留其后已有的 `ResponseParseError` / 通用异常分支不动。）

- [ ] **Step 3: 迁移流式生成 `generate_stream()`**

把第 541-553 行的 `stream = self._client.chat.completions.create(...)` 与
第 566-576 行的累积循环替换为：

```python
            # axon 同步 stream_chat:一次性收集全部 delta(本方法内部累积,
            # 不逐块推给客户端,与旧行为一致)
            deltas = self._backend.stream_chat(
                [
                    {"role": "system", "content": "你是一个专业的量化交易策略生成专家。"},
                    {"role": "user", "content": prompt},
                ]
            )
            full_content = "".join(
                d.get("content", "") for d in deltas if d.get("type") == "content"
            )
            chunk_count = len(deltas)
```

（删除原 `full_content = ""` / `for chunk in stream:` 块；异常处理同 Step 2 模式。）

- [ ] **Step 4: 运行 ai_model 测试**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/ai_model/ -v`
Expected: PASS（若有测试 mock 了 `OpenAI` 客户端，改为注入 FakeBackend 或 monkeypatch `create_llm_backend`）

- [ ] **Step 5: Commit**

```bash
git add backend/ai_model/strategy_generator.py backend/tests
git commit -m "refactor(ai_model): converge strategy generator to axon LLM backend"
```

---

## Stage 4: indicators 收敛

### Task 4.1: indicators/routes.py 两处直连改 chat_async

**Files:**
- Modify: `backend/indicators/routes.py`

- [ ] **Step 1: 替换导入**

删除第 15 行 `from openai import OpenAI`，在文件顶部导入区加：

```python
from axon_bridge.llm import classify_llm_error, create_llm_backend
```

- [ ] **Step 2: 迁移 `call_ai_generate_code`（第 693-742 行区域）**

把 `client = OpenAI(...)` + `response = client.chat.completions.create(...)` 替换为：

```python
        backend = create_llm_backend(
            api_key=api_key,
            base_url=api_host,
            model=model,
            temperature=0.7,
            max_tokens=4096,
            timeout_secs=120,
        )
        raw = await backend.chat_async(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        generated_code = raw.get("content") or ""
```

异常处理块（第 722-742 行的字符串匹配分支）替换为：

```python
    except RuntimeError as e:
        kind = classify_llm_error(e)
        if kind == "auth":
            raise Exception(f"AI模型认证失败 (401): 请检查API密钥是否正确。原始错误: {e}") from e
        if kind == "rate_limit":
            raise Exception(f"AI模型请求频率限制 (429): 请稍后重试。原始错误: {e}") from e
        if kind in ("timeout", "network"):
            raise Exception(f"AI模型连接失败: 无法连接到 {api_host}。请检查网络和API地址是否正确。原始错误: {e}") from e
        raise Exception(f"AI模型调用失败: {e}") from e
```

- [ ] **Step 3: 迁移 `_repair_indicator_code_via_llm`（第 860-886 行区域）**

把 `AIModelService.get_adapter(...)` + `adapter._client` hack 替换为：

```python
        api_key_val = provider_config.get("api_key") or ""
        api_host_val = provider_config.get("api_host") or ""
        if not api_host_val:
            return None

        model_name = model_id.split("-", 1)[-1] if "-" in str(model_id) else str(model_id)
        backend = create_llm_backend(
            api_key=api_key_val,
            base_url=api_host_val,
            model=model_name,
            temperature=0.2,
            max_tokens=4096,
        )
        raw = await backend.chat_async(
            [
                {"role": "system", "content": DEFAULT_INDICATOR_SYSTEM_PROMPT},
                {"role": "user", "content": repair_prompt},
            ]
        )
        repaired = raw.get("content") or ""
```

（删除 `from ai_model.services import AIModelService` 局部导入；后续清洗逻辑不变。）

- [ ] **Step 4: 验证无残留 openai 引用 + 导入检查**

Run: `cd backend && .venv/bin/python -c "import indicators.routes; print('ok')"`
Run: `cd backend && grep -n "from openai" indicators/routes.py`
Expected: `ok`；grep 无输出

- [ ] **Step 5: 全量回归**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/ tests/agent/ -x -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/indicators/routes.py
git commit -m "refactor(indicators): converge AI codegen to axon LLM backend"
```

---

## 收尾

- [ ] **最终验证：全量 pytest**

Run: `cd backend && .venv/bin/python -m pytest -x -q`
Expected: 全部通过

- [ ] **残留检查：确认交易/生成链路无 openai SDK 直连**

Run: `cd backend && grep -rn "from openai" --include="*.py" agent/ ai_model/strategy_generator.py indicators/`
Expected: 仅 `ai_model/services.py`（厂商管理面，按设计保留）

---

## 自审记录

- **Spec 覆盖**：①桥接层 → Task 1.1-1.3；②agent 拆抽象 → Task 2.1-2.3；③strategy_generator → Task 3.1；④indicators → Task 4.1；保留 services.py 管理面 → 收尾残留检查确认。✅
- **类型一致性**：`chat_to_dict` / `accumulate_stream` / `create_llm_backend` / `classify_llm_error` 四个函数名在全部 Task 中一致；归一化响应键（content/reasoning_content/finish_reason/has_tool_calls/tool_calls/usage）在 Task 1.2 定义、Task 2.1/2.2 消费处一致。✅
- **已知行为差异（接受）**：逐次调用的 `max_tokens`/`temperature` 覆盖被抹平（axon backend 构造时固定），memory.py 摘要的 1024 上限变为构造值 4096；流式 usage 统计不再提供（axon stream 无 usage）。
- **占位符扫描**：无 TBD/TODO。✅
