# -*- coding: utf-8 -*-
"""AI 策略生成模板测试"""
import pytest
import os


@pytest.fixture
def template_path():
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    return os.path.join(
        backend_dir, "ai_model", "prompts", "templates",
        "axon_strategy_generation.txt"
    )


class TestAxonStrategyTemplate:
    def test_template_exists(self, template_path):
        assert os.path.exists(template_path), f"模板文件不存在: {template_path}"

    def test_template_no_external_import(self, template_path):
        with open(template_path, "r") as f:
            content = f.read()
        assert "from axon_quant" not in content, "模板不应包含 axon_quant 导入"
        assert "import axon_quant" not in content, "模板不应包含 axon_quant 导入"

    def test_template_imports_axon(self, template_path):
        with open(template_path, "r") as f:
            content = f.read()
        assert "axond" in content or "AxonStrategy" in content

    def test_template_has_on_bar(self, template_path):
        with open(template_path, "r") as f:
            content = f.read()
        assert "on_bar" in content

    def test_template_has_buy_sell(self, template_path):
        with open(template_path, "r") as f:
            content = f.read()
        assert "self.buy" in content or "self.sell" in content
