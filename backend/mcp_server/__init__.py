"""MCP Server（P2-04）：把 QuantCell 既有 Agent 工具面以 Model Context Protocol
暴露给外部客户端（Claude Desktop / Cursor 等），只代理不新建能力，工具全部走
ToolRegistry 既有实现。

护栏设计：
- 只读工具默认可用；write 工具需 QUANTCELL_MCP_ENABLE_WRITE=1 显式开启，且每次
  调用必须带 confirm=true 二次确认；dangerous 工具永不通过 MCP 暴露；
- 工具数量上限 30（tool_contract.MAX_MCP_TOOLS）；
- 出站结果统一脱敏（security.redact_secrets / redact_secrets_text）；
- 启动必须携带合法 Agent Token（QUANTCELL_MCP_TOKEN），调用上下文注入
  agent_caller，与 ToolRegistry/P2-06 审计链路打通。
"""
