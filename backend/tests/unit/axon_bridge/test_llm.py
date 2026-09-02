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
        raw = json.dumps([{"id": "call_1", "function_name": "read_file", "arguments": '{"path": "a.txt"}'}])
        result = parse_tool_calls(raw)
        assert result == [{"id": "call_1", "name": "read_file", "arguments": {"path": "a.txt"}}]

    def test_invalid_arguments_json_fallback_to_empty_dict(self):
        raw = json.dumps([{"id": "call_1", "function_name": "foo", "arguments": "not-json"}])
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


from axon_bridge.llm import accumulate_stream, chat_to_dict, create_llm_backend


class TestCreateLLMBackend:
    def test_appends_v1_suffix(self):
        backend = create_llm_backend(api_key="sk-test", base_url="https://api.deepseek.com", model="deepseek-chat")
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
                "tool_calls": json.dumps([{"id": "c1", "function_name": "foo", "arguments": '{"x":1}'}]),
            }
        )
        resp = await chat_to_dict(fake, [{"role": "user", "content": "hi"}], tools=[{"function": {"name": "foo"}}])
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
