/**
 * Agent Store
 *
 * 管理Agent相关的状态和业务逻辑
 */

import { create } from 'zustand';
// import { agentApi } from '../api/agentApi';
import type {
  // Agent,
  AgentWithPerformance,
  AgentPerformanceMetrics,
  AgentTradeRecord,
  ReturnRateDataPoint,
  AgentStatus,
} from '../types/agent';

// Agent状态接口
export interface AgentState {
  // 状态
  agents: AgentWithPerformance[];
  selectedAgent: AgentWithPerformance | null;
  loading: boolean;
  error: string | null;

  // Actions
  fetchAgents: () => Promise<void>;
  selectAgent: (agent: AgentWithPerformance) => void;
  clearSelection: () => void;
  startAgent: (id: number) => Promise<void>;
  stopAgent: (id: number) => Promise<void>;
  pauseAgent: (id: number) => Promise<void>;
  fetchAgentPerformance: (id: number) => Promise<void>;
  fetchAgentTrades: (id: number) => Promise<void>;
  fetchAgentReturnRate: (id: number) => Promise<void>;
}

// Mock数据生成器 - 用于开发测试
const generateMockAgents = (): AgentWithPerformance[] => {
  const statuses: AgentStatus[] = ['running', 'stopped', 'paused', 'error'];
  const now = new Date();

  return Array.from({ length: 5 }, (_, i) => {
    const id = i + 1;
    const status = statuses[i % statuses.length];
    const totalReturn = (Math.random() * 40 - 10); // -10% to 30%
    const currentReturn = (Math.random() * 10 - 5); // -5% to 5%

    return {
      id,
      name: `策略代理 ${id}`,
      description: `这是一个自动化交易策略代理，使用机器学习算法进行交易决策。`,
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
const generateMockPerformance = (): AgentPerformanceMetrics => ({
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
const generateMockTrades = (count: number = 10): AgentTradeRecord[] => {
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
export const useAgentStore = create<AgentState>((set, get) => ({
  // 初始状态
  agents: [],
  selectedAgent: null,
  loading: false,
  error: null,

  // 获取Agent列表
  fetchAgents: async () => {
    set({ loading: true, error: null });
    try {
      // 使用Mock数据
      const mockAgents = generateMockAgents();
      set({ agents: mockAgents, loading: false });

      // 实际API调用（后续启用）
      // const response = await agentApi.listAgents();
      // const agentsWithPerformance = response.items.map(agent => ({
      //   ...agent,
      //   totalReturn: 0,
      //   currentReturn: 0,
      //   performance: {} as AgentPerformanceMetrics,
      //   tradeRecords: [],
      //   returnRateData: [],
      // }));
      // set({ agents: agentsWithPerformance, loading: false });
    } catch (error: any) {
      set({ error: error.message || '获取策略代理列表失败', loading: false });
    }
  },

  // 选择Agent
  selectAgent: (agent: AgentWithPerformance) => {
    set({ selectedAgent: agent });
    // 加载选中Agent的详细数据
    const { fetchAgentPerformance, fetchAgentTrades, fetchAgentReturnRate } = get();
    fetchAgentPerformance(agent.id);
    fetchAgentTrades(agent.id);
    fetchAgentReturnRate(agent.id);
  },

  // 清除选择
  clearSelection: () => {
    set({ selectedAgent: null });
  },

  // 启动Agent
  startAgent: async (id: number) => {
    try {
      // 使用Mock数据
      set(state => ({
        agents: state.agents.map(agent =>
          agent.id === id
            ? { ...agent, status: 'running' as AgentStatus, started_at: new Date().toISOString() }
            : agent
        ),
        selectedAgent: state.selectedAgent?.id === id
          ? { ...state.selectedAgent, status: 'running' as AgentStatus, started_at: new Date().toISOString() }
          : state.selectedAgent,
      }));

      // 实际API调用（后续启用）
      // await agentApi.startAgent(id);
      // await get().fetchAgents();
    } catch (error: any) {
      set({ error: error.message || '启动策略代理失败' });
    }
  },

  // 停止Agent
  stopAgent: async (id: number) => {
    try {
      // 使用Mock数据
      set(state => ({
        agents: state.agents.map(agent =>
          agent.id === id
            ? { ...agent, status: 'stopped' as AgentStatus, stopped_at: new Date().toISOString() }
            : agent
        ),
        selectedAgent: state.selectedAgent?.id === id
          ? { ...state.selectedAgent, status: 'stopped' as AgentStatus, stopped_at: new Date().toISOString() }
          : state.selectedAgent,
      }));

      // 实际API调用（后续启用）
      // await agentApi.stopAgent(id);
      // await get().fetchAgents();
    } catch (error: any) {
      set({ error: error.message || '停止策略代理失败' });
    }
  },

  // 暂停Agent
  pauseAgent: async (id: number) => {
    try {
      // 使用Mock数据
      set(state => ({
        agents: state.agents.map(agent =>
          agent.id === id
            ? { ...agent, status: 'paused' as AgentStatus }
            : agent
        ),
        selectedAgent: state.selectedAgent?.id === id
          ? { ...state.selectedAgent, status: 'paused' as AgentStatus }
          : state.selectedAgent,
      }));

      // 实际API调用（后续启用）
      // await agentApi.pauseAgent(id);
      // await get().fetchAgents();
    } catch (error: any) {
      set({ error: error.message || '暂停策略代理失败' });
    }
  },

  // 获取Agent绩效
  fetchAgentPerformance: async (id: number) => {
    try {
      // 使用Mock数据
      const performance = generateMockPerformance();
      set(state => ({
        selectedAgent: state.selectedAgent?.id === id
          ? { ...state.selectedAgent, performance }
          : state.selectedAgent,
      }));

      // 实际API调用（后续启用）
      // const performance = await agentApi.getAgentPerformance(id);
    } catch (error: any) {
      console.error('获取策略代理绩效失败:', error);
    }
  },

  // 获取Agent交易记录
  fetchAgentTrades: async (id: number) => {
    try {
      // 使用Mock数据
      const trades = generateMockTrades(15);
      set(state => ({
        selectedAgent: state.selectedAgent?.id === id
          ? { ...state.selectedAgent, tradeRecords: trades }
          : state.selectedAgent,
      }));

      // 实际API调用（后续启用）
      // const trades = await agentApi.getAgentTrades(id);
    } catch (error: any) {
      console.error('获取策略代理交易记录失败:', error);
    }
  },

  // 获取Agent收益率数据
  fetchAgentReturnRate: async (id: number) => {
    try {
      // 使用Mock数据
      const returnRateData = generateMockReturnRateData(30);
      set(state => ({
        selectedAgent: state.selectedAgent?.id === id
          ? { ...state.selectedAgent, returnRateData }
          : state.selectedAgent,
      }));

      // 实际API调用（后续启用）
      // const returnRateData = await agentApi.getReturnRateData(id);
    } catch (error: any) {
      console.error('获取策略代理收益率数据失败:', error);
    }
  },
}));
