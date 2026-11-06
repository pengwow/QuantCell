/**
 * 研究模块专用 WebSocket 实例
 *
 * 消息只有研究事件（type=research.event，data={session_id, event}），
 * 认证走 ?token= query（与 SSE 一致，浏览器 WS 无法自定义请求头）。
 * 事件本身已持久化，断线不补发历史，实时性丢失由前端 /events 轮询兜底。
 */
import { getAccessToken } from '../utils/tokenManager';
import { WebSocketService } from './websocketService';

const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

export const researchWsService = new WebSocketService({
  // 函数式 url：每次（重）连时取最新 token，续期后无需刷新页面即可恢复连接
  url: () => {
    const token = getAccessToken();
    return `${protocol}//${window.location.host}/ws/research${
      token ? `?token=${encodeURIComponent(token)}` : ''
    }`;
  },
  // topics 留空：研究 WS 无订阅主题，只需接收服务端按 owner 推送的事件
  topics: [],
});

// 预算耗尽事件 stage（PRD §6.10 #3），App 级全局监听用
export const RESEARCH_BUDGET_EXHAUSTED_STAGE = 'session.budget_exhausted';
