"""API 连接性测试脚本 - 用于诊断 APITimeoutError 问题"""

import asyncio
import os
import time

from openai import AsyncOpenAI, Timeout


async def test_basic_connection():
    """测试基本连接"""

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")

    if not api_key:
        return False

    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
        )

        start_time = time.time()

        response = await client.chat.completions.create(
            model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "Hi, 请回复'OK'"}],
            max_tokens=10,
        )

        time.time() - start_time
        response.choices[0].message.content

        return True

    except Exception:
        time.time() - start_time
        return False


async def test_with_longer_timeout():
    """使用更长的超时时间测试"""

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL")

    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(connect=20.0, read=120.0, write=30.0, pool=10.0),
        )

        start_time = time.time()

        response = await client.chat.completions.create(
            model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "请用一句话介绍你自己"}],
            max_tokens=100,
        )

        time.time() - start_time
        response.choices[0].message.content

        return True

    except Exception:
        time.time() - start_time
        return False


async def test_with_tools():
    """测试带工具调用的请求"""

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
                    "properties": {"city": {"type": "string", "description": "城市名称"}},
                    "required": ["city"],
                },
            },
        }
    ]

    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(connect=20.0, read=120.0, write=30.0, pool=10.0),
        )

        start_time = time.time()

        response = await client.chat.completions.create(
            model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
            tools=tools,
            tool_choice="auto",
            max_tokens=200,
        )

        time.time() - start_time
        message = response.choices[0].message

        if message.tool_calls:
            for _tc in message.tool_calls:
                pass
        else:
            pass

        return True

    except Exception:
        time.time() - start_time
        return False


async def test_network_connectivity():
    """测试网络连接性"""

    import socket

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((host, port))
        time.time() - start_time

        if result == 0:
            sock.close()

            # 测试 SSL 握手
            if parsed.scheme == "https":
                import ssl

                start_time = time.time()
                context = ssl.create_default_context()

                with socket.create_connection((host, port), timeout=10) as sock:
                    with context.wrap_socket(sock, server_hostname=host) as ssock:
                        time.time() - start_time
                        cert = ssock.getpeercert()
                        if cert:
                            pass

            return True
        else:
            return False

    except TimeoutError:
        return False
    except Exception:
        return False


async def main():
    """运行所有测试"""

    results = {}

    # 运行测试
    results["network"] = await test_network_connectivity()
    results["basic"] = await test_basic_connection()
    results["long_timeout"] = await test_with_longer_timeout()
    results["with_tools"] = await test_with_tools()

    # 汇总结果

    for _name, _passed in results.items():
        pass

    all_passed = all(results.values())

    if all_passed:
        pass
    else:
        [k for k, v in results.items() if not v]

        if not results["network"]:
            pass

        if not results["basic"] and results["network"]:
            pass

        if not results["long_timeout"] and results["basic"]:
            pass

        if not results["with_tools"] and results["basic"]:
            pass


if __name__ == "__main__":
    asyncio.run(main())
