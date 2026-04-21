"""深度网络诊断工具 - 排查 APITimeoutError 根本原因"""

import asyncio
import os
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlparse


def check_environment():
    """检查环境变量和代理设置"""
    print("\n" + "="*60)
    print("🔧 环境配置检查")
    print("="*60)
    
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
        "NO_PROXY"
    ]
    
    print("\n📌 环境变量:")
    for var in env_vars:
        value = os.environ.get(var, "")
        if var in ["OPENAI_API_KEY"]:
            display_value = f"***{value[-4:]}" if len(value) > 4 else ("✅ 已设置" if value else "❌ 未设置")
        elif value:
            display_value = value
        else:
            display_value = "❌ 未设置"
        
        status = "✅" if value else "⚠️"
        print(f"  {status} {var}: {display_value}")
    
    return {
        'api_key': bool(os.environ.get("OPENAI_API_KEY")),
        'base_url': os.environ.get("OPENAI_BASE_URL"),
        'has_proxy': any(os.environ.get(p) for p in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"])
    }


def test_dns_resolution():
    """测试 DNS 解析"""
    print("\n" + "="*60)
    print("🌐 DNS 解析测试")
    print("="*60)
    
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
    parsed = urlparse(base_url)
    host = parsed.hostname or "api.openai.com"
    
    print(f"\n目标域名: {host}")
    
    try:
        start_time = time.time()
        ip_addresses = socket.getaddrinfo(host, None)
        elapsed = time.time() - start_time
        
        print(f"✅ DNS 解析成功! 耗时: {elapsed:.3f}s")
        print(f"\n解析到的 IP 地址:")
        
        seen_ips = set()
        for info in ip_addresses[:5]:  # 只显示前5个
            ip = info[4][0]
            if ip not in seen_ips:
                seen_ips.add(ip)
                family = "IPv6" if info[0] == socket.AF_INET6 else "IPv4"
                print(f"  {family}: {ip}")
        
        return True, list(seen_ips)[:3]  # 返回前3个IP
        
    except socket.gaierror as e:
        elapsed = time.time() - start_time
        print(f"❌ DNS 解析失败: {e} (耗时: {elapsed:.3f}s)")
        return False, []
    except Exception as e:
        print(f"❌ DNS 解析异常: {type(e).__name__}: {e}")
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
            
    except socket.timeout:
        return False, (timeout, None, "连接超时")
    except Exception as e:
        return False, (0, None, str(e))


def test_multiple_ips(ips, port=443):
    """测试多个 IP 的连接性"""
    print("\n" + "="*60)
    print("🔗 多 IP 连接测试")
    print("="*60)
    
    if not ips:
        print("❌ 没有可用的 IP 地址")
        return False
    
    results = []
    for ip in ips[:3]:  # 测试前3个IP
        print(f"\n测试 IP: {ip}:{port}")
        success, info = test_tcp_connection(ip, port, timeout=10)
        
        if success:
            print(f"  ✅ 连接成功! 耗时: {info:.3f}s")
            results.append((ip, True, info))
        else:
            if isinstance(info, tuple) and len(info) == 3:
                elapsed, code, msg = info
                print(f"  ❌ 连接失败: {msg} (耗时: {elapsed:.3f}s)")
                results.append((ip, False, msg))
            else:
                print(f"  ❌ 连接失败: {info}")
                results.append((ip, False, str(info)))
    
    successful = [r for r in results if r[1]]
    return len(successful) > 0


def test_ssl_handshake(host, port=443, timeout=15):
    """测试 SSL 握手"""
    print("\n" + "="*60)
    print("🔒 SSL/TLS 握手测试")
    print("="*60)
    
    print(f"\n目标: {host}:{port}")
    
    try:
        import ssl
        
        start_time = time.time()
        context = ssl.create_default_context()
        
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                elapsed = time.time() - start_time
                
                print(f"✅ SSL 握手成功!")
                print(f"   耗时: {elapsed:.3f}s")
                print(f"   SSL 版本: {ssock.version()}")
                print(f"   加密套件: {ssock.cipher()[0] if ssock.cipher() else 'N/A'}")
                
                cert = ssock.getpeercert()
                if cert:
                    subject = cert.get('subject', [((),)])
                    if subject:
                        cn = dict(subject[0]).get('commonName', 'N/A')
                        print(f"   证书 CN: {cn}")
                    
                    issuer = cert.get('issuer', [((),)])
                    if issuer:
                        org = dict(issuer[0]).get('organizationName', 'N/A')
                        print(f"   颁发者: {org}")
                    
                    not_after = cert.get('notAfter', '')
                    if not_after:
                        print(f"   有效期至: {not_after}")
                
                return True
                
    except ssl.SSLError as e:
        elapsed = time.time() - start_time
        print(f"❌ SSL 错误: {e} (耗时: {elapsed:.3f}s)")
        if "certificate verify failed" in str(e):
            print("   💡 可能是证书验证问题或中间人攻击")
        return False
    except socket.timeout:
        print(f"❌ SSL 握手超时 (> {timeout}s)")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ SSL 握手失败: {type(e).__name__}: {e} (耗时: {elapsed:.3f}s)")
        return False


def test_http_request():
    """测试 HTTP 请求"""
    print("\n" + "="*60)
    print("📡 HTTP 层测试")
    print("="*60)
    
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
    parsed = urlparse(base_url)
    host = parsed.hostname or "api.openai.com"
    
    try:
        import urllib.request
        import ssl
        
        url = f"{parsed.scheme}://{host}/models"
        print(f"\n请求 URL: {url}")
        
        ctx = ssl.create_default_context()
        
        start_time = time.time()
        
        # 如果有代理，使用代理
        proxy_handler = None
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if https_proxy:
            print(f"使用代理: {https_proxy}")
            proxy_handler = urllib.request.ProxyHandler({
                'https': https_proxy,
                'http': os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
            })
        
        if proxy_handler:
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
        
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {os.environ.get("OPENAI_API_KEY", "")}',
            'User-Agent': 'Diagnostic-Tool/1.0'
        })
        
        response = opener.open(req, timeout=30)
        elapsed = time.time() - start_time
        
        data = response.read().decode('utf-8')
        print(f"✅ HTTP 请求成功!")
        print(f"   响应时间: {elapsed:.3f}s")
        print(f"   状态码: {response.status}")
        
        # 尝试解析 JSON
        try:
            import json
            models = json.loads(data)
            if isinstance(models, dict) and 'data' in models:
                model_count = len(models['data'])
                print(f"   可用模型数: {model_count}")
                if model_count > 0:
                    first_model = models['data'][0].get('id', 'unknown')
                    print(f"   第一个模型: {first_model}")
        except:
            pass
        
        return True
        
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_time
        print(f"❌ HTTP 错误: {e.code} - {e.reason} (耗时: {elapsed:.3f}s)")
        if e.code == 401:
            print("   💡 API Key 无效或已过期")
        elif e.code == 403:
            print("   💡 访问被拒绝，检查 IP 白名单或账户状态")
        elif e.code == 429:
            print("   💡 请求过于频繁或配额不足")
        return False
    except urllib.error.URLError as e:
        elapsed = time.time() - start_time
        print(f"❌ URL 错误: {e.reason} (耗时: {elapsed:.3f}s)")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 请求失败: {type(e).__name__}: {e} (耗时: {elapsed:.3f}s)")
        return False


async def test_openai_api_with_retry():
    """带重试的 OpenAI API 测试"""
    print("\n" + "="*60)
    print("🔄 OpenAI API 重试测试")
    print("="*60)
    
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")
    
    if not api_key:
        print("❌ OPENAI_API_KEY 未设置，跳过此测试")
        return False
    
    from openai import AsyncOpenAI, Timeout
    
    max_retries = 3
    timeouts = [
        Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
        Timeout(connect=20.0, read=60.0, write=20.0, pool=10.0),
        Timeout(connect=30.0, read=120.0, write=30.0, pool=15.0),
    ]
    
    for attempt in range(max_retries):
        timeout_config = timeouts[min(attempt, len(timeouts)-1)]
        print(f"\n尝试 {attempt + 1}/{max_retries} (timeout: connect={timeout_config.connect}s, read={timeout_config.read}s)")
        
        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout_config,
            )
            
            start_time = time.time()
            response = await client.chat.completions.create(
                model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5,
            )
            
            elapsed = time.time() - start_time
            print(f"✅ API 调用成功! 耗时: {elapsed:.2f}s")
            print(f"   响应: {response.choices[0].message.content}")
            return True
            
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ 失败: {type(e).__name__}: {e} (耗时: {elapsed:.2f}s)")
            
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"   ⏳ 等待 {wait_time}s 后重试...")
                await asyncio.sleep(wait_time)
    
    return False


def generate_recommendations(env_info, dns_ok, ips, tcp_ok, ssl_ok, http_ok, api_ok):
    """生成修复建议"""
    print("\n" + "="*60)
    print("💊 诊断结果与修复建议")
    print("="*60)
    
    issues = []
    recommendations = []
    
    # 检查各项结果
    if not dns_ok:
        issues.append("DNS 解析失败")
        recommendations.extend([
            "1. 检查 DNS 配置：/etc/resolv.conf",
            "2. 尝试更换 DNS 服务器（如 8.8.8.8 或 114.114.114.114）",
            "3. 检查 /etc/hosts 文件是否有错误的条目",
            "4. 如果使用 VPN/代理，确保其正常运行",
        ])
    
    if dns_ok and not tcp_ok and ips:
        issues.append("TCP 连接失败")
        recommendations.extend([
            "1. 检查防火墙规则是否阻止了出站连接",
            "2. 确认端口 443 未被封禁",
            "3. 检查是否有本地代理软件需要配置",
            "4. 尝试使用 VPN 或代理服务",
        ])
    
    if tcp_ok and not ssl_ok:
        issues.append("SSL 握手失败")
        recommendations.extend([
            "1. 检查系统时间和日期是否正确",
            "2. 更新 CA 证书包",
            "3. 检查是否有中间人代理干扰 SSL",
            "4. 尝试禁用 SSL 验证（仅用于测试）",
        ])
    
    if ssl_ok and not http_ok:
        issues.append("HTTP 请求失败")
        recommendations.extend([
            "1. 验证 API Key 是否有效",
            "2. 检查账户余额和配额",
            "3. 确认 Base URL 正确",
            "4. 查看 API 服务状态页面",
        ])
    
    if http_ok and not api_ok:
        issues.append("OpenAI SDK 调用失败")
        recommendations.extend([
            "1. 更新 openai Python 包: pip install --upgrade openai",
            "2. 检查 SDK 版本兼容性",
            "3. 增加 timeout 参数值",
            "4. 启用详细日志查看具体错误",
        ])
    
    if not env_info['api_key']:
        issues.append("API Key 未配置")
        recommendations.insert(0, "⚠️  紧急：设置 OPENAI_API_KEY 环境变量")
    
    if not env_info['has_proxy'] and (not tcp_ok or not dns_ok):
        issues.append("可能需要代理")
        recommendations.append("考虑配置 HTTP/HTTPS 代理访问 OpenAI API")
    
    # 输出结果
    print("\n发现的问题:")
    for i, issue in enumerate(issues, 1):
        print(f"  ❌ {i}. {issue}")
    
    if not issues:
        print("\n✨ 所有基础测试通过!")
        if not api_ok:
            print("⚠️  但 API 调用仍然失败，建议:")
            recommendations = [
                "1. 大幅增加 timeout（如 read=300s）",
                "2. 使用更稳定的网络环境",
                "3. 联系 API 提供商确认服务状态",
            ]
    
    print("\n📋 修复步骤:")
    for rec in recommendations:
        print(f"  {rec}")
    
    # 输出快速修复命令示例
    print("\n🚀 快速修复命令示例:")
    print("""
# 1. 设置环境变量（替换为你的实际值）
export OPENAI_API_KEY="sk-your-api-key-here"
export OPENAI_BASE_URL="https://api.openai.com/v1"  # 或你的代理地址
export DEFAULT_MODEL="gpt-4o-mini"

# 2. 设置代理（如果需要）
export HTTPS_PROXY="http://127.0.0.1:7890"
export HTTP_PROXY="http://127.0.0.1:7890"

# 3. 运行测试
python test_api_connection.py
""")


async def main():
    """主函数"""
    print("\n" + "🏥"*30)
    print("🔬 深度网络诊断工具 v2.0")
    print("🏥"*30)
    print(f"诊断时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 环境检查
    env_info = check_environment()
    
    # 2. DNS 测试
    dns_ok, ips = test_dns_resolution()
    
    # 3. TCP 连接测试
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
    parsed = urlparse(base_url)
    host = parsed.hostname or "api.openai.com"
    port = parsed.port or 443
    
    if ips:
        tcp_ok = test_multiple_ips(ips, port)
    else:
        print("\n跳过多 IP 测试（DNS 解析失败）")
        tcp_ok = False
    
    # 4. SSL 测试（仅在 TCP 成功时）
    if tcp_ok:
        ssl_ok = test_ssl_handshake(host, port)
    else:
        print("\n跳过 SSL 测试（TCP 连接失败）")
        ssl_ok = False
    
    # 5. HTTP 测试
    http_ok = test_http_request()
    
    # 6. API 测试
    api_ok = await test_openai_api_with_retry()
    
    # 7. 生成报告
    generate_recommendations(env_info, dns_ok, ips, tcp_ok, ssl_ok, http_ok, api_ok)


if __name__ == "__main__":
    asyncio.run(main())
