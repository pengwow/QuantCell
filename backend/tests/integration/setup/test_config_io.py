"""
配置导入导出功能测试
"""

import pytest
import tempfile
import os
from pathlib import Path

from utils.config_manager import ConfigManager as ConfigIO


class TestConfigIO:
    """测试ConfigIO类"""
    
    def test_export_to_toml(self):
        """测试导出配置到TOML"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            temp_path = f.name
        
        try:
            # 导出配置
            result_path = ConfigIO.export_to_toml(temp_path)
            
            # 验证文件存在
            assert os.path.exists(result_path)
            
            # 验证文件内容
            import toml
            with open(result_path, 'r', encoding='utf-8') as f:
                data = toml.load(f)
            
            # 验证包含元数据
            assert '_meta' in data
            assert 'export_time' in data['_meta']
            assert 'version' in data['_meta']
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_import_from_toml(self):
        """测试从TOML导入配置"""
        # 创建测试TOML文件
        test_config = """
[_meta]
export_time = "2024-01-01T00:00:00"
version = "1.0"

[general]
theme = "light"
language = "zh-CN"

[test]
key1 = "value1"
key2 = 123
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(test_config)
            temp_path = f.name
        
        try:
            # 试运行模式
            stats = ConfigIO.import_from_toml(temp_path, dry_run=True)
            
            assert stats['total'] > 0
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_parse_value(self):
        """测试配置值解析"""
        # 测试布尔值
        assert ConfigIO._parse_value('true') == True
        assert ConfigIO._parse_value('false') == False
        assert ConfigIO._parse_value('1') == True
        assert ConfigIO._parse_value('0') == False
        
        # 测试整数
        assert ConfigIO._parse_value('123') == 123
        
        # 测试浮点数
        assert ConfigIO._parse_value('123.45') == 123.45
        
        # 测试JSON
        assert ConfigIO._parse_value('{"key": "value"}') == {"key": "value"}
        
        # 测试字符串
        assert ConfigIO._parse_value('hello') == 'hello'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
