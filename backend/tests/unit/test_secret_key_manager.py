# -*- coding: utf-8 -*-
"""
JWT安全密钥管理模块单元测试
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestSecretKeyManager:
    """测试 JWT 密钥管理功能
    """

    @pytest.fixture
    def temp_config_file(self, tmp_path):
        """创建临时配置文件用于测试
        """
        config_content = """
[app]
secret_key = ""
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)

        # 覆盖模块中的 CONFIG_FILE 路径
        with patch('utils.secret_key_manager.CONFIG_FILE', config_file):
            with patch('utils.secret_key_manager.BACKUP_FILE', tmp_path / "config.toml.bak"):
                yield config_file

    def test_generate_secure_key(self):
        """测试生成安全密钥
        """
        from utils.secret_key_manager import generate_secure_key

        key1 = generate_secure_key()
        key2 = generate_secure_key()

        assert isinstance(key1, str)
        assert len(key1) > 0
        assert key1 != key2  # 每次生成的密钥应该不同

    def test_get_nested_value(self):
        """测试从嵌套字典获取值
        """
        from utils.secret_key_manager import _get_nested_value

        data = {
            "app": {
                "secret_key": "test_key_123",
                "other": "value"
            }
        }

        assert _get_nested_value(data, ["app", "secret_key"]) == "test_key_123"
        assert _get_nested_value(data, ["app", "other"]) == "value"
        assert _get_nested_value(data, ["app", "missing"]) is None
        assert _get_nested_value({}, ["app"]) is None

    def test_set_nested_value(self):
        """测试设置嵌套字典值
        """
        from utils.secret_key_manager import _set_nested_value

        data = {}
        _set_nested_value(data, ["app", "secret_key"], "new_key")

        assert data["app"]["secret_key"] == "new_key"

    def test_load_config_empty(self, tmp_path):
        """测试加载不存在的配置文件
        """
        from utils.secret_key_manager import load_config

        non_existent_file = tmp_path / "non_existent.toml"
        with patch('utils.secret_key_manager.CONFIG_FILE', non_existent_file):
            config = load_config()
            assert config == {}

    def test_get_secret_key_from_config_empty(self, temp_config_file):
        """测试从配置文件获取空密钥
        """
        from utils.secret_key_manager import get_secret_key_from_config

        key = get_secret_key_from_config()
        assert key is None

    def test_is_secret_key_configured_false(self, temp_config_file):
        """测试密钥未配置
        """
        from utils.secret_key_manager import is_secret_key_configured

        assert is_secret_key_configured() is False

    def test_generate_and_save_secret_key(self, temp_config_file):
        """测试生成并保存密钥
        """
        from utils.secret_key_manager import (
            generate_and_save_secret_key,
            get_secret_key_from_config,
            is_secret_key_configured,
        )

        new_key = generate_and_save_secret_key()
        assert new_key is not None
        assert is_secret_key_configured() is True
        assert get_secret_key_from_config() == new_key

    def test_get_or_create_secret_key(self, temp_config_file):
        """测试获取或创建密钥
        """
        from utils.secret_key_manager import get_or_create_secret_key

        key1 = get_or_create_secret_key()
        key2 = get_or_create_secret_key()

        assert key1 == key2  # 同一运行中应该返回相同的密钥

    def test_get_secret_key_cache(self, temp_config_file):
        """测试密钥缓存
        """
        from utils.secret_key_manager import (
            get_secret_key,
            clear_secret_key_cache,
        )

        key1 = get_secret_key()
        key2 = get_secret_key()
        assert key1 == key2

        clear_secret_key_cache()
        key3 = get_secret_key()
        assert key3 is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
