"""方向词汇 canonical 契约的向后兼容 re-export 壳。

实现唯一来源已提升为根级模块 ``vocab``（backend/vocab.py，与 worker 域
跨包导入惯例一致：``from vocab import ...``）。本壳仅为不破坏 worker 域
既有相对导入（``from .vocab import ...``）与单测（``from worker.vocab import ...``）；
新代码请直接 ``from vocab import ...``。
"""

from vocab import (
    PositionSide,
    Side,
    normalize_position_side,
    normalize_side,
)

__all__ = ["PositionSide", "Side", "normalize_position_side", "normalize_side"]
