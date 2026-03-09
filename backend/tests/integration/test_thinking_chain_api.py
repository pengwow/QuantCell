#!/usr/bin/env python3
"""思维链API集成测试

使用pytest和TestClient测试思维链RESTful API
"""
import json
import tempfile
import os
from io import BytesIO

import pytest
from fastapi.testclient import TestClient


# 使用已有的测试客户端fixture
@pytest.fixture
def client():
    """创建测试客户端"""
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    """获取认证token"""
    # 先登录获取token
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    response = client.post("/api/auth/login", data=login_data)
    if response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            token = data["data"]["access_token"]
            return {"Authorization": f"Bearer {token}"}
    return {}


class TestThinkingChainAPI:
    """思维链API测试类"""

    def test_get_thinking_chains_empty(self, client, auth_headers):
        """测试获取空的思维链列表"""
        response = client.get("/api/ai-models/strategy/thinking-chains", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        assert "items" in data["data"]

    def test_create_thinking_chain(self, client, auth_headers):
        """测试创建思维链"""
        payload = {
            "chain_type": "strategy_generation",
            "name": "API测试思维链",
            "description": "用于API测试的思维链",
            "steps": [
                {"key": "step_1", "title": "需求分析", "description": "分析用户需求", "order": 1},
                {"key": "step_2", "title": "策略设计", "description": "设计策略逻辑", "order": 2},
                {"key": "step_3", "title": "代码生成", "description": "生成策略代码", "order": 3}
            ],
            "is_active": True
        }

        response = client.post(
            "/api/ai-models/strategy/thinking-chains",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        assert data["data"]["name"] == payload["name"]
        assert data["data"]["chain_type"] == payload["chain_type"]
        assert len(data["data"]["steps"]) == 3

        return data["data"]["id"]

    def test_get_thinking_chain_detail(self, client, auth_headers):
        """测试获取单个思维链详情"""
        # 先创建
        payload = {
            "chain_type": "strategy_generation",
            "name": "详情测试思维链",
            "description": "测试详情获取",
            "steps": [{"key": "step_1", "title": "步骤1", "description": "第一步", "order": 1}],
            "is_active": True
        }

        create_response = client.post(
            "/api/ai-models/strategy/thinking-chains",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload
        )

        chain_id = create_response.json()["data"]["id"]

        # 再获取详情
        response = client.get(f"/api/ai-models/strategy/thinking-chains/{chain_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["id"] == chain_id

    def test_update_thinking_chain(self, client, auth_headers):
        """测试更新思维链"""
        # 先创建
        payload = {
            "chain_type": "strategy_generation",
            "name": "更新测试思维链",
            "description": "测试更新前",
            "steps": [{"key": "step_1", "title": "步骤1", "description": "第一步", "order": 1}],
            "is_active": True
        }

        create_response = client.post(
            "/api/ai-models/strategy/thinking-chains",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload
        )

        chain_id = create_response.json()["data"]["id"]

        # 更新
        update_payload = {
            "name": "更新后的名称",
            "description": "更新后的描述",
            "is_active": False
        }

        response = client.put(
            f"/api/ai-models/strategy/thinking-chains/{chain_id}",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=update_payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["name"] == update_payload["name"]
        assert data["data"]["description"] == update_payload["description"]
        assert data["data"]["is_active"] == update_payload["is_active"]

    def test_delete_thinking_chain(self, client, auth_headers):
        """测试删除思维链"""
        # 先创建
        payload = {
            "chain_type": "strategy_generation",
            "name": "删除测试思维链",
            "description": "测试删除",
            "steps": [{"key": "step_1", "title": "步骤1", "description": "第一步", "order": 1}],
            "is_active": True
        }

        create_response = client.post(
            "/api/ai-models/strategy/thinking-chains",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload
        )

        chain_id = create_response.json()["data"]["id"]

        # 删除
        response = client.delete(f"/api/ai-models/strategy/thinking-chains/{chain_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

        # 确认已删除
        get_response = client.get(f"/api/ai-models/strategy/thinking-chains/{chain_id}", headers=auth_headers)
        assert get_response.status_code == 404

    def test_import_thinking_chains_from_toml(self, client, auth_headers):
        """测试从TOML导入思维链"""
        toml_content = """
[[thinking_chain]]
chain_type = "strategy_generation"
name = "TOML导入测试思维链"
description = "从TOML文件导入的思维链"
is_active = true

[[thinking_chain.steps]]
key = "analyze"
title = "需求分析"
description = "分析用户策略需求"
order = 1

[[thinking_chain.steps]]
key = "design"
title = "策略设计"
description = "设计交易策略逻辑"
order = 2
"""

        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(toml_content)
            temp_file = f.name

        try:
            with open(temp_file, 'rb') as f:
                response = client.post(
                    "/api/ai-models/strategy/thinking-chains/import",
                    headers=auth_headers,
                    files={"file": ("test.toml", f, "application/toml")},
                    params={"update_existing": "true"}
                )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert "data" in data
            result = data["data"]
            assert result["created"] >= 1 or result["updated"] >= 1
        finally:
            os.unlink(temp_file)

    def test_filter_thinking_chains_by_type(self, client, auth_headers):
        """测试按类型筛选思维链"""
        # 创建不同类型的思维链
        payload1 = {
            "chain_type": "strategy_generation",
            "name": "策略生成思维链",
            "description": "策略类型",
            "steps": [{"key": "step_1", "title": "步骤1", "description": "第一步", "order": 1}],
            "is_active": True
        }

        payload2 = {
            "chain_type": "indicator_generation",
            "name": "指标生成思维链",
            "description": "指标类型",
            "steps": [{"key": "step_1", "title": "步骤1", "description": "第一步", "order": 1}],
            "is_active": True
        }

        client.post(
            "/api/ai-models/strategy/thinking-chains",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload1
        )

        client.post(
            "/api/ai-models/strategy/thinking-chains",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload2
        )

        # 筛选 strategy_generation 类型
        response = client.get(
            "/api/ai-models/strategy/thinking-chains",
            headers=auth_headers,
            params={"chain_type": "strategy_generation"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        items = data["data"]["items"]
        for item in items:
            assert item["chain_type"] == "strategy_generation"

    def test_get_thinking_chain_not_found(self, client, auth_headers):
        """测试获取不存在的思维链"""
        response = client.get("/api/ai-models/strategy/thinking-chains/non-existent-id", headers=auth_headers)
        assert response.status_code == 404

    def test_create_thinking_chain_missing_required_fields(self, client, auth_headers):
        """测试创建缺少必需字段的思维链"""
        payload = {
            "name": "缺少chain_type的思维链"
            # 缺少 chain_type 和 steps
        }

        response = client.post(
            "/api/ai-models/strategy/thinking-chains",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1  # 应该返回错误


class TestThinkingChainTomlValidation:
    """TOML导入验证测试"""

    def test_import_invalid_toml(self, client, auth_headers):
        """测试导入无效的TOML"""
        invalid_toml = "invalid toml content [["

        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(invalid_toml)
            temp_file = f.name

        try:
            with open(temp_file, 'rb') as f:
                response = client.post(
                    "/api/ai-models/strategy/thinking-chains/import",
                    headers=auth_headers,
                    files={"file": ("invalid.toml", f, "application/toml")}
                )

            assert response.status_code == 200
            data = response.json()
            # 导入失败应该返回 code=1
            assert data["code"] == 1 or (data["code"] == 0 and data["data"]["success"] == False)
        finally:
            os.unlink(temp_file)

    def test_import_toml_missing_required_fields(self, client, auth_headers):
        """测试导入缺少必需字段的TOML"""
        toml_content = """
[[thinking_chain]]
name = "缺少类型"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(toml_content)
            temp_file = f.name

        try:
            with open(temp_file, 'rb') as f:
                response = client.post(
                    "/api/ai-models/strategy/thinking-chains/import",
                    headers=auth_headers,
                    files={"file": ("incomplete.toml", f, "application/toml")}
                )

            assert response.status_code == 200
            data = response.json()
            # 应该有失败记录
            if data["code"] == 0:
                assert data["data"]["failed"] >= 1
        finally:
            os.unlink(temp_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
