"""删除恒空表 worker_performance（P1-9 下线）。

该表自引入以来全库无写入方（无任何业务代码 upsert 绩效行），读取端点
/monitoring/performance 与 CLI pnl-distribution / trade-history 只会返回空，
已在同一批次下线（model / schema / crud / 路由 / CLI 一并移除）。
本迁移把存量库中的空表一并删除；downgrade 不重建（model 已删，重建的表
无人读写，只会重新引入「表存在但恒空」的分裂状态）。

幂等：inspector 检测表不存在则跳过（新库 create_all 按新 schema 建立时
表本来就不会生成，迁移空跑）。
"""

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision = "49"
down_revision = "48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa_inspect(op.get_bind()).has_table("worker_performance"):
        op.drop_table("worker_performance")


def downgrade() -> None:
    # 有意不可逆：model 与读写链路已删除，重建只会恢复空表假象
    pass
