"""API 连接性测试脚本 - 用于诊断 APITimeoutError 问题"""

import asyncio
import os
import sys
import time
from pathlib import Path

# 添加 backend 目录到路径
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from openai import AsyncOpenAI, Timeout


async def test_basic_connection():
    """测试基本连接"""
    print("\n" + "="*60)
    print("📋 测试 1: 基本 API 连接")
    print("="*60)
    
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")
    
    print(f"API Key: {'***' + api_key[-4:] if api_key else '❌ 未设置'}")
    print(f"Base URL: {base_url or '默认 (OpenAI)'}")
    print(f"Default Model: {os.environ.get('DEFAULT_MODEL', 'gpt-4o-mini')}")
    
    if not api_key:
        print("❌ 错误: OPENAI_API_KEY 环境变量未设置")
        return False
    
    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
        )
        
        start_time = time.time()
        print(f"\n⏱️  发送简单请求... (timeout: connect=10s, read=30s)")
        
        response = await client.chat.completions.create(
            model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "Hi, 请回复'OK'"}],
            max_tokens=10,
        )
        
        elapsed = time.time() - start_time
        content = response.choices[0].message.content
        
        print(f"✅ 连接成功!")
        print(f"   响应内容: {content}")
        print(f"   响应时间: {elapsed:.2f}s")
        print(f"   Token 使用: {response.usage}")
        
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 连接失败: {type(e).__name__}: {e}")
        print(f"   失败时间: {elapsed:.2f}s")
        return False


async def test_with_longer_timeout():
    """使用更长的超时时间测试"""
    print("\n" + "="*60)
    print("📋 测试 2: 增加超时时间 (read=120s)")
    print("="*60)
    
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")
    
    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(connect=20.0, read=120.0, write=30.0, pool=10.0),
        )
        
        start_time = time.time()
        print(f"\n⏱️  发送请求... (timeout: connect=20s, read=120s)")
        
        response = await client.chat.completions.create(
            model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "请用一句话介绍你自己"}],
            max_tokens=100,
        )
        
        elapsed = time.time() - start_time
        content = response.choices[0].message.content
        
        print(f"✅ 长超时测试成功!")
        print(f"   响应内容: {content[:100]}...")
        print(f"   响应时间: {elapsed:.2f}s")
        
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 长超时测试失败: {type(e).__name__}: {e}")
        print(f"   失败时间: {elapsed:.2f}s")
        return False


async def test_with_tools():
    """测试带工具调用的请求"""
    print("\n" + "="*60)
    print("📋 测试 3: 带工具定义的请求 (模拟 Agent 场景)")
    print("="*60)
    
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名称"}
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    
    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(connect=20.0, read=120.0, write=30.0, pool=10.0),
        )
        
        start_time = time.time()
        print(f"\n⏱️  发送带工具的请求...")
        
        response = await client.chat.completions.create(
            model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
            tools=tools,
            tool_choice="auto",
            max_tokens=200,
        )
        
        elapsed = time.time() - start_time
        message = response.choices[0].message
        
        print(f"✅ 工具调用测试成功!")
        print(f"   响应时间: {elapsed:.2f}s")
        print(f"   有工具调用: {bool(message.tool_calls)}")
        
        if message.tool_calls:
            for tc in message.tool_calls:
                print(f"   工具: {tc.function.name}, 参数: {tc.function.arguments}")
        else:
            print(f"   响应内容: {(message.content or '')[:100]}...")
        
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 工具调用测试失败: {type(e).__name__}: {e}")
        print(f"   失败时间: {elapsed:.2f}s")
        return False


async def test_network_connectivity():
    """测试网络连接性"""
    print("\n" + "="*60)
    print("📋 测试 4: 网络连接性检查")
    print("="*60)
    
    import socket
    
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    
    print(f"\n目标主机: {host}:{port}")
    
    try:
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((host, port))
        elapsed = time.time() - start_time
        
        if result == 0:
            print(f"✅ TCP 连接成功! 耗时: {elapsed:.3f}s")
            sock.close()
            
            # 测试 SSL 握手
            if parsed.scheme == 'https':
                import ssl
                start_time = time.time()
                context = ssl.create_default_context()
                
                with socket.create_connection((host, port), timeout=10) as sock:
                    with context.wrap_socket(sock, server_hostname=host) as ssock:
                        elapsed = time.time() - start_time
                        print(f"✅ SSL 握手成功! 耗时: {elapsed:.3f}s")
                        print(f"   SSL 版本: {ssock.version()}")
                        cert = ssock.getpeercert()
                        if cert:
                            print(f"   证书主体: {cert.get('subject', [(None,)])[0][0]}")
            
            return True
        else:
            print(f"❌ TCP 连接失败, 错误码: {result} (耗时: {elapsed:.3f}s)")
            return False
            
    except socket.timeout:
        print(f"❌ 连接超时 (>10s)")
        return False
    except Exception as e:
        print(f"❌ 连接错误: {type(e).__name__}: {e}")
        return False


async def main():
    """运行所有测试"""
    print("\n" + "🔍"*30)
    print("🚀 OpenAI API 诊断测试工具")
    print("🔍"*30)
    print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # 运行测试
    results['network'] = await test_network_connectivity()
    results['basic'] = await test_basic_connection()
    results['long_timeout'] = await test_with_longer_timeout()
    results['with_tools'] = await test_with_tools()
    
    # 汇总结果
    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        test_names = {
            'network': '网络连接',
            'basic': '基本连接',
            'long_timeout': '长超时连接',
            'with_tools': '工具调用'
        }
        print(f"{test_names[name]}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n✨ 所有测试通过! API 连接正常")
        print("\n💡 建议:")
        print("  1. 如果仍然遇到超时,考虑增加 read timeout 到 180s 或更高")
        print("  2. 检查是否有代理或防火墙限制")
        print("  3. 联系 API 提供商确认服务状态")
    else:
        failed_tests = [k for k, v in results.items() if not v]
        print(f"\n⚠️  有 {len(failed_tests)} 个测试失败")
        print("\n💡 故障排查建议:")
        
        if not results['network']:
            print("  ❌ 网络层问题:")
            print("     - 检查网络连接")
            print("     - 检查 DNS 解析")
            print("     - 检查防火墙/代理设置")
            print("     - 尝试 ping 目标主机")
        
        if not results['basic'] and results['network']:
            print("  ❌ API 层问题:")
            print("     - 检查 API Key 是否有效")
            print("     - 检查账户余额/配额")
            print("     - 确认 Base URL 是否正确")
            print("     - 查看 API 服务状态页面")
        
        if not results['long_timeout'] and results['basic']:
            print("  ⏰ 超时问题:")
            print("     - 当前超时设置可能不够")
            print("     - 建议增加 timeout 值")
            print("     - 检查服务器负载情况")
        
        if not results['with_tools'] and results['basic']:
            print("  🔧 工具调用问题:")
            print("     - 检查工具定义格式")
            print("     - 确认模型支持 function calling")
            print("     - 减少工具数量或简化参数")

if __name__ == "__main__":
    asyncio.run(main())
