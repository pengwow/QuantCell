#!/usr/bin/env python3
# 时区转换功能测试

import os
import sys
from datetime import datetime
import pytz

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.timezone import get_timezone, to_local_time, to_utc_time, format_datetime, reload_timezone


def test_timezone_config():
    """测试时区配置的读取"""
    print("\n=== 测试时区配置 ===")
    
    # 测试默认时区
    tz = get_timezone()
    print(f"默认时区: {tz.zone}")
    assert tz.zone == "Asia/Shanghai", f"期望时区为 Asia/Shanghai，实际为 {tz.zone}"
    
    # 测试环境变量覆盖
    os.environ["APP_TIMEZONE"] = "America/New_York"
    reload_timezone()  # 重新加载时区配置
    tz = get_timezone()
    print(f"环境变量覆盖时区: {tz.zone}")
    assert tz.zone == "America/New_York", f"期望时区为 America/New_York，实际为 {tz.zone}"
    
    # 测试无效时区
    os.environ["APP_TIMEZONE"] = "Invalid/Timezone"
    reload_timezone()
    tz = get_timezone()
    print(f"无效时区默认值: {tz.zone}")
    assert tz.zone == "Asia/Shanghai", f"期望时区为 Asia/Shanghai，实际为 {tz.zone}"
    
    # 清理环境变量
    if "APP_TIMEZONE" in os.environ:
        del os.environ["APP_TIMEZONE"]
    reload_timezone()
    tz = get_timezone()
    print(f"清理后时区: {tz.zone}")
    assert tz.zone == "Asia/Shanghai", f"期望时区为 Asia/Shanghai，实际为 {tz.zone}"
    
    print("时区配置测试通过!")


def test_timezone_conversion():
    """测试时区转换功能"""
    print("\n=== 测试时区转换 ===")
    
    # 创建一个UTC时间
    utc_dt = datetime(2023, 1, 1, 0, 0, 0, tzinfo=pytz.utc)
    print(f"UTC时间: {utc_dt}")
    
    # 转换为本地时间
    local_dt = to_local_time(utc_dt)
    print(f"本地时间: {local_dt}")
    assert local_dt.tzinfo is not None, "本地时间应该有时区信息"
    
    # 转换回UTC时间
    converted_utc_dt = to_utc_time(local_dt)
    print(f"转换回UTC时间: {converted_utc_dt}")
    assert converted_utc_dt.tzinfo is not None, "转换回的UTC时间应该有时区信息"
    assert converted_utc_dt.tzinfo == pytz.utc, "转换回的时间应该是UTC时区"
    
    # 测试无时区信息的datetime对象
    naive_dt = datetime(2023, 1, 1, 0, 0, 0)
    print(f"无时区信息的时间: {naive_dt}")
    
    local_dt2 = to_local_time(naive_dt)
    print(f"转换为本地时间: {local_dt2}")
    assert local_dt2.tzinfo is not None, "本地时间应该有时区信息"
    
    converted_utc_dt2 = to_utc_time(naive_dt)
    print(f"转换为UTC时间: {converted_utc_dt2}")
    assert converted_utc_dt2.tzinfo is not None, "UTC时间应该有时区信息"
    assert converted_utc_dt2.tzinfo == pytz.utc, "转换后的时间应该是UTC时区"
    
    print("时区转换测试通过!")


def test_time_formatting():
    """测试时间格式化功能"""
    print("\n=== 测试时间格式化 ===")
    
    # 创建一个UTC时间
    utc_dt = datetime(2023, 1, 1, 0, 0, 0, tzinfo=pytz.utc)
    
    # 格式化时间
    formatted = format_datetime(utc_dt)
    print(f"格式化时间: {formatted}")
    assert isinstance(formatted, str), "格式化结果应该是字符串"
    assert len(formatted) > 0, "格式化结果不应该为空"
    
    # 测试自定义格式
    custom_formatted = format_datetime(utc_dt, "%Y-%m-%d")
    print(f"自定义格式: {custom_formatted}")
    assert custom_formatted == "2023-01-01", f"期望格式为 2023-01-01，实际为 {custom_formatted}"
    
    # 测试None值
    none_formatted = format_datetime(None)
    print(f"None值格式化: {none_formatted}")
    assert none_formatted is None, "None值应该返回None"
    
    print("时间格式化测试通过!")


def test_timezone_awareness():
    """测试时区感知模型"""
    print("\n=== 测试时区感知模型 ===")
    
    # 导入模型
    from collector.db.models import SystemConfig
    from collector.db.database import SessionLocal, init_database_config
    
    init_database_config()
    db = SessionLocal()
    
    try:
        # 创建测试配置
        config = SystemConfig(
            key="test_timezone",
            value="test_value",
            description="Test timezone awareness"
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        
        print(f"创建时间: {config.created_at}")
        print(f"更新时间: {config.updated_at}")
        
        # 测试to_dict方法
        config_dict = config.to_dict()
        print(f"to_dict结果: {config_dict}")
        assert "created_at" in config_dict, "to_dict应该包含created_at字段"
        assert "updated_at" in config_dict, "to_dict应该包含updated_at字段"
        assert isinstance(config_dict["created_at"], str), "created_at应该是字符串"
        assert isinstance(config_dict["updated_at"], str), "updated_at应该是字符串"
        
        # 测试时区转换
        from utils.timezone import format_datetime as utils_format
        formatted_created = utils_format(config.created_at)
        print(f"工具类格式化创建时间: {formatted_created}")
        assert formatted_created == config_dict["created_at"], "格式化结果应该一致"
        
        # 清理测试数据
        db.delete(config)
        db.commit()
        
        print("时区感知模型测试通过!")
    except Exception as e:
        print(f"测试失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def test_edge_cases():
    """测试边界情况"""
    print("\n=== 测试边界情况 ===")
    
    # 测试None值处理
    assert to_local_time(None) is None, "None值应该返回None"
    assert to_utc_time(None) is None, "None值应该返回None"
    assert format_datetime(None) is None, "None值应该返回None"
    
    # 测试异常处理
    try:
        # 传递非datetime对象
        result = to_local_time("not a datetime")
        print(f"非datetime对象处理: {result}")
    except Exception as e:
        print(f"异常处理测试: {e}")
    
    print("边界情况测试通过!")


if __name__ == "__main__":
    print("开始测试时区转换功能...")
    
    try:
        test_timezone_config()
        test_timezone_conversion()
        test_time_formatting()
        test_timezone_awareness()
        test_edge_cases()
        
        print("\n🎉 所有测试通过!")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
