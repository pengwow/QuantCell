/**
 * Config Store
 *
 * 管理系统配置相关的状态和业务逻辑
 * 支持从后端 API 加载配置并持久化到 localStorage
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

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

  // Actions
  loadConfig: () => Promise<void>;
  setConfig: (config: SystemConfig) => void;
  getDefaultPageSize: () => number;
}

// 默认配置
const DEFAULT_CONFIG: SystemConfig = {
  defaultPerPage: 10,
};

// 从 window.APP_CONFIG 获取配置（如果存在）
const getConfigFromWindow = (): Partial<SystemConfig> => {
  if (typeof window !== 'undefined' && (window as any).APP_CONFIG?.userSettings) {
    const userSettings = (window as any).APP_CONFIG.userSettings;
    return {
      defaultPerPage: userSettings.defaultPerPage
        ? parseInt(userSettings.defaultPerPage, 10)
        : undefined,
    };
  }
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

      // 加载配置
      loadConfig: async () => {
        // 如果已经有配置，不再重复加载
        const currentConfig = get().config;
        if (currentConfig) {
          return;
        }

        set({ isLoading: true, error: null });

        try {
          // 优先从 window.APP_CONFIG 获取
          const windowConfig = getConfigFromWindow();

          if (windowConfig.defaultPerPage) {
            set({
              config: { ...DEFAULT_CONFIG, ...windowConfig },
              isLoading: false,
            });
            return;
          }

          // 如果 window 中没有，尝试从 localStorage 获取（persist 会自动处理）
          // 如果都没有，使用默认配置
          set({
            config: DEFAULT_CONFIG,
            isLoading: false,
          });
        } catch (error: any) {
          set({
            error: error.message || '加载系统配置失败',
            isLoading: false,
            config: DEFAULT_CONFIG,
          });
        }
      },

      // 设置配置
      setConfig: (config: SystemConfig) => {
        set({ config });
      },

      // 获取默认分页大小
      getDefaultPageSize: () => {
        const config = get().config;
        return config?.defaultPerPage || DEFAULT_CONFIG.defaultPerPage;
      },
    }),
    {
      name: 'quantcell-config-storage',
      partialize: (state) => ({ config: state.config }),
    }
  )
);
