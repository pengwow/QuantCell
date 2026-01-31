/**
 * WebSocket客户端服务
 * 实现WebSocket连接管理、消息处理、自动重连等功能
 */

import { v4 as uuidv4 } from 'uuid';

// WebSocket消息类型定义
export interface WebSocketMessage {
  type: string;
  id: string;
  timestamp: number;
  data?: any;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
  topic?: string;
  messages?: WebSocketMessage[]; // 用于批量消息
}

// WebSocket客户端配置
export interface WebSocketConfig {
  url: string;
  clientId?: string;
  topics?: string[];
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  pingInterval?: number;
}

// WebSocket事件监听器类型
type WebSocketEventListener = (data: any) => void;

export class WebSocketService {
  private socket: WebSocket | null = null;
  private config: WebSocketConfig;
  private reconnectAttempts: number = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setTimeout> | null = null;
  private messageListeners: Map<string, Set<WebSocketEventListener>> = new Map();
  private connectionListeners: Set<(connected: boolean) => void> = new Set();
  private messageQueue: WebSocketMessage[] = [];
  private isConnected: boolean = false;
  private clientId: string;

  constructor(config: WebSocketConfig) {
    this.config = {
      url: config.url,
      clientId: config.clientId || uuidv4(),
      topics: config.topics || [],
      reconnectInterval: config.reconnectInterval || 3000,
      maxReconnectAttempts: config.maxReconnectAttempts || 5,
      pingInterval: config.pingInterval || 30000,
    };
    this.clientId = this.config.clientId!;
  }

  /**
   * 连接WebSocket服务器
   */
  connect(): void {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      // 构建WebSocket URL
      let wsUrl = this.config.url;
      if (wsUrl.includes('?')) {
        wsUrl += `&client_id=${this.clientId}`;
      } else {
        wsUrl += `?client_id=${this.clientId}`;
      }

      if (this.config.topics && this.config.topics.length > 0) {
        wsUrl += `&topics=${this.config.topics.join(',')}`;
      }

      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        console.log('WebSocket连接已建立');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.notifyConnectionListeners(true);
        this.startPing();
        this.flushMessageQueue();
      };

      this.socket.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('解析WebSocket消息失败:', error);
        }
      };

      this.socket.onclose = () => {
        console.log('WebSocket连接已关闭');
        this.isConnected = false;
        this.notifyConnectionListeners(false);
        this.stopPing();
        this.attemptReconnect();
      };

      this.socket.onerror = (error) => {
        console.error('WebSocket错误:', error);
      };
    } catch (error) {
      console.error('WebSocket连接失败:', error);
      this.attemptReconnect();
    }
  }

  /**
   * 断开WebSocket连接
   */
  disconnect(): void {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.stopPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.isConnected = false;
    this.notifyConnectionListeners(false);
  }

  /**
   * 发送消息
   */
  send(message: Partial<WebSocketMessage>): string {
    const fullMessage: WebSocketMessage = {
      type: message.type || 'message',
      id: message.id || `msg_${this.clientId}_${Date.now()}`,
      timestamp: message.timestamp || Date.now(),
      data: message.data,
      topic: message.topic,
    };

    if (this.isConnected && this.socket) {
      try {
        this.socket.send(JSON.stringify(fullMessage));
      } catch (error) {
        console.error('发送WebSocket消息失败:', error);
        this.messageQueue.push(fullMessage);
      }
    } else {
      this.messageQueue.push(fullMessage);
      this.connect();
    }

    return fullMessage.id;
  }

  /**
   * 订阅主题
   */
  subscribe(topics: string | string[]): void {
    const topicList = Array.isArray(topics) ? topics : [topics];
    this.send({
      type: 'subscribe',
      data: {
        topics: topicList,
      },
    });
  }

  /**
   * 取消订阅主题
   */
  unsubscribe(topics: string | string[]): void {
    const topicList = Array.isArray(topics) ? topics : [topics];
    this.send({
      type: 'unsubscribe',
      data: {
        topics: topicList,
      },
    });
  }

  /**
   * 注册消息监听器
   */
  on(event: string, listener: WebSocketEventListener): void {
    if (!this.messageListeners.has(event)) {
      this.messageListeners.set(event, new Set());
    }
    this.messageListeners.get(event)!.add(listener);
  }

  /**
   * 移除消息监听器
   */
  off(event: string, listener: WebSocketEventListener): void {
    if (this.messageListeners.has(event)) {
      this.messageListeners.get(event)!.delete(listener);
    }
  }

  /**
   * 注册连接状态监听器
   */
  onConnectionChange(listener: (connected: boolean) => void): void {
    this.connectionListeners.add(listener);
  }

  /**
   * 移除连接状态监听器
   */
  offConnectionChange(listener: (connected: boolean) => void): void {
    this.connectionListeners.delete(listener);
  }

  /**
   * 获取连接状态
   */
  getConnected(): boolean {
    return this.isConnected;
  }

  /**
   * 获取客户端ID
   */
  getClientId(): string {
    return this.clientId;
  }

  /**
   * 尝试重连
   */
  private attemptReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    if (this.reconnectAttempts < this.config.maxReconnectAttempts!) {
      this.reconnectAttempts++;
      console.log(`尝试重连 (${this.reconnectAttempts}/${this.config.maxReconnectAttempts!})...`);
      
      this.reconnectTimer = setTimeout(() => {
        this.connect();
      }, this.config.reconnectInterval!);
    } else {
      console.error('WebSocket重连失败，已达到最大尝试次数');
    }
  }

  /**
   * 开始心跳检测
   */
  private startPing(): void {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      if (this.isConnected && this.socket) {
        this.send({ type: 'ping' });
      }
    }, this.config.pingInterval!);
  }

  /**
   * 停止心跳检测
   */
  private stopPing(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  /**
   * 处理接收到的消息
   */
  private handleMessage(message: WebSocketMessage): void {
        // 处理心跳响应
        if (message.type === 'pong') {
            return;
        }

        // 处理错误消息
        if (message.type === 'error') {
            console.error('WebSocket错误:', message.error);
            this.notifyListeners('error', message.error);
            return;
        }

        // 处理批量消息 - 支持两种格式
        if (message.type === 'batch') {
            let messages: WebSocketMessage[] = [];
            
            // 格式1: {"type": "batch", "messages": [...]}
            if (Array.isArray(message.messages)) {
                messages = message.messages;
            }
            // 格式2: {"type": "batch", "data": {"messages": [...]}}
            else if (message.data && Array.isArray(message.data.messages)) {
                messages = message.data.messages;
            }
            
            if (messages.length > 0) {
                console.log('处理批量消息，数量:', messages.length);
                messages.forEach((msg: WebSocketMessage) => {
                    this.handleMessage(msg);
                });
            }
            return;
        }

        // 处理任务进度更新
        if (message.type === 'task_progress') {
            console.log('收到任务进度更新:', message.data);
            this.notifyListeners('task:progress', message.data);
            this.notifyListeners('task_progress', message.data);
            return;
        }

        // 处理任务状态更新
        if (message.type === 'task_status') {
            console.log('收到任务状态更新:', message.data);
            this.notifyListeners('task:status', message.data);
            this.notifyListeners('task_status', message.data);
            return;
        }

        // 处理任务列表更新
        if (message.type === 'task_list') {
            console.log('收到任务列表更新');
            this.notifyListeners('task:list', message.data);
            this.notifyListeners('task_list', message.data);
            return;
        }

        // 处理系统信息更新
        if (message.type === 'system_info') {
            console.log('收到系统信息更新:', message.data);
            this.notifyListeners('system:info', message.data);
            this.notifyListeners('system_info', message.data);
            return;
        }

        // 处理系统状态更新
        if (message.type === 'system_status') {
            // console.log('收到系统状态更新:', message.data);
            this.notifyListeners('system:status', message.data);
            this.notifyListeners('system_status', message.data);
            return;
        }

        // 处理其他消息类型
        console.log('收到其他消息:', message.type);
        this.notifyListeners(message.type, message.data);
    }

  /**
   * 通知监听器
   */
  private notifyListeners(event: string, data: any): void {
    if (this.messageListeners.has(event)) {
      this.messageListeners.get(event)!.forEach(listener => {
        try {
          listener(data);
        } catch (error) {
          console.error(`监听器处理错误 (${event}):`, error);
        }
      });
    }
  }

  /**
   * 通知连接状态监听器
   */
  private notifyConnectionListeners(connected: boolean): void {
    this.connectionListeners.forEach(listener => {
      try {
        listener(connected);
      } catch (error) {
        console.error('连接状态监听器处理错误:', error);
      }
    });
  }

  /**
   * 发送队列中的消息
   */
  private flushMessageQueue(): void {
    while (this.messageQueue.length > 0 && this.isConnected && this.socket) {
      const message = this.messageQueue.shift();
      if (message) {
        try {
          this.socket.send(JSON.stringify(message));
        } catch (error) {
          console.error('发送队列消息失败:', error);
          this.messageQueue.unshift(message);
          break;
        }
      }
    }
  }
}

// 创建默认的WebSocket服务实例
const defaultConfig: WebSocketConfig = {
  // 直接连接到后端WebSocket服务
  url: `ws://localhost:8000/ws`,
  topics: ['task:progress', 'task:status', 'system:info', 'system:status'],
};

export const wsService = new WebSocketService(defaultConfig);

export default wsService;
