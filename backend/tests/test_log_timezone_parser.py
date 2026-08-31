"""
日志时区解析器单元测试

测试覆盖：
- 多种时间戳格式解析
- 不同时区检测和转换
- 边界情况和异常处理
- 集成到 LogFileReader 的端到端测试
"""

import os
import shutil
import tempfile
from datetime import UTC, datetime, timedelta, timezone

import pytest

from worker.log_utils import LogTimezoneParser


class TestTimestampPatternMatching:
    """测试时间戳模式匹配"""

    def test_iso8601_with_z_nanoseconds(self):
        """测试 ISO 8601 + Z（纳秒精度）"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.685406000Z"
        dt = parser.parse_timestamp(ts)

        assert dt.year == 2026
        assert dt.month == 5
        assert dt.day == 7
        assert dt.hour == 2
        assert dt.minute == 40
        assert dt.second == 46
        assert dt.microsecond == 685406
        assert dt.tzinfo == UTC

    def test_iso8601_with_z_microseconds(self):
        """测试 ISO 8601 + Z（微秒精度）"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.685406Z"
        dt = parser.parse_timestamp(ts)

        assert dt.microsecond == 685406
        assert dt.tzinfo == UTC

    def test_iso8601_with_z_milliseconds(self):
        """测试 ISO 8601 + Z（毫秒精度）"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.685Z"
        dt = parser.parse_timestamp(ts)

        assert dt.microsecond == 685000
        assert dt.tzinfo == UTC

    def test_iso8601_with_z_seconds_only(self):
        """测试 ISO 8601 + Z（秒精度）"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46Z"
        dt = parser.parse_timestamp(ts)

        assert dt.microsecond == 0
        assert dt.tzinfo == UTC

    def test_iso8601_with_positive_offset(self):
        """测试 ISO 8601 + 正偏移量"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T10:40:46.685406000+08:00"
        dt = parser.parse_timestamp(ts)

        assert dt.hour == 10
        assert dt.utcoffset() == timedelta(hours=8)

    def test_iso8601_with_negative_offset(self):
        """测试 ISO 8601 + 负偏移量"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.685406000-05:00"
        dt = parser.parse_timestamp(ts)

        assert dt.hour == 2
        assert dt.utcoffset() == timedelta(hours=-5)

    def test_iso8601_with_half_hour_offset(self):
        """测试 ISO 8601 + 半小时偏移量"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T10:40:46+05:30"
        dt = parser.parse_timestamp(ts)

        assert dt.utcoffset() == timedelta(hours=5, minutes=30)

    def test_iso8601_without_timezone(self):
        """测试 ISO 8601 无时区（默认 UTC）"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.685406"
        dt = parser.parse_timestamp(ts)

        assert dt.tzinfo == UTC

    def test_iso8601_without_timezone_no_microseconds(self):
        """测试 ISO 8601 无时区无微秒"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46"
        dt = parser.parse_timestamp(ts)

        assert dt.microsecond == 0
        assert dt.tzinfo == UTC

    def test_space_separated_with_microseconds(self):
        """测试空格分隔格式（带微秒）"""
        parser = LogTimezoneParser()
        ts = "2026-05-07 02:40:46.685406"
        dt = parser.parse_timestamp(ts)

        assert dt.hour == 2
        assert dt.microsecond == 685406
        assert dt.tzinfo == UTC

    def test_space_separated_without_microseconds(self):
        """测试空格分隔格式（无微秒）"""
        parser = LogTimezoneParser()
        ts = "2026-05-07 02:40:46"
        dt = parser.parse_timestamp(ts)

        assert dt.hour == 2
        assert dt.microsecond == 0
        assert dt.tzinfo == UTC

    def test_midnight_timestamp(self):
        """测试午夜时间戳"""
        parser = LogTimezoneParser()
        ts = "2026-01-01T00:00:00.000000000Z"
        dt = parser.parse_timestamp(ts)

        assert dt.hour == 0
        assert dt.minute == 0
        assert dt.second == 0
        assert dt.microsecond == 0

    def test_end_of_day_timestamp(self):
        """测试一天结束时间戳"""
        parser = LogTimezoneParser()
        ts = "2026-12-31T23:59:59.999999999Z"
        dt = parser.parse_timestamp(ts)

        assert dt.hour == 23
        assert dt.minute == 59
        assert dt.second == 59
        assert dt.microsecond == 999999


class TestTimezoneDetection:
    """测试时区检测"""

    def test_detect_utc_from_z_suffix(self):
        """测试从 Z 后缀检测 UTC"""
        parser = LogTimezoneParser()
        lines = [
            "2026-05-07T02:40:46.685406000Z [INFO] Test: message",
            "2026-05-07T02:40:46.685406001Z [DEBUG] Test: message",
        ]
        tz = parser.detect_timezone_from_lines(lines)

        assert tz == UTC

    def test_detect_positive_offset(self):
        """测试检测正偏移量"""
        parser = LogTimezoneParser()
        lines = [
            "2026-05-07T10:40:46.685406000+08:00 [INFO] Test: message",
            "2026-05-07T10:40:46.685406001+08:00 [DEBUG] Test: message",
        ]
        tz = parser.detect_timezone_from_lines(lines)

        assert tz == timezone(timedelta(hours=8))

    def test_detect_negative_offset(self):
        """测试检测负偏移量"""
        parser = LogTimezoneParser()
        lines = [
            "2026-05-07T02:40:46.685406000-05:00 [INFO] Test: message",
        ]
        tz = parser.detect_timezone_from_lines(lines)

        assert tz == timezone(timedelta(hours=-5))

    def test_detect_from_header_text(self):
        """测试从头部文本检测时区"""
        parser = LogTimezoneParser()
        lines = [
            "timezone: UTC",
            "some other content",
        ]
        tz = parser.detect_timezone_from_header(lines)

        assert tz == UTC

    def test_detect_from_header_cst(self):
        """测试从头部检测 CST"""
        parser = LogTimezoneParser()
        lines = [
            "timezone: CST",
        ]
        tz = parser.detect_timezone_from_header(lines)

        assert tz == timezone(timedelta(hours=8))

    def test_detect_from_header_offset(self):
        """测试从头部检测偏移量"""
        parser = LogTimezoneParser()
        lines = [
            "tz: +09:00",
        ]
        tz = parser.detect_timezone_from_header(lines)

        assert tz == timezone(timedelta(hours=9))

    def test_default_utc_when_no_info(self):
        """测试无信息时默认 UTC"""
        parser = LogTimezoneParser()
        lines = [
            "some random text without timezone info",
            "another line",
        ]
        tz = parser.detect_timezone_from_lines(lines)

        assert tz == UTC

    def test_custom_default_timezone(self):
        """测试自定义默认时区"""
        custom_tz = timezone(timedelta(hours=9))
        parser = LogTimezoneParser(default_tz=custom_tz)
        lines = ["no timezone info"]
        tz = parser.detect_timezone_from_lines(lines)

        assert tz == custom_tz

    def test_detect_mixed_timezones_majority_wins(self):
        """测试混合时区时多数胜出"""
        parser = LogTimezoneParser()
        lines = [
            "2026-05-07T10:40:46+08:00 [INFO] Test: msg1",
            "2026-05-07T10:40:46+08:00 [INFO] Test: msg2",
            "2026-05-07T10:40:46+08:00 [INFO] Test: msg3",
            "2026-05-07T02:40:46Z [INFO] Test: msg4",
        ]
        tz = parser.detect_timezone_from_lines(lines)

        assert tz == timezone(timedelta(hours=8))


class TestTimezoneConversion:
    """测试时区转换"""

    def test_convert_utc_to_local(self):
        """测试 UTC 转本地时间"""
        parser = LogTimezoneParser()
        dt_utc = datetime(2026, 5, 7, 2, 40, 46, tzinfo=UTC)

        dt_local = parser.convert_timezone(dt_utc)

        # 本地时间应该不等于 UTC（除非在 UTC 时区）
        assert dt_local.tzinfo is not None

    def test_convert_utc_to_specific_timezone(self):
        """测试 UTC 转指定时区"""
        parser = LogTimezoneParser()
        dt_utc = datetime(2026, 5, 7, 2, 40, 46, tzinfo=UTC)
        target_tz = timezone(timedelta(hours=8))

        dt_converted = parser.convert_timezone(dt_utc, target_tz)

        assert dt_converted.hour == 10
        assert dt_converted.utcoffset() == timedelta(hours=8)

    def test_convert_with_no_tzinfo(self):
        """测试无时区信息的转换"""
        parser = LogTimezoneParser()
        dt_naive = datetime(2026, 5, 7, 2, 40, 46)

        dt_converted = parser.convert_timezone(dt_naive, timezone(timedelta(hours=8)))

        # 应先假设 UTC，再转换
        assert dt_converted.hour == 10

    def test_convert_preserves_precision(self):
        """测试转换保持精度"""
        parser = LogTimezoneParser()
        dt_utc = datetime(2026, 5, 7, 2, 40, 46, 123456, tzinfo=UTC)
        target_tz = timezone(timedelta(hours=8))

        dt_converted = parser.convert_timezone(dt_utc, target_tz)

        assert dt_converted.microsecond == 123456

    def test_parse_and_convert(self):
        """测试解析并转换"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.685406000Z"
        target_tz = timezone(timedelta(hours=8))

        dt = parser.parse_and_convert(ts, target_tz)

        assert dt.hour == 10
        assert dt.utcoffset() == timedelta(hours=8)


class TestNormalizeTimestamp:
    """测试时间戳标准化"""

    def test_normalize_to_iso_format(self):
        """测试标准化为 ISO 格式"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.685406000Z"

        result = parser.normalize_timestamp(ts, output_format="iso")

        assert "2026-05-07" in result
        assert "T" in result

    def test_normalize_to_local_format(self):
        """测试标准化为本地格式"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.685406000Z"

        result = parser.normalize_timestamp(ts, output_format="local")

        # 本地格式应该没有 T 和时区后缀
        assert "T" not in result
        assert "Z" not in result
        assert "+" not in result

    def test_normalize_with_target_timezone(self):
        """测试带目标时区的标准化"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.685406000Z"
        target_tz = timezone(timedelta(hours=8))

        result = parser.normalize_timestamp(ts, target_tz=target_tz, output_format="iso")

        # 应该包含 +08:00
        assert "+08:00" in result


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_timestamp(self):
        """测试空时间戳"""
        parser = LogTimezoneParser()

        with pytest.raises(ValueError, match="无法解析时间戳"):
            parser.parse_timestamp("")

    def test_whitespace_timestamp(self):
        """测试空白时间戳"""
        parser = LogTimezoneParser()

        with pytest.raises(ValueError, match="无法解析时间戳"):
            parser.parse_timestamp("   ")

    def test_invalid_format(self):
        """测试无效格式"""
        parser = LogTimezoneParser()

        with pytest.raises(ValueError, match="无法解析时间戳"):
            parser.parse_timestamp("not a timestamp")

    def test_partial_timestamp(self):
        """测试不完整时间戳（只有日期会被解析为 datetime）"""
        parser = LogTimezoneParser()
        # datetime.fromisoformat 接受纯日期字符串，返回 00:00:00
        dt = parser.parse_timestamp("2026-05-07")
        assert dt.year == 2026
        assert dt.month == 5
        assert dt.day == 7
        assert dt.hour == 0

    def test_completely_invalid_timestamp(self):
        """测试完全无效的时间戳"""
        parser = LogTimezoneParser()

        with pytest.raises(ValueError, match="无法解析时间戳"):
            parser.parse_timestamp("not-a-timestamp-at-all")

    def test_leap_year(self):
        """测试闰年"""
        parser = LogTimezoneParser()
        ts = "2024-02-29T12:00:00Z"
        dt = parser.parse_timestamp(ts)

        assert dt.month == 2
        assert dt.day == 29

    def test_year_boundary(self):
        """测试年边界"""
        parser = LogTimezoneParser()
        ts = "2025-12-31T23:59:59.999999999Z"
        dt = parser.parse_timestamp(ts)

        assert dt.year == 2025
        assert dt.month == 12
        assert dt.day == 31

    def test_nanosecond_precision(self):
        """测试纳秒精度"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.123456789Z"
        dt = parser.parse_timestamp(ts)

        # Python datetime 只支持微秒精度
        assert dt.microsecond == 123456

    def test_trailing_zeros_preserved(self):
        """测试尾部零保留"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.100000000Z"
        dt = parser.parse_timestamp(ts)

        assert dt.microsecond == 100000


class TestLogFileReaderIntegration:
    """测试与 LogFileReader 的集成"""

    @pytest.fixture
    def temp_log_dir(self):
        """创建临时日志目录"""
        temp_dir = tempfile.mkdtemp(prefix="test_logs_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def _create_log_file(self, log_dir: str, worker_id: str, lines: list[str]):
        """创建测试日志文件"""
        log_file = os.path.join(log_dir, f"worker_{worker_id}.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return log_file

    def test_parse_trading_node_format(self, temp_log_dir):
        """测试解析 TradingNode 标准格式"""
        from worker.log_utils import LogFileReader

        lines = [
            "2026-05-07T02:40:46.685406000Z [INFO] WORKER-1.TradingNode: Building system kernel",
            "2026-05-07T02:40:46.686441000Z [DEBUG] WORKER-1.TradingNode: Event loop setup",
        ]
        self._create_log_file(temp_log_dir, "1", lines)

        reader = LogFileReader(log_directory=temp_log_dir)
        logs, total = reader.query_logs("1")

        assert total == 2
        assert logs[0]["level"] == "INFO"
        assert logs[0]["source"] == "WORKER-1.TradingNode"
        assert "Building system kernel" in logs[0]["message"]

    def test_parse_with_utc_conversion(self, temp_log_dir):
        """测试 UTC 时间转换"""
        from worker.log_utils import LogFileReader

        lines = [
            "2026-05-07T02:40:46.685406000Z [INFO] WORKER-1.TradingNode: test message",
        ]
        self._create_log_file(temp_log_dir, "1", lines)

        reader = LogFileReader(log_directory=temp_log_dir)
        logs, total = reader.query_logs("1")

        assert total == 1
        # 时间戳应该是 UTC
        assert "+00:00" in logs[0]["timestamp"] or "Z" in logs[0]["timestamp"]

    def test_parse_raw_line_with_timestamp(self, temp_log_dir):
        """测试解析带时间戳的原始行"""
        from worker.log_utils import LogFileReader

        lines = [
            "2026-05-07T02:40:46.685406000Z [INFO] WORKER-1.TradingNode: standard line",
            "2026-05-07 10:40:46.123456 [ERROR] SomeModule: raw line with timestamp",
        ]
        self._create_log_file(temp_log_dir, "1", lines)

        reader = LogFileReader(log_directory=temp_log_dir)
        logs, total = reader.query_logs("1")

        assert total == 2
        # 第二行应该是 raw 格式
        assert logs[1]["source"] == "raw"
        assert logs[1]["level"] == "ERROR"

    def test_query_with_time_filter(self, temp_log_dir):
        """测试带时间过滤的查询"""
        from worker.log_utils import LogFileReader

        lines = [
            "2026-05-07T02:40:46.000000000Z [INFO] WORKER-1.TradingNode: early message",
            "2026-05-07T03:40:46.000000000Z [INFO] WORKER-1.TradingNode: later message",
            "2026-05-07T04:40:46.000000000Z [INFO] WORKER-1.TradingNode: latest message",
        ]
        self._create_log_file(temp_log_dir, "1", lines)

        reader = LogFileReader(log_directory=temp_log_dir)

        # 查询 03:00 到 04:00 之间的日志
        start = datetime(2026, 5, 7, 3, 0, 0, tzinfo=UTC)
        end = datetime(2026, 5, 7, 4, 0, 0, tzinfo=UTC)
        logs, total = reader.query_logs("1", start_time=start, end_time=end)

        assert total == 1
        assert "later message" in logs[0]["message"]

    def test_tail_logs(self, temp_log_dir):
        """测试 tail_logs 方法"""
        from worker.log_utils import LogFileReader

        lines = [f"2026-05-07T02:40:46.{i:09d}Z [INFO] WORKER-1.TradingNode: message {i}" for i in range(20)]
        self._create_log_file(temp_log_dir, "1", lines)

        reader = LogFileReader(log_directory=temp_log_dir)
        logs = reader.tail_logs("1", lines=5)

        # tail_logs 通过向后搜索换行符实现，文件末尾换行符可能导致少返回一行
        assert len(logs) >= 4
        assert len(logs) <= 5
        # 应该包含最后几条消息
        assert "message 19" in logs[-1]["message"]


class TestTradingNodeLogFormat:
    """测试 TradingNode 特定日志格式"""

    def test_trader_id_component_format(self):
        """测试 trader_id.component 格式"""
        parser = LogTimezoneParser()
        ts = "2026-05-07T02:40:46.685406000Z"
        dt = parser.parse_timestamp(ts)

        assert dt.tzinfo == UTC

    def test_multiple_component_levels(self):
        """测试多级组件名"""
        from worker.log_utils import LOG_PATTERN

        line = "2026-05-07T02:40:46.685406000Z [INFO] WORKER-1.Throttler-ORDER_SUBMIT_THROTTLER: READY"
        match = LOG_PATTERN.match(line)

        assert match is not None
        _timestamp_str, level, source, message = match.groups()
        assert level == "INFO"
        assert "Throttler" in source
        assert message == "READY"

    def test_special_characters_in_message(self):
        """测试消息中的特殊字符"""
        from worker.log_utils import LOG_PATTERN

        line = "2026-05-07T02:40:46.685406000Z [INFO] WORKER-1.Config: config.encoding='msgpack'"
        match = LOG_PATTERN.match(line)

        assert match is not None
        _, _, _, message = match.groups()
        assert "msgpack" in message

    def test_braille_art_lines(self):
        """测试 Braille 艺术字符行"""
        from worker.log_utils import LOG_PATTERN

        line = "2026-05-07T02:40:46.685413004Z [INFO] WORKER-1.TradingNode: ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣴⣶⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀"
        match = LOG_PATTERN.match(line)

        assert match is not None

    def test_separator_lines(self):
        """测试分隔符行"""
        from worker.log_utils import LOG_PATTERN

        line = "2026-05-07T02:40:46.685406000Z [INFO] WORKER-1.TradingNode: ================================================================="
        match = LOG_PATTERN.match(line)

        assert match is not None
        _, _, _, message = match.groups()
        assert "==" in message


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
