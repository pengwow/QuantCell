#!/usr/bin/env python3
"""
测试配置管理器

用于测试ConfigManager类的功能，将配置数据写入config.toml文件
"""
# 添加backend目录到Python路径
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_manager import config_manager

# 用户提供的配置数据
config_items = [
    {"key":"language","value":"zh-CN","description":"basic.language","name":"basic_settings"},
    {"key":"theme","value":"light","description":"basic.theme","name":"basic_settings"},
    {"key":"showTips","value":False,"description":"basic.showTips","name":"basic_settings"},
    {"key":"timezone","value":"Asia/Shanghai","description":"basic.timezone","name":"basic_settings"},
    {"key":"enableEmail","value":False,"description":"notifications.enableEmail","name":"notification_settings"},
    {"key":"enableWebhook","value":False,"description":"notifications.enableWebhook","name":"notification_settings"},
    {"key":"webhookUrl","value":"","description":"notifications.webhookUrl","name":"notification_settings"},
    {"key":"notifyOnAlert","value":False,"description":"notifications.notifyOnAlert","name":"notification_settings"},
    {"key":"notifyOnTaskComplete","value":False,"description":"notifications.notifyOnTaskComplete","name":"notification_settings"},
    {"key":"notifyOnSystemUpdate","value":False,"description":"notifications.notifyOnSystemUpdate","name":"notification_settings"},
    {"key":"apiKey","value":"sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","description":"api.apiKey","name":"api_settings"},
    {"key":"apiPermissions","value":"[{\"id\":\"read\",\"name\":\"读取权限\",\"description\":\"允许读取系统数据和配置\",\"enabled\":true},{\"id\":\"write\",\"name\":\"写入权限\",\"description\":\"允许修改系统数据和配置\",\"enabled\":false},{\"id\":\"execute\",\"name\":\"执行权限\",\"description\":\"允许执行系统操作和任务\",\"enabled\":true}]","description":"api.permissions","name":"api_settings"},
    {"key":"qlib_data_dir","value":"data/crypto_data","description":"system.qlib_data_dir","name":"system_config"},
    {"key":"max_workers","value":"4","description":"system.max_workers","name":"system_config"},
    {"key":"data_download_dir","value":"data/source","description":"system.data_download_dir","name":"system_config"},
    {"key":"current_market_type","value":"crypto","description":"system.current_market_type","name":"system_config"},
    {"key":"crypto_trading_mode","value":"spot","description":"system.crypto_trading_mode","name":"system_config"},
    {"key":"default_exchange","value":"binance","description":"system.default_exchange","name":"system_config"},
    {"key":"default_interval","value":"1d","description":"system.default_interval","name":"system_config"},
    {"key":"default_commission","value":0.001,"description":"system.default_commission","name":"system_config"},
    {"key":"default_initial_cash","value":1000000,"description":"system.default_initial_cash","name":"system_config"},
    {"key":"proxy_enabled","value":True,"description":"system.proxy_enabled","name":"system_config"},
    {"key":"proxy_url","value":"http://127.0.0.1:7897","description":"system.proxy_url","name":"system_config"},
    {"key":"proxy_username","value":"","description":"system.proxy_username","name":"system_config"},
    {"key":"proxy_password","value":"","description":"system.proxy_password","name":"system_config"},
    {"key":"realtime_enabled","value":False,"description":"system.realtime_enabled","name":"system_config"},
    {"key":"data_mode","value":"realtime","description":"system.data_mode","name":"system_config"},
    {"key":"frontend_update_interval","value":1000,"description":"system.frontend_update_interval","name":"system_config"},
    {"key":"frontend_data_cache_size","value":1000,"description":"system.frontend_data_cache_size","name":"system_config"},
    {"key":"test_plugin_enabled","value":"true","description":"test-plugin.test_plugin_enabled","plugin":"test-plugin","name":"测试插件设置"},
    {"key":"test_plugin_mode","value":"normal","description":"test-plugin.test_plugin_mode","plugin":"test-plugin","name":"测试插件设置"},
    {"key":"test_plugin_timeout","value":"30","description":"test-plugin.test_plugin_timeout","plugin":"test-plugin","name":"测试插件设置"}
]

if __name__ == "__main__":
    print("开始测试配置管理器...")
    
    # 保存配置项
    result = config_manager.save_config_items(config_items)
    print(f"保存配置项结果: {result}")
    
    if result:
        print("\n保存成功！")
        
        # 读取配置验证
        config_data = config_manager.read_config()
        print("\n读取配置结果:")
        print(config_data)
        
        # 验证分组配置
        print("\n验证分组配置:")
        groups = ["basic_settings", "notification_settings", "api_settings", "system_config", "测试插件设置"]
        for group in groups:
            group_config = config_manager.get_config_by_group(group)
            if group_config:
                print(f"\n{group} 分组配置:")
                print(group_config)
            else:
                print(f"\n{group} 分组配置不存在")
    else:
        print("\n保存失败！")
