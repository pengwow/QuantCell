/**
 * 能力开关状态（P2-02 capability flags）
 *
 * 只读部署能力集：应用启动后从 GET /api/v1/capabilities 加载一次，
 * 供侧边菜单过滤（ConsoleLayout）与能力域页面降级（CapabilityGuard）使用。
 */
import { create } from 'zustand';
import { capabilitiesApi } from '@/api';

export type CapabilityKey = 'live_trading' | 'agent_gateway' | 'mcp_server';

/** 未加载 / 加载失败时的兜底值，与后端内置默认值一致（mcp_server 未实现恒关） */
const FALLBACK: Record<CapabilityKey, boolean> = {
  live_trading: true,
  agent_gateway: true,
  mcp_server: false,
};

interface CapabilityState {
  /** null = 尚未就绪（首屏按兼容默认渲染，不阻塞） */
  capabilities: Record<CapabilityKey, boolean> | null;
  isLoading: boolean;
  loadCapabilities: (force?: boolean) => Promise<void>;
}

export const useCapabilityStore = create<CapabilityState>((set, get) => ({
  capabilities: null,
  isLoading: false,
  loadCapabilities: async (force = false) => {
    const { capabilities, isLoading } = get();
    if (isLoading || (capabilities && !force)) return;
    set({ isLoading: true });
    try {
      const data = await capabilitiesApi.getCapabilities();
      set({
        capabilities: { ...FALLBACK, ...(data && typeof data === 'object' ? data : {}) },
        isLoading: false,
      });
    } catch (err) {
      // 加载失败按兼容默认兜底，不阻塞 UI（能力开关属部署级静态信息，短暂失真可接受）
      console.warn('[capabilityStore] 能力集加载失败，按兼容默认处理', err);
      set({ capabilities: FALLBACK, isLoading: false });
    }
  },
}));

/** 便捷读取：能力集未就绪时按兼容默认判定（与后端默认一致） */
export const isCapabilityEnabled = (
  caps: Record<CapabilityKey, boolean> | null,
  key: CapabilityKey,
): boolean => caps?.[key] ?? FALLBACK[key];
