"""K线周期 canonical 统一：workers.trading_config JSON 补 interval 键（双键期）。

命名语义一致性审计（域八 时间与周期）：
- canonical 键 = interval；旧键 timeframe 保留共存（Phase A 双写/读取兼容），至少保留
  2 个版本后再退役收敛单键
- 增量写入由 Worker.set_trading_config_dict 保证双键；本迁移只对存量 JSON 回填
  interval 键（仅在缺失时写入，幂等），不改写 timeframe 原值
- 读取侧兼容见 Worker.get_interval / TradingConfig._accept_legacy_timeframe

Revision ID: 41
Revises: 40
Create Date: 2026-11-17
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "41"
down_revision = "40"
branch_labels = None
depends_on = None


def _iter_worker_configs():
    """逐行读取 (id, trading_config dict)；损坏 JSON 由调用方按原样跳过。"""
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, trading_config FROM workers")).fetchall()
    for worker_id, raw in rows:
        if not raw:
            continue
        try:
            cfg = json.loads(raw)
        except json.JSONDecodeError, TypeError:
            continue
        yield worker_id, cfg


def upgrade() -> None:
    conn = op.get_bind()
    for worker_id, cfg in _iter_worker_configs():
        if not isinstance(cfg, dict) or "interval" in cfg:
            continue  # 已有新键（或非 dict 异常数据）→ 幂等跳过
        interval = cfg.get("timeframe")
        if not interval:
            continue  # 无旧键不凭空造值，读取侧 get_interval 兜底默认 1h
        cfg["interval"] = str(interval)
        conn.execute(
            sa.text("UPDATE workers SET trading_config = :cfg WHERE id = :id"),
            {"cfg": json.dumps(cfg, ensure_ascii=False), "id": worker_id},
        )


def downgrade() -> None:
    # 双键设计的逆操作只删新键：timeframe 旧键全程未动，回滚后旧格式数据原样保留，零信息损失
    conn = op.get_bind()
    for worker_id, cfg in _iter_worker_configs():
        if not isinstance(cfg, dict) or "interval" not in cfg:
            continue
        cfg.pop("interval", None)
        conn.execute(
            sa.text("UPDATE workers SET trading_config = :cfg WHERE id = :id"),
            {"cfg": json.dumps(cfg, ensure_ascii=False), "id": worker_id},
        )
