"""axon_bridge.core 适配层 — 核心类型(events / 基础数据类)。

⚠️ axon_quant 0.4.0 不暴露 core 子模块,events 事件类需要等上游提供。
本模块先以 shim 形式占位,等 axon_quant 真正暴露 OrderAccepted 等
事件类时,直接把 events.py 改成 re-export 即可,业务侧零改动。
"""
