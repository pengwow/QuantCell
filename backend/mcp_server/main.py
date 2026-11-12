"""MCP stdio 入口（P2-04）。

启动：cd backend && QUANTCELL_MCP_TOKEN=qctk_xxx uv run python -m mcp_server.main
（如需暴露写工具：QUANTCELL_MCP_ENABLE_WRITE=1）
"""

import asyncio

from mcp_server.server import serve


def main() -> None:
    # mcp 2.x 官方样例即 asyncio.run + stdio_server 组合
    asyncio.run(serve())


if __name__ == "__main__":
    main()
