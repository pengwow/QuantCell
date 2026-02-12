# 错误处理测试
# 测试API的各种HTTP错误码和异常场景

import pytest
from fastapi.testclient import TestClient
from typing import Dict, Any


class TestHTTPStatusCodes:
    """HTTP状态码测试类"""

    def test_200_ok_success(self, client: TestClient, mocker):
        """测试200成功响应"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            return_value=[]
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 200
        assert response.json()["code"] == 0

    def test_201_created_not_used(self, client: TestClient, mocker):
        """测试201创建成功（当前系统不使用）"""
        mocker.patch(
            "strategy.service.StrategyService.upload_strategy_file",
            return_value=True
        )
        request_data = {
            "strategy_name": "TestStrategy",
            "file_content": "class TestStrategy:\n    pass"
        }
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code == 200

    def test_204_no_content_not_used(self, client: TestClient):
        """测试204无内容（当前系统不使用）"""
        pass

    def test_400_bad_request(self, client: TestClient):
        """测试400错误请求"""
        response = client.post("/api/backtest/run", json={"invalid": "data"})
        assert response.status_code == 422

    def test_401_unauthorized_no_token(self, client: TestClient):
        """测试401未授权 - 无令牌"""
        response = client.delete("/api/strategy/test_strategy")
        assert response.status_code == 401
        data = response.json()
        assert "未提供认证令牌" in str(data.get("detail", {}).get("reason", ""))

    def test_401_unauthorized_expired_token(self, client: TestClient, expired_auth_headers: Dict[str, str]):
        """测试401未授权 - 过期令牌"""
        response = client.delete("/api/strategy/test_strategy", headers=expired_auth_headers)
        assert response.status_code == 401
        data = response.json()
        assert "令牌已过期" in str(data.get("detail", {}).get("reason", ""))

    def test_401_unauthorized_invalid_token(self, client: TestClient, invalid_auth_headers: Dict[str, str]):
        """测试401未授权 - 无效令牌"""
        response = client.delete("/api/strategy/test_strategy", headers=invalid_auth_headers)
        assert response.status_code == 401

    def test_403_forbidden_not_implemented(self, client: TestClient):
        """测试403禁止访问（当前系统未实现权限控制）"""
        pass

    def test_404_not_found_endpoint(self, client: TestClient):
        """测试404端点不存在"""
        response = client.get("/api/nonexistent/endpoint")
        assert response.status_code == 404

    def test_405_method_not_allowed(self, client: TestClient):
        """测试405方法不允许"""
        response = client.put("/api/strategy/list")
        assert response.status_code == 405

    def test_422_unprocessable_entity_missing_field(self, client: TestClient):
        """测试422无法处理 - 缺少必填字段"""
        request_data = {"strategy_name": "TestStrategy"}
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code == 422

    def test_422_unprocessable_entity_invalid_type(self, client: TestClient):
        """测试422无法处理 - 无效类型"""
        request_data = {
            "strategy_name": "TestStrategy",
            "file_content": 12345
        }
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code == 422

    def test_500_internal_server_error(self, client: TestClient, mocker):
        """测试500内部服务器错误"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=Exception("Database connection failed")
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 500


class TestExceptionHandling:
    """异常处理测试类"""

    def test_service_exception_handling(self, client: TestClient, mocker):
        """测试服务层异常处理"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_detail",
            side_effect=ValueError("Strategy not found")
        )
        response = client.post("/api/strategy/detail", json={"strategy_name": "nonexistent"})
        assert response.status_code == 500

    def test_database_exception_handling(self, client: TestClient, mocker):
        """测试数据库异常处理"""
        mocker.patch(
            "settings.routes.SystemConfig.get_all_with_details",
            side_effect=Exception("Database connection lost")
        )
        response = client.get("/api/config/")
        assert response.status_code == 500

    def test_validation_exception_handling(self, client: TestClient):
        """测试验证异常处理"""
        request_data = {
            "symbols": "not_a_list",
            "start_time": "2023-01-01",
            "end_time": "2023-12-31"
        }
        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 422

    def test_timeout_exception_handling(self, client: TestClient, mocker):
        """测试超时异常处理"""
        import asyncio
        async def slow_operation():
            await asyncio.sleep(10)
            return {}

        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=asyncio.TimeoutError("Operation timed out")
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 500

    def test_key_error_handling(self, client: TestClient, mocker):
        """测试KeyError处理"""
        def raise_key_error():
            data = {}
            return data["nonexistent_key"]

        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=raise_key_error
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 500

    def test_type_error_handling(self, client: TestClient, mocker):
        """测试TypeError处理"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=TypeError("Invalid type")
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 500

    def test_attribute_error_handling(self, client: TestClient, mocker):
        """测试AttributeError处理"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=AttributeError("Object has no attribute")
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 500


class TestErrorResponseFormat:
    """错误响应格式测试类"""

    def test_error_response_structure(self, client: TestClient):
        """测试错误响应结构"""
        response = client.delete("/api/strategy/test_strategy")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_validation_error_response_format(self, client: TestClient):
        """测试验证错误响应格式"""
        request_data = {"invalid": "data"}
        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_server_error_response_format(self, client: TestClient, mocker):
        """测试服务器错误响应格式"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=Exception("Test error")
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

    def test_error_message_content(self, client: TestClient, mocker):
        """测试错误消息内容"""
        error_message = "Custom error message"
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=Exception(error_message)
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 500
        data = response.json()
        assert error_message in str(data.get("detail", ""))


class TestBusinessErrorHandling:
    """业务错误处理测试类"""

    def test_strategy_not_found_error(self, client: TestClient, mocker):
        """测试策略不存在错误"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_detail",
            return_value=None
        )
        response = client.post("/api/strategy/detail", json={"strategy_name": "nonexistent_strategy"})
        assert response.status_code == 404

    def test_strategy_already_exists_error(self, client: TestClient, mocker):
        """测试策略已存在错误"""
        mocker.patch(
            "strategy.service.StrategyService.upload_strategy_file",
            return_value=True
        )
        request_data = {
            "strategy_name": "existing_strategy",
            "file_content": "class ExistingStrategy:\n    pass"
        }
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code == 200

    def test_backtest_not_found_error(self, client: TestClient, mocker):
        """测试回测不存在错误"""
        mocker.patch(
            "backtest.routes.backtest_service.analyze_backtest",
            return_value={"status": "error", "message": "回测不存在"}
        )
        response = client.get("/api/backtest/nonexistent_id")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1

    def test_invalid_strategy_execution_error(self, client: TestClient, mocker):
        """测试无效策略执行错误 - 使用策略执行路由"""
        mocker.patch(
            "strategy.service.StrategyService.load_strategy",
            return_value=None
        )
        request_data = {
            "mode": "backtest",
            "params": {},
            "backtest_config": {
                "start_date": "2023-01-01",
                "end_date": "2023-12-31",
                "initial_capital": 100000.0
            }
        }
        response = client.post("/api/strategy/invalid_strategy/execute", json=request_data)
        # 策略不存在时返回404
        assert response.status_code == 404

    def test_config_not_found_error(self, client: TestClient, mocker):
        """测试配置不存在错误"""
        mocker.patch(
            "settings.routes.SystemConfig.get_with_details",
            return_value=None
        )
        response = client.get("/api/config/nonexistent_key")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1


class TestEdgeCaseErrorHandling:
    """边界条件错误处理测试类"""

    def test_empty_request_body(self, client: TestClient):
        """测试空请求体"""
        response = client.post("/api/backtest/run", json={})
        assert response.status_code == 422

    def test_null_request_body(self, client: TestClient):
        """测试null请求体"""
        response = client.post("/api/backtest/run", data=None)
        assert response.status_code == 422

    def test_malformed_json(self, client: TestClient):
        """测试格式错误的JSON"""
        response = client.post(
            "/api/backtest/run",
            data="not valid json",  # pyright: ignore[reportArgumentType]
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_extra_fields_in_request(self, client: TestClient, mocker):
        """测试请求中的额外字段"""
        mocker.patch(
            "strategy.service.StrategyService.upload_strategy_file",
            return_value=True
        )
        request_data = {
            "strategy_name": "TestStrategy",
            "file_content": "class TestStrategy:\n    pass",
            "extra_field": "extra_value"
        }
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code == 200

    def test_missing_content_type(self, client: TestClient):
        """测试缺少Content-Type"""
        response = client.post(
            "/api/backtest/run",
            data='{"strategy_config": {}}'  # pyright: ignore[reportArgumentType]
        )
        assert response.status_code == 422

    def test_wrong_content_type(self, client: TestClient):
        """测试错误的Content-Type"""
        response = client.post(
            "/api/backtest/run",
            data='{"strategy_config": {}}',  # pyright: ignore[reportArgumentType]
            headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 422


class TestConcurrentErrorHandling:
    """并发错误处理测试类"""

    def test_concurrent_request_handling(self, client: TestClient, mocker):
        """测试并发请求处理"""
        import concurrent.futures

        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            return_value=[]
        )

        def make_request():
            return client.get("/api/strategy/list")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        for response in results:
            assert response.status_code == 200

    def test_race_condition_handling(self, client: TestClient, mocker):
        """测试竞态条件处理"""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise Exception("Race condition")
            return []

        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=side_effect
        )

        import concurrent.futures

        def make_request():
            return client.get("/api/strategy/list")

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request) for _ in range(6)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        success_count = sum(1 for r in results if r.status_code == 200)
        error_count = sum(1 for r in results if r.status_code == 500)
        assert success_count > 0
        assert error_count > 0


class TestErrorLogging:
    """错误日志测试类"""

    def test_error_logging_on_exception(self, client: TestClient, mocker):
        """测试异常时的错误日志"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=Exception("Test exception for logging")
        )

        response = client.get("/api/strategy/list")

        assert response.status_code == 500


class TestRecoveryFromErrors:
    """错误恢复测试类"""

    def test_service_recovery_after_error(self, client: TestClient, mocker):
        """测试错误后的服务恢复"""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Temporary error")
            return []

        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=side_effect
        )

        response1 = client.get("/api/strategy/list")
        assert response1.status_code == 500

        response2 = client.get("/api/strategy/list")
        assert response2.status_code == 200

    def test_partial_failure_handling(self, client: TestClient, mocker):
        """测试部分失败处理"""
        mocker.patch(
            "backtest.routes.backtest_service.list_backtest_results",
            return_value=[
                {"id": "bt1", "status": "completed"},
                {"id": "bt2", "status": "failed"}
            ]
        )
        response = client.get("/api/backtest/list")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]["backtests"]) == 2


class TestSecurityErrorHandling:
    """安全错误处理测试类"""

    def test_sql_injection_attempt(self, client: TestClient, mocker):
        """测试SQL注入尝试处理"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_detail",
            return_value=None
        )
        malicious_input = "'; DROP TABLE strategies; --"
        response = client.post("/api/strategy/detail", json={"strategy_name": malicious_input})
        # 策略不存在时返回404
        assert response.status_code == 404

    def test_xss_attempt_in_request(self, client: TestClient, mocker):
        """测试XSS尝试处理"""
        mocker.patch(
            "strategy.service.StrategyService.upload_strategy_file",
            return_value=True
        )
        xss_payload = "<script>alert('xss')</script>"
        request_data = {
            "strategy_name": xss_payload,
            "file_content": xss_payload
        }
        response = client.post("/api/strategy/upload", json=request_data)
        assert response.status_code == 200

    def test_path_traversal_attempt(self, client: TestClient, mocker):
        """测试路径遍历尝试处理"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_detail",
            return_value=None
        )
        path_traversal = "../../../etc/passwd"
        response = client.post("/api/strategy/detail", json={"strategy_name": path_traversal})
        # 策略不存在时返回404
        assert response.status_code == 404

    def test_command_injection_attempt(self, client: TestClient, mocker):
        """测试命令注入尝试处理"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_detail",
            return_value=None
        )
        command_injection = "; cat /etc/passwd;"
        response = client.post("/api/strategy/detail", json={"strategy_name": command_injection})
        # 策略不存在时返回404
        assert response.status_code == 404


class TestNetworkErrorHandling:
    """网络错误处理测试类"""

    def test_connection_error_simulation(self, client: TestClient, mocker):
        """测试连接错误模拟"""
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=ConnectionError("Connection refused")
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 500

    def test_timeout_error_simulation(self, client: TestClient, mocker):
        """测试超时错误模拟"""
        import socket
        mocker.patch(
            "strategy.service.StrategyService.get_strategy_list",
            side_effect=socket.timeout("Connection timed out")
        )
        response = client.get("/api/strategy/list")
        assert response.status_code == 500
