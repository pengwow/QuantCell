"""推向前端 WebSocket 的 wire 事件 schema 版本出口。

这里的「事件」指主进程推给前端的业务事件（worker_event / strategy_event /
kernel.snapshot 等），与 worker/protocol.py 的 ZMQ 控制面信封版本是两个层级：
P2-09 的 PROTOCOL_SCHEMA_VERSION 管主进程 ↔ worker 进程的信封，本模块管
主进程 → 前端的事件本体。

版本语义（前端 websocketService.ts 的 migrate_event 依此实现）：
- 事件缺 schema_version 视为 v0，前端原样放行（向后兼容读旧版）
- 高于 EVENTS_SCHEMA_VERSION 的事件由前端丢弃，等前端升级后再支持

注入点清单（新增 wire 事件组装点时同步在此登记）：
- core/lifespan.py  worker_event 信封（orchestrator 外部事件转发）
- worker/state.py   strategy_event（策略状态变更广播）
- worker/strategy_manager.py  kernel.snapshot（paper 泵权益快照）
"""

EVENTS_SCHEMA_VERSION = 1
