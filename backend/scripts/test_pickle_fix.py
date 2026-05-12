#!/usr/bin/env python3
"""
验证 GetData 对象的 Pickle 序列化能力
"""

import sys
import pickle
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from collector.services.data_service import GetData

def test_pickle_serialization():
    """测试 GetData 对象能否被 pickle 序列化"""
    
    print("\n" + "="*60)
    print("🧪 测试 GetData Pickle 序列化")
    print("="*60 + "\n")
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix='pickle_test_')
    print(f"📁 临时目录: {temp_dir}")
    
    try:
        # 步骤1: 实例化 GetData（模拟真实参数）
        print("📦 步骤1: 实例化 GetData 对象...")
        get_data = GetData(
            symbols="BTCUSDT,ETHUSDT",
            exchange="binance",
            candle_type="spot",
            save_dir=temp_dir,
            start="2024-01-01",
            end="2024-01-10",
            interval="1h",
            max_workers=2,
            mode="inc"
        )
        print("   ✅ 实例化成功")
        
        # 步骤2: 验证属性
        print("\n🔍 步骤2: 验证对象属性...")
        assert get_data.symbols == "BTCUSDT,ETHUSDT"
        assert get_data.exchange == "binance"
        assert get_data.candle_type == "spot"
        assert get_data.interval == "1h"
        assert get_data.max_workers == 2
        assert get_data.mode == "inc"
        print("   ✅ 所有属性正确")
        
        # 步骤3: 测试序列化（关键测试！）
        print("\n⚡ 步骤3: 测试 Pickle 序列化...")
        try:
            pickled_data = pickle.dumps(get_data)
            print(f"   ✅ 序列化成功！大小: {len(pickled_data)} bytes")
            
            # 步骤4: 测试反序列化
            print("\n🔄 步骤4: 测试反序列化...")
            unpickled_data = pickle.loads(pickled_data)
            print("   ✅ 反序列化成功！")
            
            # 验证反序列化后的对象属性
            print("\n✅ 步骤5: 验证反序列化后对象完整性...")
            assert unpickled_data.symbols == get_data.symbols
            assert unpickled_data.exchange == get_data.exchange
            assert unpickled_data.interval == get_data.interval
            assert unpickled_data.candle_type == get_data.candle_type
            assert unpickled_data.max_workers == get_data.max_workers
            print("   ✅ 反序列化对象与原对象完全一致")
            
            print("\n" + "="*60)
            print("🎉 Pickle 序列化测试全部通过！")
            print("="*60)
            print("\n✅ 修复确认：GetData 对象现在可以被安全地传递给多进程 workers")
            return True
            
        except Exception as e:
            print(f"\n   ❌ 序列化失败: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"\n🧹 清理临时目录")

if __name__ == "__main__":
    success = test_pickle_serialization()
    sys.exit(0 if success else 1)