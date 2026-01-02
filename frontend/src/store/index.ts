import { create } from 'zustand';
import type { Strategy, Task, CryptoCurrency, Stock } from '../types';
import { dataApi, configApi } from '../api';

/**
 * 配置项类型定义
 */
export interface ConfigItem {
  key: string;
  value: any;
  description: string;
}

/**
 * 系统配置状态管理
 */
export interface ConfigState {
  // 配置数据，以键值对形式存储
  configs: Record<string, ConfigItem>;
  // 加载状态
  isLoading: boolean;
  // 最后加载时间戳
  lastLoaded: number | null;
  // 操作方法
  loadConfigs: () => Promise<void>;
  updateConfig: (key: string, value: any, description: string) => Promise<void>;
  updateConfigs: (configs: ConfigItem[]) => Promise<void>;
  refreshConfigs: () => Promise<void>;
}

/**
 * 策略状态管理
 */
export interface StrategyState {
  // 策略列表
  strategies: Strategy[];
  // 选中的策略
  selectedStrategy: Strategy | null;
  // 统计数据
  totalExecutions: number;
  successfulExecutions: number;
  failedExecutions: number;
  activeStrategies: number;
  // 模态框显示状态
  showDetailModal: boolean;
  // 加载状态
  isLoading: boolean;
  // 操作方法
  loadStrategies: () => Promise<void>;
  loadExecutionStats: () => Promise<void>;
  viewStrategyDetail: (strategyId: string) => void;
  closeDetailModal: () => void;
  editStrategy: (strategyId: string) => void;
  toggleStrategyStatus: (strategyId: string) => void;
  createNewStrategy: () => void;
  refreshData: () => void;
}

/**
 * 创建策略状态管理
 */
export const useStrategyStore = create<StrategyState>((set, get) => ({
  // 初始状态
  strategies: [],
  selectedStrategy: null,
  totalExecutions: 0,
  successfulExecutions: 0,
  failedExecutions: 0,
  activeStrategies: 0,
  showDetailModal: false,
  isLoading: false,

  /**
   * 加载策略列表
   */
  loadStrategies: async () => {
    set({ isLoading: true });
    try {
      // 模拟API调用获取策略数据
      // 在实际应用中，这里应该调用真实的后端API
      const strategies: Strategy[] = [
        {
          id: '1',
          name: '高优先级告警处理',
          description: '自动处理高优先级告警，执行预设的应急响应流程',
          status: 'active',
          statusText: '活跃',
          createdAt: '2024-01-15 10:30:00',
          updatedAt: '2024-01-20 14:20:00',
          createdBy: '系统管理员',
          executionFrequency: '实时',
          ruleCount: 12,
          executionHistory: [
            { timestamp: '2024-01-20 15:30:00', status: 'success' },
            { timestamp: '2024-01-20 14:15:00', status: 'success' },
            { timestamp: '2024-01-20 10:45:00', status: 'failed' }
          ]
        },
        {
          id: '2',
          name: '资源使用率监控',
          description: '监控服务器CPU、内存、磁盘使用率，超过阈值时发出告警',
          status: 'active',
          statusText: '活跃',
          createdAt: '2024-01-10 09:15:00',
          updatedAt: '2024-01-18 11:40:00',
          createdBy: '运维工程师',
          executionFrequency: '5分钟',
          ruleCount: 8,
          executionHistory: [
            { timestamp: '2024-01-20 15:00:00', status: 'success' },
            { timestamp: '2024-01-20 14:55:00', status: 'success' },
            { timestamp: '2024-01-20 14:50:00', status: 'success' }
          ]
        },
        {
          id: '3',
          name: '异常登录检测',
          description: '检测异常登录行为，包括非常规时间、非常规地点登录',
          status: 'inactive',
          statusText: '停用',
          createdAt: '2024-01-05 16:20:00',
          updatedAt: '2024-01-12 13:10:00',
          createdBy: '安全管理员',
          executionFrequency: '实时',
          ruleCount: 15,
          executionHistory: [
            { timestamp: '2024-01-15 09:30:00', status: 'success' },
            { timestamp: '2024-01-14 18:20:00', status: 'success' }
          ]
        }
      ];
      set({ strategies, isLoading: false });
    } catch (error) {
      console.error('加载策略列表失败:', error);
      set({ isLoading: false });
    }
  },

  /**
   * 加载执行统计数据
   */
  loadExecutionStats: async () => {
    try {
      // 模拟API调用获取统计数据
      set({
        totalExecutions: 456,
        successfulExecutions: 428,
        failedExecutions: 28,
        activeStrategies: 2
      });
    } catch (error) {
      console.error('加载执行统计数据失败:', error);
    }
  },

  /**
   * 查看策略详情
   * @param strategyId 策略ID
   */
  viewStrategyDetail: (strategyId: string) => {
    const { strategies } = get();
    const selectedStrategy = strategies.find(s => s.id === strategyId) || null;
    set({ selectedStrategy, showDetailModal: true });
  },

  /**
   * 关闭详情模态框
   */
  closeDetailModal: () => {
    set({ showDetailModal: false, selectedStrategy: null });
  },

  /**
   * 编辑策略
   * @param strategyId 策略ID
   */
  editStrategy: (strategyId: string) => {
    console.log('编辑策略:', strategyId);
    alert(`编辑策略 ${strategyId}`);
  },

  /**
   * 切换策略状态
   * @param strategyId 策略ID
   */
  toggleStrategyStatus: (strategyId: string) => {
    set(state => {
      const strategies: Strategy[] = state.strategies.map(strategy => {
        if (strategy.id === strategyId) {
          const newStatus = strategy.status === 'active' ? 'inactive' : 'active';
          return {
            ...strategy,
            status: newStatus as 'active' | 'inactive',
            statusText: newStatus === 'active' ? '活跃' : '停用'
          };
        }
        return strategy;
      });
      const activeStrategies = strategies.filter(s => s.status === 'active').length;
      return { strategies, activeStrategies };
    });
  },

  /**
   * 创建新策略
   */
  createNewStrategy: () => {
    console.log('创建新策略');
    alert('创建新策略功能');
  },

  /**
   * 刷新数据
   */
  refreshData: () => {
    console.log('刷新数据');
    get().loadStrategies();
    get().loadExecutionStats();
  }
}));

/**
 * 数据管理状态管理
 */
export interface DataManagementState {
  // 当前选中的标签页
  currentTab: string;
  // 加密货币数据
  cryptoData: CryptoCurrency[];
  // 股票数据
  stockData: Stock[];
  // 任务列表
  tasks: Task[];
  // 加载状态
  isLoading: boolean;
  // 操作方法
  refreshCryptoData: () => void;
  refreshStockData: () => void;
  getTasks: () => Promise<void>;
}

/**
 * 创建数据管理状态管理
 */
export const useDataManagementStore = create<DataManagementState>((set) => ({
  // 初始状态
  currentTab: 'asset-pools',
  cryptoData: [
    {
      id: 'bitcoin',
      name: '比特币',
      symbol: 'BTC',
      currentPrice: 42567.89,
      priceChange24h: 2.56,
      marketCap: 815245678901,
      tradingVolume: 35678901234
    },
    {
      id: 'ethereum',
      name: '以太坊',
      symbol: 'ETH',
      currentPrice: 2245.67,
      priceChange24h: -1.23,
      marketCap: 268901234567,
      tradingVolume: 18901234567
    },
    {
      id: 'binancecoin',
      name: '币安币',
      symbol: 'BNB',
      currentPrice: 345.67,
      priceChange24h: 0.89,
      marketCap: 56789012345,
      tradingVolume: 4567890123
    },
    {
      id: 'cardano',
      name: '卡尔达诺',
      symbol: 'ADA',
      currentPrice: 1.23,
      priceChange24h: 5.67,
      marketCap: 41234567890,
      tradingVolume: 3234567890
    },
    {
      id: 'solana',
      name: '索拉纳',
      symbol: 'SOL',
      currentPrice: 102.34,
      priceChange24h: -2.34,
      marketCap: 34567890123,
      tradingVolume: 2890123456
    }
  ],
  stockData: [
    {
      symbol: 'AAPL',
      companyName: '苹果公司',
      currentPrice: 187.45,
      priceChange: 2.34,
      priceChangePercent: 1.26,
      openPrice: 185.23,
      highPrice: 188.76,
      lowPrice: 184.98
    },
    {
      symbol: 'MSFT',
      companyName: '微软公司',
      currentPrice: 401.23,
      priceChange: -3.45,
      priceChangePercent: -0.85,
      openPrice: 404.68,
      highPrice: 405.12,
      lowPrice: 399.87
    },
    {
      symbol: 'GOOGL',
      companyName: 'Alphabet公司',
      currentPrice: 176.89,
      priceChange: 1.23,
      priceChangePercent: 0.70,
      openPrice: 175.66,
      highPrice: 177.45,
      lowPrice: 175.23
    },
    {
      symbol: 'AMZN',
      companyName: '亚马逊公司',
      currentPrice: 178.45,
      priceChange: -0.56,
      priceChangePercent: -0.31,
      openPrice: 179.01,
      highPrice: 180.23,
      lowPrice: 178.12
    },
    {
      symbol: 'TSLA',
      companyName: '特斯拉公司',
      currentPrice: 176.32,
      priceChange: 5.67,
      priceChangePercent: 3.31,
      openPrice: 170.65,
      highPrice: 177.89,
      lowPrice: 169.98
    }
  ],
  tasks: [],
  isLoading: false,

  /**
   * 刷新加密货币数据
   */
  refreshCryptoData: () => {
    console.log('刷新加密货币数据');
    // 模拟刷新数据操作
  },

  /**
   * 刷新股票数据
   */
  refreshStockData: () => {
    console.log('刷新股票数据');
    // 模拟刷新数据操作
  },

  /**
   * 获取任务列表
   */
  getTasks: async () => {
    set({ isLoading: true });
    try {
      // 调用API获取任务列表，只获取download_crypto类型的任务
      const params = {
        page: 1,
        page_size: 5,
        sort_by: 'created_at',
        sort_order: 'desc',
        task_type: 'download_crypto'
      };
      
      // 调用API获取任务列表
      const response = await dataApi.getTasks(params);
      
      // 处理API响应，提取任务列表数据
      // 注意：由于API响应拦截器直接返回data字段，所以这里直接使用response.tasks
      const tasks: Task[] = Array.isArray(response.tasks) ? response.tasks : [];
      
      set({ tasks, isLoading: false });
    } catch (error) {
      console.error('获取任务列表失败:', error);
      set({ isLoading: false });
    }
  }
}));

/**
 * 创建系统配置状态管理
 */
export const useConfigStore = create<ConfigState>((set, get) => ({
  // 初始状态
  configs: {},
  isLoading: false,
  lastLoaded: null,

  /**
   * 加载系统配置
   */
  loadConfigs: async () => {
    const state = get();
    const now = Date.now();
    const CACHE_DURATION = 5 * 60 * 1000; // 缓存有效期5分钟
    
    // 检查是否正在加载或缓存未过期
    if (state.isLoading) {
      return; // 已有请求正在进行，直接返回
    }
    
    if (state.lastLoaded && (now - state.lastLoaded < CACHE_DURATION)) {
      return; // 缓存未过期，直接返回
    }
    
    set({ isLoading: true });
    try {
      // 调用API获取配置数据
      const configData = await configApi.getConfig();
      console.log('加载配置成功:', configData);
      
      // 将配置数据转换为键值对形式存储
      const formattedConfigs: Record<string, ConfigItem> = {};
      
      // 如果configData是数组形式，转换为键值对
      if (Array.isArray(configData)) {
        configData.forEach(item => {
          formattedConfigs[item.key] = item;
        });
      } else {
        // 如果configData已经是对象形式，直接使用
        Object.keys(configData).forEach(key => {
          const item = configData[key];
          formattedConfigs[key] = {
            key,
            value: item.value,
            description: item.description || ''
          };
        });
      }
      
      set({ configs: formattedConfigs, isLoading: false, lastLoaded: now });
    } catch (error) {
      console.error('加载配置失败:', error);
      set({ isLoading: false });
    }
  },

  /**
   * 更新单个配置项
   * @param key 配置键名
   * @param value 配置值
   * @param description 配置描述
   */
  updateConfig: async (key: string, value: any, description: string) => {
    try {
      // 调用API更新单个配置
      await configApi.updateConfig([{
        key,
        value,
        description
      }]);
      
      // 更新本地状态
      set(state => ({
        configs: {
          ...state.configs,
          [key]: {
            key,
            value,
            description
          }
        }
      }));
    } catch (error) {
      console.error('更新配置失败:', error);
      throw error;
    }
  },

  /**
   * 批量更新配置项
   * @param configs 配置项数组
   */
  updateConfigs: async (configs: ConfigItem[]) => {
    try {
      // 调用API批量更新配置
      await configApi.updateConfig(configs);
      
      // 更新本地状态
      set(state => {
        const newConfigs = { ...state.configs };
        configs.forEach(item => {
          newConfigs[item.key] = item;
        });
        return { configs: newConfigs };
      });
    } catch (error) {
      console.error('批量更新配置失败:', error);
      throw error;
    }
  },

  /**
   * 刷新配置数据
   */
  refreshConfigs: async () => {
    console.log('刷新配置数据');
    await get().loadConfigs();
  }
}));
