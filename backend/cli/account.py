"""quantcell account — 凭证管理 CLI。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import typer
from rich.console import Console
from rich.table import Table

from credentials.exceptions import AccountAlreadyExistsError, AccountNotFoundError
from credentials.service import CredentialsService

app = typer.Typer(help="凭证管理（add/list/remove）")
console = Console()


def _service() -> CredentialsService:
    db = os.environ.get("QC_CREDENTIALS_DB", "backend/data/credentials.db")
    return CredentialsService(db_path=db)


@app.command("add")
def add_cmd(
    name: str = typer.Option(..., "--name", help="账号名（唯一）"),
    exchange: str = typer.Option(..., "--exchange", help="binance | okx"),
    api_key: str = typer.Option(..., "--api-key"),
    api_secret: str = typer.Option(..., "--api-secret"),
):
    """新增账号（凭证加密入库）。"""
    try:
        svc = _service()
        acct = svc.add_account(name, exchange, api_key, api_secret)
        console.print(f"[green]✓[/green] 账号 '{name}' 创建成功 (UUID: {acct.id})")
    except AccountAlreadyExistsError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=1)


@app.command("list")
def list_cmd():
    """列出所有账号（不含 secret）。"""
    svc = _service()
    accounts = svc.list_accounts()
    if not accounts:
        console.print("(无账号)")
        return
    table = Table(title="账号列表")
    table.add_column("UUID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Exchange")
    table.add_column("Created")
    for a in accounts:
        table.add_row(str(a.id), a.name, a.exchange, a.created_at.isoformat())
    console.print(table)


@app.command("remove")
def remove_cmd(name: str = typer.Option(..., "--name")):
    """软删除账号。"""
    try:
        svc = _service()
        svc.remove_account(name)
        console.print(f"[green]✓[/green] 账号 '{name}' 已删除")
    except AccountNotFoundError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
