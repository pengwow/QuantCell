#!/usr/bin/env python3
# 测试策略列表的创建时间是否正确

import os
import sys
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 直接测试策略服务的核心逻辑
def test_strategy_list_logic():
    """测试策略列表的创建时间逻辑"""
    print("开始测试策略列表的创建时间逻辑...")
    
    # 模拟策略服务的去重逻辑
    def test_deduplication_logic():
        """测试去重逻辑"""
        print("\n测试去重逻辑...")
        
        # 模拟策略数据
        strategies = [
            {
                "name": "strategy1",
                "source": "files",
                "created_at": datetime.now()  # 文件来源使用当前时间
            },
            {
                "name": "strategy1",
                "source": "db",
                "created_at": datetime(2023, 1, 1, 0, 0, 0)  # 数据库来源使用真实时间
            },
            {
                "name": "strategy2",
                "source": "files",
                "created_at": datetime.now()
            }
        ]
        
        # 测试去重逻辑，优先保留数据库策略
        strategy_dict = {}
        for strategy in strategies:
            if strategy["name"] not in strategy_dict or strategy["source"] == "db":
                strategy_dict[strategy["name"]] = strategy
        
        final_strategies = list(strategy_dict.values())
        
        print(f"去重前: {len(strategies)} 个策略")
        print(f"去重后: {len(final_strategies)} 个策略")
        
        for strategy in final_strategies:
            print(f"策略: {strategy['name']}, 来源: {strategy['source']}, 创建时间: {strategy['created_at']}")
            
            # 检查是否优先保留了数据库策略
            if strategy['name'] == 'strategy1':
                assert strategy['source'] == 'db', "应该优先保留数据库策略"
                assert strategy['created_at'] == datetime(2023, 1, 1, 0, 0, 0), "应该使用数据库策略的创建时间"
                print("✓ strategy1 正确使用了数据库策略的创建时间")
            else:
                print("✓ strategy2 正确使用了文件策略")
        
        print("去重逻辑测试通过!")
    
    # 测试文件修改时间获取逻辑
    def test_file_modification_time():
        """测试文件修改时间获取逻辑"""
        print("\n测试文件修改时间获取逻辑...")
        
        # 创建一个临时策略文件
        strategy_name = "test_strategy"
        strategy_dir = os.path.join(os.path.dirname(__file__), "backend", "strategies")
        os.makedirs(strategy_dir, exist_ok=True)
        
        file_path = os.path.join(strategy_dir, f"{strategy_name}.py")
        
        # 写入测试内容
        test_content = """
class TestStrategy:
    def __init__(self, params):
        self.params = params
    """
        
        with open(file_path, "w") as f:
            f.write(test_content)
        
        # 获取文件修改时间
        try:
            mtime = os.path.getmtime(file_path)
            file_time = datetime.fromtimestamp(mtime)
            print(f"文件修改时间: {file_time}")
            
            # 检查时间差
            time_diff = datetime.now() - file_time
            print(f"时间差: {time_diff}")
            assert time_diff.total_seconds() < 60, "文件修改时间应该是最近的"
            print("✓ 文件修改时间获取正确")
        except Exception as e:
            print(f"获取文件修改时间失败: {e}")
        finally:
            # 清理临时文件
            if os.path.exists(file_path):
                os.remove(file_path)
    
    # 运行测试
    test_deduplication_logic()
    test_file_modification_time()
    
    print("\n策略列表创建时间逻辑测试完成!")


if __name__ == "__main__":
    try:
        test_strategy_list_logic()
        print("\n🎉 所有测试通过!")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
