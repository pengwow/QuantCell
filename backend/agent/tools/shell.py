"""Shell 命令执行工具"""

import asyncio
from pathlib import Path
from typing import Any

from .base import Tool


class ExecTool(Tool):
    """执行 Shell 命令"""

    name = "exec"
    description = "在 shell 中执行命令。支持管道和重定向。超时默认为 60 秒。"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令"},
            "timeout": {"type": "integer", "description": "超时时间（秒）", "minimum": 1, "maximum": 300},
        },
        "required": ["command"],
    }

    def __init__(
        self,
        working_dir: str,
        timeout: int = 60,
        restrict_to_workspace: bool = False,
        path_append: str | None = None,
    ):
        self.working_dir = working_dir
        self.timeout = timeout
        self.restrict_to_workspace = restrict_to_workspace
        self.path_append = path_append

    async def execute(self, command: str, timeout: int | None = None, **kwargs: Any) -> str:
        """执行 shell 命令"""
        cmd_timeout = timeout or self.timeout
        
        # 构建环境变量
        env = None
        if self.path_append:
            import os
            env = {"PATH": f"{self.path_append}:{os.environ.get('PATH', '')}"}

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
                env=env,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=cmd_timeout
            )
            
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")
            
            result = []
            if stdout_str:
                result.append(f"[stdout]\n{stdout_str}")
            if stderr_str:
                result.append(f"[stderr]\n{stderr_str}")
            
            exit_info = f"\n[退出码: {process.returncode}]"
            
            return "\n\n".join(result) + exit_info if result else exit_info
            
        except asyncio.TimeoutError:
            return f"错误: 命令执行超时（{cmd_timeout}秒）"
        except Exception as e:
            return f"错误: 命令执行失败: {e}"
