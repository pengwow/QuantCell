"""API 连接测试 - 支持代理配置"""

import asyncio
import os
import time

from openai import AsyncOpenAI, Timeout


def print_banner():
    pass


def check_proxy():
    """检查并显示代理配置"""

    proxies = {
        "HTTPS_PROXY": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
        "HTTP_PROXY": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "ALL_PROXY": os.environ.get("ALL_PROXY"),
    }

    has_proxy = False
    for value in proxies.values():
        if value:
            has_proxy = True
        else:
            pass

    return has_proxy


async def test_with_current_config():
    """使用当前配置测试"""

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("DEFAULT_MODEL", "gpt-4o-mini")

    if not api_key:
        return False

    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(connect=30.0, read=120.0, write=30.0, pool=10.0),
        )

        start_time = time.time()

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "请回复'连接成功'四个字"}],
            max_tokens=20,
            temperature=0,
        )

        time.time() - start_time
        response.choices[0].message.content

        return True

    except Exception as e:
        time.time() - start_time

        # 提供针对性建议
        if "timed out" in str(e).lower() or "401" in str(e) or "connection" in str(e).lower():
            pass

        return False


async def test_simple_request():
    """简单请求测试"""

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")

    if not api_key:
        return False

    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(connect=15.0, read=30.0, write=10.0, pool=5.0),
        )

        start = time.time()
        await client.chat.completions.create(
            model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
        )
        time.time() - start

        return True

    except Exception:
        return False


def show_setup_guide():
    """显示配置指南"""


async def main():
    """主函数"""
    print_banner()

    # 显示代理状态
    has_proxy = check_proxy()

    if not has_proxy:
        pass

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
