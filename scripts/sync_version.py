"""版本号单源化工具

根目录 VERSION 是全仓版本的唯一事实源，其余 4 处静态声明全部由本工具同步：

    frontend/package.json               "version"
    desktop/src-tauri/tauri.conf.json   "version"
    desktop/src-tauri/Cargo.toml        [package] version
    backend/pyproject.toml              [project] version

backend/config/settings.py 的 app_version default="dev" 是运行时兜底（桌面端经
QUANTCELL_VERSION 环境变量注入真实版本），不随版本升级改写，只在体检时确认仍是 dev。

用法（通常经 make version 调用，避免直接记忆这段命令）：
    python scripts/sync_version.py              # 体检：各声明与 VERSION 一致则全 ✓，否则 exit 1
    python scripts/sync_version.py --set 0.0.1  # 落位：写 VERSION + 4 处声明 + 刷新两个锁文件
    python scripts/sync_version.py --set patch  # 递增：patch / minor / major（基于当前 VERSION）
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import typer

# 仓库根目录（scripts/ 的上一级），与运行时 cwd 无关
ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"

# 4 处静态版本声明
PYPROJECT = ROOT / "backend" / "pyproject.toml"
DESKTOP_CARGO_TOML = ROOT / "desktop" / "src-tauri" / "Cargo.toml"
DESKTOP_TAURI_CONF = ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
FRONTEND_PACKAGE_JSON = ROOT / "frontend" / "package.json"
# settings.py 特殊项：体检确认 default 仍是 dev，不参与落位
SETTINGS_FILE = ROOT / "backend" / "config" / "settings.py"

# 只匹配「行首的 version = "..."」：Cargo.toml 的行内表（tauri = { version = "2" }）与
# version.workspace = true 都不是行首引号等号形态，天然不受影响。
# ponytail: re.sub(count=1) 的天花板——依赖「每个 toml 文件首个行首 version 即包版本」
# 这一已盘点事实（3 个 toml 均满足）；未来出现多变 toml 结构时升级为 tomlkit 按表精确写入。
REPLACE_VERSION_RE = re.compile(r'^version\s*=\s*"(?P<v>[^"]*)"', re.M)

# settings.py 的 default 藏在多行 Field(...) 里，需跨行松匹配（200 字符窗口覆盖当前注释密度）
SETTINGS_DEFAULT_RE = re.compile(r'app_version[\s\S]{0,200}?default="([^"]*)"')

# Cargo.toml 的包名（cargo update -p 需要精确包名）
CRATE_NAME_RE = re.compile(r'^name\s*=\s*"([^"]+)"', re.M)

# 严格三段数字 semver，不带 prerelease / build 后缀
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


# ---------------- 读取 ----------------

def read_toml_version(path: Path) -> str | None:
    m = REPLACE_VERSION_RE.search(path.read_text(encoding="utf-8"))
    return m.group("v") if m else None


def read_json_version(path: Path) -> str | None:
    return json.loads(path.read_text(encoding="utf-8")).get("version")


def read_current_version() -> str | None:
    """读 VERSION 当前值；文件缺失返回 None"""
    if not VERSION_FILE.exists():
        return None
    value = VERSION_FILE.read_text(encoding="utf-8").strip()
    return value or None


def read_crate_name(path: Path) -> str:
    m = CRATE_NAME_RE.search(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path.name} 缺少 [package] name")
    return m.group(1)


# ---------------- 写入 ----------------

def render_json(data: dict) -> str:
    """统一 JSON 落盘格式：保留键序 + 中文不转义 + 2 空格缩进 + 尾换行"""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def set_json_version(path: Path, version: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = version
    path.write_text(render_json(data), encoding="utf-8")


def replace_toml_version(text: str, version: str) -> str:
    """替换首个行首 version = "..." 声明；行内表 / version.workspace 均不受影响（见正则处注释）"""
    new_text, n = REPLACE_VERSION_RE.subn(f'version = "{version}"', text, count=1)
    if n != 1:
        raise ValueError('未找到行首 version = "..." 声明，toml 结构可能已变化')
    return new_text


def bump_version(current: str, part: str) -> str:
    """递增语义：patch 末位+1（0.0.9→0.0.10）；minor 中位+1 末位归零；major 首位+1 余位归零"""
    major, minor, patch = (int(x) for x in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def resolve_target_version(current: str | None, raw: str) -> str:
    """解析落位目标：合法 semver 直接用；patch/minor/major 基于当前 VERSION 递增；其余拒绝"""
    value = raw.strip()
    if SEMVER_RE.fullmatch(value):
        return value
    if value in ("patch", "minor", "major"):
        if current is None:
            raise ValueError("递增模式（patch/minor/major）需要先有 VERSION 文件提供当前版本")
        if not SEMVER_RE.fullmatch(current):
            raise ValueError(f"当前 VERSION ({current!r}) 不是合法 semver，无法递增")
        return bump_version(current, value)
    raise ValueError(f"无法识别的版本 {raw!r}，需为 x.y.z 或 patch/minor/major")


def _run_checked(cmd: list[str], cwd: Path) -> None:
    """跑外部命令；失败时把完整输出打到 stderr 并 exit 1，保证 CI / 人肉都能看见原因"""
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        typer.echo(f"✗ 命令失败：{' '.join(cmd)}（cwd={cwd}）", err=True)
        if proc.stdout:
            typer.echo(proc.stdout, err=True)
        if proc.stderr:
            typer.echo(proc.stderr, err=True)
        raise typer.Exit(code=1)


def write_all(target: str) -> None:
    """写 VERSION + 4 处静态声明，并刷新两把锁文件"""
    VERSION_FILE.write_text(target + "\n", encoding="utf-8")

    for toml_path in (PYPROJECT, DESKTOP_CARGO_TOML):
        toml_path.write_text(
            replace_toml_version(toml_path.read_text(encoding="utf-8"), target),
            encoding="utf-8",
        )
    set_json_version(FRONTEND_PACKAGE_JSON, target)
    set_json_version(DESKTOP_TAURI_CONF, target)

    # 锁文件必须跟着包版本走，否则后端 --frozen 装不上、桌面端 cargo 提示 lock 漂移
    _run_checked(["uv", "lock"], cwd=PYPROJECT.parent)
    _run_checked(["cargo", "update", "-p", read_crate_name(DESKTOP_CARGO_TOML)], cwd=DESKTOP_CARGO_TOML.parent)


# ---------------- 体检 ----------------

def run_check() -> tuple[list[str], bool]:
    """逐条输出 "✓/✗ 相对路径 (当前值 vs 期望)"，返回（输出行, 是否全部通过）"""
    lines: list[str] = []
    ok_all = True

    def record(ok: bool, line: str) -> None:
        nonlocal ok_all
        ok_all = ok_all and ok
        lines.append(line)

    current = read_current_version()
    if current is None:
        ok_all = False
        expected_disp = "<VERSION 缺失>"
        lines.append("✗ VERSION (文件缺失)")
    elif not SEMVER_RE.fullmatch(current):
        ok_all = False
        expected_disp = "<VERSION 非法>"
        lines.append(f"✗ VERSION (非法 semver: {current})")
    else:
        expected_disp = current
        lines.append(f"✓ VERSION ({current})")

    # VERSION 合法才进一步比对 4 处静态声明
    version_valid = current is not None and SEMVER_RE.fullmatch(current) is not None
    declared: list[tuple[str, str | None]] = [
        ("frontend/package.json", read_json_version(FRONTEND_PACKAGE_JSON)),
        ("desktop/src-tauri/tauri.conf.json", read_json_version(DESKTOP_TAURI_CONF)),
        ("desktop/src-tauri/Cargo.toml", read_toml_version(DESKTOP_CARGO_TOML)),
        ("backend/pyproject.toml", read_toml_version(PYPROJECT)),
    ]
    for rel, actual in declared:
        ok = version_valid and actual == current
        record(
            ok,
            f"{'✓' if ok else '✗'} {rel} ({actual if actual is not None else '未找到'} vs {expected_disp})",
        )

    # settings.py 特殊项：default="dev" 是运行时兜底，不随 VERSION 比较，仍是 dev 即 ✓
    m = SETTINGS_DEFAULT_RE.search(SETTINGS_FILE.read_text(encoding="utf-8"))
    default_val = m.group(1) if m else None
    note = "" if default_val == "dev" else "；兜底值只允许 dev，请勿改成具体版本号"
    record(
        default_val == "dev",
        f"{'✓' if default_val == 'dev' else '✗'} backend/config/settings.py "
        f"({default_val if default_val else '未找到'} vs dev，运行时兜底不随 VERSION 比较){note}",
    )

    return lines, ok_all


# ---------------- CLI ----------------

def main(
    new_version: str | None = typer.Option(
        None,
        "--set",
        metavar="X.Y.Z|patch|minor|major",
        help="落位到指定版本（或基于当前 VERSION 递增）；缺省只做体检",
    ),
) -> None:
    """版本号单源化：无参为体检模式，--set 落位 VERSION + 4 处声明 + 两个锁文件"""
    if new_version is None:
        lines, ok_all = run_check()
        for line in lines:
            typer.echo(line)
        typer.echo("✓ 版本一致" if ok_all else "✗ 版本不一致，请运行 make version v=<X.Y.Z> 落位或手动修正")
        if not ok_all:
            raise typer.Exit(code=1)
        return

    try:
        target = resolve_target_version(read_current_version(), new_version)
    except ValueError as exc:
        typer.echo(f"✗ {exc}", err=True)
        raise typer.Exit(code=1) from None
    write_all(target)
    typer.echo(f"✓ 已落位 {target}：VERSION + 4 处声明已写入，uv.lock / Cargo.lock 已刷新")


if __name__ == "__main__":
    typer.run(main)
