import datetime
import pytz
from pydantic import BaseModel

# 测试DateTime对象的序列化
def test_datetime_serialization():
    # 创建一个带时区的datetime对象
    utc_now = datetime.datetime.now(pytz.utc)
    print(f"UTC时间: {utc_now}")
    
    # 转换为UTC+8时间
    shanghai_now = utc_now.astimezone(pytz.timezone('Asia/Shanghai'))
    print(f"上海时间: {shanghai_now}")
    
    # 格式化为字符串
    shanghai_str = shanghai_now.strftime('%Y-%m-%d %H:%M:%S')
    print(f"格式化上海时间: {shanghai_str}")
    
    # 测试Pydantic模型
    class TestModel(BaseModel):
        timestamp: str = datetime.datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
        created_at: str
        updated_at: str
    
    # 创建模型实例
    test_model = TestModel(
        created_at=shanghai_str,
        updated_at=shanghai_str
    )
    
    # 序列化模型
    json_data = test_model.model_dump()
    print(f"\nPydantic模型序列化结果:")
    print(f"timestamp: {json_data['timestamp']}")
    print(f"created_at: {json_data['created_at']}")
    print(f"updated_at: {json_data['updated_at']}")
    
    # 测试FastAPI的jsonable_encoder
    from fastapi.encoders import jsonable_encoder
    encoded_data = jsonable_encoder(test_model)
    print(f"\njsonable_encoder结果:")
    print(f"timestamp: {encoded_data['timestamp']}")
    print(f"created_at: {encoded_data['created_at']}")
    print(f"updated_at: {encoded_data['updated_at']}")

if __name__ == "__main__":
    test_datetime_serialization()