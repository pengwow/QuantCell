/**
 * 迷你价格计划图 —— demo（docs/design/qc-prototype-demo.html #wkChart）1:1 视觉移植：
 * 高 116px、70 根半透明细蜡烛、计划价位横线（买/卖/止盈虚线、中枢灰）、
 * 当前价实线（--primary）、网格区间淡色带（price_min~price_max）。
 *
 * 技术选型 canvas→SVG：视觉规格与 demo 一致；SVG 节点可直接绑定 hover 事件，
 * 行↔线联动（activePrice 高亮）无需手写 canvas 命中检测。
 * ponytail: viewBox 320x116 + preserveAspectRatio="none" 横向拉伸省 ResizeObserver，
 * 细蜡烛拉伸视觉可接受；需要精确纵横比时换成容器测量。
 *
 * 色值为 demo 视觉 token 的 hex 直写（antd 换肤 token 油不到 canvas/SVG 内联，注释保留映射）：
 *   up #26a69a (demo --up) | down #ef5350 (demo --down)
 *   warn #faad14 (demo --warn) | primary #1677ff (demo --primary)
 */
import { useMemo } from 'react';
import { computePriceScale } from './planScale';
import type { PricePlan } from '../../types/pricePlan';

export interface MiniBar {
  o: number;
  h: number;
  l: number;
  c: number;
}

const COLORS = {
  up: '#26a69a',
  down: '#ef5350',
  warn: '#faad14',
  primary: '#1677ff',
} as const;

/** 档位动作 → 线色（与 ACTION_META 语义一致，hex 供 SVG 内联） */
const LINE_COLORS: Record<string, string> = {
  buy: COLORS.up,
  sell: COLORS.down,
  tp: COLORS.warn,
  mid: 'rgba(128,128,128,0.7)',
};

const BAR_COUNT = 70;
const BAR_GAP = 320 / BAR_COUNT;

/** mulberry32 种子随机：样例走势可复现，测试与快照稳定 */
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 围绕 refPrice 的随机漫步样例 K 线（demo 同款观感：细密、低波动） */
function sampleBars(refPrice: number): MiniBar[] {
  const rand = mulberry32(42);
  let price = refPrice;
  const bars: MiniBar[] = [];
  for (let i = 0; i < BAR_COUNT; i++) {
    const drift = (rand() - 0.5) * refPrice * 0.004;
    const o = price;
    const c = o + drift;
    const h = Math.max(o, c) + rand() * refPrice * 0.0015;
    const l = Math.min(o, c) - rand() * refPrice * 0.0015;
    bars.push({ o, h, l, c });
    price = c;
  }
  return bars;
}

interface Props {
  plan: PricePlan | null;
  /** 当前参考价（现价锚点实线）；null 时只画 levels */
  refPrice: number | null;
  /** 真实 K 线（Task 8 编辑器取数注入）；缺省用内置样例走势 */
  bars?: MiniBar[];
  /** 画布高，缺省 116（demo 规格） */
  height?: number;
  /** 行↔线联动高亮价（来自明细表 / chips hover） */
  activePrice?: number | null;
  /** 加载中：整图降透明度 */
  loading?: boolean;
}

export default function PricePlanMiniChart({
  plan,
  refPrice,
  bars,
  height = 116,
  activePrice = null,
  loading = false,
}: Props) {
  const effectiveBars = useMemo(() => bars ?? (refPrice != null ? sampleBars(refPrice) : []), [bars, refPrice]);
  const barW = Math.max(BAR_GAP * 0.55, 1);

  const scale = useMemo(
    () =>
      computePriceScale({
        levels: plan?.levels.map((l) => l.price) ?? [],
        currentPrice: refPrice,
        candleHighs: effectiveBars.map((b) => b.h),
        candleLows: effectiveBars.map((b) => b.l),
      }),
    [plan, refPrice, effectiveBars],
  );

  if (!scale) return null; // 无计划且无参考价：不渲染，调用方自管占位
  const span = scale.max - scale.min;
  // 价格 → y 像素（SVG y 轴向下）
  const y = (p: number) => ((scale.max - p) / span) * height;
  const viewBox = `0 0 320 ${height}`;

  return (
    <svg
      viewBox={viewBox}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      style={{ display: 'block', opacity: loading ? 0.5 : 1, pointerEvents: 'none' }}
    >
      {/* 网格区间淡色带：订单价格范围可视化主视觉 */}
      {plan && (
        <rect
          x={0}
          y={y(plan.summary.price_max)}
          width={320}
          height={Math.max(y(plan.summary.price_min) - y(plan.summary.price_max), 1)}
          fill="rgba(22,119,255,0.06)"
        />
      )}

      {/* K 线：半透明细蜡烛，涨 --up 跌 --down */}
      {effectiveBars.map((b, i) => {
        const color = b.c >= b.o ? COLORS.up : COLORS.down;
        const top = y(Math.max(b.o, b.c));
        const bottom = y(Math.min(b.o, b.c));
        const cx = i * BAR_GAP + BAR_GAP / 2;
        return (
          <g key={i} opacity={0.55}>
            <line x1={cx} y1={y(b.h)} x2={cx} y2={y(b.l)} stroke={color} strokeWidth={0.6} />
            <rect x={cx - barW / 2} y={top} width={barW} height={Math.max(bottom - top, 0.5)} fill={color} />
          </g>
        );
      })}

      {/* 计划价位线：买/卖/止盈虚线、中枢灰；activePrice 命中加粗 */}
      {plan?.levels.map((lv) => {
        const isMid = lv.action === 'mid';
        const active = activePrice != null && Math.abs(lv.price - activePrice) < 1e-9;
        return (
          <line
            key={lv.index}
            x1={0}
            x2={320}
            y1={y(lv.price)}
            y2={y(lv.price)}
            stroke={LINE_COLORS[lv.action] ?? 'gray'}
            strokeWidth={active ? 2 : 1}
            strokeDasharray={isMid ? undefined : '4 3'}
            opacity={activePrice == null || active ? 0.95 : 0.45}
          />
        );
      })}

      {/* 当前价实线（--primary）+ 右端价签底色块 */}
      {refPrice != null && (
        <g>
          <line x1={0} x2={320} y1={y(refPrice)} y2={y(refPrice)} stroke={COLORS.primary} strokeWidth={1.4} />
          <rect x={286} y={y(refPrice) - 7} width={34} height={14} rx={2} fill={COLORS.primary} />
          <text x={303} y={y(refPrice) + 3.5} textAnchor="middle" fontSize={8} fill="#fff" dominantBaseline="middle">
            {refPrice.toFixed(2)}
          </text>
        </g>
      )}

      {/* 联动高亮价（hover 行）：白色细线描边辅助定位 */}
      {activePrice != null && Math.abs(activePrice - (refPrice ?? NaN)) > 1e-9 && (
        <line x1={0} x2={320} y1={y(activePrice)} y2={y(activePrice)} stroke="rgba(255,255,255,0.8)" strokeWidth={0.8} />
      )}
    </svg>
  );
}
