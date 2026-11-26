"""推向前端 WebSocket 的 wire 事件 schema 版本出口。

这里的「事件」指推给前端的业务事件（worker_event / strategy_event /
kernel.snapshot 等）。本模块只管事件本体的 wire schema 版本，与传输层
（REST/WS/SSE）无关。

版本语义（前端 websocketService.ts 的 migrate_event 依此实现）：
- 事件缺 schema_version 视为 v0，前端原样放行（向后兼容读旧版）
- 高于 EVENTS_SCHEMA_VERSION 的事件由前端丢弃，等前端升级后再支持

注入点清单（新增 wire 事件组装点时同步在此登记）：
- core/lifespan.py  worker_event 信封（orchestrator 外部事件转发）
- worker/state.py   strategy_event（策略状态变更广播）
- worker/strategy_manager.py  kernel.snapshot（paper 泵权益快照）
"""

EVENTS_SCHEMA_VERSION = 1
