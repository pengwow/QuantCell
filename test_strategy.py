# 测试策略

def initialize(context):
    """初始化策略"""
    context.name = "Test Strategy"
    context.description = "This is a test strategy"
    context.version = "1.0.0"
    
    # 定义策略参数
    context.params = {
        "param1": 10,
        "param2": 0.5,
        "param3": "test"
    }

def handle_data(context, data):
    """处理数据"""
    pass
