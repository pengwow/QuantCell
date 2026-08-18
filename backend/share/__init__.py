"""
Worker 分享系统

为 Worker 详情页提供生成分享链接的能力。
- 公开只读访问，无需登录
- 字段白名单：仅暴露非敏感的绩效与持仓信息
- 支持有效期、一次性访问、最大访问次数
- 数据库存 SHA256(token) 而非明文
"""

from .routes import router

__all__ = ["router"]
