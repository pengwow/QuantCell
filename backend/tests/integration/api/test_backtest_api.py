# 回测服务API集成测试
# 测试回测相关的所有API端点

import pytest
from fastapi.testclient import TestClient
from typing import Dict, Any, List
from datetime import datetime


class TestBacktestListAPI:
    """回测列表API测试类"""

    def test_get_backtest_list_success(self, client: TestClient, assert_api_response):
        """测试获取回测列表成功"""
        response = client.get("/api/backtest/list")
        assert_api_response(response)
        data = response.json()
        assert "data" in data
        assert "backtests" in data["data"]
        assert isinstance(data["data"]["backtests"], list)

    def test_get_backtest_list_with_pagination(self, client: TestClient, assert_api_response):
        """测试带分页参数获取回测列表"""
        response = client.get("/api/backtest/list?page=1&page_size=10")
        assert_api_response(response)
        data = response.json()
        assert "data" in data

    def test_get_backtest_list_empty(self, client: TestClient, mocker, assert_api_response):
        """测试获取空回测列表"""
        mocker.patch(
            "backtest.routes.backtest_service.list_backtest_results",
            return_value=[]
        )
        response = client.get("/api/backtest/list")
        assert_api_response(response)
        data = response.json()
        assert data["data"]["backtests"] == []

    def test_get_backtest_list_service_error(self, client: TestClient, mocker):
        """测试回测列表服务异常"""
        mocker.patch(
            "backtest.routes.backtest_service.list_backtest_results",
            side_effect=Exception("Database connection failed")
        )
        response = client.get("/api/backtest/list")
        assert response.status_code == 500
        assert "Database connection failed" in str(response.json().get("detail", ""))


class TestBacktestStrategiesAPI:
    """策略类型列表API测试类"""

    def test_get_strategy_list_success(self, client: TestClient, assert_api_response):
        """测试获取策略类型列表成功"""
        response = client.get("/api/backtest/strategies")
        assert_api_response(response)
        data = response.json()
        assert "data" in data
        assert "strategies" in data["data"]
        assert isinstance(data["data"]["strategies"], list)

    def test_get_strategy_list_returns_empty(self, client: TestClient):
        """测试策略类型列表返回空列表（当前实现）"""
        response = client.get("/api/backtest/strategies")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["strategies"] == []


class TestBacktestRunAPI:
    """回测执行API测试类"""

    def test_run_backtest_success(self, client: TestClient, mocker, assert_api_response):
        """测试执行回测成功"""
        mock_result = {
            "task_id": "bt_1234567890",
            "status": "completed",
            "message": "回测完成"
        }
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        request_data = {
            "strategy_config": {
                "strategy_name": "SmaCross",
                "params": {"n1": 10, "n2": 20}
            },
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-12-31 23:59:59",
                "initial_cash": 10000.0,
                "commission": 0.001
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["task_id"] == "bt_1234567890"
        assert data["data"]["status"] == "completed"

    def test_run_backtest_failed(self, client: TestClient, mocker):
        """测试执行回测失败"""
        mock_result = {
            "status": "failed",
            "message": "策略参数无效"
        }
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        request_data = {
            "strategy_config": {
                "strategy_name": "InvalidStrategy",
                "params": {}
            },
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-12-31 23:59:59"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert "策略参数无效" in data["message"]

    def test_run_backtest_missing_required_fields(self, client: TestClient):
        """测试执行回测缺少必填字段"""
        request_data = {
            "strategy_config": {
                "strategy_name": "SmaCross"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_run_backtest_invalid_strategy_config(self, client: TestClient):
        """测试执行回测无效的策略配置"""
        request_data = {
            "strategy_config": {
                "strategy_name": "",
                "params": "invalid"
            },
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-12-31 23:59:59"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 422

    def test_run_backtest_invalid_date_format(self, client: TestClient):
        """测试执行回测无效的日期格式"""
        request_data = {
            "strategy_config": {
                "strategy_name": "SmaCross",
                "params": {}
            },
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "invalid-date",
                "end_time": "2023-12-31 23:59:59"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 200

    def test_run_backtest_multiple_symbols(self, client: TestClient, mocker, assert_api_response):
        """测试多币种回测"""
        mock_result = {
            "task_id": "bt_multi_123",
            "status": "completed",
            "message": "回测完成"
        }
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        request_data = {
            "strategy_config": {
                "strategy_name": "SmaCross",
                "params": {"n1": 10, "n2": 20}
            },
            "backtest_config": {
                "symbols": ["BTCUSDT", "ETHUSDT", "ADAUSDT"],
                "interval": "1h",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-03-31 23:59:59",
                "initial_cash": 50000.0,
                "commission": 0.0005
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert_api_response(response)

    def test_run_backtest_different_intervals(self, client: TestClient, mocker, assert_api_response):
        """测试不同时间周期的回测"""
        mock_result = {"task_id": "bt_123", "status": "completed"}
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        intervals = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]
        for interval in intervals:
            request_data = {
                "strategy_config": {"strategy_name": "SmaCross", "params": {}},
                "backtest_config": {
                    "symbols": ["BTCUSDT"],
                    "interval": interval,
                    "start_time": "2023-01-01 00:00:00",
                    "end_time": "2023-01-31 23:59:59"
                }
            }
            response = client.post("/api/backtest/run", json=request_data)
            assert response.status_code == 200, f"Failed for interval {interval}"


class TestBacktestStopAPI:
    """回测终止API测试类"""

    def test_stop_backtest_success(self, client: TestClient, mocker, assert_api_response):
        """测试终止回测成功"""
        mock_result = {"status": "success", "message": "回测已终止"}
        mocker.patch(
            "backtest.routes.backtest_service.stop_backtest",
            return_value=mock_result
        )

        request_data = {"task_id": "bt_1234567890"}
        response = client.post("/api/backtest/stop", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["message"] == "回测已终止"

    def test_stop_backtest_not_found(self, client: TestClient, mocker):
        """测试终止不存在的回测任务"""
        mock_result = {"status": "error", "message": "回测任务不存在"}
        mocker.patch(
            "backtest.routes.backtest_service.stop_backtest",
            return_value=mock_result
        )

        request_data = {"task_id": "bt_nonexistent"}
        response = client.post("/api/backtest/stop", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert "不存在" in data["message"]

    def test_stop_backtest_missing_task_id(self, client: TestClient):
        """测试终止回测缺少任务ID"""
        request_data = {}
        response = client.post("/api/backtest/stop", json=request_data)
        assert response.status_code == 422

    def test_stop_backtest_empty_task_id(self, client: TestClient):
        """测试终止回测空任务ID"""
        request_data = {"task_id": ""}
        response = client.post("/api/backtest/stop", json=request_data)
        assert response.status_code == 422


class TestBacktestAnalyzeAPI:
    """回测分析API测试类"""

    def test_analyze_backtest_success(self, client: TestClient, mocker, assert_api_response):
        """测试分析回测结果成功"""
        mock_result = {
            "status": "success",
            "metrics": {
                "Return [%]": 15.5,
                "Sharpe Ratio": 1.2,
                "Max Drawdown [%]": -5.4
            },
            "trades": [],
            "equity_curve": []
        }
        mocker.patch(
            "backtest.routes.backtest_service.analyze_backtest",
            return_value=mock_result
        )

        request_data = {"backtest_id": "bt_1234567890"}
        response = client.post("/api/backtest/analyze", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert "metrics" in data["data"]

    def test_analyze_backtest_not_found(self, client: TestClient, mocker):
        """测试分析不存在的回测结果"""
        mock_result = {"status": "error", "message": "回测结果不存在"}
        mocker.patch(
            "backtest.routes.backtest_service.analyze_backtest",
            return_value=mock_result
        )

        request_data = {"backtest_id": "bt_nonexistent"}
        response = client.post("/api/backtest/analyze", json=request_data)
        assert response.status_code == 200

    def test_analyze_backtest_missing_id(self, client: TestClient):
        """测试分析回测缺少ID"""
        request_data = {}
        response = client.post("/api/backtest/analyze", json=request_data)
        assert response.status_code == 422


class TestBacktestDeleteAPI:
    """回测删除API测试类（需要认证）"""

    def test_delete_backtest_success(self, client: TestClient, auth_headers: Dict[str, str], mocker, assert_api_response):
        """测试删除回测结果成功"""
        mocker.patch(
            "backtest.routes.backtest_service.delete_backtest_result",
            return_value=True
        )

        response = client.delete("/api/backtest/delete/bt_1234567890", headers=auth_headers)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["backtest_id"] == "bt_1234567890"
        assert data["data"]["result"] == True

    def test_delete_backtest_not_found(self, client: TestClient, auth_headers: Dict[str, str], mocker):
        """测试删除不存在的回测结果"""
        mocker.patch(
            "backtest.routes.backtest_service.delete_backtest_result",
            return_value=False
        )

        response = client.delete("/api/backtest/delete/bt_nonexistent", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1

    def test_delete_backtest_without_auth(self, client: TestClient):
        """测试未认证删除回测"""
        response = client.delete("/api/backtest/delete/bt_1234567890")
        assert response.status_code == 401

    def test_delete_backtest_invalid_id(self, client: TestClient, auth_headers: Dict[str, str]):
        """测试删除无效ID的回测"""
        response = client.delete("/api/backtest/delete/", headers=auth_headers)
        assert response.status_code == 307


class TestBacktestDetailAPI:
    """回测详情API测试类"""

    def test_get_backtest_detail_success(self, client: TestClient, mocker, assert_api_response):
        """测试获取回测详情成功"""
        mock_result = {
            "status": "success",
            "task_id": "bt_1234567890",
            "strategy_name": "SmaCross",
            "metrics": {"Return [%]": 15.5}
        }
        mocker.patch(
            "backtest.routes.backtest_service.analyze_backtest",
            return_value=mock_result
        )

        response = client.get("/api/backtest/bt_1234567890")
        assert_api_response(response)
        data = response.json()
        assert data["data"]["task_id"] == "bt_1234567890"

    def test_get_backtest_detail_not_found(self, client: TestClient, mocker):
        """测试获取不存在的回测详情"""
        mock_result = {"status": "error", "message": "回测不存在"}
        mocker.patch(
            "backtest.routes.backtest_service.analyze_backtest",
            return_value=mock_result
        )

        response = client.get("/api/backtest/bt_nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1

    def test_get_backtest_detail_empty_id(self, client: TestClient):
        """测试获取空ID的回测详情"""
        response = client.get("/api/backtest/")
        assert response.status_code in [404, 307]


class TestBacktestSymbolsAPI:
    """回测货币对列表API测试类"""

    def test_get_backtest_symbols_success(self, client: TestClient, mocker, assert_api_response):
        """测试获取回测货币对列表成功"""
        mock_result = {
            "status": "success",
            "data": {
                "symbols": [
                    {"symbol": "BTCUSDT", "status": "success", "message": "回测成功"},
                    {"symbol": "ETHUSDT", "status": "success", "message": "回测成功"}
                ],
                "total": 2
            }
        }
        mocker.patch(
            "backtest.routes.backtest_service.get_backtest_symbols",
            return_value=mock_result
        )

        response = client.get("/api/backtest/bt_1234567890/symbols")
        assert_api_response(response)
        data = response.json()
        assert "symbols" in data["data"]
        assert len(data["data"]["symbols"]) == 2

    def test_get_backtest_symbols_failed(self, client: TestClient, mocker):
        """测试获取回测货币对列表失败"""
        mock_result = {"status": "error", "message": "回测不存在"}
        mocker.patch(
            "backtest.routes.backtest_service.get_backtest_symbols",
            return_value=mock_result
        )

        response = client.get("/api/backtest/bt_nonexistent/symbols")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1


class TestBacktestReplayAPI:
    """回测回放API测试类"""

    def test_get_replay_data_success(self, client: TestClient, mocker, assert_api_response):
        """测试获取回放数据成功"""
        mock_result = {
            "status": "success",
            "data": {
                "kline_data": [
                    {"timestamp": 1672531200000, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1000.0}
                ],
                "trade_signals": [
                    {"time": "2024-01-01 10:00:00", "type": "buy", "price": 100.0, "size": 1.0, "trade_id": "123"}
                ],
                "equity_data": [
                    {"time": "2024-01-01 00:00:00", "equity": 10000.0}
                ]
            }
        }
        mocker.patch(
            "backtest.routes.backtest_service.get_replay_data",
            return_value=mock_result
        )

        response = client.get("/api/backtest/bt_1234567890/replay")
        assert_api_response(response)
        data = response.json()
        assert "kline_data" in data["data"]
        assert "trade_signals" in data["data"]
        assert "equity_data" in data["data"]

    def test_get_replay_data_with_symbol(self, client: TestClient, mocker, assert_api_response):
        """测试获取指定货币对的回放数据"""
        mock_result = {
            "status": "success",
            "data": {
                "kline_data": [],
                "trade_signals": [],
                "equity_data": []
            }
        }
        mocker.patch(
            "backtest.routes.backtest_service.get_replay_data",
            return_value=mock_result
        )

        response = client.get("/api/backtest/bt_1234567890/replay?symbol=BTCUSDT")
        assert_api_response(response)

    def test_get_replay_data_not_found(self, client: TestClient, mocker):
        """测试获取不存在的回放数据"""
        mock_result = {"status": "error", "message": "回测不存在"}
        mocker.patch(
            "backtest.routes.backtest_service.get_replay_data",
            return_value=mock_result
        )

        response = client.get("/api/backtest/bt_nonexistent/replay")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1


class TestStrategyConfigAPI:
    """策略配置API测试类"""

    def test_create_strategy_config_success(self, client: TestClient, assert_api_response):
        """测试创建策略配置成功"""
        request_data = {
            "strategy_name": "SmaCross",
            "params": {"n1": 10, "n2": 20}
        }

        response = client.post("/api/backtest/strategy/config", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["strategy_config"]["strategy_name"] == "SmaCross"
        assert data["data"]["strategy_config"]["params"]["n1"] == 10

    def test_create_strategy_config_minimal(self, client: TestClient, assert_api_response):
        """测试创建最小策略配置"""
        request_data = {
            "strategy_name": "TestStrategy"
        }

        response = client.post("/api/backtest/strategy/config", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["strategy_config"]["strategy_name"] == "TestStrategy"

    def test_create_strategy_config_missing_name(self, client: TestClient):
        """测试创建策略配置缺少名称"""
        request_data = {
            "params": {"n1": 10}
        }

        response = client.post("/api/backtest/strategy/config", json=request_data)
        assert response.status_code == 422

    def test_create_strategy_config_empty_name(self, client: TestClient):
        """测试创建策略配置空名称"""
        request_data = {
            "strategy_name": "",
            "params": {}
        }

        response = client.post("/api/backtest/strategy/config", json=request_data)
        assert response.status_code == 422


class TestBacktestUploadAPI:
    """策略上传API测试类"""

    def test_upload_strategy_success(self, client: TestClient, mocker, assert_api_response):
        """测试上传策略文件成功"""
        mocker.patch(
            "backtest.routes.backtest_service.upload_strategy_file",
            return_value=True
        )

        request_data = {
            "strategy_name": "MyCustomStrategy",
            "file_content": "class MyCustomStrategy:\n    pass"
        }

        response = client.post("/api/backtest/strategy", json=request_data)
        assert_api_response(response)
        data = response.json()
        assert data["data"]["strategy_name"] == "MyCustomStrategy"

    def test_upload_strategy_failed(self, client: TestClient, mocker):
        """测试上传策略文件失败"""
        mocker.patch(
            "backtest.routes.backtest_service.upload_strategy_file",
            return_value=False
        )

        request_data = {
            "strategy_name": "InvalidStrategy",
            "file_content": "invalid python code"
        }

        response = client.post("/api/backtest/strategy", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1

    def test_upload_strategy_missing_content(self, client: TestClient):
        """测试上传策略缺少文件内容"""
        request_data = {
            "strategy_name": "TestStrategy"
        }

        response = client.post("/api/backtest/strategy", json=request_data)
        assert response.status_code == 422


class TestDataIntegrityAPI:
    """数据完整性检查API测试类"""

    def test_check_data_integrity_success(self, client: TestClient, mocker):
        """测试数据完整性检查成功"""
        from unittest.mock import MagicMock

        mock_checker = MagicMock()
        mock_result = MagicMock()
        mock_result.is_complete = True
        mock_result.total_expected = 1000
        mock_result.total_actual = 1000
        mock_result.missing_count = 0
        mock_result.missing_ranges = []
        mock_result.quality_issues = []
        mock_result.coverage_percent = 100.0
        mock_checker.check_data_completeness.return_value = mock_result

        mocker.patch("backtest.data_integrity.DataIntegrityChecker", return_value=mock_checker)

        request_data = {
            "symbol": "BTCUSDT",
            "interval": "1d",
            "start_time": "2023-01-01 00:00:00",
            "end_time": "2023-12-31 23:59:59",
            "market_type": "crypto",
            "crypto_type": "spot"
        }

        response = client.post("/api/backtest/check-data", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["is_complete"] == True
        assert data["data"]["coverage_percent"] == 100.0

    def test_check_data_integrity_incomplete(self, client: TestClient, mocker):
        """测试数据完整性检查发现缺失数据"""
        from unittest.mock import MagicMock
        from datetime import datetime

        mock_checker = MagicMock()
        mock_result = MagicMock()
        mock_result.is_complete = False
        mock_result.total_expected = 1000
        mock_result.total_actual = 900
        mock_result.missing_count = 100
        mock_result.missing_ranges = [(datetime(2023, 6, 1), datetime(2023, 6, 10))]
        mock_result.quality_issues = []
        mock_result.coverage_percent = 90.0
        mock_checker.check_data_completeness.return_value = mock_result

        mocker.patch("backtest.data_integrity.DataIntegrityChecker", return_value=mock_checker)

        request_data = {
            "symbol": "BTCUSDT",
            "interval": "1d",
            "start_time": "2023-01-01 00:00:00",
            "end_time": "2023-12-31 23:59:59"
        }

        response = client.post("/api/backtest/check-data", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["is_complete"] == False
        assert data["data"]["missing_count"] == 100

    def test_check_data_integrity_missing_required(self, client: TestClient):
        """测试数据完整性检查缺少必填字段"""
        request_data = {
            "symbol": "BTCUSDT"
        }

        response = client.post("/api/backtest/check-data", json=request_data)
        assert response.status_code == 422


class TestDataDownloadAPI:
    """数据下载API测试类"""

    def test_download_missing_data_success(self, client: TestClient, mocker):
        """测试下载缺失数据成功"""
        mock_downloader = mocker.MagicMock()
        mock_downloader.ensure_data_complete.return_value = (True, {})
        mocker.patch("backtest.data_downloader.BacktestDataDownloader", return_value=mock_downloader)

        request_data = {
            "symbol": "BTCUSDT",
            "interval": "1d",
            "start_time": "2023-01-01 00:00:00",
            "end_time": "2023-12-31 23:59:59"
        }

        response = client.post("/api/backtest/download-data", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "completed"

    def test_download_missing_data_failed(self, client: TestClient, mocker):
        """测试下载缺失数据失败"""
        mock_downloader = mocker.MagicMock()
        mock_downloader.ensure_data_complete.return_value = (False, {})
        mocker.patch("backtest.data_downloader.BacktestDataDownloader", return_value=mock_downloader)

        request_data = {
            "symbol": "BTCUSDT",
            "interval": "1d",
            "start_time": "2023-01-01 00:00:00",
            "end_time": "2023-12-31 23:59:59"
        }

        response = client.post("/api/backtest/download-data", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["data"]["status"] == "failed"


class TestBacktestEdgeCases:
    """回测API边界条件测试类"""

    def test_run_backtest_zero_initial_cash(self, client: TestClient, mocker):
        """测试初始资金为0的回测"""
        mock_result = {"task_id": "bt_123", "status": "completed"}
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        request_data = {
            "strategy_config": {"strategy_name": "SmaCross", "params": {}},
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-12-31 23:59:59",
                "initial_cash": 0.0
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 200

    def test_run_backtest_large_commission(self, client: TestClient, mocker):
        """测试高手续费率的回测"""
        mock_result = {"task_id": "bt_123", "status": "completed"}
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        request_data = {
            "strategy_config": {"strategy_name": "SmaCross", "params": {}},
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-12-31 23:59:59",
                "commission": 0.5
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 200

    def test_run_backtest_same_start_end_time(self, client: TestClient, mocker):
        """测试开始结束时间相同的回测"""
        mock_result = {"task_id": "bt_123", "status": "completed"}
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        request_data = {
            "strategy_config": {"strategy_name": "SmaCross", "params": {}},
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-01-01 00:00:00"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 200

    def test_run_backtest_special_chars_in_symbol(self, client: TestClient, mocker):
        """测试特殊字符交易对"""
        mock_result = {"task_id": "bt_123", "status": "completed"}
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        request_data = {
            "strategy_config": {"strategy_name": "SmaCross", "params": {}},
            "backtest_config": {
                "symbols": ["BTC-USDT", "ETH_USDT"],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-12-31 23:59:59"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 200

    def test_run_backtest_very_long_time_range(self, client: TestClient, mocker):
        """测试超长回测时间范围"""
        mock_result = {"task_id": "bt_123", "status": "completed"}
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        request_data = {
            "strategy_config": {"strategy_name": "SmaCross", "params": {}},
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "2010-01-01 00:00:00",
                "end_time": "2024-12-31 23:59:59"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 200

    def test_run_backtest_unicode_strategy_name(self, client: TestClient, mocker):
        """测试Unicode策略名称"""
        mock_result = {"task_id": "bt_123", "status": "completed"}
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        request_data = {
            "strategy_config": {"strategy_name": "策略_中文", "params": {}},
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-12-31 23:59:59"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 200

    def test_run_backtest_nested_params(self, client: TestClient, mocker):
        """测试嵌套参数策略"""
        mock_result = {"task_id": "bt_123", "status": "completed"}
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        request_data = {
            "strategy_config": {
                "strategy_name": "ComplexStrategy",
                "params": {
                    "ma": {"fast": 10, "slow": 20},
                    "rsi": {"period": 14, "overbought": 70}
                }
            },
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-12-31 23:59:59"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 200

    def test_run_backtest_empty_symbols(self, client: TestClient):
        """测试空交易对列表"""
        request_data = {
            "strategy_config": {"strategy_name": "SmaCross", "params": {}},
            "backtest_config": {
                "symbols": [],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-12-31 23:59:59"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 422

    def test_run_backtest_invalid_interval(self, client: TestClient):
        """测试无效时间周期"""
        request_data = {
            "strategy_config": {"strategy_name": "SmaCross", "params": {}},
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "invalid",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-12-31 23:59:59"
            }
        }

        response = client.post("/api/backtest/run", json=request_data)
        assert response.status_code == 200

    def test_backtest_id_with_special_chars(self, client: TestClient, mocker):
        """测试特殊字符回测ID"""
        mock_result = {"status": "success"}
        mocker.patch(
            "backtest.routes.backtest_service.analyze_backtest",
            return_value=mock_result
        )

        special_ids = ["bt-123", "bt_123", "bt.123", "bt:123"]
        for backtest_id in special_ids:
            response = client.get(f"/api/backtest/{backtest_id}")
            assert response.status_code == 200, f"Failed for ID: {backtest_id}"

    def test_concurrent_backtest_requests(self, client: TestClient, mocker):
        """测试并发回测请求"""
        mock_result = {"task_id": "bt_123", "status": "completed"}
        mocker.patch(
            "backtest.routes.backtest_service.run_backtest",
            return_value=mock_result
        )

        import concurrent.futures

        def make_request():
            request_data = {
                "strategy_config": {"strategy_name": "SmaCross", "params": {}},
                "backtest_config": {
                    "symbols": ["BTCUSDT"],
                    "interval": "1d",
                    "start_time": "2023-01-01 00:00:00",
                    "end_time": "2023-12-31 23:59:59"
                }
            }
            return client.post("/api/backtest/run", json=request_data)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        for response in results:
            assert response.status_code == 200
