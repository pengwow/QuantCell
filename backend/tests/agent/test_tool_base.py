"""工具基类测试 - Tool"""

import pytest
from typing import Any

from agent.tools.base import Tool


class MockTool(Tool):
    """用于测试的模拟工具"""

    name = "mock_tool"
    description = "A mock tool for testing"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "User name"},
            "age": {"type": "integer", "description": "User age", "minimum": 0, "maximum": 150},
            "email": {"type": "string", "description": "Email address"},
            "active": {"type": "boolean", "description": "Is active"},
            "tags": {"type": "array", "description": "Tags list", "items": {"type": "string"}},
            "role": {"type": "string", "description": "User role", "enum": ["admin", "user", "guest"]},
        },
        "required": ["name", "email"],
    }

    async def execute(self, **kwargs: Any) -> str:
        return f"Executed with {kwargs}"


class MockToolNoParams(Tool):
    """无参数的模拟工具"""

    name = "no_params_tool"
    description = "A tool with no parameters"
    parameters = {}

    async def execute(self, **kwargs: Any) -> str:
        return "No params"


class TestTool:
    """测试 Tool 基类"""

    @pytest.fixture
    def tool(self):
        return MockTool()

    def test_tool_properties(self, tool):
        """测试工具属性"""
        assert tool.name == "mock_tool"
        assert tool.description == "A mock tool for testing"
        assert tool.parameters is not None

    def test_to_schema(self, tool):
        """测试转换为OpenAI格式"""
        schema = tool.to_schema()
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mock_tool"
        assert schema["function"]["description"] == "A mock tool for testing"
        assert schema["function"]["parameters"] == tool.parameters

    def test_validate_params_valid(self, tool):
        """测试有效参数验证"""
        params = {
            "name": "John",
            "email": "john@example.com",
        }
        
        errors = tool.validate_params(params)
        
        assert errors == []

    def test_validate_params_all_fields(self, tool):
        """测试所有字段验证"""
        params = {
            "name": "John",
            "age": 30,
            "email": "john@example.com",
            "active": True,
            "tags": ["developer", "python"],
            "role": "admin",
        }
        
        errors = tool.validate_params(params)
        
        assert errors == []

    def test_validate_params_missing_required(self, tool):
        """测试缺少必需参数"""
        params = {
            "name": "John",
            # 缺少 email
        }
        
        errors = tool.validate_params(params)
        
        assert len(errors) > 0
        assert any("email" in e for e in errors)

    def test_validate_params_invalid_type(self, tool):
        """测试无效类型"""
        params = {
            "name": 123,  # 应该是字符串
            "email": "john@example.com",
        }
        
        errors = tool.validate_params(params)
        
        assert len(errors) > 0
        assert any("string" in e for e in errors)

    def test_validate_params_invalid_integer(self, tool):
        """测试无效整数"""
        params = {
            "name": "John",
            "email": "john@example.com",
            "age": "thirty",  # 应该是整数
        }
        
        errors = tool.validate_params(params)
        
        assert len(errors) > 0
        assert any("integer" in e for e in errors)

    def test_validate_params_minimum(self, tool):
        """测试最小值约束"""
        params = {
            "name": "John",
            "email": "john@example.com",
            "age": -5,  # 小于最小值0
        }
        
        errors = tool.validate_params(params)
        
        assert len(errors) > 0
        assert any(">=" in e for e in errors)

    def test_validate_params_maximum(self, tool):
        """测试最大值约束"""
        params = {
            "name": "John",
            "email": "john@example.com",
            "age": 200,  # 大于最大值150
        }
        
        errors = tool.validate_params(params)
        
        assert len(errors) > 0
        assert any("<=" in e for e in errors)

    def test_validate_params_enum(self, tool):
        """测试枚举约束"""
        params = {
            "name": "John",
            "email": "john@example.com",
            "role": "superadmin",  # 不在枚举中
        }
        
        errors = tool.validate_params(params)
        
        assert len(errors) > 0
        # 检查是否有枚举相关的错误
        assert any("必须是以下之一" in e or "enum" in e for e in errors)

    def test_validate_params_enum_valid(self, tool):
        """测试有效枚举值"""
        params = {
            "name": "John",
            "email": "john@example.com",
            "role": "admin",
        }
        
        errors = tool.validate_params(params)
        
        assert errors == []

    def test_validate_params_array(self, tool):
        """测试数组参数"""
        params = {
            "name": "John",
            "email": "john@example.com",
            "tags": ["tag1", "tag2"],
        }
        
        errors = tool.validate_params(params)
        
        assert errors == []

    def test_validate_params_array_invalid(self, tool):
        """测试无效数组参数"""
        params = {
            "name": "John",
            "email": "john@example.com",
            "tags": [123, 456],  # 应该是字符串数组
        }
        
        errors = tool.validate_params(params)
        
        assert len(errors) > 0

    def test_validate_params_not_dict(self, tool):
        """测试非字典参数"""
        params = "invalid"
        
        errors = tool.validate_params(params)
        
        assert len(errors) > 0
        assert any("对象" in e for e in errors)

    def test_validate_params_extra_fields(self, tool):
        """测试额外字段（应该被忽略）"""
        params = {
            "name": "John",
            "email": "john@example.com",
            "extra_field": "value",
        }
        
        errors = tool.validate_params(params)
        
        # 额外字段不应该导致错误
        assert errors == []

    def test_execute(self, tool):
        """测试工具执行"""
        import asyncio
        
        result = asyncio.run(tool.execute(name="John", email="john@example.com"))
        
        assert "Executed" in result
        assert "John" in result

    def test_tool_no_params(self):
        """测试无参数工具"""
        tool = MockToolNoParams()
        
        schema = tool.to_schema()
        assert schema["function"]["parameters"] == {}
        
        errors = tool.validate_params({})
        assert errors == []


class TestToolValidation:
    """测试工具验证逻辑"""

    def test_validate_string_min_length(self):
        """测试字符串最小长度"""
        class MinLengthTool(Tool):
            name = "min_length"
            description = "Test"
            parameters = {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 5},
                },
                "required": ["text"],
            }
            async def execute(self, **kwargs):
                return "ok"
        
        tool = MinLengthTool()
        
        # 太短
        errors = tool.validate_params({"text": "abc"})
        assert len(errors) > 0
        
        # 足够长
        errors = tool.validate_params({"text": "abcdef"})
        assert errors == []

    def test_validate_string_max_length(self):
        """测试字符串最大长度"""
        class MaxLengthTool(Tool):
            name = "max_length"
            description = "Test"
            parameters = {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "maxLength": 10},
                },
                "required": ["text"],
            }
            async def execute(self, **kwargs):
                return "ok"
        
        tool = MaxLengthTool()
        
        # 太长
        errors = tool.validate_params({"text": "a" * 20})
        assert len(errors) > 0
        
        # 足够短
        errors = tool.validate_params({"text": "short"})
        assert errors == []

    def test_validate_nested_object(self):
        """测试嵌套对象验证"""
        class NestedTool(Tool):
            name = "nested"
            description = "Test"
            parameters = {
                "type": "object",
                "properties": {
                    "user": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "age": {"type": "integer"},
                        },
                        "required": ["name"],
                    },
                },
                "required": ["user"],
            }
            async def execute(self, **kwargs):
                return "ok"
        
        tool = NestedTool()
        
        # 有效嵌套对象
        errors = tool.validate_params({"user": {"name": "John", "age": 30}})
        assert errors == []
        
        # 缺少必需字段
        errors = tool.validate_params({"user": {"age": 30}})
        assert len(errors) > 0
        
        # 类型错误
        errors = tool.validate_params({"user": {"name": 123}})
        assert len(errors) > 0

    def test_validate_array_items(self):
        """测试数组项验证"""
        class ArrayTool(Tool):
            name = "array"
            description = "Test"
            parameters = {
                "type": "object",
                "properties": {
                    "numbers": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
                "required": ["numbers"],
            }
            async def execute(self, **kwargs):
                return "ok"
        
        tool = ArrayTool()
        
        # 有效数组
        errors = tool.validate_params({"numbers": [1, 2, 3]})
        assert errors == []
        
        # 无效数组项
        errors = tool.validate_params({"numbers": [1, "two", 3]})
        assert len(errors) > 0

    def test_validate_enum(self):
        """测试枚举验证"""
        class EnumTool(Tool):
            name = "enum"
            description = "Test"
            parameters = {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["active", "inactive"]},
                },
                "required": ["status"],
            }
            async def execute(self, **kwargs):
                return "ok"
        
        tool = EnumTool()
        
        # 有效枚举
        errors = tool.validate_params({"status": "active"})
        assert errors == []
        
        # 无效枚举
        errors = tool.validate_params({"status": "deleted"})
        assert len(errors) > 0
        # 检查是否有枚举相关的错误
        assert any("必须是以下之一" in e or "enum" in e for e in errors)
