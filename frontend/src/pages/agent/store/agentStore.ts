import { create } from 'zustand';
// 非组件模块无法使用 useTranslation hook，直接用 i18n 单例取词（同 useUpdater.ts 先例）
import i18n from '../../../i18n/config';
import { useWorkbenchStore } from './workbenchStore';

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  /** 该次工具执行耗时（秒），来源 SSE tool_result.data.elapsed；未上报则 undefined */
  elapsed?: number;
}

export interface Tool {
  name: string;
  description: string;
}

export interface Session {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
}

export interface IntentAction {
  type: string;
  label: string;
}

/**
 * ReAct 单轮迭代上限（页头/徽标兜底展示用）。
 * 来源：backend/agent/core/loop.py `max_iterations: int = 40`（factory.py 装配同值）；
 * SSE `iteration_start` 事件每次都会带同值，运行期以上报为准，此常量只用于零消息时的页头真值。
 */
export const REACT_MAX_ITERATIONS = 40;

/**
 * 每日复盘结构化报告。字段逐项对照后端 `backend/agent/core/daily_review.py`：
 * `build_report` 返回 `{date, sections, summary_text, template_text, meta}`，
 * `publish` 把整份 report 挂在消息的 `meta.report` 上（daily_review.py:439-450），
 * `sections` 的形状来自 `collect_sections`（daily_review.py:196-262）。
 * 全部可选：后端降级时个别节会缺，渲染层按缺失整节跳过。
 */
export interface DailyReviewOverview {
  date?: string;
  active_workers?: number;
  total_pnl?: number;
  total_trades?: number;
  win_rate?: number;
  orders?: number;
  decisions?: number;
  anomaly_count?: number;
}

export interface DailyReviewWorker {
  worker_id?: number;
  name?: string;
  status?: string;
  pnl?: number;
  trades?: number;
  win_rate?: number;
  orders?: number;
}

export interface DailyReviewAnomaly {
  type?: string;
  /** 后端已拼好的中文描述（daily_review.py:171/176），前端直接展示不重拼 */
  detail?: string;
}

export interface DailyReviewAdvisory {
  severity?: string;
  reason?: string;
}

export interface DailyReviewRisk {
  count?: number;
  max_severity?: string | null;
  advisories?: DailyReviewAdvisory[];
  error?: string;
}

export interface DailyReviewModels {
  families?: number;
  blocked?: Array<{ family?: string; model_id?: string; reason?: string }>;
  latest_rounds?: Array<Record<string, unknown>>;
  error?: string;
}

export interface DailyReviewSections {
  overview?: DailyReviewOverview;
  workers?: DailyReviewWorker[];
  anomalies?: DailyReviewAnomaly[];
  risk_advisories?: DailyReviewRisk;
  models?: DailyReviewModels;
}

export interface DailyReviewReport {
  date?: string;
  sections?: DailyReviewSections;
  summary_text?: string;
  template_text?: string;
}

/** 后端消息 meta（history 原样带回）；目前仅定时任务注入的每日复盘使用 */
export interface MessageMeta {
  kind?: string;
  date?: string;
  degraded?: boolean;
  report?: DailyReviewReport;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: string;
  toolCalls?: ToolCall[];
  toolResult?: string;
  isError?: boolean;
  errorDetail?: string;
  // 新增：意图分类和角色信息
  intent?: string;
  roleName?: string;
  actions?: IntentAction[];
  structuredData?: Record<string, unknown>;
  /** 模型推理流（reasoning 事件累积），用于「思考中」过程展示 */
  reasoning?: string;
  /** ReAct 迭代进度（iteration_start / complete{iteration}），仅当轮流内有值 */
  iteration?: { current: number; max: number };
  /** 后端消息元信息（如定时任务每日复盘的 meta.kind="daily_review" + meta.report） */
  meta?: MessageMeta;
}

interface AgentState {
  // 状态
  messages: Message[];
  sessions: Session[];
  currentSessionId: string;
  tools: Tool[];
  loading: boolean;
  streaming: boolean;
  error: string | null;

  // Actions
  sendMessage: (content: string) => Promise<void>;
  fetchSessions: () => Promise<void>;
  switchSession: (sessionId: string) => void;
  createSession: () => Promise<void>;
  clearSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<boolean>;
  fetchTools: () => Promise<void>;
  fetchHistory: (sessionId: string) => Promise<void>;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  messages: [],
  sessions: [],
  currentSessionId: 'default',
  tools: [],
  loading: false,
  streaming: false,
  error: null,
  
  sendMessage: async (content: string) => {
    const { currentSessionId } = get();
    // 工作台选中的 Worker 一并带上，供后端注入决策/订单摘要（0/未选不带，后端可选参数）
    const workerId = useWorkbenchStore.getState().workerId;

    // 添加用户消息
    const userMessage: Message = {
      id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };

    set(state => ({
      messages: [...state.messages, userMessage],
      loading: true,
      streaming: true,
      error: null,
    }));

    // 是否已收到过流内容：收到后断线不重试（避免重复注入消息）
    let receivedAny = false;
    const retryNoticeId = `${Date.now()}-retry`;

    try {
      // 创建 AbortController 用于超时控制
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 180000); // 3分钟超时

      const body: Record<string, unknown> = { message: content, session_id: currentSessionId };
      if (workerId) body.worker_id = workerId;

      // ponytail: 仅建连阶段重试，最多 2 次、间隔 800ms；已收到内容后断流直接报错不重试。
      // 天花板是固定退避，升级路径：指数退避 + 可配置次数。
      let response: Response | null = null;
      for (let attempt = 0; !response; attempt++) {
        try {
          response = await fetch('/api/v1/agent/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: controller.signal,
          });
        } catch (err) {
          // 超时/主动 abort 不重试
          if ((err as Error).name === 'AbortError' || attempt >= 2) throw err;
          const notice: Message = {
            id: retryNoticeId,
            role: 'assistant',
            content: i18n.t('agent_reconnecting', { n: attempt + 1 }),
            timestamp: new Date().toISOString(),
            isError: true,
          };
          set(state => ({
            messages: [...state.messages.filter(m => m.id !== retryNoticeId), notice],
          }));
          await new Promise(resolve => setTimeout(resolve, 800));
        }
      }
      // 重连成功即撤掉提示，不让过期气泡留在聊天里
      set(state => ({ messages: state.messages.filter(m => m.id !== retryNoticeId) }));

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: i18n.t('agent_request_failed') }));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error(i18n.t('agent_cannot_read_stream'));
      }

      let accumulatedContent = '';
      let accumulatedReasoning = '';
      let currentIntent: string = '';
      let currentRole: string = '';
      // ReAct 迭代进度：iteration_start 逐轮推进，complete{iteration} 落最终轮次
      let iterationCurrent = 0;
      let iterationMax = 0;
      const messageId = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      let assistantMessage: Message | null = null;
      // SSE 事件可能被网络层切成半个事件，必须跨 chunk 缓冲后再按空行切分
      let sseBuffer = '';
      const decoder = new TextDecoder();

      // 首次收到内容时把 AI 气泡插入消息列表（start 阶段不插，避免闪现空气泡）
      const upsertAssistant = () => {
        if (!assistantMessage) return;
        set(state =>
          state.messages.some(m => m.id === messageId)
            ? { messages: state.messages.map(m => (m.id === messageId ? assistantMessage! : m)) }
            : { messages: [...state.messages, assistantMessage!] },
        );
      };

      // 迭代进度只写 meta：气泡未入列表时保持纯内存，入列表后原地刷新（不提前插入空气泡）
      const applyIteration = () => {
        if (!assistantMessage || iterationCurrent <= 0) return;
        assistantMessage.iteration = {
          current: iterationCurrent,
          max: iterationMax || iterationCurrent,
        };
        set(state =>
          state.messages.some(m => m.id === messageId)
            ? { messages: state.messages.map(m => (m.id === messageId ? assistantMessage! : m)) }
            : {},
        );
      };

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          break;
        }

        sseBuffer += decoder.decode(value, { stream: true });
        // 按空行分割事件，处理可能的边界情况
        const rawEvents = sseBuffer.split(/\n\n/);
        sseBuffer = rawEvents.pop() ?? '';

        for (const rawEvent of rawEvents) {
          // 健壮解析 SSE 事件格式
          // 支持: event: xxx\ndata: yyy 或 data: yyy
          const lines = rawEvent.split('\n').map(l => l.trim()).filter(l => l);
          
          let eventType = 'message';
          let dataStr = '';
          
          for (const line of lines) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim() || 'message';
            } else if (line.startsWith('data:')) {
              dataStr += line.slice(5).trim();
            }
          }
          
          if (!dataStr) continue;
          
          let data;
          try {
            data = JSON.parse(dataStr);
          } catch {
            continue;
          }

          switch (eventType) {
            case 'start':
              // 后端会发两条 start：第一条带 intent/role，第二条带 session 元信息。
              // 只在缺省时赋值，避免第二条把已识别的意图/角色覆盖成空。
              if (data.data?.intent && !currentIntent) {
                currentIntent = data.data.intent;
              }
              if (data.data?.role && !currentRole) {
                currentRole = data.data.role;
              }
              // 创建 AI 消息骨架（不落库，等首个 content 再插入）
              if (!assistantMessage) {
                assistantMessage = {
                  id: messageId,
                  role: 'assistant',
                  content: '',
                  timestamp: new Date().toISOString(),
                  intent: currentIntent,
                  roleName: currentRole || i18n.t('agent_ai_assistant'),
                };
                // iteration_start 可能先于 start 到达：骨架补上已知进度
                if (iterationCurrent > 0) {
                  assistantMessage.iteration = {
                    current: iterationCurrent,
                    max: iterationMax || iterationCurrent,
                  };
                }
              }
              break;

            case 'iteration_start':
              // ReAct 每轮开始：{iteration, max_iterations}。只记进度，不改正文。
              if (typeof data.data?.iteration === 'number') {
                iterationCurrent = data.data.iteration;
              }
              if (typeof data.data?.max_iterations === 'number') {
                iterationMax = data.data.max_iterations;
              }
              applyIteration();
              break;

            case 'reasoning':
              // 推理增量（GLM 等模型的思考过程）
              receivedAny = true;
              if (typeof data.data === 'string') {
                accumulatedReasoning += data.data;
              } else if (data.data?.content) {
                accumulatedReasoning += data.data.content;
              }
              if (assistantMessage) {
                assistantMessage.reasoning = accumulatedReasoning;
                set(state => ({ messages: state.messages.map(m => (m.id === messageId ? assistantMessage! : m)) }));
              }
              break;

            case 'content':
              // 增量内容更新（后端 content 事件 data 为 {content, full_content}，兼容旧版纯字符串）
              receivedAny = true;
              if (data.data) {
                const delta =
                  typeof data.data === 'string' ? data.data : (data.data.content ?? '');
                accumulatedContent += delta;
                if (assistantMessage) {
                  assistantMessage.content = accumulatedContent;
                  upsertAssistant();
                }
              }
              break;

            case 'tool_calls':
              // 工具调用信息（后端 data 形状为 {tools: [...]}）
              if (data.data && assistantMessage) {
                assistantMessage.toolCalls = Array.isArray(data.data)
                  ? data.data
                  : (data.data.tools ?? []);
                upsertAssistant();
              }
              break;

            case 'tool_result':
              // 工具执行结果（后端 data 形状为 {name, result, elapsed}，elapsed 单位为秒：loop.py:426-435）
              if (data.data && assistantMessage) {
                assistantMessage.toolResult =
                  typeof data.data === 'string'
                    ? data.data
                    : (data.data.result ?? JSON.stringify(data.data));
                // 逐节点回填耗时：tool_start 与 tool_result 的 name 同源于同一个
                // tool_call["name"]（loop.py:407 / :430），可直接按名匹配。
                // 同轮多个同名工具：回填第一个还没有 elapsed 的节点，不覆盖已有值；
                // 旧后端/历史消息没有 elapsed 时保持 undefined，不补假耗时。
                if (
                  typeof data.data.elapsed === 'number' &&
                  Number.isFinite(data.data.elapsed) &&
                  Array.isArray(assistantMessage.toolCalls)
                ) {
                  const node = assistantMessage.toolCalls.find(
                    tc => tc.name === data.data.name && tc.elapsed === undefined,
                  );
                  if (node) node.elapsed = data.data.elapsed;
                }
                upsertAssistant();
              }
              break;

            case 'complete': {
              // 后端有两条 complete：loop 的（content/iteration）与 routes 的（structured_data/actions）。
              // 两条都要消费，且只更新同一条消息。
              if (!assistantMessage) break;
              if (typeof data.data?.content === 'string' && !accumulatedContent) {
                accumulatedContent = data.data.content;
                assistantMessage.content = accumulatedContent;
              }
              // loop 的 complete 带最终轮次；routes 的没有，不该把已有进度清掉
              if (typeof data.data?.iteration === 'number') {
                iterationCurrent = data.data.iteration;
                assistantMessage.iteration = {
                  current: iterationCurrent,
                  max: iterationMax || iterationCurrent,
                };
              }
              if (data.data?.structured_data) {
                assistantMessage.structuredData = data.data.structured_data;
              }
              if (Array.isArray(data.data?.actions) && data.data.actions.length > 0) {
                assistantMessage.actions = data.data.actions;
              }
              upsertAssistant();
              break;
            }

            case 'error':
              // 错误事件
              throw new Error(data.data?.error || i18n.t('agent_stream_error'));
          }
        }
      }

      clearTimeout(timeoutId);

      if (!assistantMessage) {
        // 如果没有收到任何消息，创建一个默认消息
        const defaultMessage: Message = {
          id: messageId,
          role: 'assistant',
          content: accumulatedContent || i18n.t('agent_processing_complete'),
          timestamp: new Date().toISOString(),
          intent: currentIntent,
          roleName: currentRole,
        };
        set(state => ({
          messages: [...state.messages, defaultMessage],
        }));
      } else {
        // 兜底：只有 reasoning 没有 content 时也要落一条消息
        upsertAssistant();
      }

      set({ loading: false, streaming: false, error: null });

    } catch (error) {
      let errorMsg = i18n.t('agent_send_failed');
      let errorDetail = String(error);

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          errorMsg = i18n.t('agent_request_timeout');
          errorDetail = i18n.t('agent_timeout_detail');
        } else if (receivedAny) {
          // 已收到部分内容才断流：不重试，只提示本轮可能不完整（半截气泡保留）
          errorMsg = i18n.t('agent_stream_interrupted');
          errorDetail = error.stack || error.message;
        } else {
          errorMsg = error.message;
          errorDetail = error.stack || error.message;
        }
      }

      const errorMessageObj: Message = {
        id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
        role: 'assistant',
        content: errorMsg,
        timestamp: new Date().toISOString(),
        isError: true,
        errorDetail: errorDetail,
      };
      set(state => ({
        messages: [...state.messages, errorMessageObj],
        loading: false,
        streaming: false,
        error: errorMsg,
      }));
    }
  },
  
  fetchSessions: async () => {
    try {
      const response = await fetch('/api/v1/agent/sessions');
      const data = await response.json();
      if (data.success && data.sessions) {
        // 后端列表返回 {key, name, messages_count, created_at, updated_at}，
        // 前端 Session 需要 {id, name, createdAt, updatedAt}——不做映射会导致
        // 会话抽屉渲染空行（name/id 均 undefined）。
        const sessions: Session[] = (data.sessions as Record<string, unknown>[]).map(s => {
          const id = String(s.key ?? s.id ?? '');
          const rawName = String(s.name ?? '');
          // 旧会话文件的 name 可能等于 key（如 default），此时给可读名
          const name =
            rawName && rawName !== id
              ? rawName
              : id === 'default'
                ? i18n.t('agent_default_session')
                : id;
          return {
            id,
            name,
            createdAt: String(s.createdAt ?? s.created_at ?? ''),
            updatedAt: String(s.updatedAt ?? s.updated_at ?? s.created_at ?? ''),
          };
        });
        set({ sessions });
      }
    } catch (error) {
      console.error(`${i18n.t('agent_fetch_sessions_failed')}:`, error);
      // 降级使用本地存储
      const sessions: Session[] = JSON.parse(localStorage.getItem('ai-agent-sessions') || '[]');
      if (sessions.length === 0) {
        const defaultSession: Session = {
          id: 'default',
          name: i18n.t('agent_default_session'),
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        sessions.push(defaultSession);
        localStorage.setItem('ai-agent-sessions', JSON.stringify(sessions));
      }
      set({ sessions });
    }
    // 挂载时顺带恢复当前会话的聊天记录（否则刷新后聊天区恒为空态）
    if (get().messages.length === 0) {
      await get().fetchHistory(get().currentSessionId);
    }
  },
  
  switchSession: (sessionId: string) => {
    set({ currentSessionId: sessionId, messages: [] });
    get().fetchHistory(sessionId);
  },
  
  createSession: async () => {
    try {
      const response = await fetch('/api/v1/agent/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: i18n.t('agent_session_name', { time: new Date().toLocaleString() }) }),
      });
      const data = await response.json();
      if (data.success && data.session) {
        const newSession: Session = {
          id: data.session.id,
          name: data.session.name,
          createdAt: data.session.created_at ?? '',
          updatedAt: data.session.updated_at ?? data.session.created_at ?? '',
        };
        const sessions = [...get().sessions, newSession];
        set({ sessions, currentSessionId: newSession.id, messages: [] });
      }
    } catch (error) {
      console.error(`${i18n.t('agent_create_session_failed')}:`, error);
      // 降级使用本地存储
      const newSession: Session = {
        id: `session-${Date.now()}`,
        name: i18n.t('agent_session_name', { time: new Date().toLocaleString() }),
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      const sessions = [...get().sessions, newSession];
      localStorage.setItem('ai-agent-sessions', JSON.stringify(sessions));
      set({ sessions, currentSessionId: newSession.id, messages: [] });
    }
  },
  
  clearSession: async (sessionId: string) => {
    await fetch(`/api/v1/agent/sessions/${sessionId}/clear`, { method: 'POST' });
    if (get().currentSessionId === sessionId) {
      set({ messages: [] });
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
      const response = await fetch(`/api/v1/agent/sessions/${sessionId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error(i18n.t('delete_failed'));
      }

      // 更新本地状态
      const updatedSessions = get().sessions.filter(s => s.id !== sessionId);

      // 如果删除的是当前会话，切换到第一个可用会话或创建新会话
      let newCurrentId = get().currentSessionId;
      if (sessionId === get().currentSessionId) {
        if (updatedSessions.length > 0) {
          newCurrentId = updatedSessions[0].id;
        } else {
          // 创建默认会话
          const defaultSession: Session = {
            id: 'default',
            name: i18n.t('agent_default_session'),
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          };
          updatedSessions.push(defaultSession);
          newCurrentId = defaultSession.id;
        }
      }

      set({
        sessions: updatedSessions,
        currentSessionId: newCurrentId,
        messages: sessionId === get().currentSessionId ? [] : get().messages,
      });

      return true;
    } catch (error) {
      console.error(`${i18n.t('agent_delete_session_failed')}:`, error);
      return false;
    }
  },

  fetchTools: async () => {
    try {
      const response = await fetch('/api/v1/agent/tools');
      const tools = await response.json();
      set({ tools });
    } catch (error) {
      console.error(`${i18n.t('agent_fetch_tools_failed')}:`, error);
    }
  },
  
  fetchHistory: async (sessionId: string) => {
    try {
      const response = await fetch(`/api/v1/agent/sessions/${sessionId}/history`);
      const data = await response.json();
      if (data.success) {
        // 后端 history 是 OpenAI 风格原始消息（role/content，无 id/时间戳），
        // 前端渲染需要统一结构；system 提示词与空助手消息不展示。
        const history: Message[] = (data.history || [])
          .filter((m: Record<string, unknown>) => m.role !== 'system')
          // tool 消息是智能体内部往返，恢复会话时展示会刷屏（且与工具卡片重复）
          .filter((m: Record<string, unknown>) => m.role !== 'tool')
          // 带 tool_calls 但无正文的 assistant 是中间轮次，展示会得到空气泡
          .filter(
            (m: Record<string, unknown>) =>
              !(m.role === 'assistant' && !String(m.content ?? '').trim()),
          )
          .filter((m: Record<string, unknown>) => m.content || m.tool_calls)
          .map((m: Record<string, unknown>, idx: number) => {
            const role = m.role === 'assistant' ? 'assistant' : 'user';
            const rawContent = m.content;
            const content =
              typeof rawContent === 'string'
                ? rawContent
                : rawContent == null
                  ? ''
                  : JSON.stringify(rawContent);
            // 系统注入消息（每日复盘）的结构化信息全在 meta 上，丢掉就只剩纯文本：
            // 后端 history 原样返回 messages（session/manager.py:199-206），meta 结构见 daily_review.py:439-450
            const meta =
              m.meta && typeof m.meta === 'object' ? (m.meta as MessageMeta) : undefined;
            return {
              id: `history-${sessionId}-${idx}`,
              role,
              content,
              // 后端历史不带时间戳；留空由气泡隐藏，避免伪造"当前时间"
              timestamp: '',
              ...(role === 'assistant' ? { roleName: i18n.t('agent_ai_assistant') } : {}),
              ...(meta ? { meta } : {}),
            } as Message;
          });
        set({ messages: history });
      }
    } catch (error) {
      console.error(`${i18n.t('agent_fetch_history_failed')}:`, error);
    }
  },
}));
