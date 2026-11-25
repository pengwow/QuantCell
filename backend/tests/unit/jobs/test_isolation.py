"""worker 入口隔离：全新解释器里只加载作业代码，不带应用外壳与多余线程。"""

import json
import os
import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]

_PROBE = """
import json
import os
import sys
import threading

import jobs.worker_entry as worker_entry

forbidden = [
    "main",
    "core.lifespan",
    "worker.strategy_manager",
    "websocket.manager",
    "backtest.routes",
    "sqlalchemy",
]
print(json.dumps({
    "forbidden_loaded": [name for name in forbidden if name in sys.modules],
    "threads": threading.active_count(),
    "cwd": os.getcwd(),
    "has_run_job": hasattr(worker_entry, "run_job"),
}))
"""


def test_worker_entry_is_isolated(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_BACKEND_DIR)
    # cwd 指向临时目录：worker 入口不得依赖启动目录
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])

    assert payload["forbidden_loaded"] == []
    assert payload["threads"] == 1
    assert payload["has_run_job"] is True
