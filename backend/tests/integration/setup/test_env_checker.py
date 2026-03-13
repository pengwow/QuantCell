"""
环境检查功能测试
"""

import pytest
import sys

from utils.env_checker import EnvChecker


class TestEnvChecker:
    """测试EnvChecker类"""
    
    def test_check_python_version(self):
        """测试Python版本检查"""
        ok, info = EnvChecker.check_python_version()
        
        # 验证返回类型
        assert isinstance(ok, bool)
        assert isinstance(info, str)
        
        # 验证信息包含版本号
        assert "Python" in info
    
    def test_check_package_installed(self):
        """测试包安装检查"""
        # 检查已安装的包
        installed, version = EnvChecker.check_package_installed("typer")
        assert isinstance(installed, bool)
        
        # 检查不存在的包
        installed, version = EnvChecker.check_package_installed("nonexistent_package_xyz")
        assert installed is False
    
    def test_check_all_packages(self):
        """测试检查所有包"""
        results = EnvChecker.check_all_packages()
        
        # 验证结构
        assert "required" in results
        assert "optional" in results
        
        # 验证必需包
        for package in EnvChecker.REQUIRED_PACKAGES:
            assert package in results["required"]
            assert "installed" in results["required"][package]
            assert "version" in results["required"][package]
    
    def test_check_all(self):
        """测试完整环境检查"""
        results = EnvChecker.check_all()
        
        # 验证结构
        assert "python" in results
        assert "packages" in results
        assert "database" in results
        assert "config" in results
        assert "overall" in results
        
        # 验证Python检查结果
        assert "ok" in results["python"]
        assert "info" in results["python"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
