/**
 * Strategy Store
 *
 * 管理策略相关的状态和业务逻辑
 */

import { create } from 'zustand';
// import { strategyApi } from '../api';

// 策略参数接口
interface StrategyParam {
  name: string;
  type: string;
  default: any;
  description: string;
  required: boolean;
}

// 策略接口
export interface Strategy {
  id: string;
  name: string;
  file_name: string;
  file_path: string;
  description: string;
  version: string;
  tags?: string[];
  params: StrategyParam[];
  created_at: string;
  updated_at: string;
  status: 'active' | 'inactive' | 'paused';
}

// 策略状态接口
export interface StrategyState {
  // 状态
  strategies: Strategy[];
  selectedStrategy: Strategy | null;
  loading: boolean;
  error: string | null;

  // Actions
  fetchStrategies: () => Promise<void>;
  selectStrategy: (strategy: Strategy | null) => void;
  createStrategy: (data: Partial<Strategy>) => Promise<void>;
  updateStrategy: (id: string, data: Partial<Strategy>) => Promise<void>;
  deleteStrategy: (id: string) => Promise<void>;
  toggleStrategyStatus: (id: string, status: 'active' | 'inactive') => Promise<void>;
}

// Mock数据生成器
const generateMockStrategies = (): Strategy[] => {
  return [
    {
      id: '1',
      name: '双均线策略',
      file_name: 'dual_ma.py',
      file_path: '/strategies/dual_ma.py',
      description: '基于双均线交叉的交易策略',
      version: '1.0.0',
      tags: ['趋势', '均线'],
      params: [
        { name: 'fast_ma', type: 'number', default: 10, description: '快速均线周期', required: true },
        { name: 'slow_ma', type: 'number', default: 20, description: '慢速均线周期', required: true },
      ],
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      status: 'active',
    },
    {
      id: '2',
      name: 'MACD策略',
      file_name: 'macd_strategy.py',
      file_path: '/strategies/macd_strategy.py',
      description: '基于MACD指标的交易策略',
      version: '1.0.0',
      tags: ['趋势', 'MACD'],
      params: [
        { name: 'fast', type: 'number', default: 12, description: '快速EMA周期', required: true },
        { name: 'slow', type: 'number', default: 26, description: '慢速EMA周期', required: true },
        { name: 'signal', type: 'number', default: 9, description: '信号线周期', required: true },
      ],
      created_at: '2024-01-02T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
      status: 'inactive',
    },
    {
      id: '3',
      name: 'RSI策略',
      file_name: 'rsi_strategy.py',
      file_path: '/strategies/rsi_strategy.py',
      description: '基于RSI指标的交易策略',
      version: '1.0.0',
      tags: ['震荡', 'RSI'],
      params: [
        { name: 'rsi_period', type: 'number', default: 14, description: 'RSI周期', required: true },
        { name: 'overbought', type: 'number', default: 70, description: '超买阈值', required: true },
        { name: 'oversold', type: 'number', default: 30, description: '超卖阈值', required: true },
      ],
      created_at: '2024-01-03T00:00:00Z',
      updated_at: '2024-01-03T00:00:00Z',
      status: 'active',
    },
  ];
};

// 创建Store
export const useStrategyStore = create<StrategyState>((set) => ({
  // 初始状态
  strategies: [],
  selectedStrategy: null,
  loading: false,
  error: null,

  // 获取策略列表
  fetchStrategies: async () => {
    set({ loading: true, error: null });
    try {
      // 使用Mock数据
      const mockStrategies = generateMockStrategies();
      set({ strategies: mockStrategies, loading: false });

      // 实际API调用（后续启用）
      // const data = await strategyApi.getStrategies();
      // set({ strategies: data, loading: false });
    } catch (error: any) {
      set({ error: error.message || '获取策略列表失败', loading: false });
    }
  },

  // 选择策略
  selectStrategy: (strategy: Strategy | null) => {
    set({ selectedStrategy: strategy });
  },

  // 创建策略
  createStrategy: async (data: Partial<Strategy>) => {
    set({ loading: true, error: null });
    try {
      // 使用Mock数据
      const newStrategy: Strategy = {
        id: Date.now().toString(),
        name: data.name || '新策略',
        file_name: data.file_name || 'strategy.py',
        file_path: data.file_path || '/strategies/strategy.py',
        description: data.description || '',
        version: '1.0.0',
        tags: data.tags || [],
        params: data.params || [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: 'inactive',
      };
      set(state => ({
        strategies: [...state.strategies, newStrategy],
        loading: false,
      }));

      // 实际API调用（后续启用）
      // await strategyApi.createStrategy(data);
      // await get().fetchStrategies();
    } catch (error: any) {
      set({ error: error.message || '创建策略失败', loading: false });
      throw error;
    }
  },

  // 更新策略
  updateStrategy: async (id: string, data: Partial<Strategy>) => {
    set({ loading: true, error: null });
    try {
      set(state => ({
        strategies: state.strategies.map(s =>
          s.id === id ? { ...s, ...data, updated_at: new Date().toISOString() } : s
        ),
        selectedStrategy: state.selectedStrategy?.id === id
          ? { ...state.selectedStrategy, ...data, updated_at: new Date().toISOString() }
          : state.selectedStrategy,
        loading: false,
      }));

      // 实际API调用（后续启用）
      // await strategyApi.updateStrategy(id, data);
      // await get().fetchStrategies();
    } catch (error: any) {
      set({ error: error.message || '更新策略失败', loading: false });
      throw error;
    }
  },

  // 删除策略
  deleteStrategy: async (id: string) => {
    set({ loading: true, error: null });
    try {
      set(state => ({
        strategies: state.strategies.filter(s => s.id !== id),
        selectedStrategy: state.selectedStrategy?.id === id ? null : state.selectedStrategy,
        loading: false,
      }));

      // 实际API调用（后续启用）
      // await strategyApi.deleteStrategy(id);
      // await get().fetchStrategies();
    } catch (error: any) {
      set({ error: error.message || '删除策略失败', loading: false });
      throw error;
    }
  },

  // 切换策略状态
  toggleStrategyStatus: async (id: string, status: 'active' | 'inactive') => {
    try {
      set(state => ({
        strategies: state.strategies.map(s =>
          s.id === id ? { ...s, status } : s
        ),
        selectedStrategy: state.selectedStrategy?.id === id
          ? { ...state.selectedStrategy, status }
          : state.selectedStrategy,
      }));

      // 实际API调用（后续启用）
      // await strategyApi.toggleStrategyStatus(id, status);
    } catch (error: any) {
      set({ error: error.message || '切换策略状态失败' });
      throw error;
    }
  },
}));
