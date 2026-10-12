"""AI 文本润色 — 公共接口模块。"""

from .routes import router
from .service import AIPolishError, polish_text

__all__ = ["AIPolishError", "polish_text", "router"]
