/**
 * klinecharts 未内置的常用技术指标 —— 前端本地计算
 *
 * 项目所用 klinecharts v10 没有内置 MFI / AD / ADOSC / ATR（ADX 映射到内置 DMI），
 * 这些指标由本文件本地计算，产出与后端 /api/v1/indicators/{id}/execute 相同的
 * plots 契约，由 ChartPage 复用 registerCustomIndicator 链路注册渲染。
 */

/** 本地计算所需的最小 K 线字段（volume 缺失按 0 处理） */
export interface LocalBar {
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface LocalBuiltInResult {
  plots: Array<{ name: string; data: Array<number | null> }>;
  // 结构兼容后端 execute 返回契约（IndicatorExecuteResult 带索引签名）
  [key: string]: unknown;
}

// 提取数值参数（剔除 _builtInId 等非数值键），键声明顺序与 klinecharts calcParams 数组语义一致
const numParams = (params: Record<string, unknown> | undefined): number[] =>
  Object.values(params || {}).filter((v): v is number => typeof v === 'number');

const vol = (v: number | undefined): number => (typeof v === 'number' && isFinite(v) ? v : 0);

/** MFI(n)：以典型价 (H+L+C)/3 的环比方向划分正/负资金流，n 日比值 */
function calcMFI(bars: LocalBar[], period: number): { name: string; data: Array<number | null> } {
  const n = bars.length;
  const out: Array<number | null> = new Array(n).fill(null);
  const tp = bars.map((b) => (b.high + b.low + b.close) / 3);
  const mf = bars.map((b, i) => tp[i] * vol(b.volume));
  // raw[i]：典型价上涨记正流、下跌记负流（负数）、横盘记 0
  const raw: number[] = bars.map((_, i) => {
    if (i === 0) return 0;
    if (tp[i] > tp[i - 1]) return mf[i];
    if (tp[i] < tp[i - 1]) return -mf[i];
    return 0;
  });
  for (let i = period; i < n; i++) {
    let pos = 0;
    let neg = 0;
    for (let j = i - period + 1; j <= i; j++) {
      if (raw[j] > 0) pos += raw[j];
      else neg -= raw[j];
    }
    out[i] = neg === 0 ? 100 : 100 - 100 / (1 + pos / neg);
  }
  return { name: 'MFI', data: out };
}

/** AD：Clv × V 的逐日累积（H==L 时 Clv 记 0） */
function calcAD(bars: LocalBar[]): { name: string; data: number[] } {
  let acc = 0;
  const data = bars.map((b) => {
    const range = b.high - b.low;
    const clv = range === 0 ? 0 : (b.close - b.low - (b.high - b.close)) / range;
    acc += clv * vol(b.volume);
    return acc;
  });
  return { name: 'AD', data };
}

/** EMA 序列（种子取首值） */
function emaSeries(values: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const out: number[] = [];
  values.forEach((v, i) => {
    out.push(i === 0 ? v : v * k + out[i - 1] * (1 - k));
  });
  return out;
}

/** ADOSC(fast, slow)：AD 的快慢 EMA 之差 */
function calcADOSC(bars: LocalBar[], fast: number, slow: number): { name: string; data: number[] } {
  const { data: ad } = calcAD(bars);
  const emaFast = emaSeries(ad, fast);
  const emaSlow = emaSeries(ad, slow);
  return { name: 'ADOSC', data: ad.map((_, i) => emaFast[i] - emaSlow[i]) };
}

/** ATR(n)：TR 的 Wilder 平滑（前 n 根 SMA 打底） */
function calcATR(bars: LocalBar[], period: number): { name: string; data: Array<number | null> } {
  const n = bars.length;
  const out: Array<number | null> = new Array(n).fill(null);
  const tr = bars.map((b, i) => {
    if (i === 0) return b.high - b.low;
    const pc = bars[i - 1].close;
    return Math.max(b.high - b.low, Math.abs(b.high - pc), Math.abs(b.low - pc));
  });
  let atr: number | null = null;
  for (let i = 0; i < n; i++) {
    if (i === period - 1) {
      let s = 0;
      for (let j = 0; j <= i; j++) s += tr[j];
      atr = s / period;
    } else if (atr !== null) {
      atr = (atr * (period - 1) + tr[i]) / period;
    }
    if (atr !== null) out[i] = atr;
  }
  return { name: 'ATR', data: out };
}

export function calcLocalBuiltIn(
  id: string,
  bars: LocalBar[],
  params?: Record<string, unknown>,
): LocalBuiltInResult | null {
  const nums = numParams(params);
  switch (id.toLowerCase()) {
    case 'mfi':
      return { plots: [calcMFI(bars, nums[0] || 14)] };
    case 'ad':
      return { plots: [calcAD(bars)] };
    case 'adosc':
      return { plots: [calcADOSC(bars, nums[0] || 3, nums[1] || 10)] };
    case 'atr':
      return { plots: [calcATR(bars, nums[0] || 14)] };
    default:
      return null;
  }
}
