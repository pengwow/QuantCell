"""因子服务进程级单例：写入方（研究采纳/挖掘）与路由必须共享同一实例。"""

from __future__ import annotations

import factor.routes
from factor.service import get_factor_service
from research.scenarios import factor as scenario_factor


def test_get_factor_service_is_process_wide_singleton():
    # 两次拿到同一实例：否则写入方更新的是自己的内存缓存，路由看不到
    assert get_factor_service() is get_factor_service()


def test_routes_and_research_scenario_share_singleton():
    # 回归钉子：研究采纳后 factor 路由内存必须立即可见（此前各自 new 导致 404）
    assert scenario_factor.FactorScenario().service is factor.routes.factor_service
