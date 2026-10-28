"""Worker 运行期日志双写 sink 自测

验证 start_worker_log_sink / stop_worker_log_sink 的完整契约：
- 文件落盘：logs/worker/worker_{id}.log 行格式对齐读侧 LOG_PATTERN
- 内存环：get_recent(worker_id=...) 能查到，且未 bind 的日志不串入
- 级别映射：loguru WARNING → WARN（前端/读侧枚举）
- 幂等：重复 start 不重复写入；stop 后不再接收、重复 stop 静默

append_worker_error_log 契约：启动失败发生在 sink 挂载之前，手动双写
（文件 + 内存环）保证前端日志 tab 可见失败原因。
"""

import re
import shutil
import tempfile
from pathlib import Path

from utils.logger import LogType, get_logger
from worker.log_utils import (
    LOG_PATTERN,
    append_worker_error_log,
    get_global_buffer,
    start_worker_log_sink,
    stop_worker_log_sink,
)

# 独立 ID 避免与真实运行中的 worker 冲突
TEST_WORKER = 999901
WORKER_LOG = Path(__file__).resolve().parent.parent / "logs" / "worker" / f"worker_{TEST_WORKER}.log"


def _fetch(**kw):
    return get_global_buffer().get_recent(worker_id=str(TEST_WORKER), **kw)


def test_worker_log_sink_double_write():
    try:
        start_worker_log_sink(TEST_WORKER)
        start_worker_log_sink(TEST_WORKER)  # 重复 start 幂等：不应双写

        wrapper = get_logger("test_worker_sink", LogType.APPLICATION).bind(worker_id=TEST_WORKER)
        wrapper.info("sink info marker_alpha")
        wrapper.warning("sink warn marker_beta")
        # 未 bind 的模块级日志不应进 per-worker 通道
        get_logger("test_worker_sink", LogType.APPLICATION).info("sink unbound marker_gamma")

        # 内存环：级别映射 + worker_id 过滤
        entries = _fetch(limit=100)
        # get_recent 返回 dict 列表（asdict(LogEntry)），时间正序
        assert [e["level"] for e in entries] == ["INFO", "WARN"], entries
        assert all(e["worker_id"] == str(TEST_WORKER) for e in entries)
        assert not _fetch(keyword="marker_gamma"), "未 bind 的日志串入了 per-worker 通道"

        # 文件：行格式可供读侧 LOG_PATTERN 解析（SSE 数据源）
        lines = WORKER_LOG.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2, lines
        for level, line in zip(["INFO", "WARN"], lines, strict=True):
            m = LOG_PATTERN.match(line)
            assert m, f"行不匹配 LOG_PATTERN: {line!r}"
            assert m.group(2) == level and m.group(3) == f"worker_{TEST_WORKER}"

        # stop 后不再接收；重复 stop 静默
        stop_worker_log_sink(TEST_WORKER)
        stop_worker_log_sink(TEST_WORKER)
        wrapper.info("sink after-stop marker_delta")
        assert WORKER_LOG.read_text(encoding="utf-8").splitlines()[-1].endswith("marker_beta")
        assert not _fetch(keyword="marker_delta")

        # 级别名预热：正则字面量自证可编译（防 LOG_PATTERN 未来误改）
        re.compile(LOG_PATTERN.pattern)
    finally:
        # mv 式清理测试产物到系统临时目录（mkdtemp 保证目标唯一，支持重复运行）
        if WORKER_LOG.exists():
            shutil.move(str(WORKER_LOG), tempfile.mkdtemp())
        stop_worker_log_sink(TEST_WORKER)


def test_append_worker_error_log_without_sink():
    """启动失败场景：sink 未挂载时手动双写，文件与内存环均可见（读侧契约）"""
    try:
        append_worker_error_log(TEST_WORKER, "启动失败: 缺 credentials_account")

        # 进程级 buffer 与 sink 测试共享，用独特 keyword 隔离本测试写入的条目
        entries = _fetch(limit=10, keyword="credentials_account")
        assert [e["level"] for e in entries] == ["ERROR"], entries
        assert len(entries) == 1
        assert entries[-1]["message"] == "启动失败: 缺 credentials_account"

        # 文件行格式同样可被 LOG_PATTERN 解析（SSE 数据源）
        lines = WORKER_LOG.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, lines
        m = LOG_PATTERN.match(lines[0])
        assert m, f"行不匹配 LOG_PATTERN: {lines[0]!r}"
        assert m.group(2) == "ERROR" and m.group(3) == f"worker_{TEST_WORKER}"
    finally:
        if WORKER_LOG.exists():
            shutil.move(str(WORKER_LOG), tempfile.mkdtemp())
        stop_worker_log_sink(TEST_WORKER)  # 未挂载时幂等静默
