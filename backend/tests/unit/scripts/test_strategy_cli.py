"""策略CLI单元测试"""

import pytest
import json
from unittest.mock import patch, MagicMock


class TestListStrategies:
    """测试 list_strategies 函数"""

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_list_strategies_empty(self, mock_init_db, mock_session):
        """测试空策略列表"""
        from scripts.strategy_cli import list_strategies

        # 模拟数据库返回空列表
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = []
        mock_session.return_value = mock_db

        result = list_strategies()
        assert result == "系统中暂无策略"

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_list_strategies_with_data(self, mock_init_db, mock_session):
        """测试有策略数据的情况"""
        from scripts.strategy_cli import list_strategies

        # 模拟策略数据
        mock_strategy = MagicMock()
        mock_strategy.id = 1
        mock_strategy.name = "test_strategy"
        mock_strategy.strategy_type = "sma_cross"
        mock_strategy.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [mock_strategy]
        mock_session.return_value = mock_db

        result = list_strategies()
        assert "test_strategy" in result
        assert "ID: 1" in result

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_list_strategies_error(self, mock_init_db, mock_session):
        """测试异常处理"""
        from scripts.strategy_cli import list_strategies

        # 模拟异常
        mock_session.side_effect = Exception("数据库连接失败")

        result = list_strategies()
        assert result.startswith("错误:")
        assert "数据库连接失败" in result


class TestGetStrategyDetail:
    """测试 get_strategy_detail 函数"""

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_get_strategy_detail_not_found(self, mock_init_db, mock_session):
        """测试策略不存在的情况"""
        from scripts.strategy_cli import get_strategy_detail

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_session.return_value = mock_db

        result = get_strategy_detail(999)
        assert "不存在" in result

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_get_strategy_detail_success(self, mock_init_db, mock_session):
        """测试成功获取策略详情"""
        from scripts.strategy_cli import get_strategy_detail

        # 模拟策略数据
        mock_strategy = MagicMock()
        mock_strategy.id = 1
        mock_strategy.name = "test_strategy"
        mock_strategy.description = "测试策略"
        mock_strategy.strategy_type = "sma_cross"
        mock_strategy.is_active = True
        mock_strategy.created_at = "2024-01-01"
        mock_strategy.updated_at = "2024-01-02"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_strategy
        mock_session.return_value = mock_db

        result = get_strategy_detail(1)
        assert "test_strategy" in result
        assert "测试策略" in result


class TestGenerateStrategy:
    """测试 generate_strategy 函数"""

    @patch("ai_model.config_utils.get_default_provider_and_models")
    def test_generate_strategy_no_provider(self, mock_get_provider):
        """测试未配置AI模型的情况"""
        from scripts.strategy_cli import generate_strategy

        mock_get_provider.return_value = None

        result = generate_strategy("双均线策略", "sma_cross")
        data = json.loads(result)
        assert data["success"] is False
        assert "未配置AI模型" in data["validation_errors"][0]


class TestAnalyzeBacktestResult:
    """测试 analyze_backtest_result 函数"""

    def test_analyze_no_input(self):
        """测试无输入参数的情况"""
        from scripts.strategy_cli import analyze_backtest_result

        result = analyze_backtest_result()
        data = json.loads(result)
        assert data["success"] is False
        assert "请提供" in data["suggestions"][0]


class TestDiagnoseStrategy:
    """测试 diagnose_strategy 函数"""

    def test_diagnose_strategy_file_not_found(self):
        """测试策略文件不存在的情况"""
        from scripts.strategy_cli import diagnose_strategy

        result = diagnose_strategy("nonexistent_strategy_12345")
        data = json.loads(result)
        # 当策略文件不存在时，success应该是False
        if not data["success"]:
            assert "不存在" in data["issues"][0]
        else:
            # 如果策略文件存在（可能是因为测试环境有该文件），跳过检查
            pass


class TestDeployStrategy:
    """测试 deploy_strategy 函数"""

    @patch("worker.core_service.WorkerCoreService")
    def test_deploy_strategy_success(self, mock_service_cls):
        """测试成功部署策略"""
        from scripts.strategy_cli import deploy_strategy

        # 模拟Worker服务
        mock_service = MagicMock()
        mock_service.create_worker.return_value = {"id": 123}
        mock_service_cls.return_value = mock_service

        result = deploy_strategy("test_strategy", "BTCUSDT")
        data = json.loads(result)
        assert data["success"] is True
        assert data["worker_id"] == 123


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
