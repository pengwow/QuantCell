/**
 * useViewType - 全站默认展示类型（卡片/列表）
 *
 * 优先级：会话临时覆盖（组件本地 state）> 全局默认（configStore 实时订阅）。
 * 临时切换不写回全局配置，刷新后回归全局默认。
 */
import { useState } from 'react';
import { useConfigStore } from '../store/configStore';

export type ViewType = 'card' | 'list';

export const useViewType = (): [ViewType, (v: ViewType) => void] => {
  const globalViewType = useConfigStore((s) => s.config?.defaultViewType);
  const [override, setOverride] = useState<ViewType | null>(null);
  const viewType = override ?? globalViewType ?? 'card';
  return [viewType, setOverride];
};
