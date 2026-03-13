"""
项目初始化功能测试
"""

import pytest
from unittest.mock import Mock, patch

from utils.initializer import ProjectInitializer, InitializationStep


class TestInitializationStep:
    """测试InitializationStep类"""
    
    def test_step_execution_success(self):
        """测试步骤成功执行"""
        mock_func = Mock(return_value=True)
        step = InitializationStep(
            name="test",
            description="Test Step",
            func=mock_func
        )
        
        result = step.execute()
        
        assert result is True
        assert step.status == "success"
        mock_func.assert_called_once()
    
    def test_step_execution_failure(self):
        """测试步骤执行失败"""
        mock_func = Mock(return_value=False)
        step = InitializationStep(
            name="test",
            description="Test Step",
            func=mock_func
        )
        
        result = step.execute()
        
        assert result is False
        assert step.status == "failed"
    
    def test_step_skip(self):
        """测试步骤跳过"""
        step = InitializationStep(
            name="test",
            description="Test Step",
            func=Mock()
        )
        
        step.skip("Test skip reason")
        
        assert step.status == "skipped"
        assert step.message == "Test skip reason"


class TestProjectInitializer:
    """测试ProjectInitializer类"""
    
    def test_initialization(self):
        """测试初始化器创建"""
        initializer = ProjectInitializer()
        
        assert len(initializer.steps) > 0
        assert initializer.verbose is False
    
    @patch('utils.initializer.EnvChecker.check_all')
    @patch('utils.initializer.ConfigManager.import_from_toml')
    def test_run_with_config(self, mock_import, mock_check):
        """测试带配置的初始化运行"""
        mock_check.return_value = {"overall": True}
        mock_import.return_value = {
            "total": 1,
            "created": 1,
            "updated": 0,
            "skipped": 0,
            "failed": 0
        }
        
        initializer = ProjectInitializer(verbose=True)
        
        # 模拟其他步骤
        with patch.object(initializer, '_step_db_init', return_value=True):
            with patch.object(initializer, '_step_db_migrate', return_value=True):
                with patch.object(initializer, '_step_data_seed', return_value=True):
                    with patch.object(initializer, '_step_verification', return_value=True):
                        results = initializer.run(
                            config_path="test.toml",
                            skip_config_import=False
                        )
                        
                        assert "success" in results
                        assert "steps" in results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
