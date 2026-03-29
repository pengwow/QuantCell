"""update_worker_trading_config

Revision ID: 10
Revises: fe4d07250fbb
Create Date: 2026-03-29 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
import json


# revision identifiers, used by Alembic.
revision: str = '10'
down_revision: Union[str, Sequence[str], None] = '8b8f30ec3699'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - 将分散的交易配置字段合并为 trading_config JSON 字段."""
    conn = op.get_bind()
    inspector = inspect(conn)

    # 检查 workers 表是否存在
    if 'workers' not in inspector.get_table_names():
        return

    columns = {c['name']: c for c in inspector.get_columns('workers')}

    # 如果已经存在 trading_config 列，跳过
    if 'trading_config' in columns:
        return

    # 1. 添加新的 trading_config 列
    op.add_column('workers', sa.Column('trading_config', sa.Text(), nullable=True, default='{}'))

    # 2. 迁移旧数据到新的 trading_config 字段
    # 获取所有现有的 workers 数据
    result = conn.execute(text("SELECT id, exchange, symbol, timeframe, market_type, trading_mode FROM workers"))
    workers = result.fetchall()

    for worker in workers:
        worker_id, exchange, symbol, timeframe, market_type, trading_mode = worker

        # 构建交易配置
        trading_config = {
            "exchange": exchange or "binance",
            "symbols_config": {
                "type": "symbols",
                "symbols": [symbol] if symbol else ["BTCUSDT"],
                "pool_id": None,
                "pool_name": None
            },
            "timeframe": timeframe or "1h",
            "market_type": market_type or "spot",
            "trading_mode": trading_mode or "paper"
        }

        # 更新记录
        conn.execute(
            text("UPDATE workers SET trading_config = :config WHERE id = :id"),
            {"config": json.dumps(trading_config), "id": worker_id}
        )

    # 3. 删除旧的列（可选，为了兼容性可以保留）
    # 这里我们选择保留旧列，以便在需要时可以回滚
    # op.drop_column('workers', 'exchange')
    # op.drop_column('workers', 'symbol')
    # op.drop_column('workers', 'timeframe')
    # op.drop_column('workers', 'market_type')
    # op.drop_column('workers', 'trading_mode')


def downgrade() -> None:
    """Downgrade schema - 将 trading_config 拆分回分散的字段."""
    conn = op.get_bind()
    inspector = inspect(conn)

    if 'workers' not in inspector.get_table_names():
        return

    columns = {c['name']: c for c in inspector.get_columns('workers')}

    # 如果没有 trading_config 列，跳过
    if 'trading_config' not in columns:
        return

    # 1. 确保旧列存在
    if 'exchange' not in columns:
        op.add_column('workers', sa.Column('exchange', sa.String(length=50), nullable=False, server_default='binance'))
    if 'symbol' not in columns:
        op.add_column('workers', sa.Column('symbol', sa.String(length=50), nullable=False, server_default='BTCUSDT'))
    if 'timeframe' not in columns:
        op.add_column('workers', sa.Column('timeframe', sa.String(length=10), nullable=False, server_default='1h'))
    if 'market_type' not in columns:
        op.add_column('workers', sa.Column('market_type', sa.String(length=20), nullable=True, server_default='spot'))
    if 'trading_mode' not in columns:
        op.add_column('workers', sa.Column('trading_mode', sa.String(length=10), nullable=True, server_default='paper'))

    # 2. 从 trading_config 恢复数据到旧字段
    result = conn.execute(text("SELECT id, trading_config FROM workers WHERE trading_config IS NOT NULL"))
    workers = result.fetchall()

    for worker in workers:
        worker_id, trading_config_json = worker
        try:
            trading_config = json.loads(trading_config_json) if trading_config_json else {}
            symbols_config = trading_config.get('symbols_config', {})
            symbols = symbols_config.get('symbols', [])
            symbol = symbols[0] if symbols else 'BTCUSDT'

            conn.execute(
                text("""
                    UPDATE workers SET
                        exchange = :exchange,
                        symbol = :symbol,
                        timeframe = :timeframe,
                        market_type = :market_type,
                        trading_mode = :trading_mode
                    WHERE id = :id
                """),
                {
                    "exchange": trading_config.get('exchange', 'binance'),
                    "symbol": symbol,
                    "timeframe": trading_config.get('timeframe', '1h'),
                    "market_type": trading_config.get('market_type', 'spot'),
                    "trading_mode": trading_config.get('trading_mode', 'paper'),
                    "id": worker_id
                }
            )
        except json.JSONDecodeError:
            continue

    # 3. 删除 trading_config 列
    op.drop_column('workers', 'trading_config')
