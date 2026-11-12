/**
 * useViewType - 全站默认展示类型（卡片/列表）
 *
 * 只读系统设置（configStore.defaultViewType，系统设置页控制），
 * 页面内部不再提供切换入口，保证全站展示类型统一。
 */
import { useConfigStore } from '../store/configStore';

export type ViewType = 'card' | 'list';

export const useViewType = (): ViewType =>
  useConfigStore((s) => s.config?.defaultViewType) ?? 'card';
