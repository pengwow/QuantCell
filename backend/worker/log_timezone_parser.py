# -*- coding: utf-8 -*-
"""
日志时区解析器 (LogTimezoneParser)

功能：
- 自动识别日志文件中的时区信息（从头部或时间戳后缀）
- 支持多种时间戳格式的解析
- 将时间戳统一转换为目标时区

设计原则：
- 优先从时间戳后缀提取时区（如 Z、+08:00）
- 其次从日志头部信息推断时区
- 最后使用默认时区（UTC）

支持的时间戳格式：
- ISO 8601 + Z: 2026-05-07T02:40:46.685406000Z
- ISO 8601 + 偏移: 2026-05-07T02:40:46.685406000+08:00
- ISO 8601 无时区: 2026-05-07T02:40:46.685406
- 空格分隔: 2026-05-07 02:40:46.685406
- 短格式: 2026-05-07T02:40:46
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta, tzinfo
from typing import Optional, Tuple


# 时间戳正则表达式模式（按优先级排序）
TIMESTAMP_PATTERNS = [
    # ISO 8601 + Z (纳秒精度)
    re.compile(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,9})Z"
    ),
    # ISO 8601 + 偏移量 (纳秒精度)
    re.compile(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,9})([+-]\d{2}:\d{2})"
    ),
    # ISO 8601 + Z (秒精度)
    re.compile(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z"
    ),
    # ISO 8601 + 偏移量 (秒精度)
    re.compile(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}:\d{2})"
    ),
    # ISO 8601 无时区 (纳秒精度)
    re.compile(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,9})"
    ),
    # ISO 8601 无时区 (秒精度)
    re.compile(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    ),
    # 空格分隔 + 微秒
    re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{1,6})"
    ),
    # 空格分隔 + 秒
    re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
    ),
]

# 日志头部时区指示器
TZ_INDICATORS = {
    "UTC": timezone.utc,
    "GMT": timezone.utc,
    "CST": timezone(timedelta(hours=8)),  # 中国标准时间
    "CET": timezone(timedelta(hours=1)),  # 中欧时间
    "EST": timezone(timedelta(hours=-5)),  # 美国东部时间
    "PST": timezone(timedelta(hours=-8)),  # 太平洋时间
    "JST": timezone(timedelta(hours=9)),   # 日本时间
    "KST": timezone(timedelta(hours=9)),   # 韩国时间
}

# 头部时区文本模式
TZ_TEXT_PATTERN = re.compile(
    r"(?:timezone|tz|时区)[:\s]+([A-Za-z]{3,4}|[+-]\d{2}:\d{2})",
    re.IGNORECASE,
)


class LogTimezoneParser:
    """
    日志时区解析器

    自动识别日志文件中的时区信息，并提供时间戳解析和转换功能。
    """

    def __init__(self, default_tz: Optional[tzinfo] = None):
        """
        初始化解析器

        Parameters
        ----------
        default_tz : Optional[tzinfo]
            默认时区，当无法检测时区时使用。默认为 UTC。
        """
        self.default_tz = default_tz or timezone.utc
        self._detected_tz: Optional[tzinfo] = None

    @property
    def detected_timezone(self) -> tzinfo:
        """获取检测到的时区"""
        return self._detected_tz or self.default_tz

    def detect_timezone_from_header(self, header_lines: list[str]) -> tzinfo:
        """
        从日志头部行检测时区

        检测策略：
        1. 查找显式时区文本（如 "timezone: UTC"）
        2. 从时间戳后缀推断（如 Z 表示 UTC）
        3. 使用默认时区

        Parameters
        ----------
        header_lines : list[str]
            日志文件头部的行内容

        Returns
        -------
        tzinfo
            检测到的时区
        """
        # 策略1：查找显式时区文本
        for line in header_lines:
            tz = self._extract_tz_from_text(line)
            if tz:
                self._detected_tz = tz
                return tz

        # 策略2：从时间戳后缀推断
        for line in header_lines:
            tz = self._extract_tz_from_timestamp_suffix(line)
            if tz:
                self._detected_tz = tz
                return tz

        # 策略3：使用默认时区
        self._detected_tz = self.default_tz
        return self.default_tz

    def detect_timezone_from_lines(
        self, lines: list[str], sample_count: int = 10
    ) -> tzinfo:
        """
        从日志行采样检测时区

        Parameters
        ----------
        lines : list[str]
            日志行列表
        sample_count : int
            采样行数

        Returns
        -------
        tzinfo
            检测到的时区
        """
        # 采样前 N 行
        sample = lines[:sample_count]

        # 统计时区后缀
        tz_votes: dict[str, int] = {}
        for line in sample:
            for pattern in TIMESTAMP_PATTERNS[:4]:  # 只检查带时区后缀的模式
                match = pattern.match(line.strip())
                if match:
                    groups = match.groups()
                    if len(groups) > 1 and groups[1]:
                        suffix = groups[1]
                        tz_votes[suffix] = tz_votes.get(suffix, 0) + 1
                    elif len(groups) == 1 and "Z" in match.group(0):
                        tz_votes["Z"] = tz_votes.get("Z", 0) + 1
                    break

        # 选择出现次数最多的时区
        if tz_votes:
            most_common = max(tz_votes.items(), key=lambda x: x[1])[0]
            tz = self._parse_tz_suffix(most_common)
            if tz:
                self._detected_tz = tz
                return tz

        # 回退到头部检测
        if lines:
            return self.detect_timezone_from_header(lines[:sample_count])

        self._detected_tz = self.default_tz
        return self.default_tz

    def parse_timestamp(
        self,
        timestamp_str: str,
        assume_utc: bool = True,
    ) -> datetime:
        """
        解析时间戳字符串

        Parameters
        ----------
        timestamp_str : str
            时间戳字符串
        assume_utc : bool
            当时间戳无时区信息时，是否假设为 UTC

        Returns
        -------
        datetime
            解析后的 datetime 对象（带时区信息）
        """
        timestamp_str = timestamp_str.strip()

        # 尝试每种模式
        for pattern in TIMESTAMP_PATTERNS:
            match = pattern.match(timestamp_str)
            if match:
                groups = match.groups()
                dt_str = groups[0]
                tz_str = groups[1] if len(groups) > 1 else None

                # 解析基础时间
                dt = self._parse_datetime_string(dt_str)

                # 应用时区
                if tz_str == "Z" or (not tz_str and "Z" in timestamp_str):
                    return dt.replace(tzinfo=timezone.utc)
                elif tz_str and tz_str not in ("Z",):
                    tz = self._parse_tz_suffix(tz_str)
                    if tz:
                        return dt.replace(tzinfo=tz)
                elif assume_utc:
                    return dt.replace(tzinfo=timezone.utc)
                else:
                    return dt.replace(tzinfo=self.detected_timezone)

        # 所有模式都失败，尝试 ISO 格式直接解析
        try:
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None:
                if assume_utc:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.replace(tzinfo=self.detected_timezone)
            return dt
        except ValueError:
            pass

        raise ValueError(f"无法解析时间戳: {timestamp_str}")

    def convert_timezone(
        self,
        dt: datetime,
        target_tz: Optional[tzinfo] = None,
    ) -> datetime:
        """
        转换 datetime 到目标时区

        Parameters
        ----------
        dt : datetime
            原始 datetime 对象
        target_tz : Optional[tzinfo]
            目标时区，None 表示使用系统本地时区

        Returns
        -------
        datetime
            转换后的 datetime 对象
        """
        if dt.tzinfo is None:
            # 无时区信息，假设为检测到的时区
            dt = dt.replace(tzinfo=self.detected_timezone)

        if target_tz is None:
            # 使用系统本地时区
            return dt.astimezone()

        return dt.astimezone(target_tz)

    def parse_and_convert(
        self,
        timestamp_str: str,
        target_tz: Optional[tzinfo] = None,
    ) -> datetime:
        """
        解析时间戳并转换到目标时区（便捷方法）

        Parameters
        ----------
        timestamp_str : str
            时间戳字符串
        target_tz : Optional[tzinfo]
            目标时区

        Returns
        -------
        datetime
            解析并转换后的 datetime 对象
        """
        dt = self.parse_timestamp(timestamp_str)
        return self.convert_timezone(dt, target_tz)

    def _extract_tz_from_text(self, text: str) -> Optional[tzinfo]:
        """从文本中提取时区信息"""
        match = TZ_TEXT_PATTERN.search(text)
        if match:
            tz_str = match.group(1).upper()
            if tz_str in TZ_INDICATORS:
                return TZ_INDICATORS[tz_str]
            # 尝试解析偏移量
            try:
                if ":" in tz_str:
                    sign = 1 if tz_str[0] == "+" else -1
                    hours, minutes = map(int, tz_str[1:].split(":"))
                    return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
            except (ValueError, IndexError):
                pass
        return None

    def _extract_tz_from_timestamp_suffix(self, line: str) -> Optional[tzinfo]:
        """从时间戳后缀提取时区"""
        for pattern in TIMESTAMP_PATTERNS[:4]:  # 只检查带时区后缀的模式
            match = pattern.match(line.strip())
            if match:
                groups = match.groups()
                if len(groups) > 1 and groups[1]:
                    return self._parse_tz_suffix(groups[1])
                elif "Z" in match.group(0):
                    return timezone.utc
        return None

    def _parse_tz_suffix(self, suffix: str) -> Optional[tzinfo]:
        """解析时区后缀"""
        if suffix == "Z":
            return timezone.utc

        # 解析 +HH:MM 或 -HH:MM
        match = re.match(r"([+-])(\d{2}):(\d{2})", suffix)
        if match:
            sign = 1 if match.group(1) == "+" else -1
            hours = int(match.group(2))
            minutes = int(match.group(3))
            return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))

        # 检查缩写
        upper = suffix.upper()
        if upper in TZ_INDICATORS:
            return TZ_INDICATORS[upper]

        return None

    @staticmethod
    def _parse_datetime_string(dt_str: str) -> datetime:
        """解析日期时间字符串（无时区）"""
        # 标准化分隔符
        dt_str = dt_str.replace(" ", "T")

        # 尝试 ISO 格式
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            pass

        # 尝试常见格式
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(dt_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"无法解析日期时间字符串: {dt_str}")

    def normalize_timestamp(
        self,
        timestamp_str: str,
        target_tz: Optional[tzinfo] = None,
        output_format: str = "iso",
    ) -> str:
        """
        标准化时间戳字符串

        Parameters
        ----------
        timestamp_str : str
            原始时间戳字符串
        target_tz : Optional[tzinfo]
            目标时区
        output_format : str
            输出格式："iso" 或 "local"

        Returns
        -------
        str
            标准化后的时间戳字符串
        """
        dt = self.parse_and_convert(timestamp_str, target_tz)

        if output_format == "iso":
            return dt.isoformat()
        elif output_format == "local":
            # 返回本地时间格式（无时区后缀）
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            return dt.isoformat()


__all__ = [
    "LogTimezoneParser",
    "TIMESTAMP_PATTERNS",
    "TZ_INDICATORS",
]
