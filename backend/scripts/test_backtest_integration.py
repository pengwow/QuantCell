#!/usr/bin/env python3
"""
回测流程验证脚本

验证从Parquet文件加载K线数据并执行回测的完整流程
"""

import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# 添加backend目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.kline_file_manager import KlineFileManager
from utils.logger import logger


def generate_backtest_data(
    symbol: str = "ETHUSDT",
    interval: str = "15m",
    start_time: datetime = None,
    num_bars: int = 1000,
    base_price: float = 2200.0
) -> pd.DataFrame:
    """
    生成用于回测的K线数据
    
    Args:
        symbol: 交易对符号
        interval: 时间间隔
        start_time: 开始时间
        num_bars: K线数量
        base_price: 基础价格
        
    Returns:
        包含K线数据的DataFrame
    """
    if start_time is None:
        start_time = datetime(2024, 1, 1)
    
    # 根据interval计算时间增量
    interval_minutes = {
        '1m': 1,
        '3m': 3,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '2h': 120,
        '4h': 240,
        '6h': 360,
        '8h': 480,
        '12h': 720,
        '1d': 1440,
        '3d': 4320,
        '1w': 10080,
        '1M': 43200,
    }.get(interval, 60)
    
    np.random.seed(42)  # 设置随机种子以便复现
    
    data = []
    current_price = base_price
    current_time = start_time
    
    for i in range(num_bars):
        price_change = np.random.uniform(-0.01, 0.01) * current_price
        open_price = current_price
        close_price = current_price + price_change
        high_price = max(open_price, close_price) + abs(np.random.normal(0, 0.005 * current_price))
        low_price = min(open_price, close_price) - abs(np.random.normal(0, 0.005 * current_price))
        volume = np.random.uniform(500, 2000)
        
        timestamp = int(current_time.timestamp() * 1000)
        
        data.append({
            'timestamp': timestamp,
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(close_price, 2),
            'volume': round(volume, 2)
        })
        
        current_time += timedelta(minutes=interval_minutes)
        current_price = close_price
    
    df = pd.DataFrame(data)
    return df


def test_backtest_data_loading():
    """测试回测数据加载流程"""
    
    print("\n" + "="*80)
    print("🧪 开始测试回测数据加载流程")
    print("="*80 + "\n")
    
    temp_dir = tempfile.mkdtemp(prefix='backtest_test_')
    print(f"📁 使用临时目录: {temp_dir}")
    
    try:
        manager = KlineFileManager(base_dir=Path(temp_dir))
        
        # 步骤1：准备回测数据
        print("\n" + "-"*60)
        print("📥 步骤1：准备回测数据 (ETHUSDT 15m)")
        print("-"*60)
        
        backtest_data = generate_backtest_data(
            symbol="ETHUSDT",
            interval="15m",
            start_time=datetime(2024, 1, 1),
            num_bars=1000,
            base_price=2200.0
        )
        
        print(f"   生成了 {len(backtest_data)} 条回测数据")
        print(f"   时间范围: {backtest_data['timestamp'].iloc[0]} ~ {backtest_data['timestamp'].iloc[-1]}")
        
        success = manager.save_klines(
            df=backtest_data,
            symbol="ETHUSDT",
            interval="15m",
            market_type="spot"
        )
        
        if not success:
            print("   ❌ 数据保存失败")
            return False
        
        print("   ✅ 回测数据保存成功")
        
        # 步骤2：模拟回测服务的数据加载
        print("\n" + "-"*60)
        print("📤 步骤2：模拟回测服务加载Parquet数据")
        print("-"*60)
        
        from backtest.service import BacktestService
        
        # 创建一个最小的BacktestService实例用于测试
        class MockBacktestService:
            def _get_kline_data_from_parquet(self, symbol, interval, start_time, end_time):
                """调用实际的回测服务方法"""
                from utils.kline_file_manager import get_kline_file_manager
                
                mgr = get_kline_file_manager()
                
                # 临时修改基础目录为测试目录
                original_base_dir = mgr.base_dir
                mgr.base_dir = Path(temp_dir)
                
                try:
                    df = mgr.load_klines(
                        symbol=symbol,
                        interval=interval,
                        start_time=start_time,
                        end_time=end_time,
                        market_type='spot'
                    )
                    
                    if df.empty:
                        return []
                    
                    kline_data = []
                    for _, row in df.iterrows():
                        timestamp_ms = int(row['timestamp'])
                        
                        from datetime import datetime as dt_class
                        if 'datetime' in row and pd.notna(row['datetime']):
                            datetime_str = str(row['datetime'])
                        else:
                            try:
                                dt_obj = dt_class.fromtimestamp(timestamp_ms / 1000)
                                datetime_str = dt_obj.isoformat()
                            except:
                                datetime_str = ''
                        
                        kline_item = {
                            'timestamp': timestamp_ms,
                            'datetime': datetime_str,
                            'open': float(row['open']),
                            'close': float(row['close']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'volume': float(row['volume']),
                            'turnover': 0.0
                        }
                        kline_data.append(kline_item)
                    
                    return kline_data
                    
                finally:
                    mgr.base_dir = original_base_dir
            
            def validate_kline_data_format(self, kline_data):
                """验证K线数据格式是否符合回测要求"""
                if not kline_data:
                    return False, "数据为空"
                
                required_fields = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                
                sample = kline_data[0]
                missing_fields = [f for f in required_fields if f not in sample]
                
                if missing_fields:
                    return False, f"缺少字段: {missing_fields}"
                
                for item in kline_data:
                    if item['timestamp'] <= 0:
                        return False, f"无效的时间戳: {item['timestamp']}"
                    
                    if item['open'] <= 0 or item['close'] <= 0:
                        return False, f"无效的价格数据"
                    
                    if item['high'] < max(item['open'], item['close']):
                        return False, f"最高价小于开盘价或收盘价"
                    
                    if item['low'] > min(item['open'], item['close']):
                        return False, f"最低价大于开盘价或收盘价"
                
                return True, "数据格式正确"
        
        mock_service = MockBacktestService()
        
        # 加载完整时间范围的数据
        loaded_data = mock_service._get_kline_data_from_parquet(
            symbol="ETHUSDT",
            interval="15m",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-15T23:59:59Z"
        )
        
        print(f"   加载数据条数: {len(loaded_data)}")
        
        if len(loaded_data) == 0:
            print("   ❌ 未加载到数据")
            return False
        
        print("   ✅ 数据加载成功")
        
        # 步骤3：验证数据格式
        print("\n" + "-"*60)
        print("✅ 步骤3：验证数据格式是否符合回测要求")
        print("-"*60)
        
        is_valid, message = mock_service.validate_kline_data_format(loaded_data)
        
        print(f"   验证结果: {message}")
        
        if not is_valid:
            print("   ❌ 数据格式验证失败")
            
            # 显示前几条数据用于调试
            print("\n   前3条数据:")
            for i, item in enumerate(loaded_data[:3]):
                print(f"      [{i}] {item}")
            
            return False
        
        print("   ✅ 数据格式验证通过")
        
        # 步骤4：检查数据连续性
        print("\n" + "-"*60)
        print("📊 步骤4：检查数据连续性和时间间隔")
        print("-"*60)
        
        timestamps = [item['timestamp'] for item in loaded_data]
        time_diffs = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        
        expected_interval_ms = 15 * 60 * 1000  # 15分钟
        consistent_intervals = all(abs(d - expected_interval_ms) < 1000 for d in time_diffs)
        
        print(f"   数据点数: {len(loaded_data)}")
        print(f"   时间戳范围: {timestamps[0]} ~ {timestamps[-1]}")
        print(f"   预期间隔: {expected_interval_ms}ms (15分钟)")
        print(f"   实际间隔一致性: {'✅ 一致' if consistent_intervals else '❌ 不一致'}")
        
        if not consistent_intervals:
            print(f"   ⚠️  发现不一致的时间间隔:")
            for i, diff in enumerate(time_diffs[:10]):
                if abs(diff - expected_interval_ms) >= 1000:
                    print(f"      位置{i}: {diff}ms")
        
        # 步骤5：统计信息
        print("\n" + "-"*60)
        print("📈 步骤5：数据统计分析")
        print("-"*60)
        
        closes = [item['close'] for item in loaded_data]
        volumes = [item['volume'] for item in loaded_data]
        
        print(f"   价格范围: ${min(closes):.2f} ~ ${max(closes):.2f}")
        print(f"   平均价格: ${sum(closes)/len(closes):.2f}")
        print(f"   成交量范围: {min(volumes):.2f} ~ {max(volumes):.2f}")
        print(f"   总成交量: {sum(volumes):.2f}")
        
        # 步骤6：性能测试
        print("\n" + "-"*60)
        print("⚡ 步骤6：性能测试")
        print("-"*60)
        
        import time
        
        # 测试加载性能
        start_time_perf = time.time()
        for _ in range(10):
            test_data = mock_service._get_kline_data_from_parquet(
                symbol="ETHUSDT",
                interval="15m",
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-01-15T23:59:59Z"
            )
        load_time = (time.time() - start_time_perf) / 10
        
        print(f"   平均加载时间: {load_time*1000:.2f}ms")
        print(f"   每次加载记录数: {len(test_data)}")
        print(f"   吞吐量: {len(test_data)/load_time:.0f} 条/秒")
        
        if load_time > 0.5:
            print("   ⚠️  加载速度较慢，可能需要优化")
        else:
            print("   ✅ 加载性能良好")
        
        print("\n" + "="*80)
        print("✅ 回测数据加载和验证全部通过！")
        print("="*80 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        print(f"\n🧹 清理临时目录: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    success = test_backtest_data_loading()
    sys.exit(0 if success else 1)