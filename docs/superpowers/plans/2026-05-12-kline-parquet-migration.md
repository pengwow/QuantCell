# K线数据Parquet文件系统迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将QuantCell后端的所有K线数据存储从SQLite数据库迁移到Parquet文件系统，提升性能并简化架构。

**Architecture:** 实现KlineFileManager统一管理器，替换所有数据库读写操作。数据按品种+周期+月份组织为Parquet文件，使用Snappy压缩。删除数据库中的K线表及相关代码。

**Tech Stack:** Python 3.12, Pandas, PyArrow, FastAPI, SQLAlchemy（仅保留非K线表）

---

## 文件结构总览

### 新建文件
```
backend/utils/
├── kline_file_manager.py      # 核心文件管理器
└── parquet_utils.py           # 已存在，无需修改

backend/scripts/
└── migrate_kline_to_parquet.py # 数据迁移脚本
```

### 修改文件
```
backend/collector/services/
└── data_service.py            # 移除数据库写入，改用文件管理器

backend/exchange/binance/
└── downloader.py              # 返回DataFrame而非ORM对象

backend/backtest/
├── service.py                 # 替换_get_kline_data_from_db
├── adapters/data_adapter.py   # 使用新的文件管理器
└── cli.py                    # 更新CLI命令

backend/collector/db/
├── models.py                  # 删除K线模型类
└── crud.py                   # 删除K线CRUD函数

backend/collector/services/
└── kline_factory.py           # 删除或简化
```

---

## Task 1: 创建核心KlineFileManager模块

**Files:**
- Create: `backend/utils/kline_file_manager.py`
- Test: `tests/test_kline_file_manager.py` (新建)

**目标:** 实现统一的K线数据文件管理器，提供保存、加载、追加、查询等核心功能。

- [ ] **Step 1: 编写单元测试 - 基础功能**

```python
# tests/test_kline_file_manager.py
import pytest
import pandas as pd
from pathlib import Path
import tempfile
import shutil
from datetime import datetime
from utils.kline_file_manager import KlineFileManager


@pytest.fixture
def temp_dir():
    """创建临时测试目录"""
    dir_path = Path(tempfile.mkdtemp())
    yield dir_path
    shutil.rmtree(dir_path, ignore_errors=True)


@pytest.fixture
def sample_df():
    """创建示例K线数据"""
    return pd.DataFrame({
        'timestamp': [1704067200000, 1704153600000],
        'datetime': pd.to_datetime(['2024-01-01', '2024-01-02']),
        'open': [42000.0, 42500.0],
        'high': [43000.0, 43200.0],
        'low': [41500.0, 42000.0],
        'close': [42500.0, 42800.0],
        'volume': [1000.5, 1200.3]
    })


class TestKlineFileManagerInit:
    def test_init_with_default_base_dir(self):
        manager = KlineFileManager()
        assert manager.base_dir.name == 'klines'
    
    def test_init_with_custom_base_dir(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)
        assert manager.base_dir == temp_dir


class TestSaveKlines:
    def test_save_spot_klines(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)
        
        result = manager.save_klines(
            df=sample_df,
            symbol='BTCUSDT',
            interval='1h',
            market_type='spot'
        )
        
        assert result is True
        expected_path = temp_dir / 'spot' / 'BTCUSDT' / '1h' / '2024-01.parquet'
        assert expected_path.exists()
    
    def test_save_future_klines(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)
        
        result = manager.save_klines(
            df=sample_df,
            symbol='ETHUSDT',
            interval='15m',
            market_type='future'
        )
        
        assert result is True
        expected_path = temp_dir / 'future' / 'ETHUSDT' / '15m' / '2024-01.parquet'
        assert expected_path.exists()


class TestLoadKlines:
    def test_load_existing_data(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)
        
        # 先保存数据
        manager.save_klines(sample_df, 'BTCUSDT', '1h')
        
        # 加载数据
        loaded_df = manager.load_klines(
            symbol='BTCUSDT',
            interval='1h',
            market_type='spot'
        )
        
        assert len(loaded_df) == 2
        assert list(loaded_df.columns) == ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume']
    
    def test_load_nonexistent_symbol(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)
        
        loaded_df = manager.load_klines(
            symbol='NONEXISTENT',
            interval='1h'
        )
        
        assert loaded_df.empty


class TestAppendKlines:
    def test_append_to_existing_file(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)
        
        # 第一次保存
        df1 = pd.DataFrame({
            'timestamp': [1704067200000],
            'open': [42000.0], 'high': [43000.0], 'low': [41500.0],
            'close': [42500.0], 'volume': [1000.5]
        })
        manager.save_klines(df1, 'BTCUSDT', '1h')
        
        # 追加数据
        df2 = pd.DataFrame({
            'timestamp': [1704240000000],
            'open': [43000.0], 'high': [43500.0], 'low': [42500.0],
            'close': [43200.0], 'volume': [1500.7]
        })
        result = manager.append_klines(df2, 'BTCUSDT', '1h')
        
        assert result is True
        
        # 验证合并后的数据
        loaded = manager.load_klines('BTCUSDT', '1h')
        assert len(loaded) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && python -m pytest tests/test_kline_file_manager.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'utils.kline_file_manager'`

- [ ] **Step 3: 实现KlineFileManager基础结构**

```python
# backend/utils/kline_file_manager.py
# -*- coding: utf-8 -*-
"""
K线数据文件管理器

提供统一的K线数据文件管理功能：
- 按品种、周期、市场类型组织Parquet文件
- 支持保存、加载、追加、查询操作
- 自动处理文件路径和数据格式转换
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import pandas as pd
import fcntl  # 文件锁
from utils.logger import get_logger, LogType
from utils.parquet_utils import save_to_parquet, load_from_parquet, append_to_parquet

logger = get_logger(__name__, LogType.APPLICATION)


class KlineFileManager:
    """
    K线数据文件管理器
    
    管理K线数据的Parquet文件存储，支持现货和合约两种市场类型。
    数据按照以下目录结构组织：
    
    base_dir/
    ├── spot/
    │   └── {symbol}/
    │       └── {interval}/
    │           └── {YYYY-MM}.parquet
    └── future/
        └── {symbol}/
            └── {interval}/
                └── {YYYY-MM}.parquet
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        初始化文件管理器
        
        Args:
            base_dir: 基础目录路径，默认为 backend/data/klines
        """
        if base_dir is None:
            self.base_dir = Path(__file__).parent.parent / 'data' / 'klines'
        else:
            self.base_dir = Path(base_dir)
        
        logger.info(f"[KlineFileManager] 初始化完成，基础目录: {self.base_dir}")
    
    def _get_file_path(
        self,
        symbol: str,
        interval: str,
        date_str: str,
        market_type: str = 'spot'
    ) -> Path:
        """
        获取Parquet文件的完整路径
        
        Args:
            symbol: 交易对符号 (如 "BTCUSDT")
            interval: 时间周期 (如 "1h", "15m")
            date_str: 日期字符串 (如 "2024-01")
            market_type: 市场类型 ("spot" 或 "future")
            
        Returns:
            Path: 文件完整路径
        """
        return (
            self.base_dir 
            / market_type 
            / symbol 
            / interval 
            / f"{date_str}.parquet"
        )
    
    def _extract_date_from_timestamp(self, timestamp_ms: int) -> str:
        """
        从时间戳提取年月字符串
        
        Args:
            timestamp_ms: 毫秒时间戳
            
        Returns:
            str: 格式化的日期字符串 (YYYY-MM)
        """
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        return dt.strftime('%Y-%m')
    
    def _ensure_dataframe_format(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        确保DataFrame格式符合规范
        
        Args:
            df: 输入的DataFrame
            
        Returns:
            pd.DataFrame: 格式化后的DataFrame
        """
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"DataFrame缺少必需列: {required_cols}")
        
        # 确保数值列类型正确
        for col in required_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 处理时间戳
        if 'timestamp' not in df.columns and 'datetime' in df.columns:
            df['timestamp'] = pd.to_datetime(df['datetime']).astype('int64') // 10**6
        
        return df
    
    def save_klines(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
        market_type: str = 'spot'
    ) -> bool:
        """
        保存K线数据到Parquet文件
        
        自动根据数据的时间范围分割成月度文件。
        
        Args:
            df: K线数据DataFrame
            symbol: 交易对符号
            interval: 时间周期
            market_type: 市场类型
            
        Returns:
            bool: 是否保存成功
        """
        try:
            if df is None or df.empty:
                logger.warning("[KlineFileManager] 数据为空，跳过保存")
                return False
            
            # 格式化数据
            df = self._ensure_dataframe_format(df.copy())
            
            # 按月份分组保存
            if 'timestamp' in df.columns:
                df['_month'] = df['timestamp'].apply(self._extract_date_from_timestamp)
                
                success_count = 0
                for month, group in df.groupby('_month'):
                    file_path = self._get_file_path(symbol, interval, month, market_type)
                    
                    # 使用文件锁确保并发安全
                    with open(file_path.parent / '.lock', 'w') as lock_file:
                        try:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                            
                            group_to_save = group.drop(columns=['_month'])
                            if save_to_parquet(group_to_save, file_path):
                                success_count += 1
                        finally:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                
                logger.info(
                    f"[KlineFileManager] 保存成功: {symbol} {interval}, "
                    f"共{len(df)}条数据, 分{success_count}个文件"
                )
                return success_count > 0
            
            else:
                # 无时间戳，保存到默认文件
                file_path = self._get_file_path(symbol, interval, 'unknown', market_type)
                return save_to_parquet(df, file_path)
            
        except Exception as e:
            logger.error(f"[KlineFileManager] 保存失败: {e}")
            return False
    
    def load_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        market_type: str = 'spot'
    ) -> pd.DataFrame:
        """
        加载K线数据
        
        支持按时间范围过滤，自动加载相关月份的文件。
        
        Args:
            symbol: 交易对符号
            interval: 时间周期
            start_time: 开始时间 (ISO格式或毫秒时间戳)
            end_time: 结束时间
            market_type: 市场类型
            
        Returns:
            pd.DataFrame: K线数据
        """
        try:
            data_dir = self.base_dir / market_type / symbol / interval
            
            if not data_dir.exists():
                logger.warning(f"[KlineFileManager] 目录不存在: {data_dir}")
                return pd.DataFrame()
            
            # 获取所有Parquet文件并排序
            parquet_files = sorted(data_dir.glob('*.parquet'))
            
            if not parquet_files:
                logger.warning(f"[KlineFileManager] 未找到数据文件: {data_dir}")
                return pd.DataFrame()
            
            # 如果有时间范围限制，筛选相关文件
            if start_time or end_time:
                filtered_files = []
                for pf in parquet_files:
                    file_month = pf.stem  # YYYY-MM
                    
                    if start_time and file_month < start_time[:7]:
                        continue
                    if end_time and file_month > end_time[:7]:
                        continue
                    
                    filtered_files.append(pf)
                
                parquet_files = filtered_files
            
            # 加载数据
            dfs = []
            for pf in parquet_files:
                df = load_from_parquet(pf)
                if not df.empty:
                    dfs.append(df)
            
            if not dfs:
                return pd.DataFrame()
            
            # 合并所有数据
            combined_df = pd.concat(dfs, ignore_index=True)
            
            # 按时间排序
            if 'timestamp' in combined_df.columns:
                combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
                
                # 应用时间范围过滤
                if start_time:
                    if isinstance(start_time, str) and 'T' in start_time:
                        start_ts = int(datetime.fromisoformat(start_time).timestamp() * 1000)
                    else:
                        start_ts = int(start_time)
                    combined_df = combined_df[combined_df['timestamp'] >= start_ts]
                
                if end_time:
                    if isinstance(end_time, str) and 'T' in end_time:
                        end_ts = int(datetime.fromisoformat(end_time).timestamp() * 1000)
                    else:
                        end_ts = int(end_time)
                    combined_df = combined_df[combined_df['timestamp'] <= end_ts]
            
            logger.info(
                f"[KlineFileManager] 加载成功: {symbol} {interval}, "
                f"共{len(combined_df)}条数据"
            )
            
            return combined_df
            
        except Exception as e:
            logger.error(f"[KlineFileManager] 加载失败: {e}")
            return pd.DataFrame()
    
    def append_klines(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
        market_type: str = 'spot'
    ) -> bool:
        """
        追加K线数据到现有文件
        
        Args:
            df: 要追加的数据
            symbol: 交易对符号
            interval: 时间周期
            market_type: 市场类型
            
        Returns:
            bool: 是否成功
        """
        try:
            if df is None or df.empty:
                logger.warning("[KlineFileManager] 追加数据为空")
                return False
            
            df = self._ensure_dataframe_format(df.copy())
            
            # 按月份分别追加
            if 'timestamp' in df.columns:
                df['_month'] = df['timestamp'].apply(self._extract_date_from_timestamp)
                
                for month, group in df.groupby('_month'):
                    file_path = self._get_file_path(symbol, interval, month, market_type)
                    group_to_save = group.drop(columns=['_month'])
                    
                    if append_to_parquet(group_to_save, file_path):
                        logger.info(f"[KlineFileManager] 追加成功: {file_path} ({len(group)}条)")
            
            return True
            
        except Exception as e:
            logger.error(f"[KlineFileManager] 追加失败: {e}")
            return False
    
    def get_available_symbols(self, market_type: str = 'spot') -> List[str]:
        """
        获取可用的交易对列表
        
        Args:
            market_type: 市场类型
            
        Returns:
            List[str]: 交易对符号列表
        """
        market_dir = self.base_dir / market_type
        
        if not market_dir.exists():
            return []
        
        symbols = []
        for symbol_dir in market_dir.iterdir():
            if symbol_dir.is_dir() and any(symbol_dir.glob('*/*.parquet')):
                symbols.append(symbol_dir.name)
        
        return sorted(symbols)
    
    def get_available_intervals(self, symbol: str, market_type: str = 'spot') -> List[str]:
        """
        获取指定交易对的可用周期列表
        
        Args:
            symbol: 交易对符号
            market_type: 市场类型
            
        Returns:
            List[str]: 周期列表
        """
        symbol_dir = self.base_dir / market_type / symbol
        
        if not symbol_dir.exists():
            return []
        
        intervals = []
        for interval_dir in symbol_dir.iterdir():
            if interval_dir.is_dir() and list(interval_dir.glob('*.parquet')):
                intervals.append(interval_dir.name)
        
        return sorted(intervals)
    
    def get_date_range(
        self,
        symbol: str,
        interval: str,
        market_type: str = 'spot'
    ) -> tuple:
        """
        获取数据的日期范围
        
        Args:
            symbol: 交易对符号
            interval: 周期
            market_type: 市场类型
            
        Returns:
            tuple: (最早日期, 最晚日期) 或 None
        """
        data_dir = self.base_dir / market_type / symbol / interval
        
        if not data_dir.exists():
            return None
        
        files = sorted(data_dir.glob('*.parquet'))
        
        if not files:
            return None
        
        earliest = files[0].stem  # YYYY-MM
        latest = files[-1].stem
        
        return (earliest, latest)
    
    def delete_klines(
        self,
        symbol: str,
        interval: str,
        market_type: str = 'spot'
    ) -> bool:
        """
        删除指定交易对的K线数据
        
        Args:
            symbol: 交易对符号
            interval: 周期
            market_type: 市场类型
            
        Returns:
            bool: 是否成功
        """
        try:
            target_dir = self.base_dir / market_type / symbol / interval
            
            if not target_dir.exists():
                logger.warning(f"[KlineFileManager] 目录不存在: {target_dir}")
                return False
            
            import shutil
            shutil.rmtree(target_dir)
            
            logger.info(f"[KlineFileManager] 已删除: {target_dir}")
            return True
            
        except Exception as e:
            logger.error(f"[KlineFileManager] 删除失败: {e}")
            return False
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息
        
        Returns:
            dict: 统计信息
        """
        stats = {
            'total_files': 0,
            'total_size_mb': 0.0,
            'symbols': {},
            'base_dir': str(self.base_dir),
            'exists': self.base_dir.exists()
        }
        
        if not self.base_dir.exists():
            return stats
        
        for market_type in ['spot', 'future']:
            market_dir = self.base_dir / market_type
            
            if not market_dir.exists():
                continue
            
            for symbol_dir in market_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                
                symbol_stats = {
                    'intervals': {},
                    'total_size_mb': 0.0,
                    'total_files': 0
                }
                
                for interval_dir in symbol_dir.iterdir():
                    if not interval_dir.is_dir():
                        continue
                    
                    files = list(interval_dir.glob('*.parquet'))
                    interval_stats = {
                        'file_count': len(files),
                        'size_mb': sum(f.stat().st_size for f in files) / (1024 * 1024),
                        'date_range': None
                    }
                    
                    if files:
                        dates = sorted([f.stem for f in files])
                        interval_stats['date_range'] = (dates[0], dates[-1])
                    
                    symbol_stats['intervals'][interval_dir.name] = interval_stats
                    symbol_stats['total_size_mb'] += interval_stats['size_mb']
                    symbol_stats['total_files'] += interval_stats['file_count']
                
                stats['symbols'][symbol_dir.name] = symbol_stats
                stats['total_files'] += symbol_stats['total_files']
                stats['total_size_mb'] += symbol_stats['total_size_mb']
        
        stats['total_size_mb'] = round(stats['total_size_mb'], 2)
        
        return stats


# 全局单例实例
_kline_manager_instance = None

def get_kline_file_manager() -> KlineFileManager:
    """获取全局KlineFileManager实例"""
    global _kline_manager_instance
    if _kline_manager_instance is None:
        _kline_manager_instance = KlineFileManager()
    return _kline_manager_instance
```

- [ ] **Step 4: 运行测试验证实现**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && python -m pytest tests/test_kline_file_manager.py -v`
Expected: PASS - 所有测试通过

- [ ] **Step 5: 提交Task 1代码**

```bash
git add utils/kline_file_manager.py tests/test_kline_file_manager.py
git commit -m "feat: implement KlineFileManager for Parquet-based storage"
```

---

## Task 2: 修改数据下载服务（DataService）

**Files:**
- Modify: `backend/collector/services/data_service.py:150-250`
- Test: 手动验证下载功能

**目标:** 将数据下载逻辑从写入数据库改为写入Parquet文件。

- [ ] **Step 1: 分析当前DataService的数据库写入逻辑**

Run: `grep -n "CryptoSpotKline\|session\|db\.add\|db\.commit" collector/services/data_service.py | head -20`
Expected: 找到约10-15处数据库操作代码

- [ ] **Step 2: 替换数据库写入为文件管理器调用**

在 `data_service.py` 的 `_save_klines_to_db()` 方法中：

```python
# 原始代码（需要替换）:
def _save_klines_to_db(self, db_session, klines_data, symbol, interval):
    from ..db.models import CryptoSpotKline
    
    for kline in klines_data:
        record = CryptoSpotKline(
            symbol=symbol,
            interval=interval,
            timestamp=kline['timestamp'],
            open=str(kline['open']),
            high=str(kline['high']),
            low=str(kline['low']),
            close=str(kline['close']),
            volume=str(kline['volume']),
            unique_kline=f"{symbol}_{interval}_{kline['timestamp']}"
        )
        db_session.add(record)
    
    db_session.commit()

# 替换为:
def _save_klines_to_file(self, klines_data, symbol, interval):
    from utils.kline_file_manager import get_kline_file_manager
    
    import pandas as pd
    
    df = pd.DataFrame(klines_data)
    manager = get_kline_file_manager()
    
    return manager.save_klines(
        df=df,
        symbol=symbol,
        interval=interval,
        market_type='spot'
    )
```

- [ ] **Step 3: 更新调用方代码**

找到所有调用 `_save_klines_to_db()` 的地方，改为调用 `_save_klines_to_file()`：

```python
# 在 download_crypto() 方法中:
# 原始:
result = self._save_klines_to_db(db, formatted_data, symbol, interval)

# 改为:
result = self._save_klines_to_file(formatted_data, symbol, interval)
```

- [ ] **Step 4: 测试数据下载功能**

手动测试：
```bash
cd backend && python scripts/data_cli.py download --symbol BTCUSDT --interval 1h --limit 100
```
Expected: 成功下载并在 `backend/data/klines/spot/BTCUSDT/1h/` 下生成parquet文件

- [ ] **Step 5: 提交Task 2代码**

```bash
git add collector/services/data_service.py
git commit -m "refactor: switch DataService from DB to Parquet storage"
```

---

## Task 3: 修改Binance下载器返回DataFrame

**Files:**
- Modify: `backend/exchange/binance/downloader.py:200-300`
- Test: 单元测试

**目标:** 确保Binance下载器返回标准格式的DataFrame而非ORM对象。

- [ ] **Step 1: 检查当前downloader的返回值格式**

Run: `grep -A 10 "def fetch_klines\|def download" exchange/binance/downloader.py | head -30`
Expected: 了解当前返回的是字典列表还是DataFrame

- [ ] **Step 2: 标准化返回值为DataFrame**

```python
# exchange/binance/downloader.py

def fetch_klines(self, symbol, interval, limit=500, **kwargs):
    """从Binance API获取K线数据"""
    # ... API调用逻辑 ...
    
    # 将API响应转换为DataFrame
    df = pd.DataFrame(klines_data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base_vol',
        'taker_buy_quote_vol', 'ignore'
    ])
    
    # 只保留需要的列
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    
    # 类型转换
    df['timestamp'] = df['timestamp'].astype('int64')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype('float64')
    
    return df
```

- [ ] **Step 3: 验证返回值格式**

```python
# 快速测试
from exchange.binance.downloader import BinanceDownloader

downloader = BinanceDownloader()
df = downloader.fetch_klines('BTCUSDT', '1h', limit=10)

assert isinstance(df, pd.DataFrame)
assert list(df.columns) == ['timestamp', 'open', 'high', 'low', 'close', 'volume']
print("✅ 返回格式正确")
```

- [ ] **Step 4: 提交Task 3代码**

```bash
git add exchange/binance/downloader.py
git commit -m "refactor: standardize Binance downloader to return DataFrame"
```

---

## Task 4: 修改回测服务的K线读取逻辑

**Files:**
- Modify: `backend/backtest/service.py:60-145`
- Test: 回测集成测试

**目标:** 将回测服务中的 `_get_kline_data_from_db()` 方法替换为基于文件的读取。

- [ ] **Step 1: 定位并理解现有方法**

查看 `backtest/service.py` 的第60-145行，理解当前的数据库查询逻辑。

- [ ] **Step 2: 实现新的Parquet读取方法**

```python
# backtest/service.py

def _get_kline_data_from_parquet(
    self,
    symbol: str,
    interval: str,
    start_time: str,
    end_time: str
) -> list:
    """
    从Parquet文件加载K线数据
    
    :param symbol: 货币对 (如 "BTCUSDT")
    :param interval: 时间周期 (如 "15m", "1h")
    :param start_time: 开始时间 (ISO格式)
    :param end_time: 结束时间 (ISO格式)
    :return: K线数据列表
    """
    logger.info(f"[_get_kline_data_from_parquet] 开始加载: {symbol} {interval}")
    
    try:
        from utils.kline_file_manager import get_kline_file_manager
        
        manager = get_kline_file_manager()
        df = manager.load_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            market_type='spot'
        )
        
        if df.empty:
            logger.warning(f"[_get_kline_data_from_parquet] 未找到数据: {symbol} {interval}")
            return []
        
        # 转换为字典列表（保持与原接口兼容）
        kline_data = []
        for _, row in df.iterrows():
            kline_item = {
                'timestamp': int(row['timestamp']),
                'datetime': row['datetime'] if 'datetime' in row else '',
                'open': float(row['open']),
                'close': float(row['close']),
                'high': float(row['high']),
                'low': float(row['low']),
                'volume': float(row['volume']),
                'turnover': 0.0
            }
            kline_data.append(kline_item)
        
        logger.info(
            f"[_get_kline_data_from_parquet] 加载完成: {symbol} {interval}, "
            f"共{len(kline_data)}条"
        )
        return kline_data
        
    except Exception as e:
        logger.error(f"[_get_kline_data_from_parquet] 加载失败: {e}")
        logger.exception(e)
        return []
```

- [ ] **Step 3: 更新调用点**

在 `_run_event_backtest()` 方法中：

```python
# 原始:
kline_data_dict[key] = self._get_kline_data_from_db(symbol, timeframe, start_time, end_time, db)

# 改为:
kline_data_dict[key] = self._get_kline_data_from_parquet(symbol, timeframe, start_time, end_time)
```

- [ ] **Step 4: 测试回测功能**

```bash
cd backend && python scripts/backtest_cli.py run \
    --strategy grid_order_validation \
    --symbol BTCUSDT \
    --interval 1h \
    --start 2024-01-01 \
    --end 2024-01-31
```
Expected: 回测成功执行，使用Parquet文件数据

- [ ] **Step 5: 提交Task 4代码**

```bash
git add backtest/service.py
git commit -m "refactor: switch backtest service to use Parquet files"
```

---

## Task 5: 更新回测数据适配器

**Files:**
- Modify: `backend/backtest/adapters/data_adapter.py:50-150`
- Test: 单元测试

**目标:** 确保数据适配器使用新的文件管理器。

- [ ] **Step 1: 检查当前适配器实现**

Run: `cat backtest/adapters/data_adapter.py | head -80`
Expected: 了解当前如何加载数据

- [ ] **Step 2: 重构适配器使用KlineFileManager**

```python
# backtest/adapters/data_adapter.py

class ParquetDataAdapter:
    """Parquet文件数据适配器"""
    
    def __init__(self):
        from utils.kline_file_manager import get_kline_file_manager
        self.manager = get_kline_file_manager()
    
    def load_data(
        self,
        symbol: str,
        interval: str,
        start_time: str,
        end_time: str
    ) -> pd.DataFrame:
        """加载K线数据"""
        return self.manager.load_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time
        )
    
    def get_available_symbols(self) -> List[str]:
        """获取可用交易对"""
        return self.manager.get_available_symbols()
    
    def check_data_availability(
        self,
        symbol: str,
        interval: str,
        start_time: str,
        end_time: str
    ) -> Dict[str, Any]:
        """检查数据可用性"""
        date_range = self.manager.get_date_range(symbol, interval)
        
        return {
            'available': date_range is not None,
            'date_range': date_range,
            'symbol': symbol,
            'interval': interval
        }
```

- [ ] **Step 3: 更新工厂方法**

```python
# 在 data_adapter.py 中添加:

def create_data_adapter(adapter_type: str = 'parquet'):
    """创建数据适配器工厂方法"""
    if adapter_type == 'parquet':
        return ParquetDataAdapter()
    elif adapter_type == 'database':
        raise NotImplementedError("数据库适配器已移除")
    else:
        raise ValueError(f"不支持的适配器类型: {adapter_type}")
```

- [ ] **Step 4: 提交Task 5代码**

```bash
git add backtest/adapters/data_adapter.py
git commit -m "refactor: update data adapter to use Parquet files"
```

---

## Task 6: 清理数据库模型和CRUD代码

**Files:**
- Modify: `backend/collector/db/models.py:250-314`
- Modify: `backend/collector/db/crud.py`
- Modify: `backend/collector/services/kline_factory.py`

**目标:** 删除所有K线相关的数据库模型和CRUD函数。

⚠️ **重要**: 此步骤应在确认所有功能正常工作后执行！

- [ ] **Step 1: 备份当前代码（可选但推荐）**

```bash
git branch backup/kline-db-before-remove
git checkout backup/kline-db-before-remove
```

- [ ] **Step 2: 从models.py中删除K线模型类**

删除以下三个类及其导入：
- `CryptoSpotKline` (第250-269行)
- `CryptoFutureKline` (第272-291行)
- `StockKline` (第294-313行)

- [ ] **Step 3: 从crud.py中删除K线相关函数**

搜索并删除所有包含 `crypto_spot_klines`, `crypto_future_klines`, `stock_klines` 的CRUD函数。

- [ ] **Step 4: 简化或删除kline_factory.py**

如果该文件仅用于数据库查询，可以完全删除或大幅简化。

- [ ] **Step 5: 验证项目仍能正常启动**

```bash
cd backend && python -c "from main import app; print('✅ 应用启动正常')"
```
Expected: 无导入错误

- [ ] **Step 6: 提交Task 6代码**

```bash
git add collector/db/models.py collector/db/crud.py collector/services/kline_factory.py
git commit -m "remove: delete K-line database models and CRUD operations"
```

---

## Task 7: 创建数据迁移脚本

**Files:**
- Create: `backend/scripts/migrate_kline_to_parquet.py`

**目标:** 提供工具将现有数据库中的K线数据导出到Parquet文件。

- [ ] **Step 1: 编写迁移脚本**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库K线数据迁移脚本

将SQLite数据库中的K线数据导出为Parquet文件格式。
"""

import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger, LogType
from utils.kline_file_manager import KlineFileManager

logger = get_logger(__name__, LogType.APPLICATION)


def migrate_from_database(db_url: str = None, batch_size: int = 10000):
    """
    从数据库迁移K线数据到Parquet文件
    
    Args:
        db_url: 数据库连接URL
        batch_size: 每批处理的记录数
    """
    from sqlalchemy import create_engine, text
    
    if db_url is None:
        db_url = "sqlite:///./quantcell.db"
    
    engine = create_engine(db_url)
    manager = KlineFileManager()
    
    tables_to_migrate = [
        ('crypto_spot_klines', 'spot'),
        ('crypto_future_klines', 'future'),
    ]
    
    total_migrated = 0
    
    for table_name, market_type in tables_to_migrate:
        logger.info(f"\n{'='*60}")
        logger.info(f"开始迁移表: {table_name} → {market_type}")
        
        try:
            # 检查表是否存在
            with engine.connect() as conn:
                result = conn.execute(text(
                    f"SELECT COUNT(*) FROM {table_name}"
                ))
                total_rows = result.scalar()
                
                if total_rows == 0:
                    logger.warning(f"表 {table_name} 为空，跳过")
                    continue
                
                logger.info(f"总记录数: {total_rows}")
                
                # 分批读取并保存
                offset = 0
                batch_num = 0
                
                while offset < total_rows:
                    query = text(f"""
                        SELECT symbol, interval, timestamp, open, high, low, close, volume 
                        FROM {table_name}
                        ORDER BY timestamp
                        LIMIT :limit OFFSET :offset
                    """)
                    
                    with engine.connect() as conn:
                        df = pd.read_sql_query(
                            query,
                            conn,
                            params={'limit': batch_size, 'offset': offset}
                        )
                    
                    if df.empty:
                        break
                    
                    # 按品种和周期分组保存
                    for (symbol, interval), group in df.groupby(['symbol', 'interval']):
                        saved = manager.save_klines(
                            df=group,
                            symbol=symbol,
                            interval=interval,
                            market_type=market_type
                        )
                        
                        if saved:
                            logger.info(
                                f"  批次{batch_num}: {symbol} {interval} "
                                f"- {len(group)} 条 ✓"
                            )
                    
                    offset += batch_size
                    batch_num += 1
                    total_migrated += len(df)
                    
                    progress = min(offset / total_rows * 100, 100)
                    logger.info(f"进度: {progress:.1f}% ({offset}/{total_rows})")
            
            logger.info(f"✅ 表 {table_name} 迁移完成!")
            
        except Exception as e:
            logger.error(f"❌ 表 {table_name} 迁移失败: {e}")
            continue
    
    logger.info(f"\n{'='*60}")
    logger.info(f"迁移总计: {total_migrated} 条记录")
    
    # 输出统计信息
    stats = manager.get_storage_stats()
    logger.info(f"\n存储统计:")
    logger.info(f"  总文件数: {stats['total_files']}")
    logger.info(f"  总大小: {stats['total_size_mb']} MB")
    logger.info(f"  可用品种: {list(stats['symbols'].keys())}")


if __name__ == '__main__':
    import typer
    
    app = typer.Typer()
    
    @app.command()
    def main(
        db_url: str = typer.Option(None, help="数据库连接URL"),
        batch_size: int = typer.Option(10000, help="每批处理记录数"),
        dry_run: bool = typer.Option(False, help="只显示统计信息，不实际迁移")
    ):
        """迁移K线数据从数据库到Parquet文件"""
        
        if dry_run:
            from sqlalchemy import create_engine, text
            
            url = db_url or "sqlite:///./quantcell.db"
            engine = create_engine(url)
            
            print("\n📊 数据库K线数据统计:")
            for table in ['crypto_spot_klines', 'crypto_future_klines']:
                try:
                    with engine.connect() as conn:
                        count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                        print(f"  {table}: {count:,} 条记录")
                except Exception as e:
                    print(f"  {table}: 错误 - {e}")
            
            return
        
        migrate_from_database(db_url, batch_size)
        print("\n✅ 迁移完成!")
    
    app()
```

- [ ] **Step 2: 测试迁移脚本（dry-run模式）**

```bash
cd backend && python scripts/migrate_kline_to_parquet.py --dry-run
```
Expected: 显示数据库中各表的记录数统计

- [ ] **Step 3: 执行完整迁移（可选）**

⚠️ **警告**: 仅在确认备份后执行！

```bash
cd backend && python scripts/migrate_kline_to_parquet.py
```
Expected: 所有数据成功导出到Parquet文件

- [ ] **Step 4: 提交Task 7代码**

```bash
git add scripts/migrate_kline_to_parquet.py
git commit -m "feat: add database to Parquet migration script"
```

---

## Task 8: 更新CLI命令和文档

**Files:**
- Modify: `backend/scripts/data_cli.py`
- Modify: `backend/scripts/backtest_cli.py`

**目标:** 更新命令行工具以反映新的存储方式。

- [ ] **Step 1: 更新data_cli.py**

添加新命令：
```python
@app.command()
def stats():
    """显示K线数据文件存储统计"""
    from utils.kline_file_manager import get_kline_file_manager
    
    manager = get_kline_file_manager()
    stats = manager.get_storage_stats()
    
    print("\n📊 K线数据存储统计:")
    print(f"  基础目录: {stats['base_dir']}")
    print(f"  总文件数: {stats['total_files']}")
    print(f"  总大小: {stats['total_size_mb']} MB")
    print(f"\n  可用品种:")
    for symbol, info in stats['symbols'].items():
        print(f"    {symbol}: {info['total_files']} 文件, {info['total_size_mb']} MB")

@app.command()
def cleanup():
    """清理过期的K线数据缓存"""
    print("清理功能待实现...")
```

- [ ] **Step 2: 更新backtest_cli.py的帮助文本**

在帮助信息中说明数据来源已改为Parquet文件。

- [ ] **Step 3: 提交Task 8代码**

```bash
git add scripts/data_cli.py scripts/backtest_cli.py
git commit -m "docs: update CLI commands for Parquet storage"
```

---

## Task 9: 最终集成测试和性能基准

**Files:**
- Test: 手动测试 + 性能测试脚本

**目标:** 确保整个系统正常工作，并建立性能基线。

- [ ] **Step 1: 端到端测试 - 数据下载流程**

```bash
# 1. 下载少量数据
python scripts/data_cli.py download --symbol ETHUSDT --interval 15m --days 7

# 2. 验证文件生成
ls -lh data/klines/spot/ETHUSDT/15m/

# 3. 查看文件内容
python -c "
from utils.kline_file_manager import get_kline_file_manager
manager = get_kline_file_manager()
df = manager.load_klines('ETHUSDT', '15m')
print(f'✅ 加载 {len(df)} 条记录')
print(df.head())
"
```

- [ ] **Step 2: 端到端测试 - 回测流程**

```bash
# 运行一个简单的回测
python scripts/backtest_cli.py run \
    --strategy sma_cross_simple \
    --symbol ETHUSDT \
    --interval 15m \
    --start $(date -v-7d +%Y-%m-%d) \
    --end $(date +%Y-%m-%d)

# 验证结果文件生成
ls -lh backtest/results/*.json | tail -3
```

- [ ] **Step 3: 性能基准测试**

```python
# tests/benchmark_parquet_performance.py
import time
import pandas as pd
from utils.kline_file_manager import get_kline_file_manager

manager = get_kline_file_manager()

# 测试加载性能
start = time.time()
df = manager.load_klines('BTCUSDT', '1h')
load_time = time.time() - start

print(f"\n📈 性能基准:")
print(f"  加载 {len(df)} 条记录: {load_time:.3f}s")
print(f"  吞吐量: {len(df)/load_time:.0f} records/s")
print(f"  内存占用: {df.memory_usage(deep=True).sum() / 1024:.1f} KB")
```

- [ ] **Step 4: 记录性能基线**

创建文件 `docs/performance_baselines.md` 记录初始性能指标。

- [ ] **Step 5: 最终提交**

```bash
git add -A
git commit -m "feat: complete migration of K-line data to Parquet file system"
git tag v2.0-kline-parquet-migration
```

---

## 总结

### 完成的改造清单

✅ **Task 1**: 实现KlineFileManager核心模块  
✅ **Task 2**: 修改DataService使用文件存储  
✅ **Task 3**: 标准化Binance下载器返回DataFrame  
✅ **Task 4**: 修改回测服务使用Parquet读取  
✅ **Task 5**: 更新数据适配器  
✅ **Task 6**: 清理数据库模型和CRUD代码  
✅ **Task 7**: 创建数据迁移脚本  
✅ **Task 8**: 更新CLI和文档  
✅ **Task 9**: 集成测试和性能基准  

### 预期收益

- 🚀 **性能提升**: 查询速度提升 5-10x
- 💾 **空间节省**: 存储空间减少 60-80%
- 🔧 **架构简化**: 消除数据库依赖
- 📦 **易于部署**: 无需数据库初始化

### 后续优化方向

- [ ] 添加数据完整性校验机制
- [ ] 实现增量更新（避免全量覆盖）
- [ ] 添加数据过期自动清理
- [ ] 支持分布式存储（S3/NFS）
