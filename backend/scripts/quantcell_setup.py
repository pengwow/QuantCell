#!/usr/bin/env python3
"""
QuantCell 系统配置管理与数据库初始化工具

提供系统配置的导入导出、数据库初始化和迁移等功能
"""

import hashlib
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import get_logger, LogType
from utils.env_checker import EnvChecker
from utils.config_manager import ConfigManager as ConfigIO
from utils.initializer import ProjectInitializer, setup_project
from settings.models import SystemConfigBusiness as SystemConfig

# 初始化日志
logger = get_logger(__name__, LogType.APPLICATION)
console = Console()

# 创建Typer应用
app = typer.Typer(
    name="quantcell-setup",
    help="QuantCell 系统配置管理与数据库初始化工具",
    rich_markup_mode="rich",
)

# 创建子命令组
migrate_app = typer.Typer(help="数据库迁移管理")
app.add_typer(migrate_app, name="migrate")


@app.command()
def export(
    output: Optional[str] = typer.Option(
        None, "--output", "-o",
        help="输出文件路径，默认为项目根目录下的 config.toml"
    ),
    include_sensitive: bool = typer.Option(
        False, "--include-sensitive",
        help="是否包含敏感配置（密码等）"
    ),
):
    """导出系统配置到TOML文件"""
    try:
        with console.status("[bold green]正在导出配置..."):
            output_path = ConfigIO.export_to_toml(output, include_sensitive)
        
        console.print(Panel(
            f"✓ 配置已导出到: [bold cyan]{output_path}[/bold cyan]",
            title="导出成功",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(Panel(
            f"✗ 导出失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


def hash_password(password: str) -> str:
    """对密码进行单向加密（SHA256）

    Args:
        password: 原始密码

    Returns:
        str: 加密后的密码哈希值
    """
    if not password:
        return ""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


@app.command()
def create_user(
    username: Optional[str] = typer.Option(
        None, "--username", "-u",
        help="用户名，不提供则交互式输入"
    ),
    password: Optional[str] = typer.Option(
        None, "--password", "-p",
        help="密码，不提供则交互式输入（推荐，避免密码泄露）"
    ),
    force: bool = typer.Option(
        False, "--force",
        help="强制覆盖已存在的用户"
    ),
):
    """创建系统用户

    创建系统登录用户，密码使用SHA256单向加密存储。
    如果不提供用户名和密码，将进入交互式模式。
    """
    try:
        # 检查是否已存在用户
        existing_username = SystemConfig.get('user.username')
        if existing_username and not force:
            console.print(Panel(
                f"用户已存在: [bold cyan]{existing_username}[/bold cyan]\n"
                f"使用 --force 参数覆盖现有用户",
                title="警告",
                border_style="yellow"
            ))
            raise typer.Exit(1)

        # 交互式输入用户名
        if not username:
            username = Prompt.ask("请输入用户名")

        if not username:
            console.print(Panel(
                "用户名不能为空",
                title="错误",
                border_style="red"
            ))
            raise typer.Exit(1)

        # 交互式输入密码
        if not password:
            password = Prompt.ask("请输入密码", password=True)
            confirm_password = Prompt.ask("请再次输入密码", password=True)

            if password != confirm_password:
                console.print(Panel(
                    "两次输入的密码不一致",
                    title="错误",
                    border_style="red"
                ))
                raise typer.Exit(1)

        if not password:
            console.print(Panel(
                "密码不能为空",
                title="错误",
                border_style="red"
            ))
            raise typer.Exit(1)

        # 加密密码
        hashed_password = hash_password(password)

        # 保存用户配置
        with console.status("[bold green]正在创建用户..."):
            SystemConfig.set('user.username', username, description='系统登录用户名', name='general')
            SystemConfig.set('user.password', hashed_password, description='系统登录密码（SHA256加密）', name='general', is_sensitive=True)

        console.print(Panel(
            f"✓ 用户创建成功\n"
            f"用户名: [bold cyan]{username}[/bold cyan]\n"
            f"密码: [bold green]已加密存储[/bold green]",
            title="成功",
            border_style="green"
        ))

    except Exception as e:
        console.print(Panel(
            f"✗ 创建用户失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


@app.command()
def import_(
    file: str = typer.Option(
        ..., "--file", "-f",
        help="要导入的TOML配置文件路径"
    ),
    overwrite: bool = typer.Option(
        True, "--overwrite/--no-overwrite",
        help="是否覆盖已存在的配置"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="试运行模式，不实际写入数据库"
    ),
):
    """从TOML文件导入系统配置"""
    try:
        with console.status("[bold green]正在导入配置..."):
            stats = ConfigIO.import_from_toml(file, overwrite, dry_run)
        
        # 创建结果表格
        table = Table(title="导入结果统计")
        table.add_column("项目", style="cyan")
        table.add_column("数量", style="magenta")
        
        table.add_row("总计", str(stats['total']))
        table.add_row("新建", f"[green]{stats['created']}[/green]")
        table.add_row("更新", f"[yellow]{stats['updated']}[/yellow]")
        table.add_row("跳过", f"[blue]{stats['skipped']}[/blue]")
        table.add_row("失败", f"[red]{stats['failed']}[/red]")
        
        console.print(table)
        
        if stats['failed'] > 0:
            console.print(Panel(
                "部分配置导入失败，请查看日志了解详情",
                title="警告",
                border_style="yellow"
            ))
            raise typer.Exit(1)
        
    except Exception as e:
        console.print(Panel(
            f"✗ 导入失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


@app.command()
def init_db(
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="显示详细信息"
    ),
):
    """初始化数据库表结构"""
    try:
        with console.status("[bold green]正在初始化数据库..."):
            from scripts.init_database import init_database
            init_database()
        
        console.print(Panel(
            "✓ 数据库表初始化完成",
            title="成功",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(Panel(
            f"✗ 数据库初始化失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


@migrate_app.command("revision")
def migrate_revision(
    message: str = typer.Option(
        ..., "--message", "-m",
        help="迁移脚本描述信息"
    ),
    autogenerate: bool = typer.Option(
        True, "--autogenerate/--no-autogenerate",
        help="是否自动生成迁移脚本"
    ),
):
    """生成新的数据库迁移脚本"""
    try:
        from alembic.config import Config
        from alembic import command
        
        with console.status("[bold green]正在生成迁移脚本..."):
            alembic_cfg = Config("alembic.ini")
            command.revision(
                alembic_cfg,
                message=message,
                autogenerate=autogenerate
            )
        
        console.print(Panel(
            f"✓ 迁移脚本已生成: {message}",
            title="成功",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(Panel(
            f"✗ 生成迁移脚本失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


@migrate_app.command("upgrade")
def migrate_upgrade(
    revision: str = typer.Option(
        "head", "--revision", "-r",
        help="目标版本，默认为最新版本(head)"
    ),
):
    """执行数据库迁移升级"""
    try:
        from alembic.config import Config
        from alembic import command
        
        with console.status(f"[bold green]正在升级到版本: {revision}..."):
            alembic_cfg = Config("alembic.ini")
            command.upgrade(alembic_cfg, revision)
        
        console.print(Panel(
            f"✓ 数据库已升级到版本: {revision}",
            title="成功",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(Panel(
            f"✗ 数据库升级失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


@migrate_app.command("downgrade")
def migrate_downgrade(
    revision: str = typer.Option(
        ..., "--revision", "-r",
        help="目标版本，使用-1表示回滚一个版本"
    ),
):
    """执行数据库迁移回滚"""
    try:
        from alembic.config import Config
        from alembic import command
        
        with console.status(f"[bold green]正在回滚到版本: {revision}..."):
            alembic_cfg = Config("alembic.ini")
            command.downgrade(alembic_cfg, revision)
        
        console.print(Panel(
            f"✓ 数据库已回滚到版本: {revision}",
            title="成功",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(Panel(
            f"✗ 数据库回滚失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


@migrate_app.command("history")
def migrate_history(
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="显示详细信息"
    ),
):
    """查看数据库迁移历史"""
    try:
        from alembic.config import Config
        from alembic import command
        
        alembic_cfg = Config("alembic.ini")
        
        # 获取历史记录
        console.print("[bold cyan]迁移历史:[/bold cyan]")
        command.history(alembic_cfg, verbose=verbose)
        
    except Exception as e:
        console.print(Panel(
            f"✗ 获取迁移历史失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


@migrate_app.command("current")
def migrate_current():
    """查看当前数据库版本"""
    try:
        from alembic.config import Config
        from alembic import command
        
        alembic_cfg = Config("alembic.ini")
        
        console.print("[bold cyan]当前版本:[/bold cyan]")
        command.current(alembic_cfg)
        
    except Exception as e:
        console.print(Panel(
            f"✗ 获取当前版本失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


def _ensure_config_file():
    """确保配置文件存在，如果不存在则创建"""
    from utils.secret_key_manager import CONFIG_FILE, load_config, save_config, generate_secure_key, _set_nested_value, SECRET_KEY_PATH
    
    if not CONFIG_FILE.exists():
        console.print(f"[yellow]配置文件不存在，正在创建: {CONFIG_FILE}[/yellow]")
        # 创建空配置
        config = {}
        save_config(config)
        console.print(f"[green]✓ 配置文件已创建[/green]")
        return True
    return False


def _ensure_secret_key():
    """确保 secret_key 存在，如果不存在则生成"""
    from utils.secret_key_manager import (
        get_secret_key_from_config, generate_and_save_secret_key,
        is_secret_key_configured
    )
    
    if not is_secret_key_configured():
        console.print("[yellow]secret_key 未配置，正在生成...[/yellow]")
        new_key = generate_and_save_secret_key()
        if new_key:
            console.print(f"[green]✓ secret_key 已生成并保存[/green]")
            return True
        else:
            console.print("[red]✗ secret_key 生成失败[/red]")
            return False
    else:
        console.print("[green]✓ secret_key 已配置[/green]")
        return True


@app.command()
def setup(
    config_file: Optional[str] = typer.Option(
        None, "--config", "-f",
        help="配置文件路径，用于导入初始配置"
    ),
    skip_config_import: bool = typer.Option(
        False, "--skip-config-import",
        help="跳过配置导入步骤"
    ),
    skip_data_seed: bool = typer.Option(
        False, "--skip-data-seed",
        help="跳过初始数据填充步骤"
    ),
    migrate_revision: str = typer.Option(
        "head", "--migrate-revision",
        help="数据库迁移目标版本"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="显示详细执行信息"
    ),
):
    """一键初始化项目环境
    
    执行完整的初始化流程：环境检查 -> 配置文件检查 -> 密钥生成 -> 配置导入 -> 数据库初始化 -> 迁移 -> 数据填充 -> 验证
    """
    try:
        console.print(Panel(
            "开始项目环境初始化...",
            title="QuantCell Setup",
            border_style="blue"
        ))
        
        # 步骤1: 确保配置文件存在
        console.print("\n[bold cyan]步骤 1/8: 检查配置文件...[/bold cyan]")
        _ensure_config_file()
        
        # 步骤2: 确保 secret_key 存在
        console.print("\n[bold cyan]步骤 2/8: 检查 JWT 密钥...[/bold cyan]")
        _ensure_secret_key()
        
        # 执行初始化
        results = setup_project(
            config_path=config_file,
            skip_config_import=skip_config_import,
            skip_data_seed=skip_data_seed,
            migrate_revision=migrate_revision,
            verbose=verbose
        )
        
        # 显示结果
        if results["success"]:
            console.print(Panel(
                f"✓ 项目环境初始化完成\n"
                f"总耗时: {results['duration_seconds']:.2f}秒",
                title="成功",
                border_style="green"
            ))
        else:
            console.print(Panel(
                f"✗ 项目环境初始化失败\n"
                f"总耗时: {results['duration_seconds']:.2f}秒\n"
                f"请查看日志了解详情",
                title="失败",
                border_style="red"
            ))
            raise typer.Exit(1)
        
    except Exception as e:
        console.print(Panel(
            f"✗ 初始化异常: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


@app.command()
def check(
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="显示详细信息"
    ),
):
    """检查项目环境依赖"""
    try:
        with console.status("[bold green]正在检查环境..."):
            results = EnvChecker.check_all()
        
        # Python版本
        python_status = "✓" if results["python"]["ok"] else "✗"
        python_color = "green" if results["python"]["ok"] else "red"
        console.print(f"[{python_color}]{python_status}[/{python_color}] Python: {results['python']['info']}")
        
        # 依赖包
        console.print("\n[bold]依赖包:[/bold]")
        console.print("  [bold]必需包:[/bold]")
        for name, info in results["packages"]["required"].items():
            status = "✓" if info["installed"] else "✗"
            color = "green" if info["installed"] else "red"
            version = f" ({info['version']})" if info["version"] else ""
            console.print(f"    [{color}]{status}[/{color}] {name}{version}")
        
        console.print("  [bold]可选包:[/bold]")
        for name, info in results["packages"]["optional"].items():
            status = "✓" if info["installed"] else "○"
            color = "green" if info["installed"] else "yellow"
            version = f" ({info['version']})" if info["version"] else ""
            console.print(f"    [{color}]{status}[/{color}] {name}{version}")
        
        # 数据库
        db_status = "✓" if results["database"]["ok"] else "✗"
        db_color = "green" if results["database"]["ok"] else "red"
        console.print(f"\n[{db_color}]{db_status}[/{db_color}] 数据库: {results['database']['info']}")
        
        # 配置文件
        config_status = "✓" if results["config"]["ok"] else "○"
        config_color = "green" if results["config"]["ok"] else "yellow"
        console.print(f"[{config_color}]{config_status}[/{config_color}] 配置: {results['config']['info']}")
        
        # 总体状态
        console.print("\n" + "=" * 50)
        if results["overall"]:
            console.print("[bold green]✓ 环境检查通过，可以开始初始化[/bold green]")
        else:
            console.print("[bold red]✗ 环境检查未通过，请修复上述问题[/bold red]")
        
    except Exception as e:
        console.print(Panel(
            f"✗ 环境检查失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


@app.command()
def validate(
    file: str = typer.Option(
        ..., "--file", "-f",
        help="要验证的TOML配置文件路径"
    ),
):
    """验证TOML配置文件格式"""
    try:
        import toml
        
        with console.status("[bold green]正在验证配置文件..."):
            with open(file, 'r', encoding='utf-8') as f:
                data = toml.load(f)
        
        # 统计配置项
        def count_configs(d, prefix=""):
            count = 0
            for k, v in d.items():
                if k == "_meta":
                    continue
                if isinstance(v, dict):
                    count += count_configs(v, f"{prefix}{k}.")
                else:
                    count += 1
            return count
        
        config_count = count_configs(data)
        
        console.print(Panel(
            f"✓ 配置文件格式正确\n"
            f"配置项数量: {config_count}",
            title="验证通过",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(Panel(
            f"✗ 配置文件验证失败: {e}",
            title="错误",
            border_style="red"
        ))
        raise typer.Exit(1)


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version",
        help="显示版本信息",
        is_eager=True
    ),
):
    """QuantCell 系统配置管理与数据库初始化工具"""
    if version:
        console.print("QuantCell Setup Tool v1.0.0")
        raise typer.Exit()


if __name__ == "__main__":
    app()
