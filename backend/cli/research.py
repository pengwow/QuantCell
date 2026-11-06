#!/usr/bin/env python3
"""研究模块运维命令

当前只承载 P2-④：把旧 LLM 挖掘历史（factor_mining_runs 表）包成 mode=quick
的研究会话，供研究工作台统一查看（幂等，可重复执行）。

使用方式:
    uv run python -m cli.research migrate-mining-runs --owner <你的用户ID>
    uv run python -m cli.research migrate-mining-runs --owner u1 --dry-run
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# 必须在 import 业务模块（utils.logger 首次配置）前设置：CLI 模式下降级到 WARNING，
# 避免 import 期 INFO 日志污染 stdout
os.environ.setdefault("CLI_MODE", "1")

import typer

app = typer.Typer(name="research", help="研究模块运维命令", add_completion=False, no_args_is_help=True)


@app.command("migrate-mining-runs")
def migrate_mining_runs(
    owner: str = typer.Option(
        ..., "--owner", help="迁移后会话归属的用户 ID；列表页按 owner 过滤，建议传你登录用的 user_id"
    ),
    limit: int = typer.Option(None, "--limit", min=1, help="最多处理多少条 run（默认全部）"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只统计将要迁移的内容，不写库"),
) -> None:
    """旧 LLM 挖掘历史 → mode=quick 的研究会话（幂等：已迁移的 run 自动跳过）。"""
    from factor.models import FactorMiningRun
    from research.migrate_legacy import SKIP_STATUSES, migrate_run
    from utils.db_session import get_db_session

    with get_db_session() as db:
        query = db.query(FactorMiningRun).order_by(FactorMiningRun.created_at.desc())
        rows = query.all() if limit is None else query.limit(limit).all()
        migrated = skipped = failed = 0
        for run in rows:
            if dry_run:
                typer.echo(f"will migrate run={run.id} job={run.job_id} status={run.status}")
                migrated += 1
                continue
            if run.status in SKIP_STATUSES:
                typer.echo(f"skip    run={run.id} still running")
                skipped += 1
                continue
            try:
                out = migrate_run(db, run, owner)
            except Exception as exc:
                failed += 1
                typer.echo(f"[ERROR] run={run.id} 迁移失败：{exc}")
                continue
            if out["skipped"]:
                skipped += 1
                typer.echo(f"skip    run={run.id} {out['skipped']}")
            else:
                migrated += 1
                typer.echo(f"migrate run={run.id} -> session={out['session_id']} trials={out['trials']}")
        typer.echo(f"完成：迁移 {migrated}，跳过 {skipped}，失败 {failed}")


if __name__ == "__main__":
    app()
