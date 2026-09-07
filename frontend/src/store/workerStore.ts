/**
 * Worker Store - Zustand Store
 *
 * 管理策略任务Worker的状态，包括：
 * - Worker列表数据
 * - 选中Worker的详细信息
 * - 性能指标数据
 * - 交易记录
 * - 日志数据
 * - SSE日志流连接（推荐）或 WebSocket 连接（降级）
 *
 * 使用真实API与后端交互
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
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
  OverviewState,
  OverviewWindow,
} from '../types/worker';
import { workerApi, WorkerLogStreamSSE, WorkerLogStream } from '../api/workerApi';

// ============================================
// Store State Interface
// ============================================

export interface WorkerState {
  // 数据
  workers: Worker[];
  selectedWorker: Worker | null;
  /**
   * @deprecated 自 2026-06 改为 `overview` 聚合状态。
   * 旧 WorkerPerformanceTab / WorkerTradingStatsTab 合并到 WorkerOverviewTab 后，
   * 不再单独维护 performance / tradingSummary / returnRateData。
   * 仍保留字段以避免对其他模块的影响，过渡期结束后可移除。
   */
  performance: WorkerPerformance | null;
  trades: WorkerTrade[];
  logs: WorkerLog[];
  /**
   * @deprecated 见 performance 注释。
   */
  returnRateData: ReturnRateDataPoint[];

  /**
   * 总览（Overview）聚合状态：合并自旧 performance + tradingSummary + returnRateData。
   */
  overview: OverviewState | null;
  overviewWindow: OverviewWindow;

  // 分页
  total: number;
  page: number;
  pageSize: number;

  // 加载状态
  loading: boolean;
  loadingDetail: boolean;
  loadingPerformance: boolean;
  loadingOverview: boolean;
  loadingTrades: boolean;
  loadingLogs: boolean;

  // 错误状态
  error: string | null;
  detailError: string | null;
  performanceError: string | null;
  overviewError: string | null;
  tradesError: string | null;
  logsError: string | null;

  // 日志流连接（SSE 或 WebSocket）
  logStream: WorkerLogStreamSSE | WorkerLogStream | null;
  isLogStreamConnected: boolean;

  // Message API (由 App.useApp() 注入)
  messageApi: any;
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
  fetchOverview: (workerId: number, window?: OverviewWindow) => Promise<void>;

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

  // 批量操作
  batchStartWorkers: (workerIds: number[]) => Promise<any>;
  batchStopWorkers: (workerIds: number[]) => Promise<any>;
  batchRestartWorkers: (workerIds: number[]) => Promise<any>;

  // WebSocket
  connectLogStream: (workerId: number) => void;
  disconnectLogStream: () => void;
  clearLogs: () => Promise<void>;

  // 状态管理
  setSelectedWorker: (worker: Worker | null) => void;
  updateWorkerStatus: (workerId: number, status: WorkerStatus) => void;
  clearErrors: () => void;
  reset: () => void;

  // Message API 注入
  setMessageApi: (api: any) => void;
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

  overview: null,
  overviewWindow: '30d',

  total: 0,
  page: 1,
  pageSize: 20,

  loading: false,
  loadingDetail: false,
  loadingPerformance: false,
  loadingOverview: false,
  loadingTrades: false,
  loadingLogs: false,

  error: null,
  detailError: null,
  performanceError: null,
  overviewError: null,
  tradesError: null,
  logsError: null,

  logStream: null,
  isLogStreamConnected: false,

  messageApi: null,
};

// ============================================
// Store Creation
// ============================================

export const useWorkerStore = create<WorkerState & WorkerActions>()(
  devtools(
    (set, get) => ({
      ...initialState,

      // ============================================
      // Message API 注入
      // ============================================

      setMessageApi: (api: any) => {
        set({ messageApi: api });
      },

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
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : '获取Worker列表失败',
            loading: false,
          });
          get().messageApi?.error(error instanceof Error ? error.message : '获取Worker列表失败');
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
        } catch (error) {
          set({
            detailError: error instanceof Error ? error.message : '获取Worker详情失败',
            loadingDetail: false,
          });
          get().messageApi?.error(error instanceof Error ? error.message : '获取Worker详情失败');
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
        } catch (error) {
          set({
            performanceError: error instanceof Error ? error.message : '获取绩效数据失败',
            loadingPerformance: false,
          });
          get().messageApi?.error(error instanceof Error ? error.message : '获取绩效数据失败');
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
        } catch (error) {
          set({
            tradesError: error instanceof Error ? error.message : '获取交易记录失败',
            loadingTrades: false,
          });
          get().messageApi?.error(error instanceof Error ? error.message : '获取交易记录失败');
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
        } catch (error) {
          set({
            logsError: error instanceof Error ? error.message : '获取日志失败',
            loadingLogs: false,
          });
          get().messageApi?.error(error instanceof Error ? error.message : '获取日志失败');
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
        } catch (error) {
          console.error('获取收益率数据失败:', error);
        }
      },

      fetchOverview: async (workerId, window) => {
        const targetWindow: OverviewWindow = window || get().overviewWindow || '30d';
        set({ loadingOverview: true, overviewError: null, overviewWindow: targetWindow });
        try {
          // apiRequest.get() 已在 axios 拦截器中解包 ApiResponse.data，
          // 因此 response 直接就是 { metrics, cumulative_pnl_series, pnl_distribution, window }
          const response: any = await workerApi.getOverview(workerId, targetWindow);
          if (!response || !response.metrics) {
            throw new Error('总览数据为空');
          }
          set({
            overview: {
              metrics: response.metrics,
              cumulativePnlSeries: response.cumulative_pnl_series,
              pnlDistribution: response.pnl_distribution,
              window: response.window,
              updatedAt: Date.now(),
            },
            loadingOverview: false,
          });
        } catch (error) {
          set({
            overviewError: error instanceof Error ? error.message : '获取总览数据失败',
            loadingOverview: false,
          });
          get().messageApi?.error(error instanceof Error ? error.message : '获取总览数据失败');
        }
      },

      // ============================================
      // CRUD 操作
      // ============================================

      createWorker: async (data) => {
        try {
          const worker = await workerApi.createWorker(data);
          get().messageApi?.success('Worker创建成功');
          // 刷新列表
          get().fetchWorkers();
          return worker;
        } catch (error) {
          get().messageApi?.error(error instanceof Error ? error.message : '创建Worker失败');
          return null;
        }
      },

      updateWorker: async (workerId, data) => {
        try {
          const worker = await workerApi.updateWorker(workerId, data);
          get().messageApi?.success('Worker更新成功');
          // 更新选中状态
          if (get().selectedWorker?.id === workerId) {
            set({ selectedWorker: worker });
          }
          // 刷新列表
          get().fetchWorkers();
          return worker;
        } catch (error) {
          get().messageApi?.error(error instanceof Error ? error.message : '更新Worker失败');
          return null;
        }
      },

      deleteWorker: async (workerId) => {
        try {
          await workerApi.deleteWorker(workerId);
          get().messageApi?.success('Worker删除成功');
          // 如果删除的是当前选中的，清除选中状态
          if (get().selectedWorker?.id === workerId) {
            set({ selectedWorker: null });
          }
          // 刷新列表
          get().fetchWorkers();
          return true;
        } catch (error) {
          get().messageApi?.error(error instanceof Error ? error.message : '删除Worker失败');
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
          get().messageApi?.success('Worker克隆成功');
          // 刷新列表
          get().fetchWorkers();
          return worker;
        } catch (error) {
          get().messageApi?.error(error instanceof Error ? error.message : '克隆Worker失败');
          return null;
        }
      },

      // ============================================
      // 生命周期控制
      // ============================================

      startWorker: async (workerId) => {
        try {
          await workerApi.startWorker(workerId);
          get().messageApi?.success('Worker启动中');
          // 乐观更新状态
          get().updateWorkerStatus(workerId, 'starting');
          // 延迟刷新获取最新状态
          setTimeout(() => get().fetchWorkers(), 2000);
          return true;
        } catch (error) {
          get().messageApi?.error(error instanceof Error ? error.message : '启动Worker失败');
          return false;
        }
      },

      stopWorker: async (workerId) => {
        try {
          await workerApi.stopWorker(workerId);
          get().messageApi?.success('Worker停止成功');
          // 乐观更新状态
          get().updateWorkerStatus(workerId, 'stopped');
          // 延迟刷新获取最新状态
          setTimeout(() => get().fetchWorkers(), 1000);
          return true;
        } catch (error) {
          const errorMsg = error instanceof Error ? error.message || error.toString() : error ? String(error) : '';
          // 识别"已停止"的特殊情况，将其视为成功而非错误
          if (errorMsg.includes('已停止') || errorMsg.includes('already stopped') ||
              errorMsg.includes('不允许再次停止') || errorMsg.includes('当前状态为 stopped')) {
            get().messageApi?.info('Worker已处于停止状态');
            // 即使后端返回"已停止"错误，也正确更新前端状态
            get().updateWorkerStatus(workerId, 'stopped');
            return true;
          }
          get().messageApi?.error(errorMsg || '停止Worker失败');
          return false;
        }
      },

      restartWorker: async (workerId) => {
        try {
          await workerApi.restartWorker(workerId);
          get().messageApi?.success('Worker重启中');
          // 乐观更新状态
          get().updateWorkerStatus(workerId, 'starting');
          // 延迟刷新获取最新状态
          setTimeout(() => get().fetchWorkers(), 3000);
          return true;
        } catch (error) {
          get().messageApi?.error(error instanceof Error ? error.message : '重启Worker失败');
          return false;
        }
      },

      // ============================================
      // 批量操作 Actions
      // ============================================

      batchStartWorkers: async (workerIds: number[]) => {
        const result = await workerApi.batchOperation({
          worker_ids: workerIds,
          operation: 'start',
        });
        workerIds.forEach(id => get().updateWorkerStatus(id, 'starting'));
        setTimeout(() => get().fetchWorkers(), 2000);
        return result;
      },

      batchStopWorkers: async (workerIds: number[]) => {
        const result = await workerApi.batchOperation({
          worker_ids: workerIds,
          operation: 'stop',
        });
        workerIds.forEach(id => get().updateWorkerStatus(id, 'stopped'));
        setTimeout(() => get().fetchWorkers(), 1000);
        return result;
      },

      batchRestartWorkers: async (workerIds: number[]) => {
        const result = await workerApi.batchOperation({
          worker_ids: workerIds,
          operation: 'restart',
        });
        workerIds.forEach(id => get().updateWorkerStatus(id, 'starting'));
        setTimeout(() => get().fetchWorkers(), 3000);
        return result;
      },

      // ============================================
      // SSE 日志流（推荐方案）
      // ============================================

      connectLogStream: (workerId) => {
        get().disconnectLogStream();

        // 优先使用 SSE，如果浏览器不支持则降级到 WebSocket
        const useSSE = typeof EventSource !== 'undefined';
        const stream = useSSE ? new WorkerLogStreamSSE(workerId) : new WorkerLogStream(workerId);

        let logBuffer: WorkerLog[] = [];
        let rafId: number | null = null;

        const flushLogs = () => {
          if (logBuffer.length > 0) {
            const batch = logBuffer;
            logBuffer = [];
            rafId = null;
            set((state) => ({
              logs: [...state.logs, ...batch].slice(-1000),
            }));
          }
        };

        stream.onOpen(() => {
          console.log(`✅ [WorkerStore] ${useSSE ? 'SSE' : 'WebSocket'} 连接已建立, 设置 isLogStreamConnected = true`);
          set({ isLogStreamConnected: true });
        });

        stream.onMessage((log) => {
          logBuffer.push(log);
          if (!rafId) {
            rafId = requestAnimationFrame(flushLogs);
          }
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

      clearLogs: async () => {
        const { selectedWorker } = get();
        if (selectedWorker) {
          try {
            await workerApi.clearWorkerLogs(selectedWorker.id);
          } catch (error) {
            console.error('清理日志文件失败:', error);
          }
        }
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
