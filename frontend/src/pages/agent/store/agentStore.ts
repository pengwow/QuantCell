import { create } from 'zustand';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: string;
  toolCalls?: ToolCall[];
  toolResult?: string;
  isError?: boolean;
  errorDetail?: string;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
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
      error: null,
    }));

    try {
      // 创建 AbortController 用于超时控制
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000); // 2分钟超时

      const response = await fetch('/api/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, session_id: currentSessionId }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: '请求失败' }));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const data = await response.json();

      if (data.success) {
        const assistantMessage: Message = {
          id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
          role: 'assistant',
          content: data.message,
          timestamp: new Date().toISOString(),
        };

        set(state => ({
          messages: [...state.messages, assistantMessage],
          loading: false,
          error: null,
        }));
      } else {
        // 处理业务错误
        const errorMessage = data.message || data.error || '请求处理失败';
        const errorDetail = data.detail || data.stack || JSON.stringify(data, null, 2);
        const errorMessageObj: Message = {
          id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
          role: 'assistant',
          content: errorMessage,
          timestamp: new Date().toISOString(),
          isError: true,
          errorDetail: errorDetail,
        };
        set(state => ({
          messages: [...state.messages, errorMessageObj],
          loading: false,
          error: errorMessage,
        }));
      }
    } catch (error) {
      let errorMsg = '发送消息失败';
      let errorDetail = String(error);

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          errorMsg = '请求超时，Agent处理时间过长';
          errorDetail = 'Agent处理时间超过2分钟，请简化问题或稍后重试';
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
        error: errorMsg,
      }));
    }
  },
  
  fetchSessions: async () => {
    // 从后端获取会话列表
    // 简化实现：使用本地存储
    const sessions: Session[] = JSON.parse(localStorage.getItem('ai-agent-sessions') || '[]');
    if (sessions.length === 0) {
      const defaultSession: Session = {
        id: 'default',
        name: '默认会话',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      sessions.push(defaultSession);
      localStorage.setItem('ai-agent-sessions', JSON.stringify(sessions));
    }
    set({ sessions });
  },
  
  switchSession: (sessionId: string) => {
    set({ currentSessionId: sessionId, messages: [] });
    get().fetchHistory(sessionId);
  },
  
  createSession: async () => {
    const newSession: Session = {
      id: `session-${Date.now()}`,
      name: `会话 ${new Date().toLocaleString()}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    
    const sessions = [...get().sessions, newSession];
    localStorage.setItem('ai-agent-sessions', JSON.stringify(sessions));
    set({ sessions, currentSessionId: newSession.id, messages: [] });
  },
  
  clearSession: async (sessionId: string) => {
    await fetch(`/api/agent/sessions/${sessionId}/clear`, { method: 'POST' });
    if (get().currentSessionId === sessionId) {
      set({ messages: [] });
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
      const response = await fetch(`/api/agent/sessions/${sessionId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('删除失败');
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
            name: '默认会话',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          };
          updatedSessions.push(defaultSession);
          newCurrentId = defaultSession.id;
        }
      }

      // 更新 localStorage
      localStorage.setItem('ai-agent-sessions', JSON.stringify(updatedSessions));

      set({
        sessions: updatedSessions,
        currentSessionId: newCurrentId,
        messages: sessionId === get().currentSessionId ? [] : get().messages,
      });

      return true;
    } catch (error) {
      console.error('删除会话失败:', error);
      return false;
    }
  },

  fetchTools: async () => {
    try {
      const response = await fetch('/api/agent/tools');
      const tools = await response.json();
      set({ tools });
    } catch (error) {
      console.error('获取工具列表失败:', error);
    }
  },
  
  fetchHistory: async (sessionId: string) => {
    try {
      const response = await fetch(`/api/agent/sessions/${sessionId}/history`);
      const data = await response.json();
      if (data.success) {
        set({ messages: data.history });
      }
    } catch (error) {
      console.error('获取历史记录失败:', error);
    }
  },
}));
