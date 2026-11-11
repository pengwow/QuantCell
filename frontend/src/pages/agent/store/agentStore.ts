import { create } from 'zustand';
// 非组件模块无法使用 useTranslation hook，直接用 i18n 单例取词（同 useUpdater.ts 先例）
import i18n from '../../../i18n/config';

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
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

    try {
      // 创建 AbortController 用于超时控制
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 180000); // 3分钟超时

      const response = await fetch('/api/v1/agent/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, session_id: currentSessionId }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: i18n.t('agent_request_failed') }));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error(i18n.t('agent_cannot_read_stream'));
      }

      let accumulatedContent = '';
      let currentIntent: string = '';
      let currentRole: string = '';
      const messageId = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      let assistantMessage: Message | null = null;

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          break;
        }

        const chunk = new TextDecoder().decode(value);
        // 按空行分割事件，处理可能的边界情况
        const rawEvents = chunk.split(/\n\n/).filter(e => e.trim());

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
              // 收到意图和角色信息
              currentIntent = data.data?.intent || '';
              currentRole = data.data?.role || i18n.t('agent_ai_assistant');
              
              // 创建 AI 消息骨架
              assistantMessage = {
                id: messageId,
                role: 'assistant',
                content: '',
                timestamp: new Date().toISOString(),
                intent: currentIntent,
                roleName: currentRole,
              };
              break;

            case 'content':
              // 增量内容更新
              if (data.data) {
                accumulatedContent += data.data;
                if (assistantMessage) {
                  assistantMessage.content = accumulatedContent;
                  set(state => ({
                    messages: state.messages.map(m => 
                      m.id === messageId ? assistantMessage! : m
                    ),
                  }));
                }
              }
              break;

            case 'tool_calls':
              // 工具调用信息
              if (data.data && assistantMessage) {
                assistantMessage.toolCalls = data.data;
                set(state => ({
                  messages: state.messages.map(m => 
                    m.id === messageId ? assistantMessage! : m
                  ),
                }));
              }
              break;

            case 'tool_result':
              // 工具执行结果
              if (data.data && assistantMessage) {
                assistantMessage.toolResult = data.data;
                set(state => ({
                  messages: state.messages.map(m => 
                    m.id === messageId ? assistantMessage! : m
                  ),
                }));
              }
              break;

            case 'complete':
              // 处理完成，添加结构化数据和建议操作
              if (data.data && assistantMessage) {
                assistantMessage.structuredData = data.data.structured_data || {};
                assistantMessage.actions = data.data.actions || [];
                
                // 更新最终消息
                set(state => ({
                  messages: state.messages.map(m => 
                    m.id === messageId ? assistantMessage! : m
                  ),
                }));
              }
              break;

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
      }

      set({ loading: false, streaming: false });

    } catch (error) {
      let errorMsg = i18n.t('agent_send_failed');
      let errorDetail = String(error);

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          errorMsg = i18n.t('agent_request_timeout');
          errorDetail = i18n.t('agent_timeout_detail');
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
        set({ sessions: data.sessions });
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
          createdAt: data.session.created_at,
          updatedAt: data.session.updated_at,
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
        set({ messages: data.history });
      }
    } catch (error) {
      console.error(`${i18n.t('agent_fetch_history_failed')}:`, error);
    }
  },
}));
