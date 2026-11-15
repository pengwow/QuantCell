/**
 * OI / FUNDING / CVD 三个副图指标（订单簿设置弹窗的指标开关组）。
 *
 * - OI/FUNDING：行情 REST 历史（marketdataApi）按时间轴「≤ bar 时间的最近一条」透传。
 *   与后端自定义指标层先例（depthOverlay / customIndicatorDataRef）一致走模块级缓存：
 *   指标 calc 闭包没有 React 重渲通道，ChartShell 拉到历史后 setXxxHistory() 灌缓存，
 *   再 overrideIndicator 变更 extendData 触发 klinecharts 重算。
 * - CVD：纯本地累计 delta = 2 * takerBuyVolume - volume（taker 买量 - 卖量），
 *   takerBuyVolume 仅 Binance kline 源自带，缺失按 0。
 */
import type { IndicatorTemplate, KLineData } from 'klinecharts';
import { findPeriodItem } from '../chartConstants';
import type { FundingHistoryRow, OiHistoryRow } from '@/api/marketdataApi';

// ===== 透传缓存：ts(ms) -> 值。整表替换 + clear 防累计漂移 =====
const oiByTs = new Map<number, number>();
const fundingByTs = new Map<number, number>();

export const setOiHistory = (rows: readonly OiHistoryRow[]): void => {
  oiByTs.clear();
  for (const r of rows) {
    if (Number.isFinite(r.openInterest)) oiByTs.set(r.timestamp, r.openInterest);
  }
};

export const setFundingHistory = (rows: readonly FundingHistoryRow[]): void => {
  fundingByTs.clear();
  for (const r of rows) {
    if (Number.isFinite(r.fundingRate)) fundingByTs.set(r.timestamp, r.fundingRate);
  }
};

// OI 最低 5m 档 / 资金费 8h 结算点都与 bar 时间戳错位，只能取 ≤ bar 时间的最近一条对齐。
// ponytail: 每 bar O(n) 全量扫 200 条历史（200 bar × 200 条 ≈ 4 万次比较/次重算）可接受；
// 数据量上去后升级路径：key 排序数组 + 二分
const lastAtOrBefore = (store: Map<number, number>, ts: number): number | null => {
  let best: number | null = null;
  for (const t of store.keys()) {
    if (t <= ts && (best === null || t > best)) best = t;
  }
  return best === null ? null : store.get(best) ?? null;
};

// ===== period → 一根 bar 的毫秒宽（fillMarkers.alignToBar 与 OI 档位计算共用） =====
const UNIT_MS: Record<string, number> = {
  second: 1_000,
  minute: 60_000,
  hour: 3_600_000,
  day: 86_400_000,
  week: 604_800_000,
};

export const periodToMs = (period: string): number => {
  const item = findPeriodItem(period);
  if (!item || !(item.type in UNIT_MS)) {
    // ponytail: month/year 无固定毫秒宽，近似取 30d/365d；仅在 CVD/标记细粒度用，足够
    if (item?.type === 'month') return 30 * 86_400_000;
    if (item?.type === 'year') return 365 * 86_400_000;
    return 60_000;
  }
  return item.span * (UNIT_MS[item.type] ?? 60_000);
};

// ===== OI 历史 interval：取 ≥ K 线周期的最小档（后端支持 5m..1d）=====
const OI_INTERVAL_STEPS_MIN = [5, 15, 30, 60, 120, 240, 360, 720, 1440] as const;
const OI_INTERVAL_BY_MIN: Record<number, string> = {
  5: '5m',
  15: '15m',
  30: '30m',
  60: '1h',
  120: '2h',
  240: '4h',
  360: '6h',
  720: '12h',
  1440: '1d',
};

export const oiIntervalForPeriod = (period: string): string => {
  const mins = periodToMs(period) / 60_000;
  const hit = OI_INTERVAL_STEPS_MIN.find((m) => m >= mins) ?? 1440;
  return OI_INTERVAL_BY_MIN[hit] ?? '1d';
};

// ===== 三个指标模板（ChartShell init 时 registerIndicator）=====
export const OI_INDICATOR: IndicatorTemplate = {
  name: 'OI',
  shortName: 'OI',
  figures: [{ key: 'oi', title: 'OI: ', type: 'bar' }],
  calc: (dataList: KLineData[]) =>
    dataList.map((k) => {
      const v = lastAtOrBefore(oiByTs, k.timestamp);
      return v === null ? {} : { oi: v };
    }),
};

export const FUNDING_INDICATOR: IndicatorTemplate = {
  name: 'FUNDING',
  shortName: 'FUND',
  figures: [{ key: 'funding', title: 'FUND: ', type: 'line' }],
  calc: (dataList: KLineData[]) =>
    dataList.map((k) => {
      const v = lastAtOrBefore(fundingByTs, k.timestamp);
      return v === null ? {} : { funding: v };
    }),
};

export const CVD_INDICATOR: IndicatorTemplate = {
  name: 'CVD',
  shortName: 'CVD',
  figures: [{ key: 'cvd', title: 'CVD: ', type: 'line' }],
  calc: (dataList: KLineData[]) => {
    let cvd = 0;
    return dataList.map((k) => {
      // KLineData 无 takerBuyVolume 声明（index signature: unknown），按数值取用；
      // Binance 聚合自带该字段，其它数据源缺失按 0（累计偏慢一个方向，可接受）
      const takerBuy = k.takerBuyVolume as number | undefined;
      const delta = 2 * (takerBuy ?? 0) - (k.volume ?? 0);
      cvd += delta;
      return { cvd };
    });
  },
};
