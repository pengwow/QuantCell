# -*- coding: utf-8 -*-
"""
日志迁移脚本

将项目中的 `from loguru import logger` 替换为新的统一日志模块

使用方法:
    cd backend
    uv run python scripts/migrate_logger.py
"""

import os
import re
from pathlib import Path
from typing import List, Tuple


# 需要跳过的目录
SKIP_DIRS = {
    '.venv',
    '__pycache__',
    '.git',
    '.pytest_cache',
    'logs',
    'results',
    'performance_reports',
    'migrations',
    'alembic',
}

# 需要跳过的文件
SKIP_FILES = {
    'migrate_logger.py',
    'logger.py',  # 不替换日志模块本身
}


def should_skip_path(path: Path) -> bool:
    """检查是否应该跳过该路径"""
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    if path.name in SKIP_FILES:
        return True
    return False


def find_python_files(root_dir: Path) -> List[Path]:
    """查找所有Python文件"""
    python_files = []
    for py_file in root_dir.rglob("*.py"):
        if not should_skip_path(py_file):
            python_files.append(py_file)
    return python_files


def check_loguru_import(content: str) -> bool:
    """检查是否包含 loguru 导入"""
    patterns = [
        r'^from\s+loguru\s+import\s+logger',
        r'^import\s+loguru',
    ]
    for pattern in patterns:
        if re.search(pattern, content, re.MULTILINE):
            return True
    return False


def migrate_file(file_path: Path, dry_run: bool = True) -> Tuple[bool, str]:
    """
    迁移单个文件

    参数:
        file_path: 文件路径
        dry_run: 是否只预览不执行

    返回:
        (是否成功, 消息)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, f"读取文件失败: {e}"

    # 检查是否包含 loguru 导入
    if not check_loguru_import(content):
        return True, "无需修改"

    # 计算相对导入路径
    try:
        relative_depth = len(file_path.relative_to(Path(__file__).parent.parent).parts) - 1
    except ValueError:
        relative_depth = 0

    if relative_depth == 0:
        import_prefix = "utils.logger"
    else:
        import_prefix = "." * relative_depth + "utils.logger"

    # 替换导入语句
    original_content = content

    # 替换 `from loguru import logger`
    content = re.sub(
        r'^from\s+loguru\s+import\s+logger\s*$',
        f'from {import_prefix} import get_logger, LogType\n\n# 获取模块日志器\nlogger = get_logger(__name__, LogType.APPLICATION)',
        content,
        flags=re.MULTILINE
    )

    # 替换 `from loguru import logger as xxx`
    content = re.sub(
        r'^from\s+loguru\s+import\s+logger\s+as\s+(\w+)\s*$',
        f'from {import_prefix} import get_logger, LogType\n\n# 获取模块日志器\n\\1 = get_logger(__name__, LogType.APPLICATION)',
        content,
        flags=re.MULTILINE
    )

    # 替换 `import loguru` (这种情况较少)
    content = re.sub(
        r'^import\s+loguru\s*$',
        f'from {import_prefix} import get_logger, LogType\n\n# 获取模块日志器\nlogger = get_logger(__name__, LogType.APPLICATION)',
        content,
        flags=re.MULTILINE
    )

    if content == original_content:
        return True, "内容未改变"

    if dry_run:
        return True, f"[预览] 将替换 {file_path}"

    # 写入文件
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, f"已更新 {file_path}"
    except Exception as e:
        return False, f"写入文件失败: {e}"


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='迁移日志导入语句')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不实际修改文件')
    parser.add_argument('--path', type=str, default='.', help='要扫描的目录路径')
    args = parser.parse_args()

    root_dir = Path(args.path).resolve()
    if not root_dir.exists():
        print(f"错误: 目录不存在: {root_dir}")
        return

    print(f"扫描目录: {root_dir}")
    print(f"模式: {'预览' if args.dry_run else '执行'}")
    print("-" * 60)

    python_files = find_python_files(root_dir)
    print(f"找到 {len(python_files)} 个Python文件")
    print("-" * 60)

    success_count = 0
    skip_count = 0
    error_count = 0
    modified_count = 0

    for py_file in python_files:
        success, message = migrate_file(py_file, dry_run=args.dry_run)

        if not success:
            error_count += 1
            print(f"[错误] {py_file}: {message}")
        elif "无需修改" in message:
            skip_count += 1
        elif "预览" in message or "已更新" in message:
            modified_count += 1
            print(f"[修改] {message}")
        else:
            success_count += 1

    print("-" * 60)
    print(f"统计: 修改={modified_count}, 跳过={skip_count}, 错误={error_count}")

    if args.dry_run and modified_count > 0:
        print("\n提示: 使用 --dry-run=false 执行实际修改")


if __name__ == "__main__":
    main()
