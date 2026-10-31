"""ai_models schema：category 分型、is_enabled（选中模型 ID）、system_one↔laya 校验"""

import pytest
from pydantic import ValidationError

from ai.config.schemas import AIModelCreate, AIModelQueryParams, AIModelUpdate


def test_create_defaults_to_system_two():
    m = AIModelCreate(provider="openai", name="gpt", api_key="sk-x")
    assert m.category == "system_two"
    assert m.is_enabled is None


def test_system_one_requires_laya_provider():
    with pytest.raises(ValidationError, match="system_one"):
        AIModelCreate(provider="openai", name="oops", api_key="sk-x", category="system_one")


def test_system_one_with_laya_ok():
    m = AIModelCreate(
        provider="laya",
        name="laya",
        api_key="",
        category="system_one",
        api_host="http://127.0.0.1:8787",
        models=["laya"],
    )
    assert m.category == "system_one"
    assert m.is_enabled is None


def test_is_enabled_is_selected_model_id():
    # is_enabled 在 system_config 体系里表示「选中的模型 ID」，不是布尔开关
    m = AIModelCreate(provider="openai", name="gpt", api_key="sk-x", is_enabled="gpt-4")
    assert m.is_enabled == "gpt-4"

    q = AIModelQueryParams(is_enabled="gpt-4")
    assert q.is_enabled == "gpt-4"

    with pytest.raises(ValidationError):
        AIModelQueryParams(is_enabled=True)


def test_update_partial_category_without_provider_is_allowed():
    u = AIModelUpdate(category="system_two")
    assert u.category == "system_two"
