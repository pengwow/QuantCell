#!/usr/bin/env python3
"""
交易所连接测试脚本 - 全面覆盖所有场景

测试场景:
  1. Binance Spot 主网 (无/有 API Key)
  2. Binance Futures 主网 (无/有 API Key)  
  3. Binance Spot Testnet (无/有 API Key)
  4. Binance Futures Testnet (无/有 API Key)
  5. WebSocket 连通性测试

使用: cd backend && python test_connection_all.py
"""

import asyncio
import sys
import time
import json

# 测试配置
TEST_API_KEY = "00UKr6uNwMzr8usGglgLMODETvvBFzIqiPZPHeHLqaLfse0fLMZ6zr6iR6swWmw8"
TEST_SECRET = "zmCfOFzCTglccylKZp0Q2rdZ5yLyGHbTGzmXVwCeFHwHO8uzXT2LURKhv9G4Y0iQ"

# 测试场景定义
SCENARIOS = [
    # (exchange, mode, testnet, has_key, description)
    ("binance", "spot", False, False, "Binance Spot 主网 (无Key)"),
    ("binance", "spot", False, True,  "Binance Spot 主网 (有Key)"),
    ("binance", "future", False, False, "Binance Futures 主网 (无Key)"),
    ("binance", "future", False, True,  "Binance Futures 主网 (有Key)"),
    ("binance", "spot", True, False,  "Binance Spot Testnet (无Key)"),
    ("binance", "spot", True, True,   "Binance Spot Testnet (有Key)"),
    ("binance", "futures", True, False, "Binance Futures Testnet (无Key)"),
    ("binance", "futures", True, True,   "Binance Futures Testnet (有Key)"),
]

PASS_COUNT = 0
FAIL_COUNT = 0
WARN_COUNT = 0


def log(level, msg):
    """带颜色的日志输出"""
    colors = {"INFO": "\033[94m", "OK": "\033[92m", "FAIL": "\033[91m", "WARN": "\033[93m", "RESET": "\033[0m"}
    prefix = colors.get(level, "")
    print(f"{prefix}{msg}{colors['RESET']}")


def print_separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_direct_http(exchange_name, trading_mode, testnet, api_key=None, secret_key=None):
    """
    直接 HTTP 请求方式测试（与 BinanceExchange.test_connection 相同逻辑）
    """
    import requests as req
    import hashlib
    import hmac
    
    results = {"tests": {}}
    
    # 确定 URL
    is_futures = trading_mode in ('future', 'futures')
    
    if testnet:
        if is_futures:
            base_url = 'https://testnet.binancefuture.com/fapi/v1'
        else:
            base_url = 'https://testnet.binance.vision/api/v3'
    else:
        if is_futures:
            base_url = 'https://fapi.binance.com/fapi/v1'
        else:
            base_url = 'https://api.binance.com/api/v3'
    
    # 测试1: 市场数据
    t1 = time.time()
    try:
        exchange_info_url = f"{base_url}/exchangeInfo"
        resp = req.get(exchange_info_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        symbols_count = len(data.get('symbols', []))
        elapsed = (time.time() - t1) * 1000
        results["tests"]["market_data"] = {
            "success": True,
            "markets_count": symbols_count,
            "elapsed_ms": round(elapsed)
        }
        log("INFO", f"  ✓ 市场数据: {symbols_count} 个交易对 ({elapsed:.0f}ms)")
    except Exception as e:
        elapsed = (time.time() - t1) * 1000
        results["tests"]["market_data"] = {"success": False, "error": str(e), "elapsed_ms": round(elapsed)}
        log("FAIL", f"  ✗ 市场数据失败: {str(e)[:80]}")
    
    # 测试2: 服务器时间
    t2 = time.time()
    try:
        if is_futures:
            if testnet:
                time_url = 'https://testnet.binancefuture.com/fapi/v1/time'
            else:
                time_url = 'https://fapi.binance.com/fapi/v1/time'
        else:
            if testnet:
                time_url = 'https://testnet.binance.vision/api/v3/time'
            else:
                time_url = 'https://api.binance.com/api/v3/time'
        
        time_resp = req.get(time_url, timeout=10)
        server_time = int(time_resp.json().get('serverTime', 0))
        local_time = int(time.time() * 1000)
        diff = abs(server_time - local_time)
        elapsed = (time.time() - t2) * 1000
        results["tests"]["server_time"] = {"success": True, "time_diff_ms": diff, "elapsed_ms": round(elapsed)}
        log("INFO", f"  ✓ 时间同步: 差异 {diff}ms ({elapsed:.0f}ms)")
    except Exception as e:
        elapsed = (time.time() - t2) * 1000
        results["tests"]["server_time"] = {"success": False, "error": str(e), "elapsed_ms": round(elapsed)}
        log("FAIL", f"  ✗ 时间同步失败: {str(e)[:80]}")
    
    # 测试3: WebSocket (简化版 - 只检测端口可达性)
    t3 = time.time()
    try:
        import socket
        if is_futures:
            if testnet:
                ws_host = "stream.binancefuture.com"
                ws_port = 443
            else:
                ws_host = "fstream.binance.com"
                ws_port = 443
        else:
            if testnet:
                ws_host = "testnet.binance.vision"
                ws_port = 443
            else:
                ws_host = "stream.binance.com"
                ws_port = 443
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((ws_host, ws_port))
        sock.close()
        
        elapsed = (time.time() - t3) * 1000
        if result == 0:
            results["tests"]["websocket"] = {"success": True, "host": ws_host, "elapsed_ms": round(elapsed)}
            log("INFO", f"  ✓ WebSocket: {ws_host}:{ws_port} 可达 ({elapsed:.0f}ms)")
        else:
            results["tests"]["websocket"] = {"success": False, "error": f"连接被拒绝 (code={result})", "host": ws_host}
            log("FAIL", f"  ✗ WebSocket: {ws_host}:{ws_port} 不可达")
    except Exception as e:
        elapsed = (time.time() - t3) * 1000
        results["tests"]["websocket"] = {"success": False, "error": str(e), "elapsed_ms": round(elapsed)}
        log("WARN", f"  ⚠ WebSocket 异常: {str(e)[:60]}")
    
    # 测试4: API 认证 (如果有 Key)
    if api_key and secret_key:
        t4 = time.time()
        try:
            timestamp = str(int(time.time() * 1000))
            query = f'timestamp={timestamp}'
            signature = hmac.new(
                secret_key.encode('utf-8'),
                query.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            headers = {'X-MBX-APIKEY': api_key}
            params = {'timestamp': timestamp, 'signature': signature}
            
            if is_futures:
                url = f"{base_url}/balance"
            else:
                url = f"{base_url}/account"
            
            auth_resp = req.get(url, headers=headers, params=params, timeout=10)
            
            content_type = auth_resp.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                auth_data = auth_resp.json()
                elapsed = (time.time() - t4) * 1000
                
                if isinstance(auth_data, list):
                    balance_ok = any(float(b.get('balance', 0)) > 0 for b in auth_data[:5] if isinstance(b, dict))
                elif isinstance(auth_data, dict):
                    balance_ok = bool(auth_data.get('balances') or auth_data.get('assets'))
                else:
                    balance_ok = bool(auth_data)
                
                results["tests"]["authentication"] = {
                    "success": True,
                    "has_balance": balance_ok,
                    "elapsed_ms": round(elapsed)
                }
                log("INFO", f"  ✓ API认证: 成功 ({elapsed:.0f}ms)")
            else:
                elapsed = (time.time() - t4) * 1000
                raw = auth_resp.text[:100]
                results["tests"]["authentication"] = {
                    "success": False,
                    "error": f"非JSON响应 ({auth_resp.status_code}): {raw}",
                    "elapsed_ms": round(elapsed)
                }
                log("FAIL", f"  ✗ API认证: 返回非JSON - {raw}")
                
        except Exception as e:
            elapsed = (time.time() - t4) * 1000
            error_str = str(e)
            results["tests"]["authentication"] = {"success": False, "error": error_str, "elapsed_ms": round(elapsed)}
            
            if "-2015" in error_str or "-2014" in error_str:
                log("FAIL", f"  ✗ API认证: 权限/密钥错误 - {error_str[:60]}")
            elif "403" in error_str or "401" in error_str:
                log("FAIL", f"  ✗ API认证: 认证失败 - {error_str[:60]}")
            else:
                log("FAIL", f"  ✗ API认证: {error_str[:80]}")
    else:
        results["tests"]["authentication"] = {"success": None, "message": "未提供API密钥"}
        log("INFO", f"  ○ API认证: 跳过 (无Key)")
    
    return results


async def test_via_exchange_module(exchange_name, trading_mode, testnet, api_key=None, secret_key=None):
    """
    通过 exchange 模块测试（与后端 API 相同路径）
    """
    from exchange.connection import test_exchange_connection
    
    return await test_exchange_connection(
        exchange_name=exchange_name,
        api_key=api_key,
        secret_key=secret_key,
        trading_mode=trading_mode,
        testnet=testnet
    )


async def run_scenario(desc, exchange_name, mode, testnet, has_key):
    """运行单个测试场景"""
    global PASS_COUNT, FAIL_COUNT, WARN_COUNT
    
    print_separator(desc)
    
    key = TEST_API_KEY if has_key else None
    secret = TEST_SECRET if has_key else None
    
    log("INFO", f"参数: exchange={exchange_name}, mode={mode}, testnet={testnet}, key={'***' + key[-4:] if key else 'None'}")
    
    start = time.time()
    
    # 方式1: 直接 HTTP 测试（详细日志）
    log("INFO", "--- 直接 HTTP 测试 ---")
    direct_results = test_direct_http(exchange_name, mode, testnet, key, secret)
    
    # 方式2: 通过 exchange 模块测试（验证模块集成）
    log("INFO", "--- Exchange 模块测试 ---")
    try:
        module_result = await test_via_exchange_module(exchange_name, mode, testnet, key, secret)
        module_status = module_result.status.value
        module_msg = module_result.message
        module_time = module_result.response_time_ms or 0
        log("INFO", f"  模块结果: {module_status} - {module_msg} ({module_time:.0f}ms)")
    except Exception as e:
        module_status = "ERROR"
        module_msg = str(e)
        log("FAIL", f"  模块异常: {e}")
    
    total_time = (time.time() - start) * 1000
    
    # 统计结果
    tests = direct_results.get("tests", {})
    passed = sum(1 for v in tests.values() if v.get("success") is True)
    failed = sum(1 for v in tests.values() if v.get("success") is False)
    skipped = sum(1 for v in tests.values() if v.get("success") is None)
    total = len(tests)
    
    if failed == 0 and module_status == "success":
        PASS_COUNT += 1
        log("OK", f"\n  ★ 场景通过! ({passed}/{total} 通过, {skipped} 跳过, {total_time:.0f}ms)")
        return True
    elif failed > 0 and module_status == "success":
        WARN_COUNT += 1
        log("WARN", f"\n  ⚠ 部分通过 (直接HTTP有{failed}项失败, 但模块成功) ({total_time:.0f}ms)")
        return False
    else:
        FAIL_COUNT += 1
        log("FAIL", f"\n  ✗ 场景失败! ({passed}/{total} 通过, {failed} 失败, {total_time:.0f}ms)")
        return False


async def main():
    global PASS_COUNT, FAIL_COUNT, WARN_COUNT
    
    print("=" * 60)
    print("  QuantCell 交易所连接测试套件")
    print(f"  测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = []
    
    for exchange_name, mode, testnet, has_key, desc in SCENARIOS:
        ok = await run_scenario(desc, exchange_name, mode, testnet, has_key)
        results.append((desc, ok))
        await asyncio.sleep(0.5)  # 避免请求过快
    
    # 汇总
    print("\n" + "=" * 60)
    print("  测试汇总")
    print("=" * 60)
    
    for desc, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        log("OK" if ok else "FAIL", f"  {status}: {desc}")
    
    total = len(results)
    passed = PASS_COUNT
    failed = FAIL_COUNT
    warned = WARN_COUNT
    
    print(f"\n  总计: {total} | 通过: {passed} | 失败: {failed} | 警告: {warned}")
    
    if failed == 0:
        log("OK", "\n  🎉 所有场景测试通过!")
        return 0
    else:
        log("FAIL", f"\n  ❌ 有 {failed} 个场景失败!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
