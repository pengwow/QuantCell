# QuantCell LLM 调用全面收敛到 axon-quant — 设计文档

- **日期**: 2026-09-02
- **状态**: 已确认（用户批准）
- **前置**: axon-quant 0.14.1（含 `chat_async` / `chat_with_tools_async` / `stream_chat_async` 异步绑定）已发布并升级

## 1. 背景与问题

QuantCell 目前有 4 处直连 `openai` SDK 的 LLM 调用点，与 axon-quant 0.14.1 已补齐的原生能力高度重叠：

| 模块 | 现状 | 与 axon_quant 重叠度 |
|------|------|---------------------|
| `agent/providers/openai_provider.py` | 自实现 chat / chat_stream / tool_calls 累积 / reasoning_content（~330 行） | **高** — `LLMBackend.chat_with_tools` / `stream_chat` 原生支持（Rust 实现） |
| `ai_model/strategy_generator.py` | 策略生成（同步 + 流式） | 中 — 调 `chat.completions.create` |
| `ai_model/services.py` | 厂商管理：可用性检查、模型列表 | **低** — 管理面功能，axon 没有 |
| `indicators/routes.py` | 指标代码生成 / 自动修复直连调用 | 中 |

**核心矛盾**：QuantCell 在 Python 侧重复实现了 axon_quant Rust 侧已原生的完整 LLM 栈（工具调用、流式、思考链）。`axon_bridge/__init__.py` 也尚未导出 `LLMBackend`。

## 2. 目标

1. **全部收敛**：4 处 LLM 调用点统一走 axon-quant 原生 Rust 栈，消除 Python 侧重复实现。
2. **拆除抽象层**：删除 `agent/providers` 包（`LLMProvider` ABC + `OpenAIProvider` 实现），AgentLoop / Memory 直接消费 axon-quant backend。
3. **保留管理面**：`ai_model/services.py` 的厂商可用性检查、模型列表功能不动（axon 无对应能力）。
4. **行为等价**：auth / rate_limit / 超时的用户文案保持现有风格；非 OpenAI 兼容厂商在交易/生成链路给出明确报错。

## 3. 总体架构

```
改造前                                   改造后
─────────────────────                    ─────────────────────
agent/providers/openai_provider.py  →   删除整个 agent/providers/ 包
  (自实现 chat/stream/tools)             (全部走 axon_quant 原生 Rust 栈)

ai_model/strategy_generator.py      →    直接调用 axon_quant LLMBackend
  (openai SDK 同步客户端)                 (同步路径用 chat/stream_chat)
indicators/routes.py                →    直接调用 LLMBackend
  (openai SDK 直连 ×2)                   (async 路径用 chat_async)
ai_model/services.py                →    保留(厂商管理面:可用性检查/模型列表)
axon_bridge                        →    新增 axon_bridge/llm.py 桥接层
                                         (工厂 + 响应适配 + 错误分类)
```

## 4. 核心新增：`axon_bridge/llm.py`

桥接层，供全项目 4 处复用。职责：

- **`create_llm_backend(base_url, api_key, model, ...)`**
  包装 `axon_quant.llm.make_backend` 工厂，统一构造 `LLMBackend` 实例。
- **`chat_to_dict(backend, messages, tools)`**
  把 Rust 返回的 dict 适配为 QuantCell 习惯的响应结构：
  `tool_calls` JSON 字符串解析为 `[{id, name, arguments}]`。
- **`accumulate_stream(backend, messages)`**
  把 axon 原始增量重组为旧 `StreamChunk` 语义（累积 content + delta + finish 事件），
  供 AgentLoop 消费逻辑机械迁移。
- **`classify_llm_error(e)`**
  把 axon 的 RuntimeError 文本分类为 `auth / network / timeout / rate_limit`，
  沿用现有路由 401/429/超时文案分支。

## 5. 各模块收敛

### 5.1 `agent` — 拆除 LLMProvider 抽象

- `loop.py` / `memory.py`：类型注入从 `provider` 改为 `llm_backend`；
  `provider.chat(...)` → `await chat_to_dict(...)`；
  `response.xxx` 属性访问 → dict 键访问。
- `factory.py`：`OpenAIProvider(api_key, base_url)` → `create_llm_backend(...)`。
- 删除 `agent/providers/base.py`、`openai_provider.py`；
  `LLMResponse` / `StreamChunk` 类删除，改用 dict + TypeAlias。

### 5.2 `ai_model/strategy_generator.py` — 保留同步接口（行为等价）

- 同步 `chat` 改用 `backend.chat`（Rust 内部 block_on，与现状一致）。
- 流式路径改用 `backend.stream_chat`。

### 5.3 `indicators/routes.py` — 均在 async 路由内

- 两处同步直连（`call_ai_generate_code` / `_repair_indicator_code_via_llm`）
  改为 `await backend.chat_async(...)`。
- 错误分类走 `classify_llm_error`。

## 6. 分阶段落地

| 阶段 | 内容 | 验证 |
|------|------|------|
| Stage 1 | 新增 `axon_bridge/llm.py` + 导出，纯新增不破旧 | 桥接层单测 |
| Stage 2 | agent 拆 providers + loop/memory/factory 迁移 | `tests/unit/agent` 全绿 |
| Stage 3 | strategy_generator 收敛 | ai_model 相关测试 |
| Stage 4 | indicators 两处收敛 | indicators 相关测试 |

每阶段独立 commit + 全量 pytest 通过。

## 7. 边界与约束

- auth / rate_limit / 超时的用户文案保持现有风格不变。
- 非 OpenAI 兼容厂商（如 Anthropic）在交易/生成链路不支持，由 `classify_llm_error` 给出明确报错。
- 各模块直接消费 axon-quant 原生 Rust 栈，重复实现清空，且 API 兼容 backend 的未来同步升级。
- 遵循项目规范：路由层不写业务逻辑、统一 `HTTPException`、`handle_worker_exceptions` 装饰器、日志走 `utils.logger`。

## 8. 测试策略

- Stage 1：`axon_bridge/llm.py` 单测（工厂构造、响应适配、错误分类）。
- Stage 2：`tests/unit/agent` 全绿（AgentLoop / Memory 用 mock backend）。
- Stage 3/4：对应模块现有测试回归。
- 每阶段结束跑全量 pytest，确保无回归。
