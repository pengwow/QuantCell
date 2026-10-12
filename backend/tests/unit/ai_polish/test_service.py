"""ai_polish 模块单元测试。"""

from __future__ import annotations

import pytest

from ai_polish.service import _build_messages, _clean_output


class TestCleanOutput:
    """_clean_output：去 markdown 包裹、去引号、截断。"""

    def test_strip_and_plain(self):
        assert _clean_output("  5日动量  ", 12) == "5日动量"

    def test_remove_markdown_fence(self):
        assert _clean_output("```\n5日动量\n```", 12) == "5日动量"

    def test_remove_markdown_fence_with_lang(self):
        assert _clean_output("```python\n5日动量\n```", 12) == "5日动量"

    def test_remove_quotes(self):
        assert _clean_output('"5日动量"', 12) == "5日动量"
        assert _clean_output("'5日动量'", 12) == "5日动量"
        assert _clean_output("“5日动量”", 12) == "5日动量"

    def test_truncate(self):
        assert _clean_output("一二三四五六七八九十十一", 5) == "一二三四五"

    def test_empty(self):
        assert _clean_output("", 12) == ""
        assert _clean_output("   ", 12) == ""


class TestBuildMessages:
    """_build_messages：按 target 构造 system + user 消息。"""

    def test_label_uses_expression(self):
        msgs = _build_messages("label", {"factor_name": "mom", "expression": "close/Ref(close,5)-1"}, 12)
        assert msgs[0]["role"] == "system"
        assert "中文展示名" in msgs[0]["content"]
        user = msgs[1]["content"]
        assert "mom" in user
        assert "close/Ref(close,5)-1" in user

    def test_label_uses_code_when_no_expression(self):
        msgs = _build_messages("label", {"factor_name": "mom", "code": 'factor = df["close"].pct_change(5)'}, 12)
        assert 'factor = df["close"].pct_change(5)' in msgs[1]["content"]

    def test_description_includes_existing(self):
        msgs = _build_messages(
            "description",
            {"factor_name": "mom", "expression": "close/Ref(close,5)-1", "existing": "旧描述"},
            200,
        )
        assert "旧描述" in msgs[1]["content"]

    def test_description_without_existing(self):
        msgs = _build_messages("description", {"factor_name": "mom", "expression": "close/Ref(close,5)-1"}, 200)
        assert "已有描述" not in msgs[1]["content"]

    def test_name_target(self):
        msgs = _build_messages("name", {"expression": "close/Ref(close,5)-1"}, 40)
        assert "英文标识" in msgs[0]["content"]

    def test_summary_target(self):
        msgs = _build_messages("summary", {"text": "一些内容"}, 500)
        assert "总结" in msgs[0]["content"]


class TestPolishTextNoConfig:
    """未配置 AI 模型时 polish_text 抛出 AIPolishError。"""

    def test_raises_when_no_config(self, monkeypatch):
        import asyncio

        from ai_polish.service import AIPolishError, polish_text

        # 模拟无配置
        monkeypatch.setattr("ai_polish.service._resolve_llm_config", lambda model_id=None: None)
        with pytest.raises(AIPolishError) as exc:
            asyncio.run(polish_text("label", {"factor_name": "x"}))
        assert "配置" in str(exc.value)
        assert exc.value.error_type == "no_config"
