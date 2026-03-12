/**
 * Worker Store
 *
 * 管理Worker相关的状态和业务逻辑
 */

import { create } from 'zustand';
import type {
  WorkerWithPerformance,
  WorkerPerformanceMetrics,
  WorkerTradeRecord,
  ReturnRateDataPoint,
  WorkerStatus,
} from '../types/worker';

// Worker状态接口
export interface WorkerState {
  // 状态
  workers: WorkerWithPerformance[];
  selectedWorker: WorkerWithPerformance | null;
  loading: boolean;
  error: string | null;

  // Actions
  fetchWorkers: () => Promise<void>;
  selectWorker: (worker: WorkerWithPerformance) => void;
  clearSelection: () => void;
  startWorker: (id: number) => Promise<void>;
  stopWorker: (id: number) => Promise<void>;
  pauseWorker: (id: number) => Promise<void>;
  fetchWorkerPerformance: (id: number) => Promise<void>;
  fetchWorkerTrades: (id: number) => Promise<void>;
  fetchWorkerReturnRate: (id: number) => Promise<void>;
}

// Mock数据生成器 - 用于开发测试
const generateMockWorkers = (): WorkerWithPerformance[] => {
  const statuses: WorkerStatus[] = ['running', 'stopped', 'paused', 'error'];
  const now = new Date();

  return Array.from({ length: 5 }, (_, i) => {
    const id = i + 1;
    const status = statuses[i % statuses.length];
    const totalReturn = (Math.random() * 40 - 10); // -10% to 30%
    const currentReturn = (Math.random() * 10 - 5); // -5% to 5%

    return {
      id,
      name: `策略任务 ${id}`,
      description: `这是一个自动化交易策略任务，使用机器学习算法进行交易决策。`,
      status,
      strategy_id: id,
      exchange: 'binance',
      symbol: 'BTCUSDT',
      timeframe: '1h',
      market_type: 'spot',
      trading_mode: 'paper',
      cpu_limit: 50,
      memory_limit: 512,
      created_at: new Date(now.getTime() - 86400000 * 30).toISOString(),
      updated_at: now.toISOString(),
      started_at: status === 'running' ? new Date(now.getTime() - 3600000).toISOString() : undefined,
      totalReturn,
      currentReturn,
      startTime: new Date(now.getTime() - 86400000 * 7).toISOString(),
      lastTradeTime: new Date(now.getTime() - 1800000).toISOString(),
      performance: {
        winRate: 55 + Math.random() * 20,
        profitLossRatio: 1.5 + Math.random(),
        maxDrawdown: 5 + Math.random() * 10,
        sharpeRatio: 1.2 + Math.random(),
        totalTrades: Math.floor(50 + Math.random() * 200),
        winningTrades: Math.floor(30 + Math.random() * 100),
        losingTrades: Math.floor(20 + Math.random() * 80),
        totalProfit: 1000 + Math.random() * 5000,
        totalLoss: 200 + Math.random() * 1000,
      },
      tradeRecords: [],
      returnRateData: [],
    };
  });
};

// 生成Mock绩效数据
const generateMockPerformance = (): WorkerPerformanceMetrics => ({
  winRate: 55 + Math.random() * 20,
  profitLossRatio: 1.5 + Math.random(),
  maxDrawdown: 5 + Math.random() * 10,
  sharpeRatio: 1.2 + Math.random(),
  totalTrades: Math.floor(50 + Math.random() * 200),
  winningTrades: Math.floor(30 + Math.random() * 100),
  losingTrades: Math.floor(20 + Math.random() * 80),
  totalProfit: 1000 + Math.random() * 5000,
  totalLoss: 200 + Math.random() * 1000,
});

// 生成Mock交易记录
const generateMockTrades = (count: number = 10): WorkerTradeRecord[] => {
  const symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'];
  const now = new Date();

  return Array.from({ length: count }, (_, i) => {
    const isBuy = Math.random() > 0.5;
    const price = 40000 + Math.random() * 10000;
    const quantity = 0.1 + Math.random() * 0.5;

    return {
      id: `trade_${Date.now()}_${i}`,
      timestamp: new Date(now.getTime() - i * 3600000).toISOString(),
      symbol: symbols[i % symbols.length],
      action: isBuy ? 'buy' : 'sell',
      price: parseFloat(price.toFixed(2)),
      quantity: parseFloat(quantity.toFixed(4)),
      amount: parseFloat((price * quantity).toFixed(2)),
      status: Math.random() > 0.2 ? 'filled' : 'pending',
    };
  });
};

// 生成Mock收益率数据
const generateMockReturnRateData = (days: number = 30): ReturnRateDataPoint[] => {
  const data: ReturnRateDataPoint[] = [];
  const now = new Date();
  let value = 0;

  for (let i = days; i >= 0; i--) {
    const date = new Date(now.getTime() - i * 86400000);
    value += (Math.random() - 0.45) * 2; // 略微偏向上涨
    data.push({
      timestamp: date.toISOString().split('T')[0],
      value: parseFloat(value.toFixed(2)),
    });
  }

  return data;
};

// 创建Store
export const useWorkerStore = create<WorkerState>((set, get) => ({
  // 初始状态
  workers: [],
  selectedWorker: null,
  loading: false,
  error: null,

  // 获取Worker列表
  fetchWorkers: async () => {
    set({ loading: true, error: null });
    try {
      // 使用Mock数据
      const mockWorkers = generateMockWorkers();
      set({ workers: mockWorkers, loading: false });
    } catch (error: any) {
      set({ error: error.message || '获取策略任务列表失败', loading: false });
    }
  },

  // 选择Worker
  selectWorker: (worker: WorkerWithPerformance) => {
    set({ selectedWorker: worker });
    // 加载选中Worker的详细数据
    const { fetchWorkerPerformance, fetchWorkerTrades, fetchWorkerReturnRate } = get();
    fetchWorkerPerformance(worker.id);
    fetchWorkerTrades(worker.id);
    fetchWorkerReturnRate(worker.id);
  },

  // 清除选择
  clearSelection: () => {
    set({ selectedWorker: null });
  },

  // 启动Worker
  startWorker: async (id: number) => {
    try {
      // 使用Mock数据
      set(state => ({
        workers: state.workers.map(worker =>
          worker.id === id
            ? { ...worker, status: 'running' as WorkerStatus, started_at: new Date().toISOString() }
            : worker
        ),
        selectedWorker: state.selectedWorker?.id === id
          ? { ...state.selectedWorker, status: 'running' as WorkerStatus, started_at: new Date().toISOString() }
          : state.selectedWorker,
      }));
    } catch (error: any) {
      set({ error: error.message || '启动策略任务失败' });
    }
  },

  // 停止Worker
  stopWorker: async (id: number) => {
    try {
      // 使用Mock数据
      set(state => ({
        workers: state.workers.map(worker =>
          worker.id === id
            ? { ...worker, status: 'stopped' as WorkerStatus, stopped_at: new Date().toISOString() }
            : worker
        ),
        selectedWorker: state.selectedWorker?.id === id
          ? { ...state.selectedWorker, status: 'stopped' as WorkerStatus, stopped_at: new Date().toISOString() }
          : state.selectedWorker,
      }));
    } catch (error: any) {
      set({ error: error.message || '停止策略任务失败' });
    }
  },

  // 暂停Worker
  pauseWorker: async (id: number) => {
    try {
      // 使用Mock数据
      set(state => ({
        workers: state.workers.map(worker =>
          worker.id === id
            ? { ...worker, status: 'paused' as WorkerStatus }
            : worker
        ),
        selectedWorker: state.selectedWorker?.id === id
          ? { ...state.selectedWorker, status: 'paused' as WorkerStatus }
          : state.selectedWorker,
      }));
    } catch (error: any) {
      set({ error: error.message || '暂停策略任务失败' });
    }
  },

  // 获取Worker绩效
  fetchWorkerPerformance: async (id: number) => {
    try {
      // 使用Mock数据
      const performance = generateMockPerformance();
      set(state => ({
        selectedWorker: state.selectedWorker?.id === id
          ? { ...state.selectedWorker, performance }
          : state.selectedWorker,
      }));
    } catch (error: any) {
      console.error('获取策略任务绩效失败:', error);
    }
  },

  // 获取Worker交易记录
  fetchWorkerTrades: async (id: number) => {
    try {
      // 使用Mock数据
      const trades = generateMockTrades(15);
      set(state => ({
        selectedWorker: state.selectedWorker?.id === id
          ? { ...state.selectedWorker, tradeRecords: trades }
          : state.selectedWorker,
      }));
    } catch (error: any) {
      console.error('获取策略任务交易记录失败:', error);
    }
  },

  // 获取Worker收益率数据
  fetchWorkerReturnRate: async (id: number) => {
    try {
      // 使用Mock数据
      const returnRateData = generateMockReturnRateData(30);
      set(state => ({
        selectedWorker: state.selectedWorker?.id === id
          ? { ...state.selectedWorker, returnRateData }
          : state.selectedWorker,
      }));
    } catch (error: any) {
      console.error('获取策略任务收益率数据失败:', error);
    }
  },
}));
