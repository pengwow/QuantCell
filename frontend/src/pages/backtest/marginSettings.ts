/**
 * 回测配置页「杠杆与保证金」的纯函数。
 *
 * 表单里以「品种 → 值」的对象存，提交时才按当前品种顺序转成后端契约的数组：
 * 用下标对齐品种会让品种增删时串行写错，这里用 symbol 作 key 从根上避免。
 */

export type MarginMode = 'isolated' | 'cross';

export interface MarginRowValue {
  leverage?: number;
  margin_mode?: MarginMode;
}

export interface MarginSettingPayload {
  symbol: string;
  leverage: number;
  margin_mode: MarginMode;
}

/** 数据池（pool_*）要到提交时才展开成真实品种，配置页无法为其中品种预置杠杆 */
export const pickDirectSymbols = (selected?: string[]): string[] =>
  (selected ?? []).filter((value) => !value.startsWith('pool_'));

/** 表单对象 → 后端数组；缺失值按 1x 全仓兜底，列表外的残留键自动丢弃 */
export function buildMarginSettingsPayload(
  settings: Record<string, MarginRowValue> | undefined,
  symbols: string[],
): MarginSettingPayload[] {
  const raw = settings ?? {};
  return pickDirectSymbols(symbols).map((symbol) => ({
    symbol,
    leverage: raw[symbol]?.leverage ?? 1,
    margin_mode: raw[symbol]?.margin_mode ?? 'cross',
  }));
}
