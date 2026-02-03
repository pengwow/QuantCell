#!/usr/bin/env python3
# 测试配置加载功能

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/quantcell')

from config import get_config, get_all_configs, reload_config


def test_config_loading():
    """测试配置加载功能"""
    print("开始测试配置加载功能...")
    
    # 测试获取单个配置
    print("\n1. 测试获取单个配置:")
    db_type = get_config("database.type")
    print(f"数据库类型: {db_type}")
    
    db_file = get_config("database.file")
    print(f"数据库文件: {db_file}")
    
    app_host = get_config("app.host")
    print(f"应用主机: {app_host}")
    
    app_port = get_config("app.port")
    print(f"应用端口: {app_port}")
    
    # 测试获取不存在的配置（应该返回默认值）
    print("\n2. 测试获取不存在的配置:")
    non_existent = get_config("non_existent.key", "default_value")
    print(f"不存在的配置: {non_existent}")
    
    # 测试获取所有配置
    print("\n3. 测试获取所有配置:")
    all_configs = get_all_configs()
    print(f"配置项数量: {len(all_configs)}")
    print(f"配置键: {list(all_configs.keys())}")
    
    # 测试重新加载配置
    print("\n4. 测试重新加载配置:")
    reload_config()
    print("配置重新加载成功")
    
    # 再次获取配置验证
    db_type_after_reload = get_config("database.type")
    print(f"重新加载后数据库类型: {db_type_after_reload}")
    
    print("\n✓ 所有配置加载测试通过！")


if __name__ == "__main__":
    test_config_loading()
