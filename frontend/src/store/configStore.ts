/**
 * Config Store
 *
 * 管理系统配置相关的状态和业务逻辑
 * 支持从后端 API 加载配置并持久化到 localStorage
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { configApi } from '../api';

// 系统配置接口
export interface SystemConfig {
  defaultPerPage: number;
  // 其他系统配置项可以在这里添加
  [key: string]: any;
}

// Config状态接口
export interface ConfigState {
  // 状态
  config: SystemConfig | null;
  isLoading: boolean;
  error: string | null;
  lastLoadedAt: number | null; // 上次加载时间

  // Actions
  loadConfig: (force?: boolean) => Promise<void>;
  setConfig: (config: SystemConfig) => void;
  getDefaultPageSize: () => number;
}

// 默认配置
const DEFAULT_CONFIG: SystemConfig = {
  defaultPerPage: 10,
};

// 从 window.APP_CONFIG 获取配置（如果存在）
const getConfigFromWindow = (): Partial<SystemConfig> => {
  console.log('[ConfigStore] 尝试从 window.APP_CONFIG 获取配置');
  const appConfig = (window as any).APP_CONFIG;
  console.log('[ConfigStore] window.APP_CONFIG 原始数据:', appConfig);

  if (typeof window !== 'undefined' && appConfig) {
    // 尝试从 generalSettings 获取 defaultPerPage
    if (appConfig.generalSettings?.defaultPerPage) {
      const defaultPerPage = parseInt(appConfig.generalSettings.defaultPerPage, 10);
      console.log('[ConfigStore] 从 generalSettings 获取 defaultPerPage:', defaultPerPage);
      return { defaultPerPage };
    }
  }
  console.log('[ConfigStore] window.APP_CONFIG 不存在或没有 generalSettings');
  return {};
};

// 创建Store
export const useConfigStore = create<ConfigState>()(
  persist(
    (set, get) => ({
      // 初始状态
      config: null,
      isLoading: false,
      error: null,
      lastLoadedAt: null,

      // 加载配置
      loadConfig: async (force = false) => {
        console.log('[ConfigStore] loadConfig 被调用, force:', force);

        // 如果不是强制刷新，且已经加载过（5分钟内），则跳过
        const { lastLoadedAt, isLoading } = get();
        if (!force && lastLoadedAt && Date.now() - lastLoadedAt < 5 * 60 * 1000) {
          console.log('[ConfigStore] 5分钟内已加载过，跳过加载');
          return;
        }

        if (isLoading) {
          console.log('[ConfigStore] 正在加载中，跳过');
          return;
        }

        set({ isLoading: true, error: null });

        try {
          // 1. 优先从后端 API 获取系统配置（强制刷新时）
          console.log('[ConfigStore] 尝试从后端 API 获取系统配置');
          try {
            const response = await configApi.getConfig();
            console.log('[ConfigStore] 后端 API 返回原始数据:', response);

            // 处理后端返回的配置格式（按 name 分组的格式）
            // 格式: { "appearance": { "theme": "light", ... }, "notification": { ... } }
            const groupedConfig = response?.data || response;
            console.log('[ConfigStore] 分组配置数据:', groupedConfig);

            // 将分组配置扁平化
            const flattenConfig: Record<string, any> = {};
            if (groupedConfig && typeof groupedConfig === 'object') {
              Object.entries(groupedConfig).forEach(([groupName, groupValues]) => {
                console.log(`[ConfigStore] 处理分组 ${groupName}:`, groupValues);
                if (groupValues && typeof groupValues === 'object') {
                  Object.entries(groupValues as Record<string, any>).forEach(([key, value]) => {
                    flattenConfig[key] = value;
                    console.log(`[ConfigStore] 提取配置项 ${key}:`, value);
                  });
                }
              });
            }
            console.log('[ConfigStore] 扁平化后的配置:', flattenConfig);

            // 提取 defaultPerPage
            let defaultPerPage = DEFAULT_CONFIG.defaultPerPage;
            if (flattenConfig.defaultPerPage) {
              defaultPerPage = parseInt(flattenConfig.defaultPerPage, 10);
              console.log('[ConfigStore] 从 API 获取 defaultPerPage:', defaultPerPage);
            }

            const apiConfig = {
              ...DEFAULT_CONFIG,
              ...flattenConfig,
              defaultPerPage,
            };
            console.log('[ConfigStore] API 配置合并后:', apiConfig);
            console.log('[ConfigStore] API 配置字段列表:', Object.keys(apiConfig));

            set({
              config: apiConfig,
              isLoading: false,
              lastLoadedAt: Date.now(),
            });
            return;
          } catch (apiError) {
            console.error('[ConfigStore] 从 API 获取配置失败:', apiError);
          }

          // 2. 如果 API 失败，尝试从 window.APP_CONFIG 获取
          console.log('[ConfigStore] API 失败，尝试从 window.APP_CONFIG 获取');
          const windowConfig = getConfigFromWindow();
          console.log('[ConfigStore] 从 window 获取的配置:', windowConfig);

          if (windowConfig.defaultPerPage) {
            const newConfig = { ...DEFAULT_CONFIG, ...windowConfig };
            console.log('[ConfigStore] 使用 window 配置:', newConfig);
            set({
              config: newConfig,
              isLoading: false,
              lastLoadedAt: Date.now(),
            });
            return;
          }

          // 3. 如果都没有，使用默认配置
          console.log('[ConfigStore] 使用默认配置:', DEFAULT_CONFIG);
          set({
            config: DEFAULT_CONFIG,
            isLoading: false,
            lastLoadedAt: Date.now(),
          });
        } catch (error: any) {
          console.error('[ConfigStore] 加载配置失败:', error);
          set({
            error: error.message || '加载系统配置失败',
            isLoading: false,
            config: DEFAULT_CONFIG,
            lastLoadedAt: Date.now(),
          });
        }
      },

      // 设置配置
      setConfig: (config: SystemConfig) => {
        console.log('[ConfigStore] setConfig 被调用:', config);
        set({ config, lastLoadedAt: Date.now() });
      },

      // 获取默认分页大小
      getDefaultPageSize: () => {
        const config = get().config;
        const pageSize = config?.defaultPerPage || DEFAULT_CONFIG.defaultPerPage;
        console.log('[ConfigStore] getDefaultPageSize:', pageSize);
        return pageSize;
      },
    }),
    {
      name: 'quantcell-config-storage',
      partialize: (state) => ({ config: state.config, lastLoadedAt: state.lastLoadedAt }),
    }
  )
);
