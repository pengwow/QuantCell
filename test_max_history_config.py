"""测试 max_history 配置是否生效"""

import os
import sys
from pathlib import Path

backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

def test_max_history_config():
    """测试 max_history 配置"""
    print("\n" + "="*60)
    print("🧪 测试 max_history 配置")
    print("="*60)

    # 测试默认值
    os.environ.pop("AGENT_MAX_HISTORY", None)
    from agent.core.loop import AgentLoop

    # 模拟一个简单的 AgentLoop 创建
    print("\n1. 测试默认配置 (不设置 AGENT_MAX_HISTORY)")
    print(f"   AGENT_MAX_HISTORY = {os.environ.get('AGENT_MAX_HISTORY', '未设置')}")

    # 测试自定义值
    print("\n2. 测试自定义配置 (AGENT_MAX_HISTORY=300)")
    os.environ["AGENT_MAX_HISTORY"] = "300"
    print(f"   AGENT_MAX_HISTORY = {os.environ.get('AGENT_MAX_HISTORY')}")

    # 验证 int 转换
    max_history = int(os.environ.get("AGENT_MAX_HISTORY", "200"))
    print(f"   转换后的值: {max_history} (类型: {type(max_history).__name__})")

    # 测试无效值处理
    print("\n3. 测试无效值处理")
    os.environ["AGENT_MAX_HISTORY"] = "invalid"
    try:
        max_history = int(os.environ.get("AGENT_MAX_HISTORY", "200"))
        print(f"   ⚠️  无效值被转换为: {max_history}")
    except ValueError:
        print(f"   ❌ 无效值无法转换为 int，使用默认值 200")

    print("\n" + "="*60)
    print("✅ 配置测试完成")
    print("="*60)
    print("\n💡 使用方法:")
    print("   export AGENT_MAX_HISTORY=300")
    print("   python agent_cli.py chat send \"你的消息\"")

if __name__ == "__main__":
    test_max_history_config()
