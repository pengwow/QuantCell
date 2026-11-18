/**
 * 训练期 meta（P2/P3 契约，rl_service 落 meta.json）的展示格式化工具。
 * 消费方：ModelsTab 行内徽标 + ModelObsPanel 展开面板。
 * 独立成纯函数文件：.react-refresh 规则要求组件文件只导出组件。
 */

/** reward_terms 展示串：非零项「pnl 1 / downside 0.4」；无有效数据返回 null */
export const rewardText = (terms: unknown): string | null => {
  if (terms == null || typeof terms !== 'object' || Array.isArray(terms)) return null;
  const entries = Object.entries(terms as Record<string, unknown>).filter(
    ([, w]) => typeof w === 'number' && Number.isFinite(w),
  ) as [string, number][];
  if (entries.length === 0) return null;
  const nonzero = entries.filter(([, w]) => w !== 0);
  const picked = nonzero.length > 0 ? nonzero : entries;
  return picked.map(([k, w]) => `${k} ${w}`).join(' / ');
};

/** reward_terms 是否偏离默认配比（默认 = pnl 单 term、其余 0；services/rl_service.py 契约） */
export const isRewardNonDefault = (terms: unknown): boolean => {
  if (terms == null || typeof terms !== 'object') return false;
  const entries = Object.entries(terms as Record<string, unknown>);
  return entries.some(([k, w]) => (k !== 'pnl' && typeof w === 'number' && w !== 0) || (k === 'pnl' && w !== 1));
};
