#!/usr/bin/env python3
"""初始化数据库脚本"""

if __name__ == "__main__":
    try:
        from collector.db import init_db

        init_db()
    except Exception:
        import traceback

        traceback.print_exc()
        import sys

        sys.exit(1)
