"""可写数据的统一目录解析。

桌面打包（PyInstaller onefile）下 ``__file__`` 位于每次启动都重新解压的临时目录
（_MEIPASS），凡以模块相对路径作为**写入**位置的数据（K线源数据、策略文件、
已装插件、日志、LLM 录制…），重启/升级即蒸发。持久数据一律以
QUANTCELL_DATA_DIR（Tauri app_data_dir）为根；开发态 env 未设置时保持历史路径。

约定：调用点只需要「read 位置 == write 位置」来自洽，打包入口
（desktop_entry.apply_runtime_env）保证在导入业务模块前注入 env。
"""

from __future__ import annotations

import os
from pathlib import Path


def get_persistent_dir(subdir: str, legacy: Path) -> Path:
    """QUANTCELL_DATA_DIR 已设置（桌面/冻结环境）→ ``<data_dir>/<subdir>``。

    否则（开发态）原样返回 legacy，行为与历史完全一致。
    """
    override = os.environ.get("QUANTCELL_DATA_DIR")
    return Path(override) / subdir if override else legacy
