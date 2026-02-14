/**
 * Agent Store状态管理
 * 
 * 管理Agent相关的状态和操作
 * 使用Zustand实现状态管理
 */

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type {
  Agent,
  AgentStatus,
  AgentMetrics,
  AgentLog,
  AgentPerformance,
  AgentTrade,
  StrategyParameter,
  PositionInfo,
  OrderInfo,
  CreateAgentRequest,
  UpdateAgentRequest,
  BatchOperationRequest,
  AgentFilterParams,
  LogQueryParams,
  TradeQueryParams,
  AgentWithPerformance,
  AgentPerformanceMetrics,
  AgentTradeRecord,
  ReturnRateDataPoint
} from '../types/agent';
import * as agentApi from '../api/agentApi';

// 请求状态
export type RequestStatus = 'idle' | 'loading' | 'success' | 'error';

// 错误信息
export interface ErrorInfo {
  message: string;
  code?: number;
  timestamp: number;
}

// Agent Store状态
interface AgentState {
  // 数据状态
  agents: AgentWithPerformance[];
  currentAgent: Agent | null;
  selectedAgent: AgentWithPerformance | null;
  totalAgents: number;
  currentPage: number;
  pageSize: number;
  
  // 监控数据
  agentMetrics: Record<number, AgentMetrics>;
  agentLogs: Record<number, AgentLog[]>;
  agentPerformance: Record<number, AgentPerformance[]>;
  agentTrades: Record<number, { items: AgentTrade[]; total: number }>;
  
  // UI展示数据
  agentPerformanceMetrics: Record<number, AgentPerformanceMetrics>;
  agentTradeRecords: Record<number, AgentTradeRecord[]>;
  agentReturnRateData: Record<number, ReturnRateDataPoint[]>;
  
  // 策略数据
  strategyParameters: Record<number, StrategyParameter[]>;
  positions: Record<number, PositionInfo[]>;
  orders: Record<number, OrderInfo[]>;
  
  // 请求状态
  listStatus: RequestStatus;
  detailStatus: RequestStatus;
  createStatus: RequestStatus;
  updateStatus: RequestStatus;
  deleteStatus: RequestStatus;
  lifecycleStatus: RequestStatus;
  metricsStatus: RequestStatus;
  logsStatus: RequestStatus;
  
  // 错误信息
  error: ErrorInfo | null;
  
  // 基础操作
  setAgents: (agents: AgentWithPerformance[]) => void;
  setCurrentAgent: (agent: Agent | null) => void;
  setSelectedAgent: (agent: AgentWithPerformance | null) => void;
  setError: (error: ErrorInfo | null) => void;
  clearError: () => void;
  
  // 选中操作
  selectAgent: (agent: AgentWithPerformance) => void;
  clearSelection: () => void;
  
  // API操作
  fetchAgents: (params?: AgentFilterParams) => Promise<void>;
  fetchAgent: (agentId: number) => Promise<void>;
  createAgent: (request: CreateAgentRequest) => Promise<void>;
  updateAgent: (agentId: number, request: UpdateAgentRequest) => Promise<void>;
  deleteAgent: (agentId: number) => Promise<void>;
  cloneAgent: (agentId: number, newName: string) => Promise<void>;
  batchOperation: (request: BatchOperationRequest) => Promise<void>;
  
  // 生命周期操作
  startAgent: (agentId: number) => Promise<void>;
  stopAgent: (agentId: number) => Promise<void>;
  restartAgent: (agentId: number) => Promise<void>;
  pauseAgent: (agentId: number) => Promise<void>;
  resumeAgent: (agentId: number) => Promise<void>;
  
  // 监控数据操作
  fetchAgentMetrics: (agentId: number) => Promise<void>;
  fetchAgentLogs: (agentId: number, params?: LogQueryParams) => Promise<void>;
  fetchAgentPerformance: (agentId: number, days?: number) => Promise<void>;
  fetchAgentTrades: (agentId: number, params?: TradeQueryParams) => Promise<void>;
  
  // UI展示数据操作
  fetchAgentPerformanceMetrics: (agentId: number) => Promise<void>;
  fetchAgentTradeRecords: (agentId: number) => Promise<void>;
  fetchAgentReturnRateData: (agentId: number) => Promise<void>;
  
  // 策略操作
  deployStrategy: (agentId: number, strategyId: number, parameters?: Record<string, any>) => Promise<void>;
  undeployStrategy: (agentId: number) => Promise<void>;
  fetchStrategyParameters: (agentId: number) => Promise<void>;
  updateStrategyParameters: (agentId: number, parameters: Record<string, any>) => Promise<void>;
  fetchPositions: (agentId: number) => Promise<void>;
  fetchOrders: (agentId: number, status?: string) => Promise<void>;
}

// 创建Agent Store
export const useAgentStore = create<AgentState>()(
  devtools(
    persist(
      (set, get) => ({
        // 初始状态
        agents: [],
        currentAgent: null,
        selectedAgent: null,
        totalAgents: 0,
        currentPage: 1,
        pageSize: 20,
        
        agentMetrics: {},
        agentLogs: {},
        agentPerformance: {},
        agentTrades: {},
        
        // UI展示数据
        agentPerformanceMetrics: {},
        agentTradeRecords: {},
        agentReturnRateData: {},
        
        strategyParameters: {},
        positions: {},
        orders: {},
        
        listStatus: 'idle',
        detailStatus: 'idle',
        createStatus: 'idle',
        updateStatus: 'idle',
        deleteStatus: 'idle',
        lifecycleStatus: 'idle',
        metricsStatus: 'idle',
        logsStatus: 'idle',
        
        error: null,
        
        // 基础操作
        setAgents: (agents) => set({ agents }),
        setCurrentAgent: (currentAgent) => set({ currentAgent }),
        setSelectedAgent: (selectedAgent) => set({ selectedAgent }),
        setError: (error) => set({ error }),
        clearError: () => set({ error: null }),
        
        // 选中操作
        selectAgent: (agent) => set({ selectedAgent: agent }),
        clearSelection: () => set({ selectedAgent: null }),
        
        // 获取Agent列表
        fetchAgents: async (params) => {
          set({ listStatus: 'loading', error: null });
          try {
            const response = await agentApi.listAgents(params);
            // 将 Agent[] 转换为 AgentWithPerformance[]
            const agentsWithPerformance: AgentWithPerformance[] = response.items.map(agent => ({
              ...agent,
              totalReturn: Math.random() * 20 - 5, // Mock 数据，实际应从API获取
              currentReturn: Math.random() * 5 - 2,
              startTime: agent.started_at,
              lastTradeTime: undefined,
              performance: generateMockPerformanceMetrics(),
              tradeRecords: [],
              returnRateData: generateMockReturnRateData(30)
            }));
            set({
              agents: agentsWithPerformance,
              totalAgents: response.total,
              currentPage: response.page,
              pageSize: response.page_size,
              listStatus: 'success'
            });
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '获取Agent列表失败',
              timestamp: Date.now()
            };
            set({ listStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 获取Agent详情
        fetchAgent: async (agentId) => {
          set({ detailStatus: 'loading', error: null });
          try {
            const agent = await agentApi.getAgent(agentId);
            set({ currentAgent: agent, detailStatus: 'success' });
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '获取Agent详情失败',
              timestamp: Date.now()
            };
            set({ detailStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 创建Agent
        createAgent: async (request) => {
          set({ createStatus: 'loading', error: null });
          try {
            const agent = await agentApi.createAgent(request);
            // 将 Agent 转换为 AgentWithPerformance
            const agentWithPerformance: AgentWithPerformance = {
              ...agent,
              totalReturn: 0,
              currentReturn: 0,
              startTime: agent.started_at,
              lastTradeTime: undefined,
              performance: generateMockPerformanceMetrics(),
              tradeRecords: [],
              returnRateData: generateMockReturnRateData(30)
            };
            set((state) => ({
              agents: [agentWithPerformance, ...state.agents],
              totalAgents: state.totalAgents + 1,
              createStatus: 'success'
            }));
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '创建Agent失败',
              timestamp: Date.now()
            };
            set({ createStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 更新Agent
        updateAgent: async (agentId, request) => {
          set({ updateStatus: 'loading', error: null });
          try {
            const agent = await agentApi.updateAgent(agentId, request);
            // 将 Agent 转换为 AgentWithPerformance，保留原有的 performance 数据
            set((state) => {
              const existingAgent = state.agents.find(a => a.id === agentId);
              const agentWithPerformance: AgentWithPerformance = {
                ...agent,
                totalReturn: existingAgent?.totalReturn ?? 0,
                currentReturn: existingAgent?.currentReturn ?? 0,
                startTime: agent.started_at,
                lastTradeTime: existingAgent?.lastTradeTime,
                performance: existingAgent?.performance ?? generateMockPerformanceMetrics(),
                tradeRecords: existingAgent?.tradeRecords ?? [],
                returnRateData: existingAgent?.returnRateData ?? generateMockReturnRateData(30)
              };
              return {
                agents: state.agents.map(a => a.id === agentId ? agentWithPerformance : a),
                currentAgent: state.currentAgent?.id === agentId ? agentWithPerformance : state.currentAgent,
                updateStatus: 'success'
              };
            });
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '更新Agent失败',
              timestamp: Date.now()
            };
            set({ updateStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 删除Agent
        deleteAgent: async (agentId) => {
          set({ deleteStatus: 'loading', error: null });
          try {
            await agentApi.deleteAgent(agentId);
            set((state) => ({
              agents: state.agents.filter(a => a.id !== agentId),
              currentAgent: state.currentAgent?.id === agentId ? null : state.currentAgent,
              totalAgents: state.totalAgents - 1,
              deleteStatus: 'success'
            }));
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '删除Agent失败',
              timestamp: Date.now()
            };
            set({ deleteStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 克隆Agent
        cloneAgent: async (agentId, newName) => {
          set({ createStatus: 'loading', error: null });
          try {
            const agent = await agentApi.cloneAgent(agentId, {
              new_name: newName,
              copy_config: true,
              copy_parameters: true
            });
            // 将 Agent 转换为 AgentWithPerformance
            const agentWithPerformance: AgentWithPerformance = {
              ...agent,
              totalReturn: 0,
              currentReturn: 0,
              startTime: agent.started_at,
              lastTradeTime: undefined,
              performance: generateMockPerformanceMetrics(),
              tradeRecords: [],
              returnRateData: generateMockReturnRateData(30)
            };
            set((state) => ({
              agents: [agentWithPerformance, ...state.agents],
              totalAgents: state.totalAgents + 1,
              createStatus: 'success'
            }));
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '克隆Agent失败',
              timestamp: Date.now()
            };
            set({ createStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 批量操作
        batchOperation: async (request) => {
          set({ lifecycleStatus: 'loading', error: null });
          try {
            await agentApi.batchOperation(request);
            // 刷新列表以获取最新状态
            await get().fetchAgents();
            set({ lifecycleStatus: 'success' });
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '批量操作失败',
              timestamp: Date.now()
            };
            set({ lifecycleStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 启动Agent
        startAgent: async (agentId) => {
          set({ lifecycleStatus: 'loading', error: null });
          try {
            await agentApi.startAgent(agentId);
            // 乐观更新状态
            set((state) => ({
              agents: state.agents.map(a =>
                a.id === agentId ? { ...a, status: 'starting' as AgentStatus } : a
              ),
              currentAgent: state.currentAgent?.id === agentId
                ? { ...state.currentAgent, status: 'starting' as AgentStatus }
                : state.currentAgent,
              lifecycleStatus: 'success'
            }));
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '启动Agent失败',
              timestamp: Date.now()
            };
            set({ lifecycleStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 停止Agent
        stopAgent: async (agentId) => {
          set({ lifecycleStatus: 'loading', error: null });
          try {
            await agentApi.stopAgent(agentId);
            set((state) => ({
              agents: state.agents.map(a =>
                a.id === agentId ? { ...a, status: 'stopping' as AgentStatus } : a
              ),
              currentAgent: state.currentAgent?.id === agentId
                ? { ...state.currentAgent, status: 'stopping' as AgentStatus }
                : state.currentAgent,
              lifecycleStatus: 'success'
            }));
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '停止Agent失败',
              timestamp: Date.now()
            };
            set({ lifecycleStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 重启Agent
        restartAgent: async (agentId) => {
          set({ lifecycleStatus: 'loading', error: null });
          try {
            await agentApi.restartAgent(agentId);
            set((state) => ({
              agents: state.agents.map(a =>
                a.id === agentId ? { ...a, status: 'starting' as AgentStatus } : a
              ),
              currentAgent: state.currentAgent?.id === agentId
                ? { ...state.currentAgent, status: 'starting' as AgentStatus }
                : state.currentAgent,
              lifecycleStatus: 'success'
            }));
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '重启Agent失败',
              timestamp: Date.now()
            };
            set({ lifecycleStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 暂停Agent
        pauseAgent: async (agentId) => {
          set({ lifecycleStatus: 'loading', error: null });
          try {
            await agentApi.pauseAgent(agentId);
            set((state) => ({
              agents: state.agents.map(a =>
                a.id === agentId ? { ...a, status: 'paused' as AgentStatus } : a
              ),
              currentAgent: state.currentAgent?.id === agentId
                ? { ...state.currentAgent, status: 'paused' as AgentStatus }
                : state.currentAgent,
              lifecycleStatus: 'success'
            }));
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '暂停Agent失败',
              timestamp: Date.now()
            };
            set({ lifecycleStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 恢复Agent
        resumeAgent: async (agentId) => {
          set({ lifecycleStatus: 'loading', error: null });
          try {
            await agentApi.resumeAgent(agentId);
            set((state) => ({
              agents: state.agents.map(a =>
                a.id === agentId ? { ...a, status: 'running' as AgentStatus } : a
              ),
              currentAgent: state.currentAgent?.id === agentId
                ? { ...state.currentAgent, status: 'running' as AgentStatus }
                : state.currentAgent,
              lifecycleStatus: 'success'
            }));
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '恢复Agent失败',
              timestamp: Date.now()
            };
            set({ lifecycleStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 获取Agent指标
        fetchAgentMetrics: async (agentId) => {
          set({ metricsStatus: 'loading' });
          try {
            const metrics = await agentApi.getAgentMetrics(agentId);
            set((state) => ({
              agentMetrics: { ...state.agentMetrics, [agentId]: metrics },
              metricsStatus: 'success'
            }));
          } catch (error) {
            set({ metricsStatus: 'error' });
            throw error;
          }
        },
        
        // 获取Agent日志
        fetchAgentLogs: async (agentId, params) => {
          set({ logsStatus: 'loading' });
          try {
            const logs = await agentApi.getAgentLogs(agentId, params);
            set((state) => ({
              agentLogs: { ...state.agentLogs, [agentId]: logs },
              logsStatus: 'success'
            }));
          } catch (error) {
            set({ logsStatus: 'error' });
            throw error;
          }
        },
        
        // 获取Agent绩效
        fetchAgentPerformance: async (agentId, days = 30) => {
          try {
            const performance = await agentApi.getAgentPerformance(agentId, days);
            set((state) => ({
              agentPerformance: { ...state.agentPerformance, [agentId]: performance }
            }));
          } catch (error) {
            throw error;
          }
        },
        
        // 获取Agent交易记录
        fetchAgentTrades: async (agentId, params) => {
          try {
            const trades = await agentApi.getAgentTrades(agentId, params);
            set((state) => ({
              agentTrades: { ...state.agentTrades, [agentId]: trades }
            }));
          } catch (error) {
            throw error;
          }
        },
        
        // 部署策略
        deployStrategy: async (agentId, strategyId, parameters) => {
          set({ updateStatus: 'loading', error: null });
          try {
            await agentApi.deployStrategy(agentId, {
              strategy_id: strategyId,
              parameters,
              auto_start: false
            });
            set({ updateStatus: 'success' });
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '部署策略失败',
              timestamp: Date.now()
            };
            set({ updateStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 卸载策略
        undeployStrategy: async (agentId) => {
          set({ updateStatus: 'loading', error: null });
          try {
            await agentApi.undeployStrategy(agentId);
            set({ updateStatus: 'success' });
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '卸载策略失败',
              timestamp: Date.now()
            };
            set({ updateStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 获取策略参数
        fetchStrategyParameters: async (agentId) => {
          try {
            const params = await agentApi.getStrategyParameters(agentId);
            set((state) => ({
              strategyParameters: { ...state.strategyParameters, [agentId]: params }
            }));
          } catch (error) {
            throw error;
          }
        },
        
        // 更新策略参数
        updateStrategyParameters: async (agentId, parameters) => {
          set({ updateStatus: 'loading', error: null });
          try {
            await agentApi.updateStrategyParameters(agentId, { parameters });
            // 刷新参数列表
            await get().fetchStrategyParameters(agentId);
            set({ updateStatus: 'success' });
          } catch (error) {
            const errorInfo: ErrorInfo = {
              message: error instanceof Error ? error.message : '更新策略参数失败',
              timestamp: Date.now()
            };
            set({ updateStatus: 'error', error: errorInfo });
            throw error;
          }
        },
        
        // 获取持仓信息
        fetchPositions: async (agentId) => {
          try {
            const positions = await agentApi.getPositions(agentId);
            set((state) => ({
              positions: { ...state.positions, [agentId]: positions }
            }));
          } catch (error) {
            throw error;
          }
        },
        
        // 获取订单信息
        fetchOrders: async (agentId, status) => {
          try {
            const orders = await agentApi.getOrders(agentId, status);
            set((state) => ({
              orders: { ...state.orders, [agentId]: orders }
            }));
          } catch (error) {
            throw error;
          }
        },

        // 获取Agent绩效指标（UI展示用）
        fetchAgentPerformanceMetrics: async (agentId) => {
          try {
            // 生成 Mock 数据
            const metrics = generateMockPerformanceMetrics();
            set((state) => ({
              agentPerformanceMetrics: { ...state.agentPerformanceMetrics, [agentId]: metrics }
            }));
          } catch (error) {
            throw error;
          }
        },

        // 获取Agent交易记录（UI展示用）
        fetchAgentTradeRecords: async (agentId) => {
          try {
            // 生成 Mock 数据，随机生成 5-15 条交易记录
            const count = Math.floor(Math.random() * 11) + 5;
            const records = generateMockTradeRecords(count);
            set((state) => ({
              agentTradeRecords: { ...state.agentTradeRecords, [agentId]: records }
            }));
          } catch (error) {
            throw error;
          }
        },

        // 获取Agent收益率曲线数据（UI展示用）
        fetchAgentReturnRateData: async (agentId) => {
          try {
            // 生成 Mock 数据，生成 30 天的收益率数据
            const data = generateMockReturnRateData(30);
            set((state) => ({
              agentReturnRateData: { ...state.agentReturnRateData, [agentId]: data }
            }));
          } catch (error) {
            throw error;
          }
        }
      }),
      {
        name: 'agent-storage',
        partialize: (state) => ({
          agents: state.agents,
          currentAgent: state.currentAgent,
          currentPage: state.currentPage,
          pageSize: state.pageSize
        })
      }
    )
  )
);

/**
 * 生成 Mock 绩效指标数据
 */
function generateMockPerformanceMetrics(): AgentPerformanceMetrics {
  const totalTrades = Math.floor(Math.random() * 200) + 50;
  const winningTrades = Math.floor(totalTrades * (0.4 + Math.random() * 0.3));
  const losingTrades = totalTrades - winningTrades;
  const winRate = (winningTrades / totalTrades) * 100;
  const totalProfit = winningTrades * (Math.random() * 100 + 50);
  const totalLoss = losingTrades * (Math.random() * 80 + 20);
  const profitLossRatio = totalLoss > 0 ? totalProfit / totalLoss : totalProfit;

  return {
    winRate: parseFloat(winRate.toFixed(2)),
    profitLossRatio: parseFloat(profitLossRatio.toFixed(2)),
    maxDrawdown: parseFloat((Math.random() * 20 + 5).toFixed(2)),
    sharpeRatio: parseFloat((Math.random() * 2 + 0.5).toFixed(2)),
    totalTrades,
    winningTrades,
    losingTrades,
    totalProfit: parseFloat(totalProfit.toFixed(2)),
    totalLoss: parseFloat(totalLoss.toFixed(2))
  };
}

/**
 * 生成 Mock 交易记录数据
 */
function generateMockTradeRecords(count: number): AgentTradeRecord[] {
  const records: AgentTradeRecord[] = [];
  const symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT'];
  const actions: Array<'buy' | 'sell'> = ['buy', 'sell'];
  const statuses: Array<'filled' | 'pending' | 'cancelled'> = ['filled', 'filled', 'filled', 'pending', 'cancelled'];

  const now = new Date();

  for (let i = 0; i < count; i++) {
    const symbol = symbols[Math.floor(Math.random() * symbols.length)];
    const action = actions[Math.floor(Math.random() * actions.length)];
    const price = Math.random() * 50000 + 10000;
    const quantity = Math.random() * 2 + 0.1;
    const amount = price * quantity;

    // 生成过去 7 天内的时间戳
    const timestamp = new Date(now.getTime() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString();

    records.push({
      id: `trade_${Date.now()}_${i}`,
      timestamp,
      symbol,
      action,
      price: parseFloat(price.toFixed(2)),
      quantity: parseFloat(quantity.toFixed(4)),
      amount: parseFloat(amount.toFixed(2)),
      status: statuses[Math.floor(Math.random() * statuses.length)]
    });
  }

  // 按时间戳降序排序
  return records.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

/**
 * 生成 Mock 收益率曲线数据
 */
function generateMockReturnRateData(days: number): ReturnRateDataPoint[] {
  const data: ReturnRateDataPoint[] = [];
  const now = new Date();
  let currentValue = 0;

  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
    // 随机波动 -5% 到 +5%
    const change = (Math.random() - 0.5) * 10;
    currentValue += change;
    // 确保收益率不会太低
    currentValue = Math.max(-30, Math.min(50, currentValue));

    data.push({
      timestamp: date.toISOString().split('T')[0],
      value: parseFloat(currentValue.toFixed(2))
    });
  }

  return data;
}
