#!/usr/bin/env python3
"""
Web 服务管理和网页工具命令行

功能:
  - 服务管理: start/stop/status/restart 管理 FastAPI 服务
  - 网页工具: search/fetch 网页搜索和内容抓取
"""
from __future__ import annotations

import os
import sys
import json
import html
import re
import signal
import time
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import typer
from typing_extensions import Annotated

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

app = typer.Typer(
    name="web",
    help="Web 服务管理和网页工具",
    add_completion=False,
    no_args_is_help=True,
)

# 网页工具子命令
tools_app = typer.Typer(help="网页搜索/抓取工具")
app.add_typer(tools_app, name="tools")

# 常量
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PID_FILE = _BACKEND_DIR / "logs" / "web_server.pid"
_LOG_FILE = _BACKEND_DIR / "logs" / "web_server.log"
_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = 8000

# 网页工具常量
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5


# ==================== 服务管理命令 ====================

def _ensure_log_dir() -> None:
    """确保日志目录存在"""
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)


def _read_pid() -> Optional[int]:
    """读取 PID 文件"""
    try:
        if _PID_FILE.exists():
            return int(_PID_FILE.read_text().strip())
    except (ValueError, OSError):
        pass
    return None


def _write_pid(pid: int) -> None:
    """写入 PID 文件"""
    _ensure_log_dir()
    _PID_FILE.write_text(str(pid))


def _delete_pid() -> None:
    """删除 PID 文件"""
    try:
        if _PID_FILE.exists():
            _PID_FILE.unlink()
    except OSError:
        pass


def _is_running(pid: int) -> bool:
    """检查进程是否在运行"""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _get_server_status() -> tuple[bool, Optional[int]]:
    """获取服务器状态 (是否运行, PID)"""
    pid = _read_pid()
    if pid is None:
        return False, None
    if _is_running(pid):
        return True, pid
    _delete_pid()
    return False, None


def _wait_for_server(host: str, port: int, timeout: int = 30) -> bool:
    """等待服务器启动"""
    url = f"http://{host}:{port}/health"
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code < 500:
                return True
        except httpx.ConnectError:
            pass
        time.sleep(0.5)
    return False


@app.command("start")
def start_cmd(
    host: Annotated[str, typer.Option("--host", "-h", help="监听地址")] = _DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", "-p", help="监听端口")] = _DEFAULT_PORT,
    reload: Annotated[bool, typer.Option("--reload/--no-reload", help="开发模式自动重载")] = False,
    daemon: Annotated[bool, typer.Option("--daemon/--no-daemon", "-d", help="后台运行")] = True,
    wait: Annotated[int, typer.Option("--wait", help="等待启动超时(秒)")] = 30,
):
    """启动 Web API 服务"""
    running, pid = _get_server_status()
    if running:
        typer.echo(f"⚠️  服务已在运行 (PID: {pid})")
        raise typer.Exit(0)

    _ensure_log_dir()

    # 构建 uvicorn 命令
    cmd = [
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", host,
        "--port", str(port),
    ]
    if reload:
        cmd.append("--reload")
        daemon = False  # reload 模式不支持后台运行

    typer.echo(f"🚀 启动 QuantCell Web 服务...")
    typer.echo(f"   地址: http://{host}:{port}")
    typer.echo(f"   模式: {'开发(reload)' if reload else '生产'}")

    if daemon:
        # 后台运行
        log_fd = open(_LOG_FILE, "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=str(_BACKEND_DIR),
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        _write_pid(proc.pid)
        typer.echo(f"   PID: {proc.pid}")
        typer.echo(f"   日志: {_LOG_FILE}")

        if wait > 0:
            typer.echo(f"   等待服务就绪...", nl=False)
            if _wait_for_server("localhost", port, wait):
                typer.echo(" ✅")
            else:
                typer.echo(" ⚠️")
                typer.echo(f"   提示: 查看日志: tail -f {_LOG_FILE}")
    else:
        # 前台运行
        typer.echo(f"   按 Ctrl+C 停止服务\n")
        try:
            proc = subprocess.Popen(cmd, cwd=str(_BACKEND_DIR))
            proc.wait()
        except KeyboardInterrupt:
            typer.echo("\n⏹️  服务已停止")
        finally:
            _delete_pid()


@app.command("stop")
def stop_cmd(
    force: Annotated[bool, typer.Option("--force", "-f", help="强制终止(SIGKILL)")] = False,
    timeout: Annotated[int, typer.Option("--timeout", help="优雅关闭超时(秒)")] = 10,
):
    """停止 Web API 服务"""
    running, pid = _get_server_status()
    if not running:
        typer.echo("ℹ️  服务未运行")
        return

    typer.echo(f"⏹️  停止服务 (PID: {pid})...")

    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.kill(pid, sig)
    except OSError as e:
        typer.echo(f"❌ 发送信号失败: {e}")
        _delete_pid()
        raise typer.Exit(1)

    # 等待进程退出
    start = time.time()
    while time.time() - start < timeout:
        if not _is_running(pid):
            break
        time.sleep(0.5)
    else:
        if not force:
            typer.echo("⚠️  优雅关闭超时，强制终止...")
            try:
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
            except OSError:
                pass

    _delete_pid()
    typer.echo("✅ 服务已停止")


@app.command("restart")
def restart_cmd(
    host: Annotated[str, typer.Option("--host", "-h", help="监听地址")] = _DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", "-p", help="监听端口")] = _DEFAULT_PORT,
):
    """重启 Web API 服务"""
    # 先停止
    running, _ = _get_server_status()
    if running:
        stop_cmd(force=False, timeout=10)
        time.sleep(1)

    # 再启动
    start_cmd(host=host, port=port, daemon=True, wait=30)


@app.command("status")
def status_cmd(
    json_output: Annotated[bool, typer.Option("--json", help="JSON 格式输出")] = False,
):
    """查看 Web 服务状态"""
    running, pid = _get_server_status()

    status_info = {
        "running": running,
        "pid": pid,
        "host": _DEFAULT_HOST,
        "port": _DEFAULT_PORT,
        "url": f"http://localhost:{_DEFAULT_PORT}",
        "log_file": str(_LOG_FILE),
        "pid_file": str(_PID_FILE),
    }

    # 尝试获取健康状态
    if running:
        try:
            r = httpx.get(f"http://localhost:{_DEFAULT_PORT}/health", timeout=3.0)
            status_info["health_status"] = r.status_code
            try:
                status_info["health"] = r.json()
            except Exception:
                status_info["health"] = r.text[:100]
        except Exception as e:
            status_info["health_error"] = str(e)

    if json_output:
        typer.echo(json.dumps(status_info, indent=2, ensure_ascii=False))
        return

    if running:
        typer.echo(f"🟢 服务运行中")
        typer.echo(f"   PID:     {pid}")
        typer.echo(f"   地址:    http://localhost:{_DEFAULT_PORT}")
        typer.echo(f"   日志:    {_LOG_FILE}")
        if "health_status" in status_info:
            health_icon = "✅" if status_info["health_status"] == 200 else "⚠️"
            typer.echo(f"   健康:    {health_icon} HTTP {status_info['health_status']}")
    else:
        typer.echo(f"⚪ 服务未运行")
        typer.echo(f"   启动:    quantcell web start")


@app.command("logs")
def logs_cmd(
    follow: Annotated[bool, typer.Option("--follow", "-f", help="实时跟踪日志")] = False,
    lines: Annotated[int, typer.Option("--lines", "-n", help="显示最后 N 行")] = 50,
):
    """查看服务日志"""
    if not _LOG_FILE.exists():
        typer.echo("ℹ️  日志文件不存在")
        return

    if follow:
        typer.echo(f"📋 跟踪日志 (Ctrl+C 退出): {_LOG_FILE}\n")
        try:
            # 先显示最后 N 行
            with open(_LOG_FILE, "r", encoding="utf-8") as f:
                log_lines = f.readlines()
                for line in log_lines[-lines:]:
                    typer.echo(line, end="")
            # 然后跟踪
            with open(_LOG_FILE, "r", encoding="utf-8") as f:
                f.seek(0, 2)  # 移到末尾
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    typer.echo(line, end="")
        except KeyboardInterrupt:
            typer.echo("\n")
    else:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            log_lines = f.readlines()
            for line in log_lines[-lines:]:
                typer.echo(line, end="")


# ==================== 网页工具函数 ====================

def _strip_tags(text: str) -> str:
    """移除 HTML 标签并解码实体"""
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """规范化空白字符"""
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """验证 URL"""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"只允许 http/https，得到 '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "缺少域名"
        return True, ""
    except Exception as e:
        return False, str(e)


def web_search(
    query: str,
    count: int = 5,
    api_key: Optional[str] = None,
    proxy: Optional[str] = None,
) -> str:
    """使用 Brave Search API 搜索网页"""
    key = api_key or os.environ.get("BRAVE_API_KEY", "")
    if not key:
        return "错误: Brave Search API key 未配置。请在环境变量中设置 BRAVE_API_KEY。"

    try:
        n = min(max(count, 1), 10)
        proxy_url = proxy or os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")

        client_kwargs = {"timeout": 10.0}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        with httpx.Client(**client_kwargs) as client:
            r = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": n},
                headers={"Accept": "application/json", "X-Subscription-Token": key},
            )
            r.raise_for_status()

        results = r.json().get("web", {}).get("results", [])[:n]
        if not results:
            return f"未找到结果: {query}"

        lines = [f"搜索结果: {query}\n"]
        for i, item in enumerate(results, 1):
            lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
            if desc := item.get("description"):
                lines.append(f"   {desc}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return f"错误: {e}"


def web_fetch(
    url: str,
    max_chars: int = 50000,
    proxy: Optional[str] = None,
) -> str:
    """获取 URL 并提取可读内容"""
    is_valid, error_msg = _validate_url(url)
    if not is_valid:
        return json.dumps({"error": f"URL 验证失败: {error_msg}", "url": url}, ensure_ascii=False)

    try:
        proxy_url = proxy or os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")

        client_kwargs = {
            "follow_redirects": True,
            "max_redirects": MAX_REDIRECTS,
            "timeout": 30.0,
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        with httpx.Client(**client_kwargs) as client:
            r = client.get(url, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()

        ctype = r.headers.get("content-type", "")

        if "application/json" in ctype:
            text, extractor = json.dumps(r.json(), indent=2, ensure_ascii=False), "json"
        elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
            text = _normalize(_strip_tags(r.text))
            title_match = re.search(r"<title[^>]*>([^<]*)</title>", r.text, re.I)
            title = title_match.group(1).strip() if title_match else ""
            text = f"# {title}\n\n{text}" if title else text
            extractor = "html"
        else:
            text, extractor = r.text, "raw"

        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]

        return json.dumps({
            "url": url,
            "finalUrl": str(r.url),
            "status": r.status_code,
            "extractor": extractor,
            "truncated": truncated,
            "length": len(text),
            "text": text
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"获取网页失败: {e}")
        return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)


# ==================== 网页工具命令 ====================
# 同时在顶级和 tools 子命令下提供，保持向后兼容

def _search_cmd(
    query: str,
    count: int = 5,
    api_key: Optional[str] = None,
    proxy: Optional[str] = None,
):
    """搜索网页"""
    result = web_search(query, count, api_key, proxy)
    typer.echo(result)


def _fetch_cmd(
    url: str,
    max_chars: int = 50000,
    proxy: Optional[str] = None,
):
    """获取网页内容"""
    result = web_fetch(url, max_chars, proxy)
    typer.echo(result)


# tools 子命令下的版本
@tools_app.command("search")
def tools_search(
    query: Annotated[str, typer.Argument(help="搜索查询")],
    count: Annotated[int, typer.Option("--count", "-n", help="结果数量 (1-10)")] = 5,
    api_key: Annotated[Optional[str], typer.Option("--api-key", "-k", help="Brave Search API密钥")] = None,
    proxy: Annotated[Optional[str], typer.Option("--proxy", "-p", help="代理地址")] = None,
):
    """搜索网页"""
    _search_cmd(query, count, api_key, proxy)


@tools_app.command("fetch")
def tools_fetch(
    url: Annotated[str, typer.Argument(help="要获取的 URL")],
    max_chars: Annotated[int, typer.Option("--max-chars", help="最大提取字符数")] = 50000,
    proxy: Annotated[Optional[str], typer.Option("--proxy", "-p", help="代理地址")] = None,
):
    """获取网页内容"""
    _fetch_cmd(url, max_chars, proxy)


# 顶级命令（向后兼容旧的 web_cli.py）
@app.command("search", help="搜索网页")
def cli_search(
    query: Annotated[str, typer.Argument(help="搜索查询")],
    count: Annotated[int, typer.Option("--count", "-n", help="结果数量 (1-10)")] = 5,
    api_key: Annotated[Optional[str], typer.Option("--api-key", "-k", help="Brave Search API密钥")] = None,
    proxy: Annotated[Optional[str], typer.Option("--proxy", "-p", help="代理地址")] = None,
):
    """搜索网页"""
    _search_cmd(query, count, api_key, proxy)


@app.command("fetch", help="获取网页内容")
def cli_fetch(
    url: Annotated[str, typer.Argument(help="要获取的 URL")],
    max_chars: Annotated[int, typer.Option("--max-chars", help="最大提取字符数")] = 50000,
    proxy: Annotated[Optional[str], typer.Option("--proxy", "-p", help="代理地址")] = None,
):
    """获取网页内容"""
    _fetch_cmd(url, max_chars, proxy)


if __name__ == "__main__":
    app()
