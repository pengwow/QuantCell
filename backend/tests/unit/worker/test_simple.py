"""
简单测试 - 验证Worker基础功能
"""

import pytest


def test_start_worker_not_found():
    """测试启动不存在的Worker（需要完整服务端环境，跳过）"""
    pytest.skip("需要完整应用上下文和数据库，在集成环境中运行")
