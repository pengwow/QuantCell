/**
 * Agent 页顶部 Worker 选择器状态。
 *
 * 原来这里还承载右栏 8 页签工作台（决策流/持仓/绩效/模型/日志/审计/事件/自迭代）的
 * 缓存、Tab 键与日志 SSE 连接态；右栏已按 demo 收敛成「迭代足迹 + 记忆自迭代」两卡，
 * 页签整体删除，因此只剩 worker 选择本身（仍决定会话上下文与 URL ?worker= 持久化）。
 */
import { create } from 'zustand';

interface AgentWorkerState {
  workerId: number | null;
  setWorker: (workerId: number | null) => void;
}

export const useAgentWorkerStore = create<AgentWorkerState>((set) => ({
  workerId: null,
  setWorker: (workerId) => set({ workerId }),
}));
