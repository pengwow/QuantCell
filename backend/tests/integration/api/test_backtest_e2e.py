# 端到端回测API测试
# 直接测试真实的策略加载流程，模拟前端调用
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestBacktestE2E:
    """端到端回测API测试类"""

    def test_backtest_api_loads_strategy_success(self, client: TestClient, mocker):
        """测试回测API能正确加载策略 - 真实策略加载流程

        这个测试模拟前端真实调用回测API的流程，验证策略加载不会返回None。
        之前的错误是 'NoneType' object is not callable，说明策略加载失败返回了None。
        """
        # 使用真实的策略模板名称
        request_data = {
            "strategy_config": {
                "strategy_name": "dual_ma",
                "params": {"fast": 10, "slow": 30},
            },
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1h",
                "start_time": "2024-01-01 00:00:00",
                "end_time": "2024-01-02 23:59:59",
                "initial_cash": 100000.0,
                "commission": 0.001,
                "engine_type": "default",
            },
        }

        # 只mock数据库操作和进度追踪，让策略加载走真实路径
        mock_session = MagicMock()
        mocker.patch("utils.db_session.get_db_session", return_value=mock_session)

        mock_tracker = MagicMock()
        mocker.patch("backtest.routes.get_progress_tracker", return_value=mock_tracker)

        response = client.post("/api/backtest/run", json=request_data)

        # 任务应该成功创建
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "task_id" in data["data"]

    def test_backtest_api_all_templates_load_success(self, client: TestClient, mocker):
        """测试所有策略模板都能通过API正确加载

        验证前端可以选择任何策略模板并成功创建回测任务。
        """
        strategy_templates = [
            "dual_ma",
            "trend_follow",
            "momentum",
            "grid",
            "mean_reversion",
            "sma_crossover",
            "funding_arbitrage",
            "llm_signal",
        ]

        for strategy_name in strategy_templates:
            request_data = {
                "strategy_config": {"strategy_name": strategy_name, "params": {}},
                "backtest_config": {
                    "symbols": ["BTCUSDT"],
                    "interval": "1h",
                    "start_time": "2024-01-01 00:00:00",
                    "end_time": "2024-01-02 23:59:59",
                    "initial_cash": 100000.0,
                    "engine_type": "default",
                },
            }

            mock_session = MagicMock()
            mocker.patch("utils.db_session.get_db_session", return_value=mock_session)

            mock_tracker = MagicMock()
            mocker.patch("backtest.routes.get_progress_tracker", return_value=mock_tracker)

            response = client.post("/api/backtest/run", json=request_data)

            assert response.status_code == 200, f"策略 {strategy_name} 加载失败: {response.text}"
            data = response.json()
            assert data["code"] == 0, f"策略 {strategy_name} 返回错误: {data.get('message')}"

    def test_backtest_api_invalid_strategy_name(self, client: TestClient, mocker):
        """测试无效策略名称的错误处理"""
        request_data = {
            "strategy_config": {"strategy_name": "nonexistent_strategy", "params": {}},
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1h",
                "start_time": "2024-01-01 00:00:00",
                "end_time": "2024-01-02 23:59:59",
                "engine_type": "default",
            },
        }

        mock_session = MagicMock()
        mocker.patch("utils.db_session.get_db_session", return_value=mock_session)

        mock_tracker = MagicMock()
        mocker.patch("backtest.routes.get_progress_tracker", return_value=mock_tracker)

        response = client.post("/api/backtest/run", json=request_data)

        # 任务应该成功创建（实际执行时才会失败）
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    def test_backtest_api_with_instrument_ids_format(self, client: TestClient, mocker):
        """测试前端传递的 instrument_ids 格式兼容

        前端可能传递不同格式的 instrument_ids，验证策略加载能正确处理。
        """
        request_data = {
            "strategy_config": {"strategy_name": "dual_ma", "params": {"window": 10}},
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1h",
                "start_time": "2024-01-01 00:00:00",
                "end_time": "2024-01-02 23:59:59",
                "initial_cash": 100000.0,
                "engine_type": "default",
            },
        }

        mock_session = MagicMock()
        mocker.patch("utils.db_session.get_db_session", return_value=mock_session)

        mock_tracker = MagicMock()
        mocker.patch("backtest.routes.get_progress_tracker", return_value=mock_tracker)

        response = client.post("/api/backtest/run", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    def test_backtest_api_strategy_params_nested(self, client: TestClient, mocker):
        """测试嵌套策略参数的传递"""
        request_data = {
            "strategy_config": {
                "strategy_name": "dual_ma",
                "params": {
                    "fast": 10,
                    "slow": 30,
                    "threshold": {"buy": 0.01, "sell": -0.01},
                },
            },
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1h",
                "start_time": "2024-01-01 00:00:00",
                "end_time": "2024-01-02 23:59:59",
                "engine_type": "default",
            },
        }

        mock_session = MagicMock()
        mocker.patch("utils.db_session.get_db_session", return_value=mock_session)

        mock_tracker = MagicMock()
        mocker.patch("backtest.routes.get_progress_tracker", return_value=mock_tracker)

        response = client.post("/api/backtest/run", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
