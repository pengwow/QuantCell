#!/usr/bin/env python3
"""
QuantCell 插件构建脚本
用于构建独立的插件模块
"""

import os
import sys
import json
import subprocess
import shutil
import time
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path("/Users/liupeng/workspace/quantcell")
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
PLUGIN_DIR = FRONTEND_ROOT / "src" / "plugins"
DIST_DIR = FRONTEND_ROOT / "dist"


def get_plugin_list():
    """获取所有插件目录列表"""
    plugin_list = []
    
    if not PLUGIN_DIR.exists():
        print(f"插件目录不存在: {PLUGIN_DIR}")
        return plugin_list
    
    for item in PLUGIN_DIR.iterdir():
        if item.is_dir():
            manifest_path = item / "manifest.json"
            if manifest_path.exists():
                plugin_list.append(item.name)
    
    return plugin_list


def build_all_plugins():
    """构建所有插件"""
    print("开始构建所有插件")
    
    # 插件构建由主构建过程处理，这里只准备插件清单
    plugin_list = get_plugin_list()
    
    if not plugin_list:
        print("没有找到可构建的插件")
        return
    
    print(f"找到 {len(plugin_list)} 个插件: {', '.join(plugin_list)}")
    print("插件将在主构建过程中一起构建")


def generate_plugin_manifest():
    """生成插件清单文件"""
    print("\n生成插件清单文件")
    
    plugin_list = get_plugin_list()
    manifest_data = {
        "plugins": plugin_list,
        "timestamp": int(time.time())
    }
    
    # 写入插件清单文件
    manifest_path = DIST_DIR / "plugins" / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
    
    print(f"插件清单已生成: {manifest_path}")
    
    # 在 index.html 中注入插件列表
    inject_plugin_list_to_index()


def inject_plugin_list_to_index():
    """在 index.html 中注入插件列表"""
    print("在 index.html 中注入插件列表")
    
    index_path = FRONTEND_ROOT / "index.html"
    dist_index_path = DIST_DIR / "index.html"
    
    if not dist_index_path.exists():
        print(f"dist/index.html 不存在，请先运行主构建")
        return
    
    # 读取 index.html
    with open(dist_index_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 获取插件列表
    plugin_list = get_plugin_list()
    plugin_list_str = json.dumps(plugin_list)
    
    # 注入插件列表
    injection = f"\n    <script>window.__QUANTCELL_PLUGINS__ = {plugin_list_str};</script>\n    </head>"
    modified_content = content.replace("</head>", injection)
    
    # 写入修改后的 index.html
    with open(dist_index_path, "w", encoding="utf-8") as f:
        f.write(modified_content)
    
    print(f"插件列表已注入到: {dist_index_path}")


def main():
    """主函数"""
    print("QuantCell 插件构建脚本")
    print("=" * 50)
    
    # 检查前端目录
    if not FRONTEND_ROOT.exists():
        print(f"前端目录不存在: {FRONTEND_ROOT}")
        sys.exit(1)
    
    # 构建所有插件
    build_all_plugins()
    
    # 生成插件清单
    generate_plugin_manifest()
    
    print("\n" + "=" * 50)
    print("插件构建脚本执行完成")


if __name__ == "__main__":
    main()