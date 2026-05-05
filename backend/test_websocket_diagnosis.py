#!/usr/bin/env python3
"""
WebSocket 连接诊断测试脚本

专门用于诊断 Binance WebSocket 连接失败的原因
支持所有交易模式（spot/futures）和网络环境（主网/testnet）

使用: cd backend && python test_websocket_diagnosis.py
"""

import asyncio
import socket
import ssl
import time
import json
import sys
from typing import Dict, Any, List, Tuple

# 测试配置
TEST_API_KEY = "00UKr6uNwMzr8usGglgLMODETvvBFzIqiPZPHeHLqaLfse0fLMZ6zr6iR6swWmw8"
TEST_SECRET = "zmCfOFzCTglccylKZp0Q2rdZ5yLyGHbTGzmXVwCeFHwHO8uzXT2LURKhv9G4Y0iQ"

# WebSocket 端点配置（从 live_adapter.py 提取）
WEBSOCKET_ENDPOINTS = {
    # (trading_mode, testnet, is_us): [(host, port, url), ...]
    ("spot", False, False): [
        ("stream.binance.com", 9443, "wss://stream.binance.com:9443/ws"),  # 正确端口
        ("stream.binance.com", 443, "wss://stream.binance.com/ws"),       # 常见错误端口
    ],
    ("spot", True, False): [
        ("testnet.binance.vision", 443, "wss://testnet.binance.vision/ws"),
    ],
    ("future", False, False): [
        ("fstream.binance.com", 443, "wss://fstream.binance.com/ws"),
    ],
    ("future", True, False): [
        ("stream.binancefuture.com", 443, "wss://stream.binancefuture.com/ws"),
    ],
    ("futures", False, False): [
        ("fstream.binance.com", 443, "wss://fstream.binance.com/ws"),
    ],
    ("futures", True, False): [
        ("stream.binancefuture.com", 443, "wss://stream.binancefuture.com/ws"),
    ],
}

PASS_COUNT = 0
FAIL_COUNT = 0
WARN_COUNT = 0


def log(level: str, msg: str):
    """带颜色的日志输出"""
    colors = {
        "INFO": "\033[94m",
        "OK": "\033[92m",
        "FAIL": "\033[91m",
        "WARN": "\033[93m",
        "SUCCESS": "\033[92m",
        "ERROR": "\033[91m",
        "RESET": "\033[0m"
    }
    prefix = colors.get(level, "")
    print(f"{prefix}{msg}{colors['RESET']}")


def print_separator(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def test_tcp_connection(host: str, port: int, timeout: float = 5.0) -> Dict[str, Any]:
    """
    测试 TCP 端口连通性
    
    Returns:
        dict: 包含连接结果的字典
    """
    result = {
        "host": host,
        "port": port,
        "success": False,
        "error": None,
        "elapsed_ms": 0,
    }
    
    start_time = time.time()
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        # DNS 解析
        log("INFO", f"  解析 DNS: {host}")
        resolved_ip = socket.gethostbyname(host)
        log("INFO", f"  DNS 解析成功: {resolved_ip}")
        
        # TCP 连接
        connect_result = sock.connect_ex((resolved_ip, port))
        elapsed_ms = (time.time() - start_time) * 1000
        
        result["elapsed_ms"] = round(elapsed_ms)
        result["resolved_ip"] = resolved_ip
        
        if connect_result == 0:
            result["success"] = True
            log("OK", f"  ✓ TCP 连接成功: {host}:{port} ({elapsed_ms:.0f}ms)")
        else:
            error_messages = {
                111: "连接被拒绝 (Connection refused)",
                110: "连接超时 (Connection timed out)",
                113: "没有到主机的路由 (No route to host)",
                101: "网络不可达 (Network is unreachable)",
            }
            error_msg = error_messages.get(connect_result, f"未知错误码: {connect_result}")
            result["success"] = False
            result["error"] = error_msg
            log("FAIL", f"  ✗ TCP 连接失败: {host}:{port} - {error_msg} ({elapsed_ms:.0f}ms)")
        
        sock.close()
        
    except socket.gaierror as e:
        elapsed_ms = (time.time() - start_time) * 1000
        result["elapsed_ms"] = round(elapsed_ms)
        result["error"] = f"DNS 解析失败: {e}"
        log("FAIL", f"  ✗ DNS 解析失败: {host} - {e}")
    except socket.timeout:
        elapsed_ms = (time.time() - start_time) * 1000
        result["elapsed_ms"] = round(elapsed_ms)
        result["error"] = "连接超时"
        log("FAIL", f"  ✗ 连接超时: {host}:{port} ({elapsed_ms:.0f}ms)")
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        result["elapsed_ms"] = round(elapsed_ms)
        result["error"] = str(e)
        log("FAIL", f"  ✗ 连接异常: {host}:{port} - {e}")
    
    return result


def test_ssl_handshake(host: str, port: int, timeout: float = 10.0) -> Dict[str, Any]:
    """
    测试 SSL/TLS 握手
    
    Returns:
        dict: 包含握手结果的字典
    """
    result = {
        "host": host,
        "port": port,
        "success": False,
        "error": None,
        "certificate_info": None,
        "elapsed_ms": 0,
    }
    
    start_time = time.time()
    
    try:
        context = ssl.create_default_context()
        
        # 创建 socket 并包装 SSL
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        wrapped_socket = context.wrap_socket(sock, server_hostname=host)
        wrapped_socket.connect((host, port))
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # 获取证书信息
        cert = wrapped_socket.getpeercert()
        certificate_info = {
            "subject": dict(x[0] for x in cert.get('subject', ())),
            "issuer": dict(x[0] for x in cert.get('issuer', ())),
            "version": cert.get('version'),
            "serialNumber": cert.get('serialNumber'),
        }
        
        result["success"] = True
        result["certificate_info"] = certificate_info
        result["elapsed_ms"] = round(elapsed_ms)
        
        log("OK", f"  ✓ SSL 握手成功: {host}:{port} ({elapsed_ms:.0f}ms)")
        log("INFO", f"     证书主体: {certificate_info['subject'].get('commonName', 'N/A')}")
        
        wrapped_socket.close()
        sock.close()
        
    except ssl.SSLError as e:
        elapsed_ms = (time.time() - start_time) * 1000
        result["elapsed_ms"] = round(elapsed_ms)
        result["error"] = f"SSL 错误: {e}"
        log("FAIL", f"  ✗ SSL 握手失败: {host}:{port} - {e}")
    except socket.timeout:
        elapsed_ms = (time.time() - start_time) * 1000
        result["elapsed_ms"] = round(elapsed_ms)
        result["error"] = "SSL 握手超时"
        log("FAIL", f"  ✗ SSL 握手超时: {host}:{port} ({elapsed_ms:.0f}ms)")
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        result["elapsed_ms"] = round(elapsed_ms)
        result["error"] = str(e)
        log("FAIL", f"  ✗ SSL 握手异常: {host}:{port} - {e}")
    
    return result


async def test_websocket_connection(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """
    测试 WebSocket 连接（实际握手）
    
    Args:
        url: WebSocket URL
        timeout: 超时时间（秒）
    
    Returns:
        dict: 包含连接结果的字典
    """
    result = {
        "url": url,
        "success": False,
        "error": None,
        "elapsed_ms": 0,
        "protocol": None,
    }
    
    start_time = time.time()
    
    try:
        import websockets
        
        # websockets 15.x 兼容写法：使用 asyncio.wait_for 控制超时
        async def _connect_with_timeout():
            return await websockets.connect(
                url,
                ssl=True if url.startswith('wss://') else None,
            )
        
        try:
            ws = await asyncio.wait_for(_connect_with_timeout(), timeout=timeout)
        except TypeError:
            # 旧版本兼容：直接传入 timeout 参数
            ws = await websockets.connect(
                url,
                timeout=timeout,
                ssl=True if url.startswith('wss://') else None,
            )
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        result["success"] = True
        result["elapsed_ms"] = round(elapsed_ms)
        
        log("OK", f"  ✓ WebSocket 连接成功: {url} ({elapsed_ms:.0f}ms)")
        
        # 尝试订阅测试（可选）
        try:
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": ["btcusdt@trade"],
                "id": 1
            }
            await ws.send(json.dumps(subscribe_msg))
            
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            log("OK", f"     订阅响应: {response[:100]}")
            
            result["subscription_test"] = "success"
        except Exception as sub_err:
            log("WARN", f"     订阅测试失败: {sub_err}")
            result["subscription_test"] = f"failed: {sub_err}"
        finally:
            await ws.close()
        
        return result
            
    except ImportError:
        result["error"] = "websockets 库未安装，请运行: uv add websockets"
        log("WARN", f"  ⚠ 缺少依赖: websockets")
        return result
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        result["elapsed_ms"] = round(elapsed_ms)
        result["error"] = str(e)
        log("FAIL", f"  ✗ WebSocket 连接失败: {url} - {e} ({elapsed_ms:.0f}ms)")
        return result


async def test_all_endpoints_for_scenario(trading_mode: str, testnet: bool) -> List[Dict[str, Any]]:
    """
    测试某个场景下的所有 WebSocket 端点
    
    Args:
        trading_mode: 交易模式 (spot/future/futures)
        testnet: 是否为测试网
    
    Returns:
        list: 所有端点的测试结果列表
    """
    results = []
    
    key = (trading_mode, testnet, False)
    endpoints = WEBSOCKET_ENDPOINTS.get(key, [])
    
    if not endpoints:
        log("WARN", f"  未找到 {trading_mode} (testnet={testnet}) 的 WebSocket 端点配置")
        return results
    
    for host, port, url in endpoints:
        print(f"\n{'─'*60}")
        log("INFO", f"测试端点: {url}")
        print(f"{'─'*60}")
        
        endpoint_result = {
            "url": url,
            "host": host,
            "port": port,
            "tests": {},
        }
        
        # 测试1: TCP 连通性
        log("INFO", "测试 1/3: TCP 端口连通性")
        tcp_result = test_tcp_connection(host, port)
        endpoint_result["tests"]["tcp"] = tcp_result
        
        if not tcp_result["success"]:
            results.append(endpoint_result)
            continue  # TCP 不通过则跳过后续测试
        
        # 测试2: SSL 握手
        log("INFO", "测试 2/3: SSL/TLS 握手")
        ssl_result = test_ssl_handshake(host, port)
        endpoint_result["tests"]["ssl"] = ssl_result
        
        if not ssl_result["success"]:
            results.append(endpoint_result)
            continue  # SSL 不通过则跳过后续测试
        
        # 测试3: WebSocket 实际连接
        log("INFO", "测试 3/3: WebSocket 实际连接")
        ws_result = await test_websocket_connection(url)
        endpoint_result["tests"]["websocket"] = ws_result
        
        results.append(endpoint_result)
    
    return results


async def run_comprehensive_test():
    """运行全面的 WebSocket 诊断测试"""
    global PASS_COUNT, FAIL_COUNT, WARN_COUNT
    
    print("=" * 70)
    print("  QuantCell WebSocket 连接诊断套件")
    print(f"  测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 测试场景
    scenarios = [
        ("spot", False, "Binance Spot 主网"),
        ("spot", True, "Binance Spot Testnet"),
        ("future", False, "Binance Futures 主网"),
        ("future", True, "Binance Futures Testnet"),
        ("futures", False, "Binance Futures (别名) 主网"),
        ("futures", True, "Binance Futures (别名) Testnet"),
    ]
    
    all_results = []
    
    for trading_mode, testnet, description in scenarios:
        print_separator(description)
        log("INFO", f"参数: mode={trading_mode}, testnet={testnet}")
        
        results = await test_all_endpoints_for_scenario(trading_mode, testnet)
        all_results.extend(results)
        
        await asyncio.sleep(0.3)  # 避免请求过快
    
    # 汇总报告
    print("\n" + "=" * 70)
    print("  诊断汇总")
    print("=" * 70)
    
    success_count = 0
    fail_count = 0
    warning_count = 0
    
    issues_found = []
    fixes_needed = []
    
    for result in all_results:
        url = result.get("url", "N/A")
        tests = result.get("tests", {})
        
        tcp_ok = tests.get("tcp", {}).get("success", False)
        ssl_ok = tests.get("ssl", {}).get("success", False)
        ws_ok = tests.get("websocket", {}).get("success", False)
        
        status_parts = []
        if tcp_ok:
            status_parts.append("✓ TCP")
        else:
            status_parts.append("✗ TCP")
        
        if "ssl" in tests:
            if ssl_ok:
                status_parts.append("✓ SSL")
            else:
                status_parts.append("✗ SSL")
        
        if "websocket" in tests:
            if ws_ok:
                status_parts.append("✓ WS")
            else:
                status_parts.append("✗ WS")
        
        status_str = " | ".join(status_parts)
        
        if tcp_ok and ssl_ok and ws_ok:
            success_count += 1
            log("OK", f"  ✅ {url}: {status_str}")
        elif tcp_ok and not ssl_ok:
            fail_count += 1
            log("FAIL", f"  ❌ {url}: {status_str}")
            issues_found.append(f"{url}: SSL 握手失败")
        elif tcp_ok and ssl_ok and not ws_ok:
            warning_count += 1
            log("WARN", f"  ⚠️  {url}: {status_str}")
            issues_found.append(f"{url}: WebSocket 协议层失败")
        else:
            fail_count += 1
            log("FAIL", f"  ❌ {url}: {status_str}")
            issues_found.append(f"{url}: TCP 层连接失败")
    
    total = len(all_results)
    print(f"\n  总计: {total} 个端点 | 成功: {success_count} | 失败: {fail_count} | 警告: {warning_count}")
    
    # 问题分析和修复建议
    if issues_found:
        print("\n" + "=" * 70)
        print("  问题分析与修复建议")
        print("=" * 70)
        
        for i, issue in enumerate(issues_found, 1):
            print(f"\n  问题 {i}: {issue}")
            
            if "TCP" in issue and "失败" in issue:
                print("    可能原因:")
                print("      • 防火墙阻止了出站连接")
                print("      • 代理设置不正确")
                print("      • DNS 解析失败")
                print("    修复建议:")
                print("      1. 检查系统防火墙规则")
                print("      2. 配置正确的 HTTP/SOCKS5 代理")
                print("      3. 检查 /etc/hosts 或 DNS 设置")
                fixes_needed.append("检查网络连通性和代理配置")
            
            elif "SSL" in issue and "失败" in issue:
                print("    可能原因:")
                print("      • SSL/TLS 证书验证失败")
                print("      • Python SSL 库版本过旧")
                print("      • 中间人攻击或网络干扰")
                print("    修复建议:")
                print("      1. 更新 Python 和 openssl")
                print("      2. 检查系统时间是否准确")
                print("      3. 排查网络是否有 SSL 拦截")
                fixes_needed.append("更新 SSL 库或排查网络拦截")
            
            elif "WebSocket" in issue and "失败" in issue:
                print("    可能原因:")
                print("      • WebSocket 协议不支持")
                print("      • 服务器拒绝升级请求")
                print("      • websockets 库版本兼容性问题")
                print("    修复建议:")
                print("      1. 运行: uv add websockets")
                print("      2. 检查 websockets 版本 >= 10.0")
                print("      3. 尝试使用 websocket-client 作为替代")
                fixes_needed.append("安装或更新 websockets 库")
    
    # 特殊提示：关于端口 9443 vs 443
    print("\n" + "=" * 70)
    print("  重要提示：Binance Spot WebSocket 端口")
    print("=" * 70)
    print("""
  ⚠️  Binance Spot 主网的 WebSocket 使用端口 9443 而非 443！

  错误配置示例:
    wss://stream.binance.com/ws          ❌ (端口 443，可能无法连接)

  正确配置示例:
    wss://stream.binance.com:9443/ws     ✓ (端口 9443，官方推荐)

  这就是为什么之前测试显示 "stream.binance.com:443 不可达" 的原因！
  
  请确保在 live_adapter.py 和相关代码中使用正确的端口。
""")
    
    if fail_count == 0 and warning_count == 0:
        log("SUCCESS", "\n🎉 所有 WebSocket 端点连接正常!")
        return 0
    else:
        log("ERROR", f"\n❌ 发现 {fail_count + warning_count} 个问题需要处理!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_comprehensive_test())
    sys.exit(exit_code)
