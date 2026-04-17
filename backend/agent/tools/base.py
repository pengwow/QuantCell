"""Agent 工具基类定义"""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """
    Agent 工具抽象基类
    
    所有工具必须继承此类并实现必要的方法
    """

    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，用于 LLM 调用"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema 格式的参数定义"""
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        执行工具
        
        Args:
            **kwargs: 工具特定参数
            
        Returns:
            执行结果的字符串表示
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """验证参数是否符合 schema"""
        if not isinstance(params, dict):
            return [f"参数必须是对象，得到 {type(params).__name__}"]
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema 必须是 object 类型，得到 {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        t, label = schema.get("type"), path or "参数"
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} 应该是 {t}"]

        errors = []
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} 必须是以下之一: {schema['enum']}")
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} 必须 >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} 必须 <= {schema['maximum']}")
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} 至少需要 {schema['minLength']} 个字符")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} 最多 {schema['maxLength']} 个字符")
        if t == "object":
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"缺少必需的 {path + '.' + k if path else k}")
            for k, v in val.items():
                if k in props:
                    errors.extend(self._validate(v, props[k], path + "." + k if path else k))
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(
                    self._validate(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]")
                )
        return errors

    def to_schema(self) -> dict[str, Any]:
        """转换为 OpenAI 函数调用格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
