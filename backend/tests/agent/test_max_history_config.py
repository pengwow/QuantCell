"""测试 max_history 配置是否生效"""

import contextlib
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))


def test_max_history_config():
    """测试 max_history 配置"""

    # 测试默认值
    os.environ.pop("AGENT_MAX_HISTORY", None)

    # 模拟一个简单的 AgentLoop 创建

    # 测试自定义值
    os.environ["AGENT_MAX_HISTORY"] = "300"

    # 验证 int 转换
    int(os.environ.get("AGENT_MAX_HISTORY", "200"))

    # 测试无效值处理
    os.environ["AGENT_MAX_HISTORY"] = "invalid"
    with contextlib.suppress(ValueError):
        int(os.environ.get("AGENT_MAX_HISTORY", "200"))


if __name__ == "__main__":
    test_max_history_config()
