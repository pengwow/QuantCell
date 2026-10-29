"""聚合各平台 Tauri 更新产物，生成 updater manifest（latest.json / latest-mirror.json）。

用法：
    uv run --with typer python desktop/scripts/aggregate_updater_manifest.py \
        --version 0.2.0 --tag v0.2.0 \
        --input dist --output dist/manifest \
        --mirror-base https://mirror.example.com/quantcell

manifest 结构（Tauri updater v2）：
    {"version": ..., "notes": ..., "pub_date": ..., "platforms": {"<target>": {"signature": ..., "url": ...}}}

镜像版仅把 url 前缀换成 `<mirror-base>/<tag>/`，其余字段与官方版一致。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import typer

REPO_SLUG = "pengwow/QuantCell"

# target -> CI upload-artifact 的 name（download-artifact 不加 merge 时就是目录名）
DEFAULT_PLATFORMS = {
    "darwin-aarch64": "quantcell-desktop-macos-aarch64",
    "darwin-x86_64": "quantcell-desktop-macos-x86_64",
    "windows-x86_64": "quantcell-desktop-windows-x86_64",
    "linux-x86_64": "quantcell-desktop-linux-x86_64",
}

# target -> 候选产物后缀（按优先级）；签名文件固定为「产物同名 + .sig」
ARTIFACT_SUFFIXES = {
    "darwin-aarch64": [".app.tar.gz"],
    "darwin-x86_64": [".app.tar.gz"],
    "windows-x86_64": ["-setup.exe", ".msi"],
    "linux-x86_64": [".AppImage.tar.gz"],
}


# target -> 裸安装包 glob 模式（官网下载页直链；顺序即前端展示优先级，首个为主推格式）
BARE_FILE_PATTERNS = {
    "darwin-aarch64": ["*.dmg"],
    "darwin-x86_64": ["*.dmg"],
    "windows-x86_64": ["*-setup.exe", "*.msi"],
    "linux-x86_64": ["*.AppImage", "*.deb"],
}


def _find_signed_artifact(platform_dir: Path, suffixes: list[str]) -> tuple[Path, Path] | None:
    """按后缀优先级找「产物 + 同名 .sig」，找不到返回 None"""
    for suffix in suffixes:
        for sig in sorted(platform_dir.rglob(f"*{suffix}.sig")):
            artifact = Path(str(sig)[: -len(".sig")])
            if artifact.is_file():
                return artifact, sig
    return None


def _find_bare_artifacts(platform_dir: Path, patterns: list[str]) -> list[Path]:
    """按 glob 优先级收集裸安装包；升级包（*.app.tar.gz / *.AppImage.tar.gz）不会被这些模式命中"""
    found: list[Path] = []
    for pattern in patterns:
        for path in sorted(platform_dir.rglob(pattern)):
            if path.is_file() and path not in found:
                found.append(path)
    return found


app = typer.Typer(add_completion=False)


@app.command()
def main(
    version: str = typer.Option(..., help="语义版本号，如 0.2.0"),
    tag: str = typer.Option(..., help="git tag，如 v0.2.0"),
    input_dir: Path = typer.Option(..., "--input", help="各平台产物解压根目录"),
    output_dir: Path = typer.Option(..., "--output", help="manifest 输出目录"),
    notes: str = typer.Option("", help="更新说明，写入 manifest.notes"),
    mirror_base: str = typer.Option("", help="镜像基址；非空才生成 latest-mirror.json"),
) -> None:
    platforms: dict[str, dict] = {}
    missing: list[str] = []

    for target, dir_name in DEFAULT_PLATFORMS.items():
        platform_dir = input_dir / dir_name
        found = (
            _find_signed_artifact(platform_dir, ARTIFACT_SUFFIXES[target])
            if platform_dir.is_dir()
            else None
        )
        if found is None:
            missing.append(target)
            continue
        artifact, sig = found
        platforms[target] = {
            "signature": sig.read_text(encoding="utf-8").strip(),
            "url": f"https://github.com/{REPO_SLUG}/releases/download/{tag}/{artifact.name}",
        }
        typer.echo(f"[ok] {target}: {artifact.name}")

    if missing:
        typer.echo(f"[error] 缺少平台产物: {', '.join(missing)}", err=True)
        raise typer.Exit(code=1)

    # 裸安装包（官网下载页直链）：cargo bundle 与升级包同源产出，主推格式缺失按异常处理
    def _bare_url(name: str) -> str:
        if mirror_base.strip():
            return f"{mirror_base.strip().rstrip('/')}/{tag}/{name}"
        return f"https://github.com/{REPO_SLUG}/releases/download/{tag}/{name}"

    download_files: dict[str, list[dict]] = {}
    missing_bare: list[str] = []
    for target, dir_name in DEFAULT_PLATFORMS.items():
        platform_dir = input_dir / dir_name
        bare = (
            _find_bare_artifacts(platform_dir, BARE_FILE_PATTERNS[target])
            if platform_dir.is_dir()
            else []
        )
        if not bare:
            missing_bare.append(target)
            continue
        download_files[target] = [
            {
                "kind": path.suffix.lower().lstrip("."),
                "file": path.name,
                "size": path.stat().st_size,
                "url": _bare_url(path.name),
            }
            for path in bare
        ]
        typer.echo(f"[ok] bare {target}: {[p.name for p in bare]}")

    if missing_bare:
        typer.echo(f"[error] 缺少裸安装包: {', '.join(missing_bare)}", err=True)
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)
    base_manifest = {
        "version": version,
        "notes": notes,
        "pub_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": platforms,
    }
    official_path = output_dir / "latest.json"
    official_path.write_text(
        json.dumps(base_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    typer.echo(f"[ok] 写出 {official_path}")

    # latest-mirror.json 始终写出：release job 的 rsync 同步与首次 bootstrap 都直接
    # 从 Release 下载它，文件缺位会让发版流程依赖"配没配 Variables"这一隐式条件。
    # 未配置镜像基址时与官方版相同（URL 仍指 GitHub），客户端行为不受影响。
    if mirror_base.strip():
        mirror_root = f"{mirror_base.strip().rstrip('/')}/{tag}"
        mirror_manifest = json.loads(json.dumps(base_manifest))
        for entry in mirror_manifest["platforms"].values():
            entry["url"] = entry["url"].replace(
                f"https://github.com/{REPO_SLUG}/releases/download/{tag}/",
                f"{mirror_root}/",
            )
    else:
        mirror_manifest = base_manifest
    mirror_path = output_dir / "latest-mirror.json"
    mirror_path.write_text(
        json.dumps(mirror_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    typer.echo(f"[ok] 写出 {mirror_path}")

    # 官网下载页数据源：镜像基址已配置时 URL 直接指向自有域名（与 rsync 到镜像站的
    # 布局对齐），未配置时指 GitHub Release。网页 fetch 失败时自行兜底到 GitHub。
    downloads_manifest = {
        "version": version,
        "tag": tag,
        "pub_date": base_manifest["pub_date"],
        "downloads": download_files,
    }
    downloads_path = output_dir / "latest-downloads.json"
    downloads_path.write_text(
        json.dumps(downloads_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    typer.echo(f"[ok] 写出 {downloads_path}")


if __name__ == "__main__":
    app()
