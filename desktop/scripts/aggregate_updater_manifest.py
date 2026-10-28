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


def _find_signed_artifact(platform_dir: Path, suffixes: list[str]) -> tuple[Path, Path] | None:
    """按后缀优先级找「产物 + 同名 .sig」，找不到返回 None"""
    for suffix in suffixes:
        for sig in sorted(platform_dir.rglob(f"*{suffix}.sig")):
            artifact = Path(str(sig)[: -len(".sig")])
            if artifact.is_file():
                return artifact, sig
    return None


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

    if mirror_base.strip():
        mirror_root = f"{mirror_base.strip().rstrip('/')}/{tag}"
        mirror_manifest = json.loads(json.dumps(base_manifest))
        for entry in mirror_manifest["platforms"].values():
            entry["url"] = entry["url"].replace(
                f"https://github.com/{REPO_SLUG}/releases/download/{tag}/",
                f"{mirror_root}/",
            )
        mirror_path = output_dir / "latest-mirror.json"
        mirror_path.write_text(
            json.dumps(mirror_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        typer.echo(f"[ok] 写出 {mirror_path}")


if __name__ == "__main__":
    app()
