"""深度网络诊断工具 - 排查 APITimeoutError 根本原因

注意：此文件为手动诊断脚本，依赖外部 OpenAI API 网络连接。
在自动化测试环境中跳过。
"""

import asyncio
import os
import socket
import time
from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.skip(reason="手动网络诊断工具，依赖外部 OpenAI API 连接")


def check_environment():
    """检查环境变量和代理设置"""

    # 检查关键环境变量
    env_vars = [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "DEFAULT_MODEL",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "NO_PROXY",
    ]

    for var in env_vars:
        value = os.environ.get(var, "")
        if var == "OPENAI_API_KEY":
            f"***{value[-4:]}" if len(value) > 4 else ("✅ 已设置" if value else "❌ 未设置")
        elif value:
            pass
        else:
            pass

    return {
        "api_key": bool(os.environ.get("OPENAI_API_KEY")),
        "base_url": os.environ.get("OPENAI_BASE_URL"),
        "has_proxy": any(os.environ.get(p) for p in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]),
    }


def test_dns_resolution():
    """测试 DNS 解析"""

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
    parsed = urlparse(base_url)
    host = parsed.hostname or "api.openai.com"

    try:
        start_time = time.time()
        ip_addresses = socket.getaddrinfo(host, None)
        time.time() - start_time

        seen_ips = set()
        for info in ip_addresses[:5]:  # 只显示前5个
            ip = info[4][0]
            if ip not in seen_ips:
                seen_ips.add(ip)
                "IPv6" if info[0] == socket.AF_INET6 else "IPv4"

        return True, list(seen_ips)[:3]  # 返回前3个IP

    except socket.gaierror:
        time.time() - start_time
        return False, []
    except Exception:
        return False, []


def test_tcp_connection(host, port, timeout=10):
    """测试 TCP 连接"""
    try:
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        elapsed = time.time() - start_time

        if result == 0:
            sock.close()
            return True, elapsed
        else:
            error_messages = {
                35: "SSL 握手失败",
                51: "网络不可达",
                60: "操作超时",
                61: "拒绝连接",
                111: "连接被拒绝",
                113: "没有路由到主机",
            }
            msg = error_messages.get(result, f"未知错误码: {result}")
            return False, (elapsed, result, msg)

    except TimeoutError:
        return False, (timeout, None, "连接超时")
    except Exception as e:
        return False, (0, None, str(e))


def test_multiple_ips(ips, port=443):
    """测试多个 IP 的连接性"""

    if not ips:
        return False

    results = []
    for ip in ips[:3]:  # 测试前3个IP
        success, info = test_tcp_connection(ip, port, timeout=10)

        if success:
            results.append((ip, True, info))
        else:
            if isinstance(info, tuple) and len(info) == 3:
                _elapsed, _code, msg = info
                results.append((ip, False, msg))
            else:
                results.append((ip, False, str(info)))

    successful = [r for r in results if r[1]]
    return len(successful) > 0


def test_ssl_handshake(host, port=443, timeout=15):
    """测试 SSL 握手"""

    try:
        import ssl

        start_time = time.time()
        context = ssl.create_default_context()

        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                time.time() - start_time

                cert = ssock.getpeercert()
                if cert:
                    subject = cert.get("subject", [((),)])
                    if subject:
                        dict(subject[0]).get("commonName", "N/A")

                    issuer = cert.get("issuer", [((),)])
                    if issuer:
                        dict(issuer[0]).get("organizationName", "N/A")

                    not_after = cert.get("notAfter", "")
                    if not_after:
                        pass

                return True

    except ssl.SSLError as e:
        time.time() - start_time
        if "certificate verify failed" in str(e):
            pass
        return False
    except TimeoutError:
        return False
    except Exception:
        time.time() - start_time
        return False


def test_http_request():
    """测试 HTTP 请求"""

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
    parsed = urlparse(base_url)
    host = parsed.hostname or "api.openai.com"

    try:
        import ssl
        import urllib.request

        url = f"{parsed.scheme}://{host}/models"

        ctx = ssl.create_default_context()

        start_time = time.time()

        # 如果有代理，使用代理
        proxy_handler = None
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if https_proxy:
            proxy_handler = urllib.request.ProxyHandler(
                {
                    "https": https_proxy,
                    "http": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
                }
            )

        if proxy_handler:
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}",
                "User-Agent": "Diagnostic-Tool/1.0",
            },
        )

        response = opener.open(req, timeout=30)
        time.time() - start_time

        data = response.read().decode("utf-8")

        # 尝试解析 JSON
        try:
            import json

            models = json.loads(data)
            if isinstance(models, dict) and "data" in models:
                model_count = len(models["data"])
                if model_count > 0:
                    models["data"][0].get("id", "unknown")
        except:
            pass

        return True

    except urllib.error.HTTPError as e:
        time.time() - start_time
        if e.code == 401 or e.code == 403 or e.code == 429:
            pass
        return False
    except urllib.error.URLError:
        time.time() - start_time
        return False
    except Exception:
        time.time() - start_time
        return False


async def test_openai_api_with_retry():
    """带重试的 OpenAI API 测试"""

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")

    if not api_key:
        return False

    from openai import AsyncOpenAI, Timeout

    max_retries = 3
    timeouts = [
        Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
        Timeout(connect=20.0, read=60.0, write=20.0, pool=10.0),
        Timeout(connect=30.0, read=120.0, write=30.0, pool=15.0),
    ]

    for attempt in range(max_retries):
        timeout_config = timeouts[min(attempt, len(timeouts) - 1)]

        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout_config,
            )

            start_time = time.time()
            await client.chat.completions.create(
                model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5,
            )

            time.time() - start_time
            return True

        except Exception:
            time.time() - start_time

            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                await asyncio.sleep(wait_time)

    return False


def generate_recommendations(env_info, dns_ok, ips, tcp_ok, ssl_ok, http_ok, api_ok):
    """生成修复建议"""

    issues = []
    recommendations = []

    # 检查各项结果
    if not dns_ok:
        issues.append("DNS 解析失败")
        recommendations.extend(
            [
                "1. 检查 DNS 配置：/etc/resolv.conf",
                "2. 尝试更换 DNS 服务器（如 8.8.8.8 或 114.114.114.114）",
                "3. 检查 /etc/hosts 文件是否有错误的条目",
                "4. 如果使用 VPN/代理，确保其正常运行",
            ]
        )

    if dns_ok and not tcp_ok and ips:
        issues.append("TCP 连接失败")
        recommendations.extend(
            [
                "1. 检查防火墙规则是否阻止了出站连接",
                "2. 确认端口 443 未被封禁",
                "3. 检查是否有本地代理软件需要配置",
                "4. 尝试使用 VPN 或代理服务",
            ]
        )

    if tcp_ok and not ssl_ok:
        issues.append("SSL 握手失败")
        recommendations.extend(
            [
                "1. 检查系统时间和日期是否正确",
                "2. 更新 CA 证书包",
                "3. 检查是否有中间人代理干扰 SSL",
                "4. 尝试禁用 SSL 验证（仅用于测试）",
            ]
        )

    if ssl_ok and not http_ok:
        issues.append("HTTP 请求失败")
        recommendations.extend(
            [
                "1. 验证 API Key 是否有效",
                "2. 检查账户余额和配额",
                "3. 确认 Base URL 正确",
                "4. 查看 API 服务状态页面",
            ]
        )

    if http_ok and not api_ok:
        issues.append("OpenAI SDK 调用失败")
        recommendations.extend(
            [
                "1. 更新 openai Python 包: pip install --upgrade openai",
                "2. 检查 SDK 版本兼容性",
                "3. 增加 timeout 参数值",
                "4. 启用详细日志查看具体错误",
            ]
        )

    if not env_info["api_key"]:
        issues.append("API Key 未配置")
        recommendations.insert(0, "⚠️  紧急：设置 OPENAI_API_KEY 环境变量")

    if not env_info["has_proxy"] and (not tcp_ok or not dns_ok):
        issues.append("可能需要代理")
        recommendations.append("考虑配置 HTTP/HTTPS 代理访问 OpenAI API")

    # 输出结果
    for _i, _issue in enumerate(issues, 1):
        pass

    if not issues and not api_ok:
        recommendations = [
            "1. 大幅增加 timeout（如 read=300s）",
            "2. 使用更稳定的网络环境",
            "3. 联系 API 提供商确认服务状态",
        ]

    for _rec in recommendations:
        pass

    # 输出快速修复命令示例


async def main():
    """主函数"""

    # 1. 环境检查
    env_info = check_environment()

    # 2. DNS 测试
    dns_ok, ips = test_dns_resolution()

    # 3. TCP 连接测试
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
    parsed = urlparse(base_url)
    host = parsed.hostname or "api.openai.com"
    port = parsed.port or 443

    tcp_ok = test_multiple_ips(ips, port) if ips else False

    # 4. SSL 测试（仅在 TCP 成功时）
    ssl_ok = test_ssl_handshake(host, port) if tcp_ok else False

    # 5. HTTP 测试
    http_ok = test_http_request()

    # 6. API 测试
    api_ok = await test_openai_api_with_retry()

    # 7. 生成报告
    generate_recommendations(env_info, dns_ok, ips, tcp_ok, ssl_ok, http_ok, api_ok)


if __name__ == "__main__":
    asyncio.run(main())
