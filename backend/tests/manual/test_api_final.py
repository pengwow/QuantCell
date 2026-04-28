"""API 连接测试 - 支持代理配置"""

import asyncio
import os
import sys
import time
from pathlib import Path

backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from openai import AsyncOpenAI, Timeout


def print_banner():
    print("\n" + "🚀"*30)
    print("🔧 OpenAI API 连接测试工具 (支持代理)")
    print("🚀"*30)
    print(f"⏰ 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")


def check_proxy():
    """检查并显示代理配置"""
    print("\n" + "="*60)
    print("🌐 代理配置检查")
    print("="*60)
    
    proxies = {
        "HTTPS_PROXY": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
        "HTTP_PROXY": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "ALL_PROXY": os.environ.get("ALL_PROXY"),
    }
    
    has_proxy = False
    for name, value in proxies.items():
        if value:
            has_proxy = True
            print(f"✅ {name}: {value}")
        else:
            print(f"⚠️  {name}: 未设置")
    
    return has_proxy


async def test_with_current_config():
    """使用当前配置测试"""
    print("\n" + "="*60)
    print("📡 使用当前配置测试 API")
    print("="*60)
    
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("DEFAULT_MODEL", "gpt-4o-mini")
    
    print(f"\n配置信息:")
    print(f"  API Key: {'***' + api_key[-4:] if len(api_key) > 4 else ('❌ 未设置' if not api_key else '✅ 已设置')}")
    print(f"  Base URL: {base_url or '(默认 OpenAI)'}")
    print(f"  Model: {model}")
    
    if not api_key:
        print("\n❌ 错误: 请先设置 OPENAI_API_KEY")
        print("\n示例:")
        print('  export OPENAI_API_KEY="sk-your-key-here"')
        return False
    
    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(connect=30.0, read=120.0, write=30.0, pool=10.0),
        )
        
        start_time = time.time()
        print(f"\n⏱️  发送测试请求...")
        
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "请回复'连接成功'四个字"}],
            max_tokens=20,
            temperature=0,
        )
        
        elapsed = time.time() - start_time
        content = response.choices[0].message.content
        
        print(f"\n✅ API 连接成功!")
        print(f"   响应内容: {content}")
        print(f"   响应时间: {elapsed:.2f}s")
        print(f"   Token 用量: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}")
        
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ API 调用失败: {type(e).__name__}: {e}")
        print(f"   失败时间: {elapsed:.2f}s")
        
        # 提供针对性建议
        if "timed out" in str(e).lower():
            print("\n💡 超时问题建议:")
            print("  1. 检查代理是否正常运行")
            print("  2. 尝试切换代理节点")
            print("  3. 增加超时时间")
        elif "401" in str(e):
            print("\n💡 认证错误:")
            print("  1. 检查 API Key 是否正确")
            print("  2. 确认 API Key 未过期")
        elif "connection" in str(e).lower():
            print("\n💡 连接错误:")
            print("  1. 检查网络连接")
            print("  2. 确认代理地址正确")
            print("  3. 检查防火墙设置")
        
        return False


async def test_simple_request():
    """简单请求测试"""
    print("\n" + "="*60)
    print("🎯 快速连通性测试 (短消息)")
    print("="*60)
    
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")
    
    if not api_key:
        print("❌ 缺少 API Key")
        return False
    
    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(connect=15.0, read=30.0, write=10.0, pool=5.0),
        )
        
        start = time.time()
        resp = await client.chat.completions.create(
            model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
        )
        elapsed = time.time() - start
        
        print(f"✅ 快速测试通过! 响应时间: {elapsed:.2f}s")
        print(f"   回复: {resp.choices[0].message.content}")
        return True
        
    except Exception as e:
        print(f"❌ 快速测试失败: {type(e).__name__}: {e}")
        return False


def show_setup_guide():
    """显示配置指南"""
    print("\n" + "="*60)
    print("📖 配置指南")
    print("="*60)
    
    print("""
┌─────────────────────────────────────────────────────┐
│  步骤 1: 设置 API Key                              │
├─────────────────────────────────────────────────────┤
│  export OPENAI_API_KEY="sk-proj-xxxxxxxxxxxx"      │
│                                                     │
│  或者在 .env 文件中添加:                            │
│  OPENAI_API_KEY=sk-proj-xxxxxxxxxxxx               │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  步骤 2: 设置代理 (如果需要)                        │
├─────────────────────────────────────────────────────┤
│  # Clash/V2Ray 代理示例:                           │
│  export HTTPS_PROXY="http://127.0.0.1:7890"       │
│  export HTTP_PROXY="http://127.0.0.1:7890"        │
│                                                     │
│  # 或者使用 socks5:                                 │
│  export HTTPS_PROXY="socks5://127.0.0.1:7890"     │
│  export HTTP_PROXY="socks5://127.0.0.1:7890"      │
│                                                     │
│  # 如果使用自定义 API 中转服务:                     │
│  export OPENAI_BASE_URL="https://your-api.com/v1" │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  步骤 3: 运行测试                                  │
├─────────────────────────────────────────────────────┤
│  python test_api_final.py                          │
│                                                     │
│  或者在 Python 代码中加载 .env:                     │
│  from dotenv import load_dotenv                    │
│  load_dotenv()                                     │
└─────────────────────────────────────────────────────┘

常见代理端口:
  - Clash: 7890
  - V2Ray: 10808 或 10809
  - Shadowsocks: 1080
  - Trojan: 1080

如果不确定代理端口，请查看你的代理软件设置。
""")


async def main():
    """主函数"""
    print_banner()
    
    # 显示代理状态
    has_proxy = check_proxy()
    
    if not has_proxy:
        print("\n⚠️  未检测到代理配置")
        print("   如果你在中国大陆，通常需要代理才能访问 OpenAI API\n")
    
    # 运行测试
    success = await test_simple_request()
    
    if success:
        await test_with_current_config()
    else:
        await test_with_current_config()
    
    # 显示配置指南
    show_setup_guide()


if __name__ == "__main__":
    asyncio.run(main())
