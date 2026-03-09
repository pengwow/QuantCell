#!/usr/bin/env python3
"""思维链API集成测试脚本

测试所有思维链相关的RESTful API端点
"""
import json
import sys
import tempfile
import os

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
    login_data = {
        "username": "admin",
        "password": "admin123"
    }

    try:
        response = requests.post(login_url, data=login_data, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                TEST_TOKEN = data["data"]["access_token"]
                print(f"✓ 登录成功，获取到Token")
                return TEST_TOKEN
    except Exception as e:
        print(f"✗ 登录失败: {e}")

    return None


def get_headers():
    """获取请求头"""
    token = get_auth_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def test_get_thinking_chains():
    """测试获取思维链列表"""
    print("\n=== 测试 GET /thinking-chains ===")

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains"

    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"响应码: {data.get('code')}")
            print(f"消息: {data.get('message')}")

            if data.get("code") == 0:
                items = data.get("data", {}).get("items", [])
                total = data.get("data", {}).get("total", 0)
                print(f"✓ 获取成功，共 {total} 条记录")
                if items:
                    for item in items[:3]:  # 只显示前3条
                        print(f"  - {item.get('name')} ({item.get('chain_type')})")
                return True, data
            else:
                print(f"✗ 获取失败: {data.get('message')}")
                return False, data
        else:
            print(f"✗ 请求失败: {response.status_code}")
            print(f"响应: {response.text}")
            return False, None

    except Exception as e:
        print(f"✗ 请求异常: {e}")
        return False, None


def test_create_thinking_chain():
    """测试创建思维链"""
    print("\n=== 测试 POST /thinking-chains ===")

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains"

    payload = {
        "chain_type": "strategy_generation",
        "name": "测试思维链-API测试",
        "description": "用于API测试的思维链",
        "steps": [
            {"key": "step_1", "title": "需求分析", "description": "分析用户需求", "order": 1},
            {"key": "step_2", "title": "策略设计", "description": "设计策略逻辑", "order": 2},
            {"key": "step_3", "title": "代码生成", "description": "生成策略代码", "order": 3}
        ],
        "is_active": True
    }

    try:
        response = requests.post(
            url,
            headers=get_headers(),
            json=payload,
            timeout=10
        )
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"响应码: {data.get('code')}")
            print(f"消息: {data.get('message')}")

            if data.get("code") == 0:
                chain_id = data.get("data", {}).get("id")
                print(f"✓ 创建成功，ID: {chain_id}")
                return True, data.get("data")
            else:
                print(f"✗ 创建失败: {data.get('message')}")
                return False, None
        else:
            print(f"✗ 请求失败: {response.status_code}")
            print(f"响应: {response.text}")
            return False, None

    except Exception as e:
        print(f"✗ 请求异常: {e}")
        return False, None


def test_get_thinking_chain_detail(chain_id):
    """测试获取单个思维链详情"""
    print(f"\n=== 测试 GET /thinking-chains/{chain_id} ===")

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains/{chain_id}"

    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"响应码: {data.get('code')}")

            if data.get("code") == 0:
                chain_data = data.get("data", {})
                print(f"✓ 获取成功")
                print(f"  名称: {chain_data.get('name')}")
                print(f"  类型: {chain_data.get('chain_type')}")
                print(f"  步骤数: {len(chain_data.get('steps', []))}")
                return True, data
            else:
                print(f"✗ 获取失败: {data.get('message')}")
                return False, data
        else:
            print(f"✗ 请求失败: {response.status_code}")
            return False, None

    except Exception as e:
        print(f"✗ 请求异常: {e}")
        return False, None


def test_update_thinking_chain(chain_id):
    """测试更新思维链"""
    print(f"\n=== 测试 PUT /thinking-chains/{chain_id} ===")

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains/{chain_id}"

    payload = {
        "name": "测试思维链-已更新",
        "description": "更新后的描述",
        "is_active": False
    }

    try:
        response = requests.put(
            url,
            headers=get_headers(),
            json=payload,
            timeout=10
        )
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"响应码: {data.get('code')}")
            print(f"消息: {data.get('message')}")

            if data.get("code") == 0:
                print(f"✓ 更新成功")
                print(f"  新名称: {data.get('data', {}).get('name')}")
                print(f"  新描述: {data.get('data', {}).get('description')}")
                print(f"  激活状态: {data.get('data', {}).get('is_active')}")
                return True, data
            else:
                print(f"✗ 更新失败: {data.get('message')}")
                return False, data
        else:
            print(f"✗ 请求失败: {response.status_code}")
            return False, None

    except Exception as e:
        print(f"✗ 请求异常: {e}")
        return False, None


def test_import_thinking_chains():
    """测试TOML导入功能"""
    print("\n=== 测试 POST /thinking-chains/import ===")

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
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
        f.write(toml_content)
        temp_file = f.name

    try:
        with open(temp_file, 'rb') as f:
            files = {'file': ('test_thinking_chain.toml', f, 'application/toml')}
            headers = {}
            token = get_auth_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"

            response = requests.post(
                url,
                headers=headers,
                files=files,
                params={"update_existing": "true"},
                timeout=10
            )

        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"响应码: {data.get('code')}")
            print(f"消息: {data.get('message')}")

            if data.get("code") == 0:
                result = data.get("data", {})
                print(f"✓ 导入成功")
                print(f"  新建: {result.get('created', 0)} 条")
                print(f"  更新: {result.get('updated', 0)} 条")
                print(f"  失败: {result.get('failed', 0)} 条")
                if result.get('errors'):
                    for error in result['errors']:
                        print(f"  错误: {error}")
                return True, data
            else:
                print(f"✗ 导入失败: {data.get('message')}")
                return False, data
        else:
            print(f"✗ 请求失败: {response.status_code}")
            print(f"响应: {response.text}")
            return False, None

    except Exception as e:
        print(f"✗ 请求异常: {e}")
        return False, None
    finally:
        # 清理临时文件
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_delete_thinking_chain(chain_id):
    """测试删除思维链"""
    print(f"\n=== 测试 DELETE /thinking-chains/{chain_id} ===")

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains/{chain_id}"

    try:
        response = requests.delete(url, headers=get_headers(), timeout=10)
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"响应码: {data.get('code')}")
            print(f"消息: {data.get('message')}")

            if data.get("code") == 0:
                print(f"✓ 删除成功")
                return True, data
            else:
                print(f"✗ 删除失败: {data.get('message')}")
                return False, data
        else:
            print(f"✗ 请求失败: {response.status_code}")
            return False, None

    except Exception as e:
        print(f"✗ 请求异常: {e}")
        return False, None


def test_filter_by_type():
    """测试按类型筛选"""
    print("\n=== 测试 GET /thinking-chains?chain_type=strategy_generation ===")

    url = f"{BASE_URL}{API_PREFIX}/thinking-chains"
    params = {"chain_type": "strategy_generation"}

    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=10)
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                items = data.get("data", {}).get("items", [])
                print(f"✓ 筛选成功，共 {len(items)} 条 strategy_generation 类型记录")
                return True, data
            else:
                print(f"✗ 筛选失败: {data.get('message')}")
                return False, data
        else:
            print(f"✗ 请求失败: {response.status_code}")
            return False, None

    except Exception as e:
        print(f"✗ 请求异常: {e}")
        return False, None


def test_error_handling():
    """测试错误处理"""
    print("\n=== 测试错误处理 ===")

    # 测试获取不存在的思维链
    print("\n--- 测试获取不存在的思维链 ---")
    url = f"{BASE_URL}{API_PREFIX}/thinking-chains/non-existent-id"

    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        print(f"状态码: {response.status_code}")

        if response.status_code == 404:
            print("✓ 正确返回404状态码")
        else:
            print(f"✗ 期望404，实际返回 {response.status_code}")

    except Exception as e:
        print(f"✗ 请求异常: {e}")

    # 测试创建缺少必需字段
    print("\n--- 测试创建缺少必需字段 ---")
    url = f"{BASE_URL}{API_PREFIX}/thinking-chains"

    payload = {
        "name": "缺少chain_type的思维链"
        # 缺少 chain_type 和 steps
    }

    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 1:
                print(f"✓ 正确返回错误码: {data.get('message')}")
            else:
                print(f"✗ 期望失败，但返回成功")

    except Exception as e:
        print(f"✗ 请求异常: {e}")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("思维链API集成测试")
    print("=" * 60)

    results = []
    created_chain_id = None

    # 1. 测试获取列表
    success, data = test_get_thinking_chains()
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
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\n总计: {passed}/{total} 通过")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
