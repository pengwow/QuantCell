"""测试 API 日志输出 - 验证增强的日志功能"""

import asyncio
import os


async def test_api_logging():
    """测试 API 调用时的详细日志"""

    # 检查环境变量
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return await show_mock_log_example()

    # 真实 API 测试
    try:
        from agent.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider()

        # 模拟一个简单的请求
        messages = [
            {"role": "system", "content": "你是一个有用的助手"},
            {"role": "user", "content": "列出来文件夹内文件"},
        ]

        await provider.chat(
            messages=messages,
            model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
            temperature=0.1,
            max_tokens=100,
        )

    except Exception:
        import traceback

        traceback.print_exc()


async def show_mock_log_example():
    """展示模拟的日志示例（用于说明日志格式）"""


if __name__ == "__main__":
    asyncio.run(test_api_logging())
