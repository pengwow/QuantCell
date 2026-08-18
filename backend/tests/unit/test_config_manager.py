"""
配置文件管理模块单元测试
"""

import json

import pytest


class TestConfigManager:
    """测试 ConfigManager 类"""

    @pytest.fixture
    def temp_config_file(self, tmp_path):
        """创建临时配置文件用于测试"""
        config_file = tmp_path / "config.toml"
        return config_file

    def test_read_config_nonexistent(self, temp_config_file):
        """测试读取不存在的配置文件"""
        from utils.config_manager import ConfigManager

        cm = ConfigManager(str(temp_config_file))
        config = cm.read_config()
        assert config == {}

    def test_write_and_read_config(self, temp_config_file):
        """测试写入和读取配置"""
        from utils.config_manager import ConfigManager

        cm = ConfigManager(str(temp_config_file))

        test_config = {
            "general": {"theme": "dark", "language": "zh-CN"},
            "app": {"debug": True, "port": 8000},
        }

        success = cm.write_config(test_config)
        assert success is True
        assert temp_config_file.exists()

        loaded_config = cm.read_config()
        assert loaded_config == test_config

    def test_get_config_by_group(self, temp_config_file):
        """测试按分组获取配置"""
        from utils.config_manager import ConfigManager

        cm = ConfigManager(str(temp_config_file))
        test_config = {"general": {"theme": "dark", "language": "zh-CN"}}
        cm.write_config(test_config)

        group = cm.get_config_by_group("general")
        assert group == test_config["general"]

        missing_group = cm.get_config_by_group("missing")
        assert missing_group == {}

    def test_get_config_item(self, temp_config_file):
        """测试获取单个配置项"""
        from utils.config_manager import ConfigManager

        cm = ConfigManager(str(temp_config_file))
        test_config = {"general": {"theme": "dark"}}
        cm.write_config(test_config)

        assert cm.get_config_item("general", "theme") == "dark"
        assert cm.get_config_item("general", "missing", "default") == "default"

    def test_update_config_item(self, temp_config_file):
        """测试更新配置项"""
        from utils.config_manager import ConfigManager

        cm = ConfigManager(str(temp_config_file))
        test_config = {"general": {"theme": "dark"}}
        cm.write_config(test_config)

        success = cm.update_config_item("general", "theme", "light")
        assert success is True
        assert cm.get_config_item("general", "theme") == "light"

        # 测试添加新配置项
        success = cm.update_config_item("general", "new_key", "new_value")
        assert success is True
        assert cm.get_config_item("general", "new_key") == "new_value"

    def test_parse_value(self):
        """测试 _parse_value 函数"""
        from utils.config_manager import ConfigManager

        # 测试 JSON 解析
        assert ConfigManager._parse_value('{"key": "value"}') == {"key": "value"}
        # 测试布尔值
        assert ConfigManager._parse_value("true") is True
        assert ConfigManager._parse_value("false") is False
        assert ConfigManager._parse_value("1") is True
        assert ConfigManager._parse_value("0") is False
        # 测试数字
        assert ConfigManager._parse_value("123") == 123
        assert ConfigManager._parse_value("123.45") == 123.45
        # 测试字符串
        assert ConfigManager._parse_value("hello") == "hello"
        # 测试 None
        assert ConfigManager._parse_value(None) is None

    def test_value_to_string(self):
        """测试 _value_to_string 函数"""
        from utils.config_manager import ConfigManager

        # 测试布尔值
        assert ConfigManager._value_to_string(True) == "1"
        assert ConfigManager._value_to_string(False) == "0"
        # 测试数字
        assert ConfigManager._value_to_string(123) == "123"
        assert ConfigManager._value_to_string(123.45) == "123.45"
        # 测试 JSON 转换
        assert ConfigManager._value_to_string({"key": "value"}) == json.dumps({"key": "value"}, ensure_ascii=False)
        # 测试字符串
        assert ConfigManager._value_to_string("hello") == "hello"

    def test_set_nested_value(self):
        """测试 _set_nested_value 函数"""
        from utils.config_manager import ConfigManager

        data = {}
        ConfigManager._set_nested_value(data, "a.b.c", "value")
        assert data["a"]["b"]["c"] == "value"

        # 测试带元数据的嵌套值
        data = {}
        ConfigManager._set_nested_value(data, "a.b", "value", "description")
        assert data["a"]["b"]["_value"] == "value"
        assert data["a"]["b"]["_description"] == "description"

    def test_flatten_dict(self):
        """测试 _flatten_dict 函数"""
        from utils.config_manager import ConfigManager

        data = {"general": {"theme": "dark", "settings": {"debug": True, "port": 8000}}}
        flat = ConfigManager._flatten_dict(data, "general")

        expected = [
            {"key": "theme", "value": "dark", "description": "", "is_sensitive": False},
            {
                "key": "settings.debug",
                "value": True,
                "description": "",
                "is_sensitive": False,
            },
            {
                "key": "settings.port",
                "value": 8000,
                "description": "",
                "is_sensitive": False,
            },
        ]

        # 检查结果数量
        assert len(flat) == len(expected)

    def test_to_and_from_json(self, temp_config_file):
        """测试 JSON 转换功能"""
        from utils.config_manager import ConfigManager

        cm = ConfigManager(str(temp_config_file))

        test_config = {"a": 1, "b": "test"}
        cm.write_config(test_config)

        json_str = cm.to_json()
        loaded = json.loads(json_str)
        assert loaded == test_config

        new_config = {"x": "new", "y": 2}
        success = cm.from_json(json.dumps(new_config))
        assert success is True
        assert cm.read_config() == new_config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
