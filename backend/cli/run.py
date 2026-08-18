#!/usr/bin/env python3
"""
QuantCell 测试运行 CLI

运行项目的各种测试套件，支持单元测试、集成测试、API测试、覆盖率报告等。
"""

import subprocess
from pathlib import Path

import typer

app = typer.Typer(
    name="run_tests",
    help="QuantCell 测试运行脚本",
    add_completion=False,
)


def get_project_root() -> Path:
    """获取项目根目录(backend目录)"""
    return Path(__file__).resolve().parent.parent


def run_command(cmd: list, verbose: bool = False) -> int:
    """运行命令并返回退出码，异常时返回1"""
    if verbose:
        typer.echo(f"执行命令: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=get_project_root(),
            capture_output=not verbose,
            text=True,
            check=False,
        )

        if not verbose and result.returncode != 0:
            typer.echo(f"错误输出:\n{result.stderr}", err=True)

        return result.returncode
    except Exception as e:
        typer.echo(f"运行命令时出错: {e}", err=True)
        return 1


def run_all_tests(verbose: bool = False, parallel: bool = False) -> int:
    """运行所有测试，parallel时加 -n auto"""
    cmd = ["uv", "run", "pytest"]

    if verbose:
        cmd.append("-v")

    if parallel:
        cmd.extend(["-n", "auto"])

    typer.echo("=" * 60)
    typer.echo("运行所有测试...")
    typer.echo("=" * 60)

    return run_command(cmd, verbose)


def run_unit_tests(verbose: bool = False) -> int:
    """运行单元测试"""
    cmd = ["uv", "run", "pytest", "tests/unit"]

    if verbose:
        cmd.append("-v")

    typer.echo("=" * 60)
    typer.echo("运行单元测试...")
    typer.echo("=" * 60)

    return run_command(cmd, verbose)


def run_integration_tests(verbose: bool = False, parallel: bool = False) -> int:
    """运行集成测试"""
    cmd = ["uv", "run", "pytest", "tests/integration", "-m", "integration"]

    if verbose:
        cmd.append("-v")

    if parallel:
        cmd.extend(["-n", "auto"])

    typer.echo("=" * 60)
    typer.echo("运行集成测试...")
    typer.echo("=" * 60)

    return run_command(cmd, verbose)


def run_api_tests(verbose: bool = False) -> int:
    """运行API测试"""
    cmd = ["uv", "run", "pytest", "tests/integration/api", "-m", "api"]

    if verbose:
        cmd.append("-v")

    typer.echo("=" * 60)
    typer.echo("运行API测试...")
    typer.echo("=" * 60)

    return run_command(cmd, verbose)


def run_coverage_report(verbose: bool = False) -> int:
    """生成测试覆盖率报告"""
    cmd = [
        "uv",
        "run",
        "pytest",
        "--cov=.",
        "--cov-report=term-missing",
        "--cov-report=html",
        "--cov-fail-under=90",
    ]

    if verbose:
        cmd.append("-v")

    typer.echo("=" * 60)
    typer.echo("生成测试覆盖率报告...")
    typer.echo("=" * 60)

    exit_code = run_command(cmd, verbose)

    if exit_code == 0:
        typer.echo("\n" + "=" * 60)
        typer.echo("覆盖率报告已生成: htmlcov/index.html")
        typer.echo("=" * 60)

    return exit_code


def run_specific_test(test_path: str, verbose: bool = False) -> int:
    """运行特定测试文件"""
    cmd = ["uv", "run", "pytest", test_path]

    if verbose:
        cmd.append("-v")

    typer.echo("=" * 60)
    typer.echo(f"运行测试: {test_path}")
    typer.echo("=" * 60)

    return run_command(cmd, verbose)


@app.command()
def main(
    unit: bool = typer.Option(False, "--unit", help="仅运行单元测试"),
    integration: bool = typer.Option(False, "--integration", help="仅运行集成测试"),
    api: bool = typer.Option(False, "--api", help="仅运行API测试"),
    coverage: bool = typer.Option(False, "--coverage", help="生成测试覆盖率报告"),
    parallel: bool = typer.Option(False, "--parallel", help="并行运行测试"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="显示详细输出"),
    test_path: str | None = typer.Argument(None, help="指定测试文件或目录路径"),
):
    """QuantCell 测试运行脚本"""
    project_root = get_project_root()
    if not (project_root / "pyproject.toml").exists():
        typer.echo("未找到 pyproject.toml", err=True)
        raise typer.Exit(1)

    exit_code = 0
    if coverage:
        exit_code = run_coverage_report(verbose)
    elif unit:
        exit_code = run_unit_tests(verbose)
    elif integration:
        exit_code = run_integration_tests(verbose, parallel)
    elif api:
        exit_code = run_api_tests(verbose)
    elif test_path:
        exit_code = run_specific_test(test_path, verbose)
    else:
        exit_code = run_all_tests(verbose, parallel)

    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
