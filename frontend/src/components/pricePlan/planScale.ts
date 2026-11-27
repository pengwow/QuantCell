/**
 * 迷你价格图 / overlay 共用的纵轴范围纯函数。
 *
 * 范围 = 计划价位 ∪ 当前价 ∪ K线高低（可选），上下各留跨度 10% 的余量，
 * 保证价位线与现价线不贴边。与 demo（docs/design/qc-prototype-demo.html #wkChart）同口径。
 * ponytail: 跨度为 0（单一价位）时按价格千分位兜底，避免除零与零高图。
 */
export interface PriceScaleInputs {
  /** 计划价位（买/卖/止盈/中枢任意档） */
  levels: number[];
  /** 当前参考价；可能未知（null） */
  currentPrice: number | null;
  /** 可选 K 线高低序列（迷你图有真实/样例 K 线时传入） */
  candleHighs?: number[];
  candleLows?: number[];
}

export interface PriceScale {
  min: number;
  max: number;
}

export function computePriceScale({
  levels,
  currentPrice,
  candleHighs,
  candleLows,
}: PriceScaleInputs): PriceScale | null {
  const all = [
    ...levels,
    ...(currentPrice != null ? [currentPrice] : []),
    ...(candleHighs ?? []),
    ...(candleLows ?? []),
  ];
  const valid = all.filter((v) => Number.isFinite(v));
  if (valid.length === 0) return null;
  const rawMin = Math.min(...valid);
  const rawMax = Math.max(...valid);
  // 跨度 0 时 pad 退化为价格量级千分之一；Math.max 保证非 0
  const pad = Math.max((rawMax - rawMin) * 0.1, Math.abs(rawMax) * 0.001, 1e-9);
  return { min: rawMin - pad, max: rawMax + pad };
}
