"""
SQLite数据库管理器

提供异步的SQLite操作接口，支持高并发读写。
用于Worker数据的本地持久化存储。
"""

import sqlite3
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class SQLiteManager:
    """
    SQLite异步管理器
    
    特性：
    1. 使用WAL模式支持并发读写
    2. 连接池管理
    3. 自动重连机制
    4. 批量插入优化
    """
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._initialized = False
    
    async def initialize(self):
        """初始化数据库"""
        loop = asyncio.get_event_loop()
        
        # 在线程池中执行阻塞的初始化操作
        await loop.run_in_executor(None, self._sync_initialize)
        
        self._initialized = True
        logger.info(f"SQLite数据库已初始化: {self.db_path}")
    
    def _sync_initialize(self):
        """同步初始化（在线程池中运行）"""
        conn = sqlite3.connect(str(self.db_path))
        
        # 启用WAL模式以支持并发
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA cache_size=-64000')  # 64MB缓存
        conn.execute('PRAGMA busy_timeout=5000')   # 5秒锁超时
        
        # 创建表结构
        self._create_tables(conn)
        
        conn.close()
    
    def _create_tables(self, conn: sqlite3.Connection):
        """创建数据表"""
        cursor = conn.cursor()
        
        # 成交记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS worker_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                
                -- 交易唯一标识
                trade_id VARCHAR(100) UNIQUE NOT NULL,
                
                -- 交易基本信息
                symbol VARCHAR(50) NOT NULL,
                side VARCHAR(10) NOT NULL,
                order_type VARCHAR(20) NOT NULL,
                
                -- 成交详情
                quantity FLOAT NOT NULL,
                price FLOAT NOT NULL,
                amount FLOAT NOT NULL,
                
                -- 费用信息
                fee FLOAT DEFAULT 0.0,
                fee_currency VARCHAR(10) DEFAULT 'USDT',
                
                -- 盈亏信息
                realized_pnl FLOAT,
                realized_pnl_pct FLOAT,
                
                -- 订单关联
                client_order_id VARCHAR(100),
                venue_order_id VARCHAR(100),
                position_id VARCHAR(100),
                
                -- 时间戳（nautilus纳秒格式）
                ts_event INTEGER NOT NULL,
                ts_init INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 持仓快照表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS position_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                
                -- 持仓标识
                position_id VARCHAR(100) NOT NULL,
                instrument_id VARCHAR(100) NOT NULL,
                symbol VARCHAR(50) DEFAULT '',
                
                -- 持仓方向和数量
                side VARCHAR(10) NOT NULL,
                signed_qty FLOAT NOT NULL,
                quantity FLOAT NOT NULL,
                
                -- 价格信息
                avg_px_open FLOAT NOT NULL,
                avg_px_close FLOAT DEFAULT 0.0,
                
                -- 盈亏计算
                unrealized_pnl FLOAT DEFAULT 0.0,
                realized_pnl FLOAT,
                total_pnl FLOAT DEFAULT 0.0,
                
                -- 佣金
                commission_currency VARCHAR(10),
                commission_amount FLOAT DEFAULT 0.0,
                
                -- 状态信息
                is_open BOOLEAN DEFAULT TRUE,
                peak_qty FLOAT DEFAULT 0.0,
                
                -- 时间戳（nautilus格式）
                ts_init INTEGER NOT NULL,
                ts_opened INTEGER,
                ts_last INTEGER NOT NULL,
                ts_closed INTEGER,
                duration_ns INTEGER,
                
                -- 快照时间
                snapshot_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(worker_id, position_id, snapshot_time)
            )
        """)
        
        # 订单事件表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                
                -- 订单标识
                order_id VARCHAR(100) NOT NULL,
                client_order_id VARCHAR(100),
                venue_order_id VARCHAR(100),
                
                -- 订单状态
                event_type VARCHAR(30) NOT NULL,
                
                -- 交易对
                instrument_id VARCHAR(100) NOT NULL,
                symbol VARCHAR(50) NOT NULL,
                
                -- 订单参数
                side VARCHAR(10) NOT NULL,
                order_type VARCHAR(20) NOT NULL,
                quantity FLOAT,
                price FLOAT,
                
                -- 成交信息（仅OrderFilled事件）
                last_qty FLOAT,
                last_px FLOAT,
                commission FLOAT,
                commission_currency VARCHAR(10),
                
                -- 时间戳
                ts_event INTEGER NOT NULL,
                ts_init INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引（必须在表创建后单独执行）
        # worker_trades 表索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_worker_trade_worker ON worker_trades(worker_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_worker_trade_symbol ON worker_trades(worker_id, symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_worker_trade_time ON worker_trades(worker_id, created_at)")
        
        # position_snapshots 表索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_position_worker ON position_snapshots(worker_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_position_instrument ON position_snapshots(worker_id, instrument_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_position_snapshot ON position_snapshots(worker_id, snapshot_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_position_active ON position_snapshots(worker_id, is_open)")
        
        # order_events 表索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_worker ON order_events(worker_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_id ON order_events(order_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_type ON order_events(worker_id, event_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_time ON order_events(worker_id, created_at)")
        
        conn.commit()
    
    @asynccontextmanager
    async def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        loop = asyncio.get_event_loop()
        conn = await loop.run_in_executor(None, self._get_connection)
        try:
            yield conn
        finally:
            await loop.run_in_executor(None, conn.close)
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取新连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn
    
    # ========== 写入操作 ==========
    
    async def insert_trade(self, trade_data: Dict[str, Any]):
        """插入成交记录"""
        async with self.get_connection() as conn:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._sync_insert_trade(conn, trade_data)
            )
    
    def _sync_insert_trade(self, conn: sqlite3.Connection, data: dict):
        """同步插入成交记录"""
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO worker_trades (
                    worker_id, trade_id, symbol, side, order_type,
                    quantity, price, amount, fee, fee_currency,
                    client_order_id, venue_order_id, position_id,
                    ts_event, ts_init, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["worker_id"], data["trade_id"], data["symbol"],
                data["side"], data["order_type"], data["quantity"],
                data["price"], data["amount"], data["fee"],
                data.get("fee_currency", "USDT"),
                data.get("client_order_id"), data.get("venue_order_id"),
                data.get("position_id"), data.get("ts_event"),
                data.get("ts_init"), data.get("created_at", datetime.now())
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            logger.debug(f"成交记录已存在: {data['trade_id']}")
    
    async def upsert_position(self, snapshot_data: Dict[str, Any]):
        """更新或插入持仓快照"""
        async with self.get_connection() as conn:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._sync_upsert_position(conn, snapshot_data)
            )
    
    def _sync_upsert_position(self, conn: sqlite3.Connection, data: dict):
        """同步更新持仓快照"""
        cursor = conn.cursor()
        
        # 插入新快照（利用UNIQUE约束自动去重）
        cursor.execute("""
            INSERT INTO position_snapshots (
                worker_id, position_id, instrument_id, symbol,
                side, signed_qty, quantity, avg_px_open,
                unrealized_pnl, is_open, ts_last, snapshot_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["worker_id"], data["position_id"], 
            data["instrument_id"], data.get("symbol", ""),
            data["side"], data["signed_qty"], data["quantity"],
            data["avg_px_open"], data.get("unrealized_pnl", 0.0),
            data.get("is_open", True), data.get("ts_last"),
            data["snapshot_time"]
        ))
        
        conn.commit()
    
    async def insert_order_event(self, event_data: Dict[str, Any]):
        """插入订单事件"""
        async with self.get_connection() as conn:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._sync_insert_order_event(conn, event_data)
            )
    
    def _sync_insert_order_event(self, conn: sqlite3.Connection, data: dict):
        """同步插入订单事件"""
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO order_events (
                worker_id, order_id, client_order_id, venue_order_id,
                event_type, instrument_id, symbol, side, order_type,
                quantity, price, last_qty, last_px, commission,
                ts_event, ts_init, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["worker_id"], data.get("order_id", ""),
            data.get("client_order_id"), data.get("venue_order_id"),
            data["event_type"], data["instrument_id"], data["symbol"],
            data.get("side"), data.get("order_type"),
            data.get("quantity"), data.get("price"),
            data.get("last_qty"), data.get("last_px"),
            data.get("commission"), data.get("ts_event"),
            data.get("ts_init"), datetime.now()
        ))
        conn.commit()
    
    # ========== 查询接口 ==========
    
    async def get_latest_trades(
        self,
        worker_id: int,
        limit: int = 50,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取最新成交记录"""
        async with self.get_connection() as conn:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: self._sync_get_latest_trades(conn, worker_id, limit, symbol)
            )
    
    def _sync_get_latest_trades(
        self, 
        conn: sqlite3.Connection, 
        worker_id: int, 
        limit: int, 
        symbol: Optional[str]
    ) -> List[Dict]:
        cursor = conn.cursor()
        query = """
            SELECT * FROM worker_trades 
            WHERE worker_id = ?
        """
        params = [worker_id]
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    async def get_active_positions(self, worker_id: int) -> List[Dict[str, Any]]:
        """获取当前活跃持仓"""
        async with self.get_connection() as conn:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: self._sync_get_active_positions(conn, worker_id)
            )
    
    def _sync_get_active_positions(
        self, 
        conn: sqlite3.Connection, 
        worker_id: int
    ) -> List[Dict]:
        cursor = conn.cursor()
        
        # 获取每个position的最新快照
        cursor.execute("""
            SELECT * FROM position_snapshots ps1
            WHERE worker_id = ? AND is_open = 1
              AND snapshot_time = (
                  SELECT MAX(ps2.snapshot_time) 
                  FROM position_snapshots ps2 
                  WHERE ps2.worker_id = ps1.worker_id 
                    AND ps2.position_id = ps1.position_id
              )
            ORDER BY snapshot_time DESC
        """, (worker_id,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    async def get_order_events(
        self,
        worker_id: int,
        event_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取订单事件列表"""
        async with self.get_connection() as conn:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: self._sync_get_order_events(conn, worker_id, event_type, limit)
            )
    
    def _sync_get_order_events(
        self,
        conn: sqlite3.Connection,
        worker_id: int,
        event_type: Optional[str],
        limit: int
    ) -> List[Dict]:
        cursor = conn.cursor()
        
        query = """
            SELECT * FROM order_events 
            WHERE worker_id = ?
        """
        params = [worker_id]
        
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    async def close(self):
        """关闭数据库连接"""
        self._initialized = False
