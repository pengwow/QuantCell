# 模型验证测试
# 测试Pydantic模型的请求/响应验证

import pytest
from pydantic import ValidationError
from datetime import datetime


class TestStrategySchemas:
    """策略模型验证测试类"""

    def test_strategy_upload_request_valid(self):
        """测试有效的策略上传请求"""
        from strategy.schemas import StrategyUploadRequest

        request = StrategyUploadRequest(
            strategy_name="TestStrategy",
            file_content="class TestStrategy:\n    pass",
            description="测试策略",
        )
        assert request.strategy_name == "TestStrategy"
        assert request.description == "测试策略"

    def test_strategy_upload_request_minimal(self):
        """测试最小策略上传请求"""
        from strategy.schemas import StrategyUploadRequest

        request = StrategyUploadRequest(
            strategy_name="TestStrategy", file_content="class TestStrategy:\n    pass"
        )
        assert request.description is None

    def test_strategy_upload_request_missing_required(self):
        """测试缺少必填字段的策略上传请求"""
        from strategy.schemas import StrategyUploadRequest

        with pytest.raises(ValidationError) as exc_info:
            StrategyUploadRequest(strategy_name="TestStrategy")
        assert "file_content" in str(exc_info.value)

    def test_strategy_upload_request_empty_name(self):
        """测试空策略名称应该抛出验证错误"""
        from strategy.schemas import StrategyUploadRequest

        with pytest.raises(ValidationError) as exc_info:
            StrategyUploadRequest(
                strategy_name="", file_content="class TestStrategy:\n    pass"
            )
        assert "strategy_name" in str(exc_info.value)

    def test_strategy_upload_request_unicode(self):
        """测试Unicode策略名称"""
        from strategy.schemas import StrategyUploadRequest

        request = StrategyUploadRequest(
            strategy_name="策略_中文",
            file_content="class 策略:\n    pass",
            description="中文描述",
        )
        assert "策略" in request.strategy_name

    def test_strategy_upload_request_very_long_content(self):
        """测试超长策略内容"""
        from strategy.schemas import StrategyUploadRequest

        long_content = "# Line\n" * 10000
        request = StrategyUploadRequest(
            strategy_name="LongStrategy", file_content=long_content
        )
        assert len(request.file_content) > 50000


class TestBacktestSchemas:
    """回测模型验证测试类"""

    def test_backtest_config_valid(self):
        """测试有效的回测配置"""
        from backtest.schemas import BacktestConfig

        config = BacktestConfig(
            symbols=["BTCUSDT", "ETHUSDT"],
            interval="1d",
            start_time="2023-01-01 00:00:00",
            end_time="2023-12-31 23:59:59",
            initial_cash=10000.0,
            commission=0.001,
        )
        assert config.symbols == ["BTCUSDT", "ETHUSDT"]
        assert config.interval == "1d"

    def test_backtest_config_defaults(self):
        """测试回测配置默认值"""
        from backtest.schemas import BacktestConfig

        config = BacktestConfig(
            symbols=["BTCUSDT"],
            start_time="2023-01-01 00:00:00",
            end_time="2023-12-31 23:59:59",
        )
        assert config.interval == "1d"
        assert config.initial_cash == 10000.0
        assert config.commission == 0.001
        assert config.exclusive_orders == True

    def test_backtest_config_missing_required(self):
        """测试缺少必填字段的回测配置"""
        from backtest.schemas import BacktestConfig

        with pytest.raises(ValidationError) as exc_info:
            BacktestConfig(symbols=["BTCUSDT"])
        assert "start_time" in str(exc_info.value)

    def test_backtest_config_empty_symbols(self):
        """测试空交易对列表"""
        from backtest.schemas import BacktestConfig

        with pytest.raises(ValidationError) as exc_info:
            BacktestConfig(
                symbols=[],
                start_time="2023-01-01 00:00:00",
                end_time="2023-12-31 23:59:59",
            )
        assert "symbols" in str(exc_info.value)

    def test_backtest_config_invalid_interval(self):
        """测试无效的时间周期"""
        from backtest.schemas import BacktestConfig

        config = BacktestConfig(
            symbols=["BTCUSDT"],
            interval="invalid",
            start_time="2023-01-01 00:00:00",
            end_time="2023-12-31 23:59:59",
        )
        assert config.interval == "invalid"

    def test_backtest_config_negative_cash(self):
        """测试负初始资金应该抛出验证错误"""
        from backtest.schemas import BacktestConfig

        with pytest.raises(ValidationError) as exc_info:
            BacktestConfig(
                symbols=["BTCUSDT"],
                start_time="2023-01-01 00:00:00",
                end_time="2023-12-31 23:59:59",
                initial_cash=-1000.0,
            )
        assert "initial_cash" in str(exc_info.value)

    def test_backtest_config_high_commission(self):
        """测试高手续费率"""
        from backtest.schemas import BacktestConfig

        config = BacktestConfig(
            symbols=["BTCUSDT"],
            start_time="2023-01-01 00:00:00",
            end_time="2023-12-31 23:59:59",
            commission=0.5,
        )
        assert config.commission == 0.5

    def test_strategy_config_valid(self):
        """测试有效的策略配置"""
        from backtest.schemas import StrategyConfig

        config = StrategyConfig(strategy_name="SmaCross", params={"n1": 10, "n2": 20})
        assert config.strategy_name == "SmaCross"
        assert config.params["n1"] == 10

    def test_strategy_config_defaults(self):
        """测试策略配置默认值"""
        from backtest.schemas import StrategyConfig

        config = StrategyConfig(strategy_name="TestStrategy")
        assert config.params == {}

    def test_strategy_config_nested_params(self):
        """测试嵌套参数策略配置"""
        from backtest.schemas import StrategyConfig

        config = StrategyConfig(
            strategy_name="ComplexStrategy",
            params={"ma": {"fast": 10, "slow": 20}, "rsi": {"period": 14}},
        )
        assert config.params["ma"]["fast"] == 10

    def test_backtest_run_request_valid(self):
        """测试有效的回测执行请求"""
        from backtest.schemas import BacktestRunRequest, StrategyConfig, BacktestConfig

        request = BacktestRunRequest(
            strategy_config=StrategyConfig(
                strategy_name="SmaCross", params={"n1": 10, "n2": 20}
            ),
            backtest_config=BacktestConfig(
                symbols=["BTCUSDT"],
                interval="1d",
                start_time="2023-01-01 00:00:00",
                end_time="2023-12-31 23:59:59",
            ),
        )
        assert request.strategy_config.strategy_name == "SmaCross"

    def test_backtest_run_request_missing_strategy_config(self):
        """测试缺少策略配置的回测请求"""
        from backtest.schemas import BacktestRunRequest, BacktestConfig

        with pytest.raises(ValidationError) as exc_info:
            BacktestRunRequest(
                backtest_config=BacktestConfig(
                    symbols=["BTCUSDT"],
                    start_time="2023-01-01 00:00:00",
                    end_time="2023-12-31 23:59:59",
                )
            )
        assert "strategy_config" in str(exc_info.value)


class TestSettingsSchemas:
    """设置模型验证测试类"""

    def test_config_update_request_valid(self):
        """测试有效的配置更新请求"""
        from settings.schemas import ConfigUpdateRequest

        request = ConfigUpdateRequest(
            key="test_config",
            value="test_value",
            description="测试配置",
            is_sensitive=False,
        )
        assert request.key == "test_config"
        assert request.is_sensitive == False

    def test_config_update_request_minimal(self):
        """测试最小配置更新请求"""
        from settings.schemas import ConfigUpdateRequest

        request = ConfigUpdateRequest(key="test_config", value="test_value")
        assert request.description is None
        assert request.is_sensitive == False

    def test_config_update_request_sensitive(self):
        """测试敏感配置更新请求"""
        from settings.schemas import ConfigUpdateRequest

        request = ConfigUpdateRequest(
            key="api_key", value="secret123", is_sensitive=True
        )
        assert request.is_sensitive == True

    def test_config_update_request_missing_key(self):
        """测试缺少键的配置更新请求"""
        from settings.schemas import ConfigUpdateRequest

        with pytest.raises(ValidationError) as exc_info:
            ConfigUpdateRequest(value="test_value")
        assert "key" in str(exc_info.value)

    def test_config_batch_update_request_dict(self):
        """测试字典格式的批量配置更新请求"""
        from settings.schemas import ConfigBatchUpdateRequest

        request = ConfigBatchUpdateRequest(
            configs={"config1": "value1", "config2": "value2"}
        )
        assert request.configs["config1"] == "value1"

    def test_config_batch_update_request_list(self):
        """测试列表格式的批量配置更新请求"""
        from settings.schemas import ConfigBatchUpdateRequest, ConfigBatchUpdateItem

        request = ConfigBatchUpdateRequest(
            configs=[
                ConfigBatchUpdateItem(key="config1", value="value1"),
                ConfigBatchUpdateItem(key="config2", value="value2"),
            ]
        )
        assert len(request.configs) == 2

    def test_system_config_item_valid(self):
        """测试有效的系统配置项"""
        from settings.schemas import SystemConfigItem

        config = SystemConfigItem(
            key="test_config",
            value="test_value",
            description="测试配置",
            is_sensitive=False,
        )
        assert config.created_at is None
        assert config.updated_at is None

    def test_system_info_valid(self):
        """测试有效的系统信息"""
        from settings.schemas import (
            SystemInfo,
            VersionInfo,
            RunningStatus,
            ResourceUsage,
        )

        info = SystemInfo(
            version=VersionInfo(
                system_version="1.0.0",
                python_version="3.12.12",
                build_date="2025-11-30",
            ),
            running_status=RunningStatus(
                uptime="0 天 0 小时",
                status="running",
                status_color="green",
                last_check="2026-01-24 18:00:00",
            ),
            resource_usage=ResourceUsage(
                cpu_usage=24.9,
                memory_usage="5.25GB / 16.0GB",
                disk_space="11.43GB / 228.27GB",
            ),
        )
        assert info.version.system_version == "1.0.0"


class TestCommonSchemas:
    """通用模型验证测试类"""

    def test_api_response_valid(self):
        """测试有效的API响应"""
        from common.schemas import ApiResponse

        response = ApiResponse(code=0, message="操作成功", data={"key": "value"})
        assert response.code == 0
        assert response.message == "操作成功"

    def test_api_response_error(self):
        """测试错误API响应"""
        from common.schemas import ApiResponse

        response = ApiResponse(code=1, message="操作失败", data=None)
        assert response.code == 1

    def test_api_response_with_list_data(self):
        """测试列表数据的API响应"""
        from common.schemas import ApiResponse

        response = ApiResponse(
            code=0, message="获取列表成功", data=[{"id": 1}, {"id": 2}]
        )
        assert len(response.data) == 2

    def test_pagination_request_valid(self):
        """测试有效的分页请求"""
        from common.schemas import PaginationRequest

        request = PaginationRequest(page=1, page_size=20)
        assert request.page == 1
        assert request.page_size == 20

    def test_pagination_request_defaults(self):
        """测试分页请求默认值"""
        from common.schemas import PaginationRequest

        request = PaginationRequest()
        assert request.page == 1
        assert request.page_size == 10

    def test_pagination_request_zero_page(self):
        """测试零页码的分页请求"""
        from common.schemas import PaginationRequest

        request = PaginationRequest(page=0)
        assert request.page == 0

    def test_pagination_request_large_page_size(self):
        """测试超大页面大小的分页请求"""
        from common.schemas import PaginationRequest

        request = PaginationRequest(page_size=10000)
        assert request.page_size == 10000


class TestDataIntegritySchemas:
    """数据完整性模型验证测试类"""

    def test_data_integrity_check_request_valid(self):
        """测试有效的数据完整性检查请求"""
        from backtest.schemas import DataIntegrityCheckRequest

        request = DataIntegrityCheckRequest(
            symbol="BTCUSDT",
            interval="1d",
            start_time="2023-01-01 00:00:00",
            end_time="2023-12-31 23:59:59",
        )
        assert request.symbol == "BTCUSDT"
        assert request.market_type == "crypto"
        assert request.crypto_type == "spot"

    def test_data_integrity_check_request_defaults(self):
        """测试数据完整性检查请求默认值"""
        from backtest.schemas import DataIntegrityCheckRequest

        request = DataIntegrityCheckRequest(
            symbol="BTCUSDT",
            interval="1d",
            start_time="2023-01-01 00:00:00",
            end_time="2023-12-31 23:59:59",
        )
        assert request.market_type == "crypto"
        assert request.crypto_type == "spot"

    def test_data_integrity_result_valid(self):
        """测试有效的数据完整性结果"""
        from backtest.schemas import DataIntegrityResult, MissingRange, QualityIssue

        result = DataIntegrityResult(
            is_complete=True,
            total_expected=1000,
            total_actual=1000,
            missing_count=0,
            coverage_percent=100.0,
        )
        assert result.is_complete == True
        assert result.missing_ranges == []
        assert result.quality_issues == []

    def test_data_integrity_result_with_issues(self):
        """测试带问题的数据完整性结果"""
        from backtest.schemas import DataIntegrityResult, MissingRange, QualityIssue

        result = DataIntegrityResult(
            is_complete=False,
            total_expected=1000,
            total_actual=900,
            missing_count=100,
            missing_ranges=[MissingRange(start="2023-06-01", end="2023-06-10")],
            quality_issues=[QualityIssue(type="missing_data", message="数据缺失")],
            coverage_percent=90.0,
        )
        assert result.is_complete == False
        assert len(result.missing_ranges) == 1


class TestSchemaEdgeCases:
    """模型边界条件测试类"""

    def test_very_long_string_values(self):
        """测试超长字符串值"""
        from strategy.schemas import StrategyUploadRequest

        long_string = "a" * 100000
        request = StrategyUploadRequest(
            strategy_name=long_string[:100], file_content=long_string
        )
        assert len(request.file_content) == 100000

    def test_unicode_in_all_fields(self):
        """测试所有字段的Unicode支持"""
        from strategy.schemas import StrategyUploadRequest

        request = StrategyUploadRequest(
            strategy_name="策略_中文",
            file_content="# 中文注释\nclass 策略:\n    pass",
            description="中文描述_日本語_한국어",
        )
        assert "中文" in request.strategy_name

    def test_special_characters_in_strings(self):
        """测试字符串中的特殊字符"""
        from strategy.schemas import StrategyUploadRequest

        special_chars = "<script>alert('xss')</script>&\"'\n\t\r"
        request = StrategyUploadRequest(
            strategy_name="TestStrategy", file_content=special_chars
        )
        assert request.file_content == special_chars

    def test_null_values_handling(self):
        """测试null值处理"""
        from strategy.schemas import StrategyUploadRequest

        request = StrategyUploadRequest(
            strategy_name="TestStrategy", file_content="content", description=None
        )
        assert request.description is None

    def test_empty_strings(self):
        """测试空字符串"""
        from settings.schemas import ConfigUpdateRequest

        request = ConfigUpdateRequest(key="", value="")
        assert request.key == ""
        assert request.value == ""

    def test_whitespace_only_strings(self):
        """测试仅空白字符的字符串"""
        from settings.schemas import ConfigUpdateRequest

        request = ConfigUpdateRequest(key="   ", value="\t\n")
        assert request.key == "   "
        assert request.value == "\t\n"

    def test_numeric_string_values(self):
        """测试数字字符串值"""
        from settings.schemas import ConfigUpdateRequest

        request = ConfigUpdateRequest(key="123", value="456.789")
        assert request.key == "123"
        assert request.value == "456.789"

    def test_boolean_string_values(self):
        """测试布尔字符串值"""
        from settings.schemas import ConfigUpdateRequest

        request = ConfigUpdateRequest(key="true", value="false")
        assert request.key == "true"
        assert request.value == "false"

    def test_json_string_values(self):
        """测试JSON字符串值"""
        from settings.schemas import ConfigUpdateRequest

        json_value = '{"nested": {"key": "value"}, "array": [1, 2, 3]}'
        request = ConfigUpdateRequest(key="json_config", value=json_value)
        assert request.value == json_value

    def test_datetime_string_formats(self):
        """测试日期时间字符串格式"""
        from backtest.schemas import BacktestConfig

        formats = ["2023-01-01 00:00:00", "2023-12-31 23:59:59", "2023-06-15 12:30:45"]
        for fmt in formats:
            config = BacktestConfig(
                symbols=["BTCUSDT"], start_time=fmt, end_time="2023-12-31 23:59:59"
            )
            assert config.start_time == fmt

    def test_array_with_various_types(self):
        """测试包含各种类型的数组"""
        from backtest.schemas import BacktestConfig

        symbols = ["BTCUSDT", "ETH-USDT", "ADA_USDT", "XRP/USD"]
        config = BacktestConfig(
            symbols=symbols,
            start_time="2023-01-01 00:00:00",
            end_time="2023-12-31 23:59:59",
        )
        assert len(config.symbols) == 4

    def test_nested_dict_validation(self):
        """测试嵌套字典验证"""
        from backtest.schemas import StrategyConfig

        nested_params = {
            "level1": {"level2": {"level3": "deep_value"}},
            "array": [1, 2, {"nested": "value"}],
        }
        config = StrategyConfig(strategy_name="NestedStrategy", params=nested_params)
        assert config.params["level1"]["level2"]["level3"] == "deep_value"

    def test_schema_serialization(self):
        """测试模型序列化"""
        from common.schemas import ApiResponse

        response = ApiResponse(code=0, message="成功", data={"key": "value"})
        serialized = response.model_dump()
        assert serialized["code"] == 0
        assert "timestamp" in serialized

    def test_schema_json_serialization(self):
        """测试模型JSON序列化"""
        import json
        from common.schemas import ApiResponse

        response = ApiResponse(code=0, message="成功", data={"key": "value"})
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["code"] == 0
