"""get_agent LLM 配置签名热替换回归（2026-11-26 用户踩坑）。

修复前：_agent_instance 进程级单例只在首次调用读 system_config，设置页保存新模型后
会话仍用旧快照请求，报错文案永远显示旧模型。
修复后：每次调用重读 ai_model.* 做签名（provider|host|key|model）比对，变化即热替换
llm_backend/model，实例复用（会话历史与工具注册不丢）。
"""

import sys
import tempfile
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import agent.core.factory as f


class FakeAgent:
    def __init__(self, llm_backend, workspace, model, **kwargs):
        self.llm_backend = llm_backend
        self.model = model
        self.workspace = workspace

    def register_tool(self, tool):
        pass


@pytest.fixture()
def factory_env(monkeypatch):
    built = []
    monkeypatch.setattr(
        f, "create_llm_backend", lambda **kw: (built.append(kw["model"]), types.SimpleNamespace(model=kw["model"]))[1]
    )
    cfg = {"cfg": None}
    monkeypatch.setattr(f, "get_ai_config", lambda: cfg["cfg"])
    monkeypatch.setattr(f, "AgentLoop", FakeAgent)
    import agent.tools

    monkeypatch.setattr(agent.tools, "create_registry", lambda ws: types.SimpleNamespace(_tools={}))
    monkeypatch.setattr(f, "get_persistent_dir", lambda *a: Path(tempfile.mkdtemp()))
    f._agent_instance = None
    f._agent_signature = None
    return {"built": built, "cfg": cfg}


def _ai_config(model, host="http://10.36.35.120:18888/v1"):
    return {
        "provider": {"id": "openai-compatible", "name": "OpenAI兼容API", "api_host": host, "api_key": "k"},
        "enabled_model": {"id": model, "name": model},
    }


def test_first_build_uses_config(factory_env):
    factory_env["cfg"]["cfg"] = _ai_config("m1")
    agent = f.get_agent()
    assert agent.model == "m1"
    assert factory_env["built"] == ["m1"]


def test_same_config_reuses_instance(factory_env):
    factory_env["cfg"]["cfg"] = _ai_config("m1")
    a1 = f.get_agent()
    assert f.get_agent() is a1
    assert factory_env["built"] == ["m1"]


def test_model_change_hotswaps_backend(factory_env):
    factory_env["cfg"]["cfg"] = _ai_config("m1")
    a1 = f.get_agent()
    factory_env["cfg"]["cfg"] = _ai_config("GLM-5.3-Flash")
    a2 = f.get_agent()
    assert a2 is a1, "实例必须复用（会话历史/工具注册不丢）"
    assert a1.model == "GLM-5.3-Flash"
    assert factory_env["built"] == ["m1", "GLM-5.3-Flash"]


def test_host_change_hotswaps_backend(factory_env):
    factory_env["cfg"]["cfg"] = _ai_config("m1")
    f.get_agent()
    factory_env["cfg"]["cfg"] = _ai_config("m1", host="http://newhost/v1")
    f.get_agent()
    assert len(factory_env["built"]) == 2


def test_fallback_to_env_when_config_removed(factory_env):
    factory_env["cfg"]["cfg"] = _ai_config("m1")
    a1 = f.get_agent()
    factory_env["cfg"]["cfg"] = None
    a2 = f.get_agent()
    assert a2 is a1
    assert a2.model == "gpt-4o-mini"
