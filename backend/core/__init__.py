# -*- coding: utf-8 -*-
"""
核心模块

包含应用核心功能：调度器、生命周期管理等
"""

from .scheduler import start_scheduler
from .lifespan import lifespan

__all__ = ['start_scheduler', 'lifespan']
