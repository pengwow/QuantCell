/**
 * Worker Store - Zustand Store
 *
 * 管理策略任务Worker的状态，包括：
 * - Worker列表数据
 * - 选中Worker的详细信息
 * - 性能指标数据
 * - 交易记录
 * - 日志数据
 * - WebSocket连接
 *
 * 使用真实API与后端交互
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import { message } from 'antd';
import type {
  Worker,
  WorkerStatus,
  WorkerPerformance,
  WorkerTrade,
  WorkerLog,
  ReturnRateDataPoint,
  CreateWorkerRequest,
  UpdateWorkerRequest,
  WorkerFilterParams,
  TradeQueryParams,
  LogQueryParams,
} from '../types/worker';
import { workerApi, WorkerLogStream } from '../api/workerApi';

// ============================================
// Store State Interface
// ============================================

export interface WorkerState {
  // 数据
  workers: Worker[];
  selectedWorker: Worker | null;
  performance: WorkerPerformance | null;
  trades: WorkerTrade[];
  logs: WorkerLog[];
  returnRateData: ReturnRateDataPoint[];

  // 分页
  total: number;
  page: number;
  pageSize: number;

  // 加载状态
  loading: boolean;
  loadingDetail: boolean;
  loadingPerformance: boolean;
  loadingTrades: boolean;
  loadingLogs: boolean;

  // 错误状态
  error: string | null;
  detailError: string | null;
  performanceError: string | null;
  tradesError: string | null;
  logsError: string | null;

  // WebSocket
  logStream: WorkerLogStream | null;
  isLogStreamConnected: boolean;
}

// ============================================
// Store Actions Interface
// ============================================

interface WorkerActions {
  // 数据获取
  fetchWorkers: (params?: WorkerFilterParams) => Promise<void>;
  fetchWorkerDetail: (workerId: number) => Promise<void>;
  fetchPerformance: (workerId: number, days?: number) => Promise<void>;
  fetchTrades: (workerId: number, params?: TradeQueryParams) => Promise<void>;
  fetchLogs: (workerId: number, params?: LogQueryParams) => Promise<void>;
  fetchReturnRateData: (workerId: number, days?: number) => Promise<void>;

  // CRUD 操作
  createWorker: (data: CreateWorkerRequest) => Promise<Worker | null>;
  updateWorker: (workerId: number, data: UpdateWorkerRequest) => Promise<Worker | null>;
  deleteWorker: (workerId: number) => Promise<boolean>;
  cloneWorker: (workerId: number, newName: string) => Promise<Worker | null>;

  // 生命周期控制
  startWorker: (workerId: number) => Promise<boolean>;
  stopWorker: (workerId: number) => Promise<boolean>;
  pauseWorker: (workerId: number) => Promise<boolean>;
  resumeWorker: (workerId: number) => Promise<boolean>;
  restartWorker: (workerId: number) => Promise<boolean>;

  // WebSocket
  connectLogStream: (workerId: number) => void;
  disconnectLogStream: () => void;
  clearLogs: () => void;

  // 状态管理
  setSelectedWorker: (worker: Worker | null) => void;
  updateWorkerStatus: (workerId: number, status: WorkerStatus) => void;
  clearErrors: () => void;
  reset: () => void;
}

// ============================================
// Initial State
// ============================================

const initialState: WorkerState = {
  workers: [],
  selectedWorker: null,
  performance: null,
  trades: [],
  logs: [],
  returnRateData: [],

  total: 0,
  page: 1,
  pageSize: 20,

  loading: false,
  loadingDetail: false,
  loadingPerformance: false,
  loadingTrades: false,
  loadingLogs: false,

  error: null,
  detailError: null,
  performanceError: null,
  tradesError: null,
  logsError: null,

  logStream: null,
  isLogStreamConnected: false,
};

// ============================================
// Store Creation
// ============================================

export const useWorkerStore = create<WorkerState & WorkerActions>()(
  devtools(
    (set, get) => ({
      ...initialState,

      // ============================================
      // 数据获取操作
      // ============================================

      fetchWorkers: async (params) => {
        set({ loading: true, error: null });
        try {
          const response = await workerApi.getWorkers({
            page: get().page,
            page_size: get().pageSize,
            ...params,
          });
          set({
            workers: response.items,
            total: response.total,
            page: response.page,
            pageSize: response.page_size,
            loading: false,
          });
        } catch (error: any) {
          set({
            error: error.message || '获取Worker列表失败',
            loading: false,
          });
          message.error(error.message || '获取Worker列表失败');
        }
      },

      fetchWorkerDetail: async (workerId) => {
        set({ loadingDetail: true, detailError: null });
        try {
          const worker = await workerApi.getWorker(workerId);
          set({
            selectedWorker: worker,
            loadingDetail: false,
          });
        } catch (error: any) {
          set({
            detailError: error.message || '获取Worker详情失败',
            loadingDetail: false,
          });
          message.error(error.message || '获取Worker详情失败');
        }
      },

      fetchPerformance: async (workerId, days = 30) => {
        set({ loadingPerformance: true, performanceError: null });
        try {
          const performance = await workerApi.getWorkerPerformance(workerId, days);
          // 取最新的绩效数据
          const latestPerformance = performance[performance.length - 1] || null;
          set({
            performance: latestPerformance,
            loadingPerformance: false,
          });
        } catch (error: any) {
          set({
            performanceError: error.message || '获取绩效数据失败',
            loadingPerformance: false,
          });
          message.error(error.message || '获取绩效数据失败');
        }
      },

      fetchTrades: async (workerId, params) => {
        set({ loadingTrades: true, tradesError: null });
        try {
          const response = await workerApi.getWorkerTrades(workerId, {
            page: 1,
            page_size: 50,
            ...params,
          });
          set({
            trades: response.items,
            loadingTrades: false,
          });
        } catch (error: any) {
          set({
            tradesError: error.message || '获取交易记录失败',
            loadingTrades: false,
          });
          message.error(error.message || '获取交易记录失败');
        }
      },

      fetchLogs: async (workerId, params) => {
        set({ loadingLogs: true, logsError: null });
        try {
          const logs = await workerApi.getWorkerLogs(workerId, {
            page_size: 100,
            ...params,
          });
          set({
            logs: logs,
            loadingLogs: false,
          });
        } catch (error: any) {
          set({
            logsError: error.message || '获取日志失败',
            loadingLogs: false,
          });
          message.error(error.message || '获取日志失败');
        }
      },

      fetchReturnRateData: async (workerId, days = 30) => {
        try {
          const performance = await workerApi.getWorkerPerformance(workerId, days);
          // 将绩效数据转换为收益率曲线数据
          const returnRateData: ReturnRateDataPoint[] = performance.map((p, index) => ({
            timestamp: p.date,
            value: index === 0 ? 0 : ((p.net_profit / (p.total_trades || 1)) * 100),
          }));
          set({ returnRateData });
        } catch (error: any) {
          console.error('获取收益率数据失败:', error);
        }
      },

      // ============================================
      // CRUD 操作
      // ============================================

      createWorker: async (data) => {
        try {
          const worker = await workerApi.createWorker(data);
          message.success('Worker创建成功');
          // 刷新列表
          get().fetchWorkers();
          return worker;
        } catch (error: any) {
          message.error(error.message || '创建Worker失败');
          return null;
        }
      },

      updateWorker: async (workerId, data) => {
        try {
          const worker = await workerApi.updateWorker(workerId, data);
          message.success('Worker更新成功');
          // 更新选中状态
          if (get().selectedWorker?.id === workerId) {
            set({ selectedWorker: worker });
          }
          // 刷新列表
          get().fetchWorkers();
          return worker;
        } catch (error: any) {
          message.error(error.message || '更新Worker失败');
          return null;
        }
      },

      deleteWorker: async (workerId) => {
        try {
          await workerApi.deleteWorker(workerId);
          message.success('Worker删除成功');
          // 如果删除的是当前选中的，清除选中状态
          if (get().selectedWorker?.id === workerId) {
            set({ selectedWorker: null });
          }
          // 刷新列表
          get().fetchWorkers();
          return true;
        } catch (error: any) {
          message.error(error.message || '删除Worker失败');
          return false;
        }
      },

      cloneWorker: async (workerId, newName) => {
        try {
          const worker = await workerApi.cloneWorker(workerId, {
            new_name: newName,
            copy_config: true,
            copy_parameters: true,
          });
          message.success('Worker克隆成功');
          // 刷新列表
          get().fetchWorkers();
          return worker;
        } catch (error: any) {
          message.error(error.message || '克隆Worker失败');
          return null;
        }
      },

      // ============================================
      // 生命周期控制
      // ============================================

      startWorker: async (workerId) => {
        try {
          await workerApi.startWorker(workerId);
          message.success('Worker启动中');
          // 乐观更新状态
          get().updateWorkerStatus(workerId, 'starting');
          // 延迟刷新获取最新状态
          setTimeout(() => get().fetchWorkers(), 2000);
          return true;
        } catch (error: any) {
          message.error(error.message || '启动Worker失败');
          return false;
        }
      },

      stopWorker: async (workerId) => {
        try {
          await workerApi.stopWorker(workerId);
          message.success('Worker停止成功');
          // 乐观更新状态
          get().updateWorkerStatus(workerId, 'stopped');
          // 延迟刷新获取最新状态
          setTimeout(() => get().fetchWorkers(), 1000);
          return true;
        } catch (error: any) {
          message.error(error.message || '停止Worker失败');
          return false;
        }
      },

      pauseWorker: async (workerId) => {
        try {
          await workerApi.pauseWorker(workerId);
          message.success('Worker已暂停');
          // 乐观更新状态
          get().updateWorkerStatus(workerId, 'paused');
          // 延迟刷新获取最新状态
          setTimeout(() => get().fetchWorkers(), 1000);
          return true;
        } catch (error: any) {
          message.error(error.message || '暂停Worker失败');
          return false;
        }
      },

      resumeWorker: async (workerId) => {
        try {
          await workerApi.resumeWorker(workerId);
          message.success('Worker已恢复');
          // 乐观更新状态
          get().updateWorkerStatus(workerId, 'running');
          // 延迟刷新获取最新状态
          setTimeout(() => get().fetchWorkers(), 1000);
          return true;
        } catch (error: any) {
          message.error(error.message || '恢复Worker失败');
          return false;
        }
      },

      restartWorker: async (workerId) => {
        try {
          await workerApi.restartWorker(workerId);
          message.success('Worker重启中');
          // 乐观更新状态
          get().updateWorkerStatus(workerId, 'starting');
          // 延迟刷新获取最新状态
          setTimeout(() => get().fetchWorkers(), 3000);
          return true;
        } catch (error: any) {
          message.error(error.message || '重启Worker失败');
          return false;
        }
      },

      // ============================================
      // WebSocket 日志流
      // ============================================

      connectLogStream: (workerId) => {
        // 先断开现有连接
        get().disconnectLogStream();

        const stream = new WorkerLogStream(workerId);

        stream.onMessage((log) => {
          set((state) => ({
            logs: [...state.logs, log].slice(-1000), // 新日志追加到末尾（正序：旧→新），限制最多1000条
          }));
        });

        stream.onError((error) => {
          console.error('Log stream error:', error);
          set({ isLogStreamConnected: false });
        });

        stream.onClose(() => {
          set({ isLogStreamConnected: false });
        });

        stream.connect();

        set({
          logStream: stream,
          isLogStreamConnected: true,
        });
      },

      disconnectLogStream: () => {
        const { logStream } = get();
        if (logStream) {
          logStream.disconnect();
          set({
            logStream: null,
            isLogStreamConnected: false,
          });
        }
      },

      clearLogs: () => {
        set({ logs: [] });
      },

      // ============================================
      // 状态管理
      // ============================================

      setSelectedWorker: (worker) => {
        set({ selectedWorker: worker });
        // 如果选中了worker，连接日志流
        if (worker) {
          get().connectLogStream(worker.id);
        } else {
          get().disconnectLogStream();
        }
      },

      updateWorkerStatus: (workerId, status) => {
        set((state) => ({
          workers: state.workers.map((w) =>
            w.id === workerId ? { ...w, status } : w
          ),
          selectedWorker:
            state.selectedWorker?.id === workerId
              ? { ...state.selectedWorker, status }
              : state.selectedWorker,
        }));
      },

      clearErrors: () => {
        set({
          error: null,
          detailError: null,
          performanceError: null,
          tradesError: null,
          logsError: null,
        });
      },

      reset: () => {
        get().disconnectLogStream();
        set(initialState);
      },
    }),
    { name: 'worker-store' }
  )
);

export default useWorkerStore;
