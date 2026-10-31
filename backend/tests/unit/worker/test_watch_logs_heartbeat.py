"""watch_logs 空窗心跳最小自检（修复：worker 面板在通道零产出时无法区分流死活）。

注意 watch_logs 只监控增量（初始 position=文件当前大小），历史回放是 tail_logs 的职责，
所以测试时序为：启动即空窗 → 心跳哨兵 → 写入新行 → 产出 entry → 再空窗 → 再心跳。
"""

import asyncio
import os

import pytest

from worker.log_utils import LogFileReader


@pytest.fixture
def reader(tmp_path, monkeypatch):
    r = LogFileReader(log_directory=str(tmp_path))
    # 心跳时序是本测试的关注点，行解析不是 —— 固定解析结果排除格式干扰
    monkeypatch.setattr(
        LogFileReader,
        "_parse_line",
        staticmethod(
            lambda line, tz_parser=None, default_timestamp=None: {"message": line.strip()} if line.strip() else None
        ),
    )
    return r


def _write(reader, worker_id, text):
    path = os.path.join(reader.log_directory, f"worker_{worker_id}.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def test_watch_logs_entries_then_heartbeat(reader):
    """entry 与心跳交替产出：日志流动时用 entry，空窗超阈值时发 None 哨兵。"""

    async def run():
        it = reader.watch_logs(worker_id="42", poll_interval=0.01, idle_heartbeat_s=0.05).__aiter__()
        # 启动即空窗：第一个产出只能是心跳哨兵（增量监控不回放已有内容）
        assert await asyncio.wait_for(it.__anext__(), timeout=2) is None
        # 消费方挂起等待期间写入新日志 → 产出 entry 而非心跳
        task = asyncio.ensure_future(it.__anext__())
        await asyncio.sleep(0.03)
        _write(reader, "42", "2026-10-29 09:40:57.490 | INFO | 启动")
        entry = await asyncio.wait_for(task, timeout=2)
        assert entry == {"message": "2026-10-29 09:40:57.490 | INFO | 启动"}
        # 之后再空窗 → 心跳恢复周期性，不枯竭
        assert await asyncio.wait_for(it.__anext__(), timeout=2) is None

    asyncio.run(asyncio.wait_for(run(), timeout=5))


def test_watch_logs_default_no_heartbeat(reader):
    """默认 idle_heartbeat_s=None 保持旧行为：空窗时纯挂起，不产出任何值（含哨兵）。"""

    async def run():
        it = reader.watch_logs(worker_id="43", poll_interval=0.01).__aiter__()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(it.__anext__(), timeout=0.15)

    asyncio.run(run())
