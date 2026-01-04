#!/usr/bin/env python3
"""
插件打包脚本
用于将插件目录打包成 tar.gz 文件
"""
import os
import tarfile
import json
import argparse
import sys

def validate_plugin_structure(plugin_dir):
    """验证插件目录结构"""
    # 检查 manifest.json
    manifest_path = os.path.join(plugin_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise ValueError(f"插件目录缺少 manifest.json 文件: {plugin_dir}")
    
    # 读取 manifest.json
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    # 检查必要字段
    required_fields = ["name", "version", "description", "author"]
    for field in required_fields:
        if field not in manifest:
            raise ValueError(f"manifest.json 缺少必要字段: {field}")
    
    return manifest

def detect_plugin_type(plugin_dir):
    """检测插件类型（前端/后端）"""
    if "frontend" in plugin_dir:
        return "frontend"
    elif "backend" in plugin_dir:
        return "backend"
    else:
        # 检查目录结构
        if os.path.exists(os.path.join(plugin_dir, "index.tsx")):
            return "frontend"
        elif os.path.exists(os.path.join(plugin_dir, "plugin.py")):
            return "backend"
        else:
            raise ValueError(f"无法确定插件类型: {plugin_dir}")

def pack_plugin(plugin_dir):
    """打包插件"""
    # 验证插件结构
    manifest = validate_plugin_structure(plugin_dir)
    
    # 检测插件类型
    plugin_type = detect_plugin_type(plugin_dir)
    
    # 生成包文件名
    plugin_name = manifest["name"]
    version = manifest["version"]
    package_name = f"{plugin_name}-{version}-{plugin_type}.tar.gz"
    
    # 获取插件目录名
    plugin_dir_name = os.path.basename(plugin_dir)
    
    # 创建 tar.gz 文件
    with tarfile.open(package_name, "w:gz") as tar:
        # 将插件目录内容添加到 tar 文件
        tar.add(plugin_dir, arcname=plugin_dir_name)
    
    print(f"插件打包成功: {package_name}")
    return package_name

def main():
    parser = argparse.ArgumentParser(description="插件打包脚本")
    parser.add_argument("plugin_dir", help="插件目录路径")
    args = parser.parse_args()
    
    plugin_dir = args.plugin_dir
    if not os.path.exists(plugin_dir):
        print(f"插件目录不存在: {plugin_dir}")
        sys.exit(1)
    
    try:
        pack_plugin(plugin_dir)
    except Exception as e:
        print(f"打包失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()