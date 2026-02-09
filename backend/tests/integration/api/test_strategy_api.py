"""
策略管理API集成测试

测试策略相关的所有API端点，包括：
- 策略列表获取
- 策略详情获取
- 策略上传
- 策略执行
- 策略解析
- 策略删除（需要认证）
"""

import pytest
from fastapi.testclient import TestClient
from typing import Dict, Any


class TestStrategyListAPI:
    """策略列表API测试类"""
    
    # ========== 成功路径测试 ==========
    
    def test_get_strategy_list_success(self, client: TestClient):
        """测试获取策略列表成功"""
        response = client.get("/api/strategy/list")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        assert "strategies" in data["data"]
    
    @pytest.mark.parametrize("source", ["files", "db", None])
    def test_get_strategy_list_with_source(self, client: TestClient, source):
        """测试不同来源参数的策略列表获取"""
        params = {"source": source} if source else {}
        response = client.get("/api/strategy/list", params=params)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "strategies" in data["data"]
    
    # ========== 边界条件测试 ==========
    
    @pytest.mark.parametrize("source", ["", "invalid", "FILES", "DB", "files,db"])
    def test_get_strategy_list_invalid_source(self, client: TestClient, source):
        """测试无效来源参数处理"""
        response = client.get("/api/strategy/list", params={"source": source})
        # 根据实现，可能返回400或200（忽略无效参数）
        assert response.status_code in [200, 400]
        if response.status_code == 400:
            data = response.json()
            assert "无效的source参数" in str(data.get("detail", ""))
    
    def test_get_strategy_list_empty_source(self, client: TestClient):
        """测试空来源参数"""
        response = client.get("/api/strategy/list", params={"source": ""})
        assert response.status_code in [200, 400]
    
    # ========== 错误场景测试 ==========
    
    def test_get_strategy_list_service_error(self, client: TestClient, monkeypatch):
        """测试服务层异常处理"""
        def mock_get_strategy_list(source=None):
            raise Exception("服务异常")
        
        monkeypatch.setattr(
            "strategy.routes.get_strategy_service",
            lambda: type('MockService', (), {'get_strategy_list': mock_get_strategy_list})()
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data


class TestStrategyDetailAPI:
    """策略详情API测试类"""
    
    def test_get_strategy_detail_success(self, client: TestClient):
        """测试获取策略详情成功（如果策略存在）或404（如果策略不存在）"""
        request_data = {"strategy_name": "sma_cross"}
        response = client.post("/api/strategy/detail", json=request_data)
        # 策略可能不存在，接受200或404
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert data["code"] == 0
            assert "name" in data["data"] or "strategy" in data["data"]
    
    def test_get_strategy_detail_with_file_content(self, client: TestClient):
        """测试带文件内容的策略详情获取"""
        request_data = {
            "strategy_name": "test_strategy",
            "file_content": "class TestStrategy(Strategy):\n    pass"
        }
        response = client.post("/api/strategy/detail", json=request_data)
        assert response.status_code in [200, 404]
    
    def test_get_strategy_detail_not_found(self, client: TestClient):
        """测试策略不存在场景"""
        request_data = {"strategy_name": "non_existent_strategy_12345"}
        response = client.post("/api/strategy/detail", json=request_data)
        # 根据实现可能返回404或200（code=1）
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert data["code"] == 1 or "不存在" in data.get("message", "")
    
    @pytest.mark.parametrize("strategy_name", ["", "   ", None])
    def test_get_strategy_detail_invalid_name(self, client: TestClient, strategy_name):
        """测试无效策略名称"""
        request_data = {"strategy_name": strategy_name}
        response = client.post("/api/strategy/detail", json=request_data)
        # 应该返回422验证错误或404
        assert response.status_code in [400, 404, 422]
    
    def test_get_strategy_detail_missing_name(self, client: TestClient):
        """测试缺少策略名称"""
        response = client.post("/api/strategy/detail", json={})
        assert response.status_code == 422


class TestStrategyUploadAPI:
    """策略上传API测试类"""
    
    def test_upload_strategy_success(self, client: TestClient):
        """测试策略上传成功"""
        request_data = {
            "strategy_name": "test_strategy_upload",
            "file_content": (
                "class TestStrategy(Strategy):\n"
                "    '''测试策略'''\n"
                "    def next(self):\n"
                "        if self.data.close > self.data.open:\n"
                "            self.buy()\n"
            ),
            "version": "1.0.0",
            "description": "测试策略",
            "tags": ["test", "demo"]
        }
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
    
    def test_upload_strategy_update_existing(self, client: TestClient):
        """测试更新现有策略"""
        request_data = {
            "id": 1,
            "strategy_name": "existing_strategy",
            "file_content": "class UpdatedStrategy(Strategy):\n    pass",
            "version": "2.0.0",
            "description": "更新后的策略"
        }
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code == 200
    
    def test_upload_strategy_minimal_data(self, client: TestClient):
        """测试最小数据上传"""
        request_data = {
            "strategy_name": "minimal_strategy",
            "file_content": "class MinimalStrategy(Strategy):\n    pass"
        }
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code == 200
    
    # ========== 请求体验证测试 ==========
    
    @pytest.mark.parametrize("missing_field", ["strategy_name", "file_content"])
    def test_upload_strategy_missing_required_field(self, client: TestClient, missing_field):
        """测试缺少必填字段"""
        request_data = {
            "strategy_name": "test",
            "file_content": "class Test(Strategy): pass"
        }
        del request_data[missing_field]
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code == 422
    
    def test_upload_strategy_empty_content(self, client: TestClient):
        """测试空文件内容"""
        request_data = {
            "strategy_name": "empty_strategy",
            "file_content": ""
        }
        response = client.post("/api/strategy/upload", json=request_data)
        # 可能接受空内容或返回错误
        assert response.status_code in [200, 400, 422]
    
    def test_upload_strategy_invalid_content_type(self, client: TestClient):
        """测试无效内容类型"""
        response = client.post(
            "/api/strategy/upload",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422


class TestStrategyExecuteAPI:
    """策略执行API测试类"""
    
    def test_execute_strategy_backtest_mode(self, client: TestClient):
        """测试回测模式执行策略"""
        request_data = {
            "params": {"n1": 10, "n2": 20},
            "mode": "backtest",
            "backtest_config": {
                "start_date": "2023-01-01",
                "end_date": "2023-12-31",
                "initial_capital": 100000.0
            }
        }
        response = client.post("/api/strategy/sma_cross/execute", json=request_data)
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "execution_id" in data.get("data", {})
    
    def test_execute_strategy_live_mode(self, client: TestClient):
        """测试实盘模式执行策略"""
        request_data = {
            "params": {"n1": 10, "n2": 20},
            "mode": "live"
        }
        response = client.post("/api/strategy/sma_cross/execute", json=request_data)
        assert response.status_code in [200, 404]
    
    def test_execute_strategy_not_found(self, client: TestClient):
        """测试执行不存在的策略"""
        request_data = {
            "params": {},
            "mode": "backtest"
        }
        response = client.post("/api/strategy/non_existent_strategy_12345/execute", json=request_data)
        assert response.status_code == 404
    
    @pytest.mark.parametrize("mode", ["invalid_mode", "", None])
    def test_execute_strategy_invalid_mode(self, client: TestClient, mode):
        """测试无效执行模式"""
        request_data = {
            "params": {},
            "mode": mode
        }
        response = client.post("/api/strategy/sma_cross/execute", json=request_data)
        # 应该返回422验证错误
        assert response.status_code in [400, 422]
    
    def test_execute_strategy_missing_mode(self, client: TestClient):
        """测试缺少执行模式"""
        request_data = {"params": {}}
        response = client.post("/api/strategy/sma_cross/execute", json=request_data)
        assert response.status_code == 422
    
    def test_execute_strategy_invalid_params(self, client: TestClient):
        """测试无效参数"""
        request_data = {
            "params": "invalid_params_type",
            "mode": "backtest"
        }
        response = client.post("/api/strategy/sma_cross/execute", json=request_data)
        assert response.status_code == 422


class TestStrategyParseAPI:
    """策略解析API测试类"""
    
    def test_parse_strategy_success(self, client: TestClient):
        """测试解析策略成功"""
        request_data = {
            "strategy_name": "test_strategy",
            "file_content": (
                "class TestStrategy(Strategy):\n"
                "    '''测试策略描述'''\n"
                "    params = {'n1': 10, 'n2': 20}\n"
                "    def next(self):\n"
                "        pass\n"
            )
        }
        response = client.post("/api/strategy/parse", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
    
    def test_parse_strategy_missing_content(self, client: TestClient):
        """测试缺少文件内容"""
        request_data = {"strategy_name": "test_strategy"}
        response = client.post("/api/strategy/parse", json=request_data)
        assert response.status_code == 422
    
    def test_parse_strategy_empty_content(self, client: TestClient):
        """测试空文件内容"""
        request_data = {
            "strategy_name": "test_strategy",
            "file_content": ""
        }
        response = client.post("/api/strategy/parse", json=request_data)
        # 可能接受或返回错误
        assert response.status_code in [200, 400, 422]


class TestStrategyDeleteAPI:
    """策略删除API测试类（需要认证）"""
    
    def test_delete_strategy_success(self, client: TestClient, auth_headers):
        """测试删除策略成功"""
        # 先创建一个测试策略
        upload_data = {
            "strategy_name": "strategy_to_delete",
            "file_content": "class StrategyToDelete(Strategy):\n    pass"
        }
        client.post("/api/strategy/upload", json=upload_data)
        
        # 删除策略
        response = client.delete(
            "/api/strategy/strategy_to_delete",
            headers=auth_headers
        )
        assert response.status_code in [200, 401]
        if response.status_code == 200:
            data = response.json()
            assert data.get("code") == 0 or "success" in str(data).lower()
    
    # ========== 认证测试 ==========
    
    def test_delete_strategy_without_auth(self, client: TestClient):
        """测试未认证访问"""
        response = client.delete("/api/strategy/test_strategy")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "未提供认证令牌" in str(data.get("detail", ""))
    
    def test_delete_strategy_with_invalid_token(self, client: TestClient, invalid_auth_headers):
        """测试无效令牌"""
        response = client.delete(
            "/api/strategy/test_strategy",
            headers=invalid_auth_headers
        )
        assert response.status_code == 401
    
    def test_delete_strategy_with_expired_token(self, client: TestClient, expired_auth_headers):
        """测试过期令牌"""
        response = client.delete(
            "/api/strategy/test_strategy",
            headers=expired_auth_headers
        )
        assert response.status_code == 401
        data = response.json()
        assert "令牌已过期" in str(data.get("detail", ""))
    
    def test_delete_strategy_malformed_token(self, client: TestClient, malformed_auth_headers):
        """测试格式错误的令牌"""
        response = client.delete(
            "/api/strategy/test_strategy",
            headers=malformed_auth_headers
        )
        assert response.status_code == 401
    
    def test_delete_strategy_missing_bearer(self, client: TestClient, missing_auth_headers):
        """测试缺少Bearer前缀"""
        response = client.delete(
            "/api/strategy/test_strategy",
            headers=missing_auth_headers
        )
        assert response.status_code == 401
        data = response.json()
        assert "无效的认证令牌格式" in str(data.get("detail", ""))
    
    def test_delete_strategy_not_found(self, client: TestClient, auth_headers):
        """测试删除不存在的策略"""
        response = client.delete(
            "/api/strategy/non_existent_strategy_12345",
            headers=auth_headers
        )
        # 可能返回404或200（code=1）
        assert response.status_code in [200, 401, 404]


class TestStrategyAPIEdgeCases:
    """策略API边界情况测试类"""
    
    @pytest.mark.parametrize("strategy_name", [
        "a",  # 单个字符
        "a" * 100,  # 长名称
        "strategy-with-dashes",  # 带横线
        "strategy_with_underscores",  # 带下划线
        "StrategyWithCamelCase",  # 驼峰命名
        "123numeric",  # 数字开头
    ])
    def test_strategy_name_variations(self, client: TestClient, strategy_name):
        """测试各种策略名称格式"""
        request_data = {
            "strategy_name": strategy_name,
            "file_content": f"class {strategy_name.title()}(Strategy):\n    pass"
        }
        response = client.post("/api/strategy/upload", json=request_data)
        # 应该接受或根据业务规则拒绝
        assert response.status_code in [200, 400]
    
    def test_strategy_with_special_characters(self, client: TestClient):
        """测试特殊字符的策略名称"""
        special_names = [
            "strategy with spaces",
            "strategy@symbol",
            "strategy#hash",
            "strategy$dollar",
        ]
        for name in special_names:
            request_data = {
                "strategy_name": name,
                "file_content": "class Test(Strategy):\n    pass"
            }
            response = client.post("/api/strategy/upload", json=request_data)
            # 可能接受或拒绝
            assert response.status_code in [200, 400]
    
    def test_strategy_with_unicode(self, client: TestClient):
        """测试Unicode字符的策略名称"""
        request_data = {
            "strategy_name": "测试策略",
            "file_content": "class TestStrategy(Strategy):\n    pass"
        }
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code in [200, 400]
    
    def test_strategy_large_file_content(self, client: TestClient):
        """测试大文件内容"""
        large_content = "class LargeStrategy(Strategy):\n    pass\n" + "# comment\n" * 1000
        request_data = {
            "strategy_name": "large_strategy",
            "file_content": large_content
        }
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code in [200, 413]  # 413 = Payload Too Large
    
    def test_concurrent_strategy_uploads(self, client: TestClient):
        """测试并发策略上传（简化版）"""
        import concurrent.futures
        
        def upload_strategy(index):
            request_data = {
                "strategy_name": f"concurrent_strategy_{index}",
                "file_content": f"class ConcurrentStrategy{index}(Strategy):\n    pass"
            }
            return client.post("/api/strategy/upload", json=request_data)
        
        # 使用线程池模拟并发
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(upload_strategy, i) for i in range(3)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # 所有请求都应该成功
        for response in results:
            assert response.status_code in [200, 409]  # 409 = Conflict
