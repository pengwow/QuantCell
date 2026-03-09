# -*- coding: utf-8 -*-
"""
修复日志导入路径脚本

修复迁移后的错误导入路径

使用方法:
    cd backend
    uv run python scripts/fix_logger_imports.py
"""

import re
from pathlib import Path
from typing import List, Tuple


def get_relative_import_prefix(file_path: Path) -> str:
    """
    根据文件路径计算正确的相对导入前缀
    
    参数:
        file_path: Python文件路径
        
    返回:
        str: 正确的相对导入前缀
    """
    # 获取相对于 backend 目录的路径
    try:
        rel_path = file_path.relative_to(Path(__file__).parent.parent)
    except ValueError:
        return "utils.logger"
    
    # 计算目录深度（不包括文件名）
    depth = len(rel_path.parts) - 1
    
    if depth == 0:
        # 在 backend 根目录下
        return "utils.logger"
    else:
        # 在子目录下，使用正确的相对路径
        return "utils.logger"


def fix_import_in_file(file_path: Path, dry_run: bool = True) -> Tuple[bool, str]:
    """
    修复单个文件中的导入路径
    
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
    
    original_content = content
    
    # 修复各种错误的相对导入路径
    # 匹配模式: from ..utils.logger 或 from ...utils.logger 等
    patterns = [
        (r'^from \.\.\.\.utils\.logger import', 'from utils.logger import'),
        (r'^from \.\.\.utils\.logger import', 'from utils.logger import'),
        (r'^from \.\.utils\.logger import', 'from utils.logger import'),
        (r'^from \.utils\.logger import', 'from utils.logger import'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    if content == original_content:
        return True, "无需修改"
    
    if dry_run:
        return True, f"[预览] 将修复 {file_path}"
    
    # 写入文件
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, f"已修复 {file_path}"
    except Exception as e:
        return False, f"写入文件失败: {e}"


def find_files_with_wrong_imports(root_dir: Path) -> List[Path]:
    """查找包含错误导入的文件"""
    python_files = []
    for py_file in root_dir.rglob("*.py"):
        # 跳过 .venv 和其他不需要的目录
        if '.venv' in str(py_file):
            continue
        if '__pycache__' in str(py_file):
            continue
        
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            # 检查是否包含错误的相对导入
            if re.search(r'^from \.+utils\.logger import', content, re.MULTILINE):
                python_files.append(py_file)
        except Exception:
            pass
    
    return python_files


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='修复日志导入路径')
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
    
    python_files = find_files_with_wrong_imports(root_dir)
    print(f"找到 {len(python_files)} 个需要修复的文件")
    print("-" * 60)
    
    success_count = 0
    skip_count = 0
    error_count = 0
    fixed_count = 0
    
    for py_file in python_files:
        success, message = fix_import_in_file(py_file, dry_run=args.dry_run)
        
        if not success:
            error_count += 1
            print(f"[错误] {py_file}: {message}")
        elif "无需修改" in message:
            skip_count += 1
        elif "预览" in message or "已修复" in message:
            fixed_count += 1
            print(f"[修复] {message}")
        else:
            success_count += 1
    
    print("-" * 60)
    print(f"统计: 修复={fixed_count}, 跳过={skip_count}, 错误={error_count}")
    
    if args.dry_run and fixed_count > 0:
        print("\n提示: 移除 --dry-run 参数执行实际修复")


if __name__ == "__main__":
    main()
