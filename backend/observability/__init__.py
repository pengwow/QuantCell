"""可观测性模块（P2-01 Prometheus 指标埋点）

提供 /api/v1/metrics 端点、HTTP 中间件埋点与 worker 侧三项指标。
模块顶层只依赖 prometheus_client（轻量，无 DB 链路），可被任意模块安全导入；
对 utils.config_manager / worker.state 的引用一律延迟到调用/抓取时刻。
"""
