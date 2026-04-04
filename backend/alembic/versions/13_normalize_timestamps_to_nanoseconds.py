"""Normalize timestamps to nanoseconds

Revision ID: 13_normalize_timestamps_to_nanoseconds
Revises: 12_normalize_timestamps_to_microseconds
Create Date: 2026-04-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision: str = '12'
down_revision: Union[str, Sequence[str], None] = '11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def detect_precision(ts_str: str) -> str:
    """检测时间戳精度"""
    try:
        ts_int = int(ts_str)
        if ts_int > 10**18:  # 纳秒级 (19位+)
            return 'ns'
        elif ts_int > 10**15:  # 微秒级 (16-18位)
            return 'us'
        elif ts_int > 10**12:  # 毫秒级 (13-15位)
            return 'ms'
        else:  # 秒级 (10位)
            return 's'
    except (ValueError, TypeError):
        return 'unknown'


def upgrade() -> None:
    """将数据库中所有时间戳统一转换为纳秒级"""

    # 获取数据库连接
    conn = op.get_bind()

    # 需要处理的表
    tables = [
        'crypto_spot_klines',
        'crypto_future_klines',
        'stock_klines'
    ]

    for table in tables:
        print(f"\n处理表: {table}")

        # 检查表是否存在
        result = conn.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = '{table}'
            )
        """))
        if not result.scalar():
            print(f"  表 {table} 不存在，跳过")
            continue

        # 获取所有记录
        result = conn.execute(text(f"""
            SELECT id, timestamp, unique_kline
            FROM {table}
            ORDER BY id
        """))

        records = result.fetchall()
        total = len(records)
        print(f"  总记录数: {total}")

        if total == 0:
            continue

        # 统计各精度数量
        ms_count = 0
        us_count = 0
        ns_count = 0
        s_count = 0
        unknown_count = 0

        for record in records:
            ts = str(record[1]) if record[1] else None
            if ts:
                precision = detect_precision(ts)
                if precision == 'ms':
                    ms_count += 1
                elif precision == 'us':
                    us_count += 1
                elif precision == 'ns':
                    ns_count += 1
                elif precision == 's':
                    s_count += 1
                else:
                    unknown_count += 1

        print(f"  毫秒级(ms): {ms_count}, 微秒级(us): {us_count}, 纳秒级(ns): {ns_count}, 秒级(s): {s_count}, 未知: {unknown_count}")

        # 转换毫秒级为纳秒级
        if ms_count > 0:
            print(f"  开始转换毫秒级时间戳...")

            updated = 0
            batch_size = 1000

            for i in range(0, len(records), batch_size):
                batch = records[i:i+batch_size]

                for record in batch:
                    record_id = record[0]
                    ts = str(record[1]) if record[1] else None
                    unique_kline = record[2]

                    if not ts:
                        continue

                    precision = detect_precision(ts)

                    if precision == 'ms':
                        # 毫秒转纳秒: ×1,000,000
                        new_ts = str(int(ts) * 1_000_000)

                        # 更新unique_kline (格式: symbol_interval_timestamp)
                        if unique_kline:
                            parts = unique_kline.split('_')
                            if len(parts) >= 3:
                                parts[-1] = new_ts
                                new_unique_kline = '_'.join(parts)
                            else:
                                new_unique_kline = unique_kline
                        else:
                            new_unique_kline = None

                        # 执行更新
                        conn.execute(text(f"""
                            UPDATE {table}
                            SET timestamp = :ts, unique_kline = :uk
                            WHERE id = :id
                        """), {'ts': new_ts, 'uk': new_unique_kline, 'id': record_id})

                        updated += 1

                if (i // batch_size + 1) % 10 == 0:
                    print(f"    已处理 {min(i + batch_size, total)}/{total} 条记录，更新 {updated} 条")

            print(f"  完成！共更新 {updated} 条记录")

        # 转换微秒级为纳秒级
        if us_count > 0:
            print(f"  开始转换微秒级时间戳...")

            updated = 0
            batch_size = 1000

            for i in range(0, len(records), batch_size):
                batch = records[i:i+batch_size]

                for record in batch:
                    record_id = record[0]
                    ts = str(record[1]) if record[1] else None
                    unique_kline = record[2]

                    if not ts:
                        continue

                    precision = detect_precision(ts)

                    if precision == 'us':
                        # 微秒转纳秒: ×1000
                        new_ts = str(int(ts) * 1000)

                        # 更新unique_kline
                        if unique_kline:
                            parts = unique_kline.split('_')
                            if len(parts) >= 3:
                                parts[-1] = new_ts
                                new_unique_kline = '_'.join(parts)
                            else:
                                new_unique_kline = unique_kline
                        else:
                            new_unique_kline = None

                        conn.execute(text(f"""
                            UPDATE {table}
                            SET timestamp = :ts, unique_kline = :uk
                            WHERE id = :id
                        """), {'ts': new_ts, 'uk': new_unique_kline, 'id': record_id})

                        updated += 1

                if (i // batch_size + 1) % 10 == 0:
                    print(f"    已处理 {min(i + batch_size, total)}/{total} 条记录，更新 {updated} 条")

            print(f"  完成！共更新 {updated} 条记录")

        # 转换秒级为纳秒级
        if s_count > 0:
            print(f"  开始转换秒级时间戳...")

            updated = 0

            for record in records:
                record_id = record[0]
                ts = str(record[1]) if record[1] else None
                unique_kline = record[2]

                if not ts:
                    continue

                precision = detect_precision(ts)

                if precision == 's':
                    # 秒转纳秒: ×1,000,000,000
                    new_ts = str(int(ts) * 1_000_000_000)

                    # 更新unique_kline
                    if unique_kline:
                        parts = unique_kline.split('_')
                        if len(parts) >= 3:
                            parts[-1] = new_ts
                            new_unique_kline = '_'.join(parts)
                        else:
                            new_unique_kline = unique_kline
                    else:
                        new_unique_kline = None

                    conn.execute(text(f"""
                        UPDATE {table}
                        SET timestamp = :ts, unique_kline = :uk
                        WHERE id = :id
                    """), {'ts': new_ts, 'uk': new_unique_kline, 'id': record_id})

                    updated += 1

            print(f"  完成！共更新 {updated} 条记录")

    print("\n✓ 时间戳标准化为纳秒级完成！")


def downgrade() -> None:
    """降级：将纳秒级时间戳转换回微秒级（不推荐）"""

    print("警告：降级操作会将纳秒级时间戳转换回微秒级，可能导致精度丢失！")

    conn = op.get_bind()

    tables = [
        'crypto_spot_klines',
        'crypto_future_klines',
        'stock_klines'
    ]

    for table in tables:
        print(f"\n处理表: {table}")

        result = conn.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = '{table}'
            )
        """))
        if not result.scalar():
            continue

        result = conn.execute(text(f"""
            SELECT id, timestamp, unique_kline
            FROM {table}
            WHERE LENGTH(timestamp) = 19
        """))

        records = result.fetchall()

        for record in records:
            record_id = record[0]
            ts = str(record[1]) if record[1] else None
            unique_kline = record[2]

            if not ts:
                continue

            # 纳秒转微秒: //1000
            new_ts = str(int(ts) // 1000)

            if unique_kline:
                parts = unique_kline.split('_')
                if len(parts) >= 3:
                    parts[-1] = new_ts
                    new_unique_kline = '_'.join(parts)
                else:
                    new_unique_kline = unique_kline
            else:
                new_unique_kline = None

            conn.execute(text(f"""
                UPDATE {table}
                SET timestamp = :ts, unique_kline = :uk
                WHERE id = :id
            """), {'ts': new_ts, 'uk': new_unique_kline, 'id': record_id})

        print(f"  降级完成: {len(records)} 条记录")
