/**
 * 价格计划价位线 overlay：把预览/固化计划的档位画成横跨可见区间的水平线。
 * 复用 ChartShell 的 signalTag 先例（fillMarkers 同款契约）：两点 timestamp 取可见 bar 区间
 * 首尾、value 同为档位价 ⇒ 绘制退化为贴 coord0 的标签 + 横跨水平线。
 * extendData.source='pricePlan'，与成交标记（backtest/live）/深度轮廓幂等互不干扰。
 * canvas 需字面色：buy/sell 与成交点同 palette 槽位（线点同源），tp 用 info（spec ② --info 色系）。
 * ponytail: 档位价超出 y 轴可视范围时线被裁剪（用户缩放可查）；自动拉伸 y 轴的升级路径是
 * 换用使 yAxis extendRange 的 overlay 实现或约定 yAxis includeOverlays，本版不做。
 */
import type { Chart, Nullable } from 'klinecharts';
import i18n from '@/i18n/config';
import { getPalette } from '@/theme';
import { currentChartThemeMode } from './chartStyles';
import type { PricePlan, PlanAction } from '../../types/pricePlan';

export interface PricePlanOverlayLevel {
  price: number;
  action: PlanAction;
  label: string;
}

const lineColor = (action: PlanAction): string | null => {
  const p = getPalette(currentChartThemeMode());
  if (action === 'buy') return p.chartBuyMarker;
  if (action === 'sell') return p.chartSellMarker;
  if (action === 'tp') return p.info;
  return null; // mid 不画线
};

/** PricePlan → 可绘制档位（纯函数，单测覆盖）：过滤非法价位，mid 不画 */
export const planToOverlayLevels = (plan: PricePlan | null | undefined): PricePlanOverlayLevel[] => {
  if (!plan || !Array.isArray(plan.levels)) return [];
  const out: PricePlanOverlayLevel[] = [];
  for (const l of plan.levels) {
    if (!Number.isFinite(l.price) || l.price <= 0) continue;
    if (l.action === 'mid') continue;
    out.push({ price: l.price, action: l.action, label: l.label });
  }
  return out;
};

// 标签短词复用既有 pricePlan.action_* 词条（i18n 单例取词——非组件模块拿不到 useTranslation hook）
const legendText = (action: PlanAction): string => i18n.t(`pricePlan.action_${action}`);

/**
 * 先清后画、幂等。bars 决定线端点 timestamp（首尾 bar）；空 bars 退化为单点标注。
 * signalTag 的 side 决定标签上下：buy 在价上方、sell/tp 在价下方（沿用先例语义）。
 */
export const drawPricePlanOverlays = (
  chart: Nullable<Chart>,
  levels: PricePlanOverlayLevel[],
  bars: { timestamp: number }[],
): void => {
  if (!chart) return;
  clearPricePlanOverlays(chart);
  const startTs = bars[0]?.timestamp ?? Date.now();
  const endTs = bars[bars.length - 1]?.timestamp ?? startTs;
  for (const lvl of levels) {
    const color = lineColor(lvl.action);
    if (!color) continue;
    try {
      chart.createOverlay({
        name: 'signalTag',
        lock: true,
        extendData: {
          text: `${legendText(lvl.action)} ${lvl.label}`.trim(),
          color,
          side: lvl.action,
          source: 'pricePlan',
          label: lvl.label,
        },
        points: [
          { timestamp: startTs, value: lvl.price },
          { timestamp: endTs, value: lvl.price },
        ],
      });
    } catch (e) {
      console.warn('[PricePlanOverlays] Failed to create overlay:', e);
    }
  }
};

/** 幂等清除（按 source 过滤，不动成交标记/深度轮廓/下单信号标注） */
export const clearPricePlanOverlays = (chart: Nullable<Chart>): void => {
  if (!chart) return;
  const overlays = chart.getOverlays({ name: 'signalTag' }) || [];
  for (const o of overlays) {
    const ext = o.extendData as { source?: string } | null | undefined;
    if (ext?.source === 'pricePlan') {
      try {
        chart.removeOverlay({ id: o.id });
      } catch (e) {
        console.warn('[PricePlanOverlays] Failed to remove overlay:', e);
      }
    }
  }
};
