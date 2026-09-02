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
