# 系统设置API集成测试
# 测试系统配置和系统信息相关的所有API端点

import pytest
from fastapi.testclient import TestClient
from typing import Dict, Any, List


class TestConfigListAPI:
    """配置列表API测试类"""

    def test_get_all_configs_success(self, client: TestClient, mocker, assert_api_response):
        """测试获取所有配置成功"""
        mock_configs = {
            "qlib_data_dir": {
                "value": "data/crypto_data",
                "description": "QLib数据目录",
                "is_sensitive": False
            },
            "api_key": {
                "value": "secret_key_123",
                "description": "API密钥",
                "is_sensitive": True
            }
        }
        mocker.patch(
            "settings.api.SystemConfig.get_all_with_details",
            return_value=mock_configs
        )

        response = client.get("/api/config/")
        assert_api_response(response)
        data = response.json()
        assert "qlib_data_dir" in data["data"]
        assert data["data"]["qlib_data_dir"] == "data/crypto_data"
        assert data["data"]["api_key"] == "******"

    def test_get_all_configs_empty(self, client: TestClient, mocker, assert_api_response):
        """测试获取空配置列表"""
        mocker.patch(
            "settings.api.SystemConfig.get_all_with_details",
            return_value={}
        )

        response = client.get("/api/config/")
        assert_api_response(response)
        data = response.json()
        assert data["data"] == {}

    def test_get_all_configs_service_error(self, client: TestClient, mocker):
        """测试获取配置服务异常"""
        mocker.patch(
            "settings.api.SystemConfig.get_all_with_details",
            side_effect=Exception("Database error")
        )

        response = client.get("/api/config/")
        assert response.status_code == 500
        assert "Database error" in str(response.json().get("detail", ""))


class TestConfigDetailAPI:
    """配置详情API测试类"""

    def test_get_config_success(self, client: TestClient, mocker, assert_api_response):
        """测试获取单个配置成功"""
        mock_config = {
            "key": "qlib_data_dir",
            "value": "data/crypto_data",
            "description": "QLib数据目录",
            "is_sensitive": False,
            "plugin": None,
            "name": "数据配置"
        }
        mocker.patch(
            "settings.api.SystemConfig.get_with_details",
            return_value=mock_config
        )

        response = client.get("/api/config/qlib_data_dir")
        assert_api_response(response)
        data = response.json()
        assert data["data"]["key"] == "qlib_data_dir"
        assert data["data"]["value"] == "data/crypto_data"

    def test_get_sensitive_config(self, client: TestClient, mocker, assert_api_response):
        """测试获取敏感配置"""
        mock_config = {
            "key": "api_secret",
            "value": "secret_value",
            "description": "API密钥",
            "is_sensitive": True
        }
        mocker.patch(
            "settings.api.SystemConfig.get_with_details",
            return_value=mock_config
        )

        response = client.get("/api/config/api_secret")
        assert_api_response(response)
        data = response.json()
        assert data["data"]["value"] == "******"

    def test_get_config_not_found(self, client: TestClient, mocker):
        """测试获取不存在的配置"""
        mocker.patch(
            "settings.api.SystemConfig.get_with_details",
            return_value=None
        )

        response = client.get("/api/config/nonexistent_key")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert "不存在" in data["message"]

    def test_get_config_empty_key(self, client: TestClient):
        """测试获取空键配置"""
        response = client.get("/api/config/")
        assert response.status_code == 200

    def test_get_config_special_chars_key(self, client: TestClient, mocker, assert_api_response):
        """测试获取特殊字符键配置"""
        mock_config = {
            "key": "config_with-special.chars",
            "value": "value",
            "description": "测试配置",
            "is_sensitive": False
        }
        mocker.patch(
            "settings.api.SystemConfig.get_with_details",
            return_value=mock_config
        )

        response = client.get("/api/config/config_with-special.chars")
        assert_api_response(response)


class TestConfigUpdateAPI:
    """配置更新API测试类"""

    def test_update_config_success(self, client: TestClient, mocker, assert_api_response):
        """测试更新配置成功"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "key": "new_config",
            "value": "new_value",
            "description": "新的配置项",
            "is_sensitive": False
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["key"] == "new_config"
        assert data["data"]["value"] == "new_value"

    def test_update_sensitive_config(self, client: TestClient, mocker, assert_api_response):
        """测试更新敏感配置"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "key": "api_key",
            "value": "secret123",
            "description": "API密钥",
            "is_sensitive": True
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["value"] == "******"
        assert data["data"]["is_sensitive"] == True

    def test_update_config_with_plugin(self, client: TestClient, mocker, assert_api_response):
        """测试更新带插件的配置"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "key": "plugin_config",
            "value": "plugin_value",
            "description": "插件配置",
            "plugin": "my_plugin",
            "name": "插件设置"
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["plugin"] == "my_plugin"
        assert data["data"]["name"] == "插件设置"

    def test_update_config_missing_key(self, client: TestClient):
        """测试更新配置缺少键"""
        request_data = {
            "value": "new_value"
        }

        response = client.post("/api/config/", json=request_data)
        assert response.status_code == 422

    def test_update_config_missing_value(self, client: TestClient):
        """测试更新配置缺少值"""
        request_data = {
            "key": "new_config"
        }

        response = client.post("/api/config/", json=request_data)
        assert response.status_code == 422

    def test_update_config_empty_key(self, client: TestClient, mocker):
        """测试更新配置空键"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "key": "",
            "value": "value"
        }

        response = client.post("/api/config/", json=request_data)
        assert response.status_code == 200

    def test_update_config_failed(self, client: TestClient, mocker):
        """测试更新配置失败"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=False
        )

        request_data = {
            "key": "new_config",
            "value": "new_value"
        }

        response = client.post("/api/config/", json=request_data)
        assert response.status_code == 500


class TestConfigDeleteAPI:
    """配置删除API测试类（需要认证）"""

    def test_delete_config_success(self, client: TestClient, auth_headers: Dict[str, str], mocker, assert_api_response):
        """测试删除配置成功"""
        mocker.patch(
            "settings.api.SystemConfig.delete",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        response = client.delete("/api/config/test_config", headers=auth_headers)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["key"] == "test_config"

    def test_delete_config_not_found(self, client: TestClient, auth_headers: Dict[str, str], mocker):
        """测试删除不存在的配置"""
        mocker.patch(
            "settings.api.SystemConfig.delete",
            return_value=False
        )

        response = client.delete("/api/config/nonexistent", headers=auth_headers)
        assert response.status_code == 500

    def test_delete_config_without_auth(self, client: TestClient):
        """测试未认证删除配置"""
        response = client.delete("/api/config/test_config")
        assert response.status_code == 401

    def test_delete_config_invalid_token(self, client: TestClient, invalid_auth_headers: Dict[str, str]):
        """测试无效令牌删除配置"""
        response = client.delete("/api/config/test_config", headers=invalid_auth_headers)
        assert response.status_code == 401

    def test_delete_config_special_chars_key(self, client: TestClient, auth_headers: Dict[str, str], mocker, assert_api_response):
        """测试删除特殊字符键配置"""
        mocker.patch(
            "settings.api.SystemConfig.delete",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        response = client.delete("/api/config/config-with_special.chars", headers=auth_headers)
        assert_api_response(response)


class TestConfigBatchUpdateAPI:
    """配置批量更新API测试类"""

    def test_batch_update_dict_format(self, client: TestClient, mocker, assert_api_response):
        """测试批量更新字典格式"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "config1": "value1",
            "config2": "value2"
        }

        response = client.post("/api/config/batch", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["updated_count"] == 2

    def test_batch_update_list_format(self, client: TestClient, mocker, assert_api_response):
        """测试批量更新列表格式"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = [
            {
                "key": "config1",
                "value": "value1",
                "description": "配置项1",
                "is_sensitive": False
            },
            {
                "key": "config2",
                "value": "value2",
                "description": "配置项2",
                "plugin": "test_plugin"
            }
        ]

        response = client.post("/api/config/batch", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["updated_count"] == 2

    def test_batch_update_with_configs_field(self, client: TestClient, mocker, assert_api_response):
        """测试批量更新带configs字段格式"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "configs": {
                "config1": "value1",
                "config2": "value2"
            }
        }

        response = client.post("/api/config/batch", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["updated_count"] == 2

    def test_batch_update_skip_vue_internal(self, client: TestClient, mocker, assert_api_response):
        """测试批量更新跳过Vue内部属性"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "config1": "value1",
            "__v_id": "internal",
            "__v_skip": "skip_this"
        }

        response = client.post("/api/config/batch", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["updated_count"] == 1

    def test_batch_update_empty(self, client: TestClient, mocker, assert_api_response):
        """测试批量更新空数据"""
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {}

        response = client.post("/api/config/batch", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["updated_count"] == 0

    def test_batch_update_service_error(self, client: TestClient, mocker):
        """测试批量更新服务异常"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            side_effect=Exception("Update failed")
        )

        request_data = {
            "config1": "value1"
        }

        response = client.post("/api/config/batch", json=request_data)
        assert response.status_code == 500


class TestPluginConfigAPI:
    """插件配置API测试类"""

    def test_get_plugin_config_success(self, client: TestClient, mocker, assert_api_response):
        """测试获取插件配置成功"""
        mock_configs = {
            "plugin1_config1": {
                "value": "value1",
                "plugin": "plugin1",
                "is_sensitive": False
            },
            "plugin1_config2": {
                "value": "secret",
                "plugin": "plugin1",
                "is_sensitive": True
            },
            "other_config": {
                "value": "other",
                "plugin": "other_plugin",
                "is_sensitive": False
            }
        }
        mocker.patch(
            "settings.api.SystemConfig.get_all_with_details",
            return_value=mock_configs
        )

        response = client.get("/api/config/plugin/plugin1")
        assert_api_response(response)
        data = response.json()
        assert "plugin1_config1" in data["data"]
        assert data["data"]["plugin1_config2"] == "******"
        assert "other_config" not in data["data"]

    def test_get_plugin_config_empty(self, client: TestClient, mocker, assert_api_response):
        """测试获取空插件配置"""
        mocker.patch(
            "settings.api.SystemConfig.get_all_with_details",
            return_value={}
        )

        response = client.get("/api/config/plugin/nonexistent_plugin")
        assert_api_response(response)
        data = response.json()
        assert data["data"] == {}

    def test_get_plugin_config_special_chars(self, client: TestClient, mocker, assert_api_response):
        """测试获取特殊字符插件配置"""
        mock_configs = {
            "config1": {
                "value": "value1",
                "plugin": "my-plugin_v1.0",
                "is_sensitive": False
            }
        }
        mocker.patch(
            "settings.api.SystemConfig.get_all_with_details",
            return_value=mock_configs
        )

        response = client.get("/api/config/plugin/my-plugin_v1.0")
        assert_api_response(response)


class TestSystemInfoAPI:
    """系统信息API测试类"""

    def test_get_system_info_success(self, client: TestClient, mocker, assert_api_response):
        """测试获取系统信息成功"""
        mock_result = {
            "success": True,
            "message": "获取系统信息成功",
            "system_info": {
                "version": {
                    "system_version": "1.0.0",
                    "python_version": "3.12.12",
                    "build_date": "2025-11-30"
                },
                "running_status": {
                    "uptime": "0 天 0 小时",
                    "status": "running",
                    "status_color": "green",
                    "last_check": "2026-01-24 18:00:00"
                },
                "resource_usage": {
                    "cpu_usage": 24.9,
                    "memory_usage": "5.25GB / 16.0GB",
                    "disk_space": "11.43GB / 228.27GB"
                }
            }
        }
        mocker.patch(
            "settings.api.SystemService.get_system_info",
            return_value=mock_result
        )

        response = client.get("/api/system/info")
        assert_api_response(response)
        data = response.json()
        assert "version" in data["data"]
        assert "running_status" in data["data"]
        assert "resource_usage" in data["data"]

    def test_get_system_info_failed(self, client: TestClient, mocker):
        """测试获取系统信息失败"""
        mock_result = {
            "success": False,
            "message": "获取系统信息失败",
            "error": "Service unavailable"
        }
        mocker.patch(
            "settings.api.SystemService.get_system_info",
            return_value=mock_result
        )

        response = client.get("/api/system/info")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1

    def test_get_system_info_exception(self, client: TestClient, mocker):
        """测试获取系统信息异常"""
        mocker.patch(
            "settings.api.SystemService.get_system_info",
            side_effect=Exception("System error")
        )

        response = client.get("/api/system/info")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1


class TestSettingsEdgeCases:
    """设置API边界条件测试类"""

    def test_update_config_very_long_key(self, client: TestClient, mocker, assert_api_response):
        """测试更新超长键配置"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        long_key = "a" * 200
        request_data = {
            "key": long_key,
            "value": "value"
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)

    def test_update_config_very_long_value(self, client: TestClient, mocker, assert_api_response):
        """测试更新超长值配置"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        long_value = "b" * 10000
        request_data = {
            "key": "long_value_config",
            "value": long_value
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)

    def test_update_config_unicode(self, client: TestClient, mocker, assert_api_response):
        """测试更新Unicode配置"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "key": "unicode_config",
            "value": "中文值_日本語_한국어_🚀",
            "description": "中文描述"
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)

    def test_update_config_special_chars_in_value(self, client: TestClient, mocker, assert_api_response):
        """测试更新特殊字符值配置"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "key": "special_config",
            "value": "<script>alert('xss')</script>&\"'"
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)

    def test_batch_update_large_number(self, client: TestClient, mocker, assert_api_response):
        """测试批量更新大量配置"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {f"config_{i}": f"value_{i}" for i in range(100)}

        response = client.post("/api/config/batch", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["updated_count"] == 100

    def test_nested_config_value(self, client: TestClient, mocker, assert_api_response):
        """测试嵌套配置值（JSON字符串）"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "key": "json_config",
            "value": '{"nested": {"key": "value"}, "array": [1, 2, 3]}'
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)

    def test_config_with_null_values(self, client: TestClient, mocker, assert_api_response):
        """测试带null值的配置"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "key": "null_config",
            "value": "value",
            "description": None,
            "plugin": None
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)

    def test_boolean_config_values(self, client: TestClient, mocker, assert_api_response):
        """测试布尔值配置"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "key": "bool_config",
            "value": "true",
            "is_sensitive": True
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["is_sensitive"] == True

    def test_numeric_config_values(self, client: TestClient, mocker, assert_api_response):
        """测试数值配置"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        request_data = {
            "key": "numeric_config",
            "value": "12345"
        }

        response = client.post("/api/config/", json=request_data)
        assert_api_response(response)

    def test_concurrent_config_updates(self, client: TestClient, mocker):
        """测试并发配置更新"""
        mocker.patch(
            "settings.api.SystemConfig.set",
            return_value=True
        )
        mocker.patch(
            "settings.api.load_system_configs",
            return_value={}
        )

        import concurrent.futures

        def make_request(i):
            request_data = {
                "key": f"concurrent_config_{i}",
                "value": f"value_{i}"
            }
            return client.post("/api/config/", json=request_data)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        for response in results:
            assert response.status_code == 200
