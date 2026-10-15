"""一次性脚本：清理 strategies 表中可被证伪的测试垃圾数据。

背景：strategies 表里混入了测试产生的垃圾记录（裸 ``class X: pass``、引用已删除的
EventDrivenStrategy/nautilus 体系、带空格文件名等），需要甄别并归档。

判定逻辑（**双条件同时满足**才判定为垃圾，避免误删）：
  ① 加载失败：把 DB 的 ``code`` 字段当源码 exec，并复用 StrategyLoaderService 的
     类识别契约（``_find_strategy_class``）查找 BaseStrategy 子类；语法错误、
     执行/导入失败或找不到策略类，均视为加载失败。
  ② 基类非法：AST 扫描源码，若存在类定义的直接基类不在合法基类集合内
     （无显式基类的裸 ``class`` 等价于 object，同样命中），即命中。

判定不出的（能加载但基类合法、无源码、源码无法 AST 解析等）**一律不删**。

⚠️ 安全提示：为复用加载契约，本脚本会把 DB 的 ``code`` 字段当源码 ``exec()``，
因此**只应对可信的本地数据库运行**，不要对来源不明的库执行。

行为：默认 dry-run，仅打印拟删清单；``--apply`` 时不物理删表数据，而是把整行内容
落到 JSON 备份文件并打印汇总。重复执行分类结果一致（判定只读 DB，不改 DB）。

用法：
    .venv/bin/python -m tools.clean_strategy_dirty_data            # dry-run
    .venv/bin/python -m tools.clean_strategy_dirty_data --apply    # 备份（不删表）
"""

from __future__ import annotations

import ast
import json
import types
from datetime import UTC, datetime
from pathlib import Path

import typer

from backtest.strategy_loader_service import StrategyLoaderService
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

app = typer.Typer(help="清理 strategies 表中可被证伪的测试垃圾数据（默认 dry-run，--apply 仅备份）")

# 当前唯一的合法策略基类（策略契约见 strategy/base.py：on_bar -> Action）
LEGAL_BASE_CLASSES = {"BaseStrategy"}

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def _load_strategy_source(code: str, name: str):
    """按加载入口的契约尝试加载策略源码。

    复用 StrategyLoaderService 的类识别逻辑（load 的最终契约就是"能找到一个
    BaseStrategy 子类"），因此这里 exec 源码后直接用其 ``_find_strategy_class``。

    Returns:
        (策略类, None) 表示加载成功；(None, 失败原因) 表示加载失败。
    """
    module = types.ModuleType(f"dirty_check_{name}")
    try:
        compiled = compile(code, f"<strategy:{name}>", "exec")
    except SyntaxError as e:
        return None, f"语法错误: {e}"
    try:
        exec(compiled, module.__dict__)
    except Exception as e:
        return None, f"执行/导入失败: {type(e).__name__}: {e}"

    cls = StrategyLoaderService._find_strategy_class(module)
    if cls is None:
        return None, "未找到 BaseStrategy 子类"
    return cls, None


def _base_name(base: ast.expr) -> str | None:
    """取基类名：Name→id；Attribute→末段 attr（strategy.base.BaseStrategy → BaseStrategy）。"""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _has_illegal_base(code: str) -> bool | None:
    """AST 扫描：模块是否「不含任何合法策略基类」且存在非法基类的类定义。

    判定收窄，避免误伤含 helper/dataclass/Enum 的合法策略文件：
      - 只要模块内存在任一 ``class X(BaseStrategy)``（含 ``strategy.base.BaseStrategy``
        这类属性访问写法），即认为基类合法，返回 False；
      - 否则，若存在「无显式基类的裸类」或「基类名不在白名单」的类，返回 True。

    Returns:
        True/False 为判定结果；None 表示无法解析（交由调用方按"判定不出不删"处理）。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    if any(_base_name(base) in LEGAL_BASE_CLASSES for node in classes for base in node.bases):
        return False
    return any(
        (not node.bases) or any(_base_name(base) not in LEGAL_BASE_CLASSES for base in node.bases) for node in classes
    )


def _classify(code: str | None, name: str) -> tuple[bool, str | None]:
    """判定单条记录是否为可证伪的垃圾。返回 (是否垃圾, 证伪原因)。"""
    if not code or not code.strip():
        return False, None  # 无源码无法证伪 → 不删

    loaded_cls, load_err = _load_strategy_source(code, name)
    if loaded_cls is not None:
        return False, None  # 能正常加载 → 不删

    illegal = _has_illegal_base(code)
    if illegal is None or not illegal:
        return False, None  # 基类合法或无法解析 → 不删

    return True, load_err or "加载失败"


def _fetch_rows():
    """读取 strategies 全表；DB 不可用时返回 None（不抛出）。"""
    # DB 相关模块延迟导入：保证本机 DB 不可用或未初始化时，--help / import 仍不报错
    try:
        from strategy.models import Strategy
        from utils.db_session import get_db_session

        with get_db_session() as db:
            return db.query(Strategy).order_by(Strategy.id).all()
    except Exception as e:
        logger.error(f"读取 strategies 表失败: {e}")
        return None


@app.command()
def main(
    apply: bool = typer.Option(False, "--apply", help="把垃圾记录内容备份到 JSON（不删表数据）"),
) -> None:
    """扫描 strategies 表，输出可证伪的垃圾清单；--apply 时落盘备份。"""
    rows = _fetch_rows()
    if rows is None:
        typer.echo("数据库不可用：无法读取 strategies 表，已跳过（未做任何修改）。")
        raise typer.Exit(code=1)

    garbage: list[tuple[object, str]] = []
    for row in rows:
        is_junk, reason = _classify(row.code, row.name)
        if is_junk:
            garbage.append((row, reason or "加载失败"))

    if not garbage:
        typer.echo(f"扫描 {len(rows)} 条策略，未发现可证伪的垃圾数据。")
        logger.info(f"策略垃圾扫描完成: 扫描 {len(rows)} 条, 未命中垃圾")
        return

    typer.echo(f"扫描 {len(rows)} 条策略，判定为垃圾 {len(garbage)} 条：")
    for row, reason in garbage:
        loc = row.file_path or row.file_name or "-"
        typer.echo(f"  id={row.id} name={row.name!r} file={loc} 原因={reason}")

    if not apply:
        typer.echo("\n（dry-run，未做任何修改；加 --apply 可备份）")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out_file = OUTPUT_DIR / f"strategy_dirty_archive_{ts}.json"
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_scanned": len(rows),
        "dirty_count": len(garbage),
        "records": [
            {
                "id": row.id,
                "name": row.name,
                "file_path": row.file_path,
                "file_name": row.file_name,
                "reason": reason,
                "code": row.code,
            }
            for row, reason in garbage
        ],
    }
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"\n已备份 {len(garbage)} 条到 {out_file}（未删除表数据）")
    logger.info(f"策略垃圾数据备份完成: {out_file} ({len(garbage)} 条)")


if __name__ == "__main__":
    app()
