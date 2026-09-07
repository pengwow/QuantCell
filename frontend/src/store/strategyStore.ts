/**
 * Strategy Store
 *
 * 管理策略相关的状态和业务逻辑
 * 支持两种策略类型：rule（规则策略）/ rl（RL策略）
 */

import { create } from 'zustand';
import { strategyApi } from '../api';

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
  strategy_type: 'rule' | 'rl';
  strategy_class?: string;
  code?: string;
}

// 策略状态接口
export interface StrategyState {
  strategies: Strategy[];
  selectedStrategy: Strategy | null;
  loading: boolean;
  error: string | null;

  fetchStrategies: () => Promise<void>;
  selectStrategy: (strategy: Strategy | null) => void;
  createStrategy: (data: Partial<Strategy>) => Promise<void>;
  updateStrategy: (id: string, data: Partial<Strategy>) => Promise<void>;
  deleteStrategy: (id: string) => Promise<void>;
  toggleStrategyStatus: (id: string, status: 'active' | 'inactive') => Promise<void>;
}

export const useStrategyStore = create<StrategyState>((set, get) => ({
  strategies: [],
  selectedStrategy: null,
  loading: false,
  error: null,

  fetchStrategies: async () => {
    set({ loading: true, error: null });
    try {
      const response = await strategyApi.getStrategies();
      const strategies = response?.data?.strategies || response?.strategies || [];
      set({ strategies, loading: false });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : '获取策略列表失败', loading: false });
    }
  },

  selectStrategy: (strategy: Strategy | null) => {
    set({ selectedStrategy: strategy });
  },

  createStrategy: async (data: Partial<Strategy>) => {
    set({ loading: true, error: null });
    try {
      await strategyApi.uploadStrategyFile({
        strategy_name: data.name || 'new_strategy',
        file_content: data.code || '',
        version: data.version,
        description: data.description,
        tags: data.tags,
      });
      await get().fetchStrategies();
      set({ loading: false });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : '创建策略失败', loading: false });
      throw error;
    }
  },

  updateStrategy: async (id: string, data: Partial<Strategy>) => {
    set({ loading: true, error: null });
    try {
      if (data.code && data.name) {
        await strategyApi.uploadStrategyFile({
          strategy_name: data.name,
          file_content: data.code,
          id: parseInt(id),
        });
      }
      await get().fetchStrategies();
      set({ loading: false });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : '更新策略失败', loading: false });
      throw error;
    }
  },

  deleteStrategy: async (id: string) => {
    set({ loading: true, error: null });
    try {
      const strategy = get().strategies.find(s => s.id === id);
      if (strategy) {
        await strategyApi.deleteStrategy(strategy.name);
      }
      await get().fetchStrategies();
      set({ loading: false });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : '删除策略失败', loading: false });
      throw error;
    }
  },

  toggleStrategyStatus: async (id: string, status: 'active' | 'inactive') => {
    set(state => ({
      strategies: state.strategies.map(s =>
        s.id === id ? { ...s, status } : s
      ),
    }));
  },
}));
