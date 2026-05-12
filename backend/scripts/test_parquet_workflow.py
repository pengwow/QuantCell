#!/usr/bin/env python3
"""
模拟数据下载并保存到Parquet的测试脚本

用于验证完整的K线数据下载、存储和读取流程
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


def generate_sample_kline_data(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    start_time: datetime = None,
    num_bars: int = 100,
    base_price: float = 42000.0
) -> pd.DataFrame:
    """
    生成模拟的K线数据
    
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
        # 默认从2024年1月1日开始
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
    
    data = []
    current_price = base_price
    current_time = start_time
    
    for i in range(num_bars):
        # 生成随机价格变动（模拟真实市场波动）
        price_change = np.random.uniform(-0.02, 0.02) * current_price
        open_price = current_price
        close_price = current_price + price_change
        high_price = max(open_price, close_price) + abs(np.random.normal(0, 0.01 * current_price))
        low_price = min(open_price, close_price) - abs(np.random.normal(0, 0.01 * current_price))
        volume = np.random.uniform(100, 1000)
        
        timestamp = int(current_time.timestamp() * 1000)
        
        data.append({
            'timestamp': timestamp,
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(close_price, 2),
            'volume': round(volume, 2)
        })
        
        # 更新时间和价格
        current_time += timedelta(minutes=interval_minutes)
        current_price = close_price
    
    df = pd.DataFrame(data)
    return df


def test_complete_workflow():
    """测试完整的数据下载和存储工作流"""
    
    print("\n" + "="*80)
    print("🚀 开始测试完整的K线数据下载和存储流程")
    print("="*80 + "\n")
    
    # 创建临时目录用于测试
    temp_dir = tempfile.mkdtemp(prefix='kline_test_')
    print(f"📁 使用临时目录: {temp_dir}")
    
    try:
        # 初始化文件管理器
        manager = KlineFileManager(base_dir=Path(temp_dir))
        
        # 测试场景1：下载BTCUSDT 1小时K线数据
        print("\n" + "-"*60)
        print("📥 场景1：下载 BTCUSDT 1小时K线数据 (2024年1月)")
        print("-"*60)
        
        btc_data = generate_sample_kline_data(
            symbol="BTCUSDT",
            interval="1h",
            start_time=datetime(2024, 1, 1),
            num_bars=200,
            base_price=42000.0
        )
        
        print(f"   生成了 {len(btc_data)} 条BTCUSDT 1h K线数据")
        print(f"   时间范围: {btc_data['timestamp'].iloc[0]} ~ {btc_data['timestamp'].iloc[-1]}")
        
        # 保存数据
        success = manager.save_klines(
            df=btc_data,
            symbol="BTCUSDT",
            interval="1h",
            market_type="spot"
        )
        
        if success:
            print("   ✅ 数据保存成功")
            
            # 查询可用信息
            symbols = manager.get_available_symbols(market_type="spot")
            intervals = manager.get_available_intervals(symbol="BTCUSDT", market_type="spot")
            date_range = manager.get_date_range(symbol="BTCUSDT", interval="1h", market_type="spot")
            
            print(f"   📊 可用交易对: {symbols}")
            print(f"   ⏱️  可用周期: {intervals}")
            print(f"   📅 数据范围: {date_range}")
        else:
            print("   ❌ 数据保存失败")
            return False
        
        # 测试场景2：下载ETHUSDT 15分钟K线数据
        print("\n" + "-"*60)
        print("📥 场景2：下载 ETHUSDT 15分钟K线数据 (2024年1-2月)")
        print("-"*60)
        
        eth_data = generate_sample_kline_data(
            symbol="ETHUSDT",
            interval="15m",
            start_time=datetime(2024, 1, 15),
            num_bars=500,
            base_price=2200.0
        )
        
        print(f"   生成了 {len(eth_data)} 条ETHUSDT 15m K线数据")
        
        success = manager.save_klines(
            df=eth_data,
            symbol="ETHUSDT",
            interval="15m",
            market_type="spot"
        )
        
        if success:
            print("   ✅ ETHUSDT数据保存成功")
        else:
            print("   ❌ ETHUSDT数据保存失败")
            return False
        
        # 测试场景3：追加更多BTCUSDT数据（跨月）
        print("\n" + "-"*60)
        print("📥 场景3：追加 BTCUSDT 2月份数据")
        print("-"*60)
        
        btc_feb_data = generate_sample_kline_data(
            symbol="BTCUSDT",
            interval="1h",
            start_time=datetime(2024, 2, 1),
            num_bars=150,
            base_price=43000.0
        )
        
        print(f"   生成了 {len(btc_feb_data)} 条BTCUSDT 2月数据")
        
        success = manager.append_klines(
            df=btc_feb_data,
            symbol="BTCUSDT",
            interval="1h",
            market_type="spot"
        )
        
        if success:
            print("   ✅ 追加数据成功")
        else:
            print("   ❌ 追加数据失败")
            return False
        
        # 测试场景4：加载并验证数据
        print("\n" + "-"*60)
        print("📤 场景4：加载数据并验证完整性")
        print("-"*60)
        
        # 加载BTCUSDT 1月数据
        loaded_jan = manager.load_klines(
            symbol="BTCUSDT",
            interval="1h",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-31T23:59:59Z",
            market_type="spot"
        )
        
        print(f"   加载BTCUSDT 1月数据: {len(loaded_jan)} 条")
        
        if len(loaded_jan) > 0:
            print(f"   ✅ 数据加载成功")
            print(f"   列名: {list(loaded_jan.columns)}")
            print(f"   前3行数据:")
            print(loaded_jan.head(3).to_string(index=False))
        else:
            print("   ❌ 未找到数据")
            return False
        
        # 加载全部BTCUSDT数据
        loaded_all = manager.load_klines(
            symbol="BTCUSDT",
            interval="1h",
            market_type="spot"
        )
        
        expected_total = len(btc_data) + len(btc_feb_data)
        print(f"\n   加载全部BTCUSDT数据: {len(loaded_all)} 条 (预期: ~{expected_total})")
        
        if len(loaded_all) >= expected_total - 5:  # 允许少量误差
            print("   ✅ 完整性验证通过")
        else:
            print("   ❌ 数据不完整")
            return False
        
        # 测试场景5：查询存储统计
        print("\n" + "-"*60)
        print("📊 场景5：查询存储统计信息")
        print("-"*60)
        
        stats = manager.get_storage_stats()
        
        print(f"   总文件数: {stats.get('total_files', 0)}")
        print(f"   总大小: {stats.get('total_size_mb', 0):.2f} MB")
        
        symbols_info = stats.get('symbols', {})
        if isinstance(symbols_info, dict):
            print(f"   市场类型数: {len(symbols_info)}")
            
            for market_type, symbols in symbols_info.items():
                if not isinstance(symbols, dict):
                    continue
                    
                print(f"\n   [{market_type.upper()}]")
                for symbol, info in symbols.items():
                    if isinstance(info, dict) and 'intervals' in info:
                        intervals = list(info.get('intervals', {}).keys())
                        print(f"      {symbol}: {intervals}")
                    else:
                        print(f"      {symbol}: {info}")
        else:
            print(f"   符号信息: {symbols_info}")
        
        print("   ✅ 统计信息获取成功")
        
        # 测试场景6：合约数据存储
        print("\n" + "-"*60)
        print("📥 场景6：测试合约市场数据存储")
        print("-"*60)
        
        future_data = generate_sample_kline_data(
            symbol="BTCUSDT",
            interval="4h",
            start_time=datetime(2024, 1, 1),
            num_bars=50,
            base_price=42500.0
        )
        
        success = manager.save_klines(
            df=future_data,
            symbol="BTCUSDT",
            interval="4h",
            market_type="future"
        )
        
        if success:
            print("   ✅ 合约数据保存成功")
            
            # 验证目录结构
            spot_dir = Path(temp_dir) / 'spot' / 'BTCUSDT' / '1h'
            future_dir = Path(temp_dir) / 'future' / 'BTCUSDT' / '4h'
            
            spot_files = list(spot_dir.glob('*.parquet')) if spot_dir.exists() else []
            future_files = list(future_dir.glob('*.parquet')) if future_dir.exists() else []
            
            print(f"   现货文件数: {len(spot_files)}")
            print(f"   合约文件数: {len(future_files)}")
        else:
            print("   ❌ 合约数据保存失败")
            return False
        
        print("\n" + "="*80)
        print("✅ 所有测试场景通过！Parquet存储系统工作正常")
        print("="*80 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # 清理临时目录
        print(f"🧹 清理临时目录: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    success = test_complete_workflow()
    sys.exit(0 if success else 1)