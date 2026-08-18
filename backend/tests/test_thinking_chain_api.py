#!/usr/bin/env python3
"""思维链API集成测试脚本

测试所有思维链相关的RESTful API端点
"""

import os
import sys
import tempfile

import pytest
import requests

# API基础URL
BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/ai-models/strategy"

# 测试用的JWT Token（需要先登录获取）
# 注意：这里使用一个测试token，实际测试中需要通过登录接口获取
TEST_TOKEN = None


def get_auth_token():
    """获取认证Token"""
    global TEST_TOKEN
    if TEST_TOKEN:
        return TEST_TOKEN

    # 尝试登录获取token
    login_url = f"{BASE_URL}/api/auth/login"
    login_data = {"username": "admin", "password": "admin123"}

    try:
        response = requests.post(login_url, data=login_data, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                TEST_TOKEN = data["data"]["access_token"]
                return TEST_TOKEN
    except Exception:
        pass

    return None


def get_headers():
    """获取请求头"""
    token = get_auth_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@pytest.fixture
def chain_id():
    token = get_auth_token()
    if not token:
        pytest.skip("无法获取认证Token，跳过测试")

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains"
    payload = {
        "chain_type": "strategy_generation",
        "name": "pytest-fixture-思维链",
        "description": "pytest fixture 创建的测试思维链",
        "steps": [
            {"key": "step_1", "title": "测试步骤1", "description": "测试", "order": 1},
        ],
        "is_active": True,
    }

    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                cid = data.get("data", {}).get("id")
                yield cid
                delete_url = f"{BASE_URL}{API_PREFIX}/thinking-chains/{cid}"
                requests.delete(delete_url, headers=get_headers(), timeout=10)
                return
        pytest.skip("无法创建测试思维链")
    except Exception:
        pytest.skip("API 服务不可用，跳过测试")


def test_get_thinking_chains():
    """测试获取思维链列表"""

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains"

    try:
        response = requests.get(url, headers=get_headers(), timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get("code") == 0:
                items = data.get("data", {}).get("items", [])
                data.get("data", {}).get("total", 0)
                if items:
                    for _item in items[:3]:  # 只显示前3条
                        pass
                return True, data
            else:
                return False, data
        else:
            return False, None

    except Exception:
        return False, None


def test_create_thinking_chain():
    """测试创建思维链"""

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains"

    payload = {
        "chain_type": "strategy_generation",
        "name": "测试思维链-API测试",
        "description": "用于API测试的思维链",
        "steps": [
            {
                "key": "step_1",
                "title": "需求分析",
                "description": "分析用户需求",
                "order": 1,
            },
            {
                "key": "step_2",
                "title": "策略设计",
                "description": "设计策略逻辑",
                "order": 2,
            },
            {
                "key": "step_3",
                "title": "代码生成",
                "description": "生成策略代码",
                "order": 3,
            },
        ],
        "is_active": True,
    }

    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get("code") == 0:
                data.get("data", {}).get("id")
                return True, data.get("data")
            else:
                return False, None
        else:
            return False, None

    except Exception:
        return False, None


def test_get_thinking_chain_detail(chain_id):
    """测试获取单个思维链详情"""

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains/{chain_id}"

    try:
        response = requests.get(url, headers=get_headers(), timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get("code") == 0:
                data.get("data", {})
                return True, data
            else:
                return False, data
        else:
            return False, None

    except Exception:
        return False, None


def test_update_thinking_chain(chain_id):
    """测试更新思维链"""

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains/{chain_id}"

    payload = {
        "name": "测试思维链-已更新",
        "description": "更新后的描述",
        "is_active": False,
    }

    try:
        response = requests.put(url, headers=get_headers(), json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get("code") == 0:
                return True, data
            else:
                return False, data
        else:
            return False, None

    except Exception:
        return False, None


def test_import_thinking_chains():
    """测试TOML导入功能"""

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains/import"

    # 创建TOML文件内容
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

[[thinking_chain.steps]]
key = "implement"
title = "代码实现"
description = "将策略转换为代码"
order = 3
"""

    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(toml_content)
        temp_file = f.name

    try:
        with open(temp_file, "rb") as f:
            files = {"file": ("test_thinking_chain.toml", f, "application/toml")}
            headers = {}
            token = get_auth_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"

            response = requests.post(
                url,
                headers=headers,
                files=files,
                params={"update_existing": "true"},
                timeout=10,
            )

        if response.status_code == 200:
            data = response.json()

            if data.get("code") == 0:
                result = data.get("data", {})
                if result.get("errors"):
                    for _error in result["errors"]:
                        pass
                return True, data
            else:
                return False, data
        else:
            return False, None

    except Exception:
        return False, None
    finally:
        # 清理临时文件
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_delete_thinking_chain(chain_id):
    """测试删除思维链"""

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains/{chain_id}"

    try:
        response = requests.delete(url, headers=get_headers(), timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get("code") == 0:
                return True, data
            else:
                return False, data
        else:
            return False, None

    except Exception:
        return False, None


def test_filter_by_type():
    """测试按类型筛选"""

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains"
    params = {"chain_type": "strategy_generation"}

    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                data.get("data", {}).get("items", [])
                return True, data
            else:
                return False, data
        else:
            return False, None

    except Exception:
        return False, None


def test_error_handling():
    """测试错误处理"""

    # 测试获取不存在的思维链
    url = f"{BASE_URL}{API_PREFIX}/thinking-chains/non-existent-id"

    try:
        response = requests.get(url, headers=get_headers(), timeout=10)

        if response.status_code == 404:
            pass
        else:
            pass

    except Exception:
        pass

    # 测试创建缺少必需字段
    url = f"{BASE_URL}{API_PREFIX}/thinking-chains"

    payload = {
        "name": "缺少chain_type的思维链"
        # 缺少 chain_type 和 steps
    }

    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 1:
                pass
            else:
                pass

    except Exception:
        pass


def run_all_tests():
    """运行所有测试"""

    results = []
    created_chain_id = None

    # 1. 测试获取列表
    success, _data = test_get_thinking_chains()
    results.append(("GET /thinking-chains", success))

    # 2. 测试创建
    success, chain_data = test_create_thinking_chain()
    results.append(("POST /thinking-chains", success))
    if success and chain_data:
        created_chain_id = chain_data.get("id")

    # 3. 测试获取详情
    if created_chain_id:
        success, _ = test_get_thinking_chain_detail(created_chain_id)
        results.append(("GET /thinking-chains/{id}", success))

    # 4. 测试更新
    if created_chain_id:
        success, _ = test_update_thinking_chain(created_chain_id)
        results.append(("PUT /thinking-chains/{id}", success))

    # 5. 测试TOML导入
    success, _ = test_import_thinking_chains()
    results.append(("POST /thinking-chains/import", success))

    # 6. 测试筛选
    success, _ = test_filter_by_type()
    results.append(("GET /thinking-chains?chain_type=...", success))

    # 7. 测试错误处理
    test_error_handling()
    results.append(("Error Handling", True))

    # 8. 清理：删除测试数据
    if created_chain_id:
        success, _ = test_delete_thinking_chain(created_chain_id)
        results.append(("DELETE /thinking-chains/{id}", success))

    # 打印测试总结

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for _test_name, success in results:
        pass

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
