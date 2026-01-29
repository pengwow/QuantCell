#!/usr/bin/env python3
"""
插件安装脚本
用于解压并安装插件包
"""
import os
import tarfile
import json
import argparse
import sys
import shutil

def validate_package(package_path):
    """验证插件包完整性"""
    if not os.path.exists(package_path):
        raise ValueError(f"插件包不存在: {package_path}")
    
    if not package_path.endswith(".tar.gz"):
        raise ValueError(f"插件包必须是 tar.gz 格式: {package_path}")

def detect_package_type(package_path):
    """从包名检测插件类型"""
    package_name = os.path.basename(package_path)
    if "-frontend." in package_name:
        return "frontend"
    elif "-backend." in package_name:
        return "backend"
    else:
        raise ValueError(f"无法从包名确定插件类型: {package_name}")

def extract_package(package_path, extract_dir):
    """解压插件包"""
    with tarfile.open(package_path, "r:gz") as tar:
        tar.extractall(extract_dir)

def install_frontend_plugin(plugin_dir):
    """安装前端插件"""
    target_dir = "/Users/liupeng/workspace/quantcell/frontend/src/plugins"
    plugin_name = os.path.basename(plugin_dir)
    target_path = os.path.join(target_dir, plugin_name)
    
    # 检查是否已存在
    if os.path.exists(target_path):
        print(f"前端插件 {plugin_name} 已存在，将覆盖")
        shutil.rmtree(target_path)
    
    # 移动插件目录
    shutil.move(plugin_dir, target_path)
    
    print(f"前端插件 {plugin_name} 安装成功")
    print("\n注意:")
    print("- 开发模式下会自动热加载")
    print("- 生产模式需要重新构建: cd frontend && bun run build")

def install_backend_plugin(plugin_dir):
    """安装后端插件"""
    target_dir = "/Users/liupeng/workspace/quantcell/backend/plugins"
    plugin_name = os.path.basename(plugin_dir)
    target_path = os.path.join(target_dir, plugin_name)
    
    # 检查是否已存在
    if os.path.exists(target_path):
        print(f"后端插件 {plugin_name} 已存在，将覆盖")
        shutil.rmtree(target_path)
    
    # 移动插件目录
    shutil.move(plugin_dir, target_path)
    
    print(f"后端插件 {plugin_name} 安装成功")
    print("\n注意:")
    print("- 后端插件需要重启服务才能加载")
    print("- 重启命令: python service_manager.py restart backend")

def install_plugin(package_path):
    """安装插件"""
    # 验证包完整性
    validate_package(package_path)
    
    # 检测插件类型
    plugin_type = detect_package_type(package_path)
    
    # 创建临时目录
    temp_dir = "/tmp/quantcell_plugin_temp"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    try:
        # 解压包
        extract_package(package_path, temp_dir)
        
        # 获取插件目录
        plugin_dirs = os.listdir(temp_dir)
        if len(plugin_dirs) != 1:
            raise ValueError(f"插件包结构错误，应该只有一个目录: {plugin_dirs}")
        
        plugin_dir = os.path.join(temp_dir, plugin_dirs[0])
        
        # 安装插件
        if plugin_type == "frontend":
            install_frontend_plugin(plugin_dir)
        elif plugin_type == "backend":
            install_backend_plugin(plugin_dir)
        
    finally:
        # 清理临时目录
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def main():
    parser = argparse.ArgumentParser(description="插件安装脚本")
    parser.add_argument("package_path", help="插件包路径 (.tar.gz)")
    args = parser.parse_args()
    
    package_path = args.package_path
    
    try:
        install_plugin(package_path)
    except Exception as e:
        print(f"安装失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()