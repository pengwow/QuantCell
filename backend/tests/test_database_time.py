from collector.db.database import SessionLocal, init_database_config
from collector.db.models import SystemConfig

# 测试直接查询数据库，查看时间字段的实际格式
def test_database_time():
    init_database_config()
    db = SessionLocal()
    try:
        # 查询所有系统配置
        configs = db.query(SystemConfig).all()
        
        print("=== 数据库直接查询结果 ===")
        for config in configs:
            print(f"key: {config.key}")
            print(f"created_at: {config.created_at}, type: {type(config.created_at)}")
            print(f"updated_at: {config.updated_at}, type: {type(config.updated_at)}")
            print()
        
        # 测试get_with_details方法
        print("=== get_with_details方法结果 ===")
        if configs:
            key = configs[0].key
            config_dict = SystemConfig.get_with_details(key)
            print(f"key: {key}")
            print(f"created_at: {config_dict['created_at']}, type: {type(config_dict['created_at'])}")
            print(f"updated_at: {config_dict['updated_at']}, type: {type(config_dict['updated_at'])}")
    finally:
        db.close()

if __name__ == "__main__":
    test_database_time()