#!/usr/bin/env python3
"""初始化数据库脚本"""


if __name__ == "__main__":
    print("初始化数据库...")
    
    try:
        from collector.db import init_db
        init_db()
        print("数据库初始化成功")
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        import sys
        sys.exit(1)
