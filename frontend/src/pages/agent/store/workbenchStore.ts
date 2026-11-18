/**
 * 工作面板（右栏）状态仓 —— 与 agentStore（会话/SSE 聊天）互不阻塞。
 *
 * 职责边界（设计文档 §2A.1）：
 * - 当前 worker（决定右面板数据域）+ 激活 Tab + 面板折叠；
 * - 各 Tab 的数据缓存（带 workerId 归属 + 拉取时间，切 worker 即失效）；
 * - 日志流连接态（SSE 挂在 store 上，切 Tab 不断流）。
 *
 * 聊天侧状态一律不进这里：messages/sessions 继续走 agentStore。
 */
import { create } from 'zustand';
import type { CascadeDecisionRecord } from '@/types/backtest';
import type { PositionInfo, OrderInfo, WorkerLog } from '@/types/worker';
import type { OverviewMetrics, TradeHistoryChart } from '@/types/worker';
import type { UnifiedModelRow } from '@/api/modelApi';

/** 右栏 Tab 键（写入 URL ?tab= 的值域） */
export type WorkbenchTab =
  | 'decisions'
  | 'positions'
  | 'performance'
  | 'models'
  | 'logs'
  | 'audit'
  | 'events';

export const WORKBENCH_TABS: WorkbenchTab[] = [
  'decisions',
  'positions',
  'performance',
  'models',
  'logs',
  'audit',
  'events',
];

export const isWorkbenchTab = (v: string | null): v is WorkbenchTab =>
  !!v && (WORKBENCH_TABS as string[]).includes(v);

/** 带缓存归属的数据条：workerId 不匹配即视为失效 */
interface CacheEntry<T> {
  workerId: number;
  data: T;
  fetchedAt: number;
}

export interface DecisionsPayload {
  total: number;
  decisions: CascadeDecisionRecord[];
}

export interface PerformancePayload {
  metrics: OverviewMetrics;
  series: TradeHistoryChart;
  /** 本次拉取使用的时间窗（回写 UI 的 Segmented） */
  window: string;
}

interface WorkbenchState {
  workerId: number | null;
  activeTab: WorkbenchTab;
  collapsed: boolean;

  decisions: CacheEntry<DecisionsPayload> | null;
  positions: CacheEntry<PositionInfo[]> | null;
  orders: CacheEntry<OrderInfo[]> | null;
  performance: CacheEntry<PerformancePayload> | null;
  models: CacheEntry<UnifiedModelRow[]> | null;

  /** 日志流（SSE）缓存与连接态 */
  logs: WorkerLog[];
  logConnected: boolean;

  setWorker: (workerId: number | null) => void;
  setTab: (tab: WorkbenchTab) => void;
  togglePanel: () => void;

  setDecisions: (workerId: number, data: DecisionsPayload) => void;
  setPositions: (workerId: number, data: PositionInfo[]) => void;
  setOrders: (workerId: number, data: OrderInfo[]) => void;
  setPerformance: (workerId: number, data: PerformancePayload) => void;
  setModels: (workerId: number, data: UnifiedModelRow[]) => void;

  appendLog: (log: WorkerLog) => void;
  setLogConnected: (connected: boolean) => void;
  clearLogs: () => void;
}

/** 日志缓冲上限：终端式滚动展示，超出裁最旧的（与 workerStore 同量级） */
const MAX_LOGS = 1000;

export const useWorkbenchStore = create<WorkbenchState>((set) => ({
  workerId: null,
  activeTab: 'decisions',
  collapsed: false,

  decisions: null,
  positions: null,
  orders: null,
  performance: null,
  models: null,

  logs: [],
  logConnected: false,

  setWorker: (workerId) =>
    // 切 worker = 换数据域：缓存整体失效，日志缓冲清空（新连接随后建立）
    set({
      workerId,
      decisions: null,
      positions: null,
      orders: null,
      performance: null,
      models: null,
      logs: [],
      logConnected: false,
    }),

  setTab: (activeTab) => set({ activeTab }),
  togglePanel: () => set((s) => ({ collapsed: !s.collapsed })),

  setDecisions: (workerId, data) => set({ decisions: { workerId, data, fetchedAt: Date.now() } }),
  setPositions: (workerId, data) => set({ positions: { workerId, data, fetchedAt: Date.now() } }),
  setOrders: (workerId, data) => set({ orders: { workerId, data, fetchedAt: Date.now() } }),
  setPerformance: (workerId, data) => set({ performance: { workerId, data, fetchedAt: Date.now() } }),
  setModels: (workerId, data) => set({ models: { workerId, data, fetchedAt: Date.now() } }),

  appendLog: (log) =>
    set((s) => {
      const logs = [...s.logs, log];
      return { logs: logs.length > MAX_LOGS ? logs.slice(logs.length - MAX_LOGS) : logs };
    }),
  setLogConnected: (logConnected) => set({ logConnected }),
  clearLogs: () => set({ logs: [] }),
}));
