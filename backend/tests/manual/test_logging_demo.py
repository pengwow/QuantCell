"""测试 API 日志输出 - 验证增强的日志功能"""

import asyncio
import sys
import os
from pathlib import Path

# 添加后端目录到路径
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

async def test_api_logging():
    """测试 API 调用时的详细日志"""
    print("\n" + "🧪"*30)
    print("🔍 测试 API 详细日志功能")
    print("🧪"*30)

    # 检查环境变量
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("\n⚠️  未设置 OPENAI_API_KEY，使用模拟数据展示日志格式")
        print("设置环境变量后可进行真实 API 测试:\n")
        print('  export OPENAI_API_KEY="sk-your-key"')
        print('  export OPENAI_BASE_URL="https://your-api.com/v1"  # 可选')
        return await show_mock_log_example()
    
    # 真实 API 测试
    try:
        from agent.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider()

        # 模拟一个简单的请求
        messages = [
            {"role": "system", "content": "你是一个有用的助手"},
            {"role": "user", "content": "列出来文件夹内文件"}
        ]

        print("\n📤 发送测试请求...")
        response = await provider.chat(
            messages=messages,
            model=os.environ.get("DEFAULT_MODEL", "gpt-4o-mini"),
            temperature=0.1,
            max_tokens=100,
        )

        print(f"\n✅ 测试成功!")
        print(f"响应: {response.content[:100] if response.content else '无内容'}...")

    except Exception as e:
        print(f"\n❌ 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def show_mock_log_example():
    """展示模拟的日志示例（用于说明日志格式）"""
    print("\n" + "="*80)
    print("📋 日志输出示例 (运行 agent_cli.py chat send 时会看到)")
    print("="*80)

    example_log = """
================================================================================
[OpenAIProvider] 📤 API 请求详情
--------------------------------------------------------------------------------
API 接口: https://api.openai.com/v1/chat/completions
模型名称: gpt-4o-mini
温度参数: 0.1
最大 Token: 4096

📨 Messages (3 条):
  1. [system] 你是一个专业的文件管理助手，可以帮助用户操作文件和目录...
  2. [user] 列出来文件夹内文件

🔧 工具定义 (8 个):
  1. list_directory
     描述: 列出指定目录的文件和子目录
     参数: path [必填]

  2. read_file
     描述: 读取文件内容
     参数: path [必填], encoding, offset, limit

  3. write_file
     描述: 写入或创建文件
     参数: path [必填], content [必填], mode

  ... 还有 5 个工具
--------------------------------------------------------------------------------
================================================================================

[OpenAIProvider] API 响应成功, 耗时: 3.45s, usage=CompletionUsage(prompt_tokens=150, completion_tokens=45, total_tokens=195)

[OpenAIProvider] 📥 API 响应详情
--------------------------------------------------------------------------------
完成原因: tool_calls
Token 使用: prompt=150, completion=45, total=195

🔧 返回的工具调用 (1 个):
  - list_directory({"path": "/workspace", "show_hidden": false})
--------------------------------------------------------------------------------
"""

    print(example_log)
    print("="*80)
    print("\n💡 说明:")
    print("   ✅ 显示完整的 API 接口地址")
    print("   ✅ 显示模型名称和参数配置")
    print("   ✅ 显示所有消息内容（自动截断过长内容）")
    print("   ✅ 显示所有可用工具及其参数定义")
    print("   ✅ 显示响应详情（Token 使用、工具调用等）")
    print()


if __name__ == "__main__":
    asyncio.run(test_api_logging())
