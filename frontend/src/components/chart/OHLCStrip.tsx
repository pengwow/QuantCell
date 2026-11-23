/**
 * OHLC 十字光标联动条（对应 demo qc-prototype-demo.html #view-charts 的 .ohlc-row）：
 * 「时间 UTC · O/H/L/C · 涨跌 · 量」一行，默认显示末根；十字光标移动时随 hover bar 更新，
 * 移出图表恢复末根；无数据整条不渲染（不显示空壳）。
 *
 * 纯展示件：crosshair 订阅与 hover state 都在本组件内（叶子），高频移动不重渲染壳；
 * 悬停 bar 对齐回页面原始 K 线数组取值，display 蜡烛类型（平均K等）下字段仍是真实 OHLCV。
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Chart, KLineData, Nullable } from 'klinecharts';
import { formatUtcBarTime } from './chartConstants';

// 价格形制与页头现价块同口径（千分位 + 8 位小数上限兜底低价品种）
const priceFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 8 });
// 成交量 compact 记法（123.45K / 2.31M）：真实数值仅记法折叠，不造字段。
// ponytail: 币种量级跨度大（主流币万级、长尾币亿级），compact 两头都放得下；需要完整尾数时改千分位
const volFmt = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 });

interface OHLCStripProps {
  /** 图表实例（init 就绪后由壳传入；null 不订阅不渲染） */
  chart: Nullable<Chart>;
  /** 页面当前 K 线（真实字段：末根兜底 + 涨跌基准；壳透传页面 getBars） */
  getBars: () => KLineData[];
  /** 页面喂数信号（refreshData 递增）：实时更新后重读末根，值本身不参与渲染 */
  refreshSignal?: number;
}

const OHLCStrip = ({ chart, getBars }: OHLCStripProps) => {
  const { t } = useTranslation();
  const [hover, setHover] = useState<KLineData | null>(null);

  // crosshair 联动：有 kLineData 即悬停 bar（同 bar 内引用不变，React 同值短路，不逐帧渲染）；
  // 离开图区 klinecharts 以空 payload 收尾 → 置 null 回落末根，容器 mouseleave 可能不发事件时兜同效
  useEffect(() => {
    if (!chart) return;
    const onCrosshair = (data?: unknown) => {
      const bar = (data as { kLineData?: KLineData } | undefined)?.kLineData;
      setHover(bar ?? null);
    };
    const reset = () => setHover(null);
    chart.subscribeAction('onCrosshairChange', onCrosshair);
    const dom = chart.getDom();
    dom?.addEventListener('mouseleave', reset);
    return () => {
      chart.unsubscribeAction('onCrosshairChange', onCrosshair);
      dom?.removeEventListener('mouseleave', reset);
    };
  }, [chart]);

  const bars = getBars() || [];
  if (bars.length === 0) return null;

  // 展示 bar：hover 时按 timestamp 对齐回原始数组（crosshair 给的是显示数据，派生蜡烛类型下
  // 须经原始 bar 取值）；对不齐才回退显示 bar 自身字段（不造字段）。
  // ponytail: O(n) findIdx 随 crosshair 越栏才命中一次重渲染，500 根量级不可感知；上量再建 timestamp 查表
  let active = bars[bars.length - 1];
  let idx = bars.length - 1;
  if (hover) {
    const hit = bars.findIndex(b => b.timestamp === hover.timestamp);
    if (hit >= 0) {
      active = bars[hit];
      idx = hit;
    } else {
      active = hover;
      idx = -1;
    }
  }

  // 涨跌基准：对前一根 close（首根无前一根用自身 open，与 demo 同构）；0 不染色（全站涨跌口径）
  const prev = idx > 0 ? bars[idx - 1] : null;
  const base = prev ? Number(prev.close) : Number(active.open);
  const chg = base > 0 ? (Number(active.close) / base - 1) * 100 : 0;
  const chgUp = chg > 0;
  const chgDown = chg < 0;

  return (
    <div className="ohlc-strip">
      <span className="ohlc-time">{formatUtcBarTime(active.timestamp)} UTC</span>
      <span>O <b>{priceFmt.format(active.open)}</b></span>
      <span>H <b>{priceFmt.format(active.high)}</b></span>
      <span>L <b>{priceFmt.format(active.low)}</b></span>
      <span>C <b>{priceFmt.format(active.close)}</b></span>
      <span className={chgUp ? 'up' : chgDown ? 'down' : ''}>
        {`${chgUp ? '+' : ''}${chg.toFixed(2)}%`}
      </span>
      <span className="ohlc-vol">
        {t('chart.ohlc.volume')} <b>{volFmt.format(active.volume ?? 0)}</b>
      </span>
    </div>
  );
};

export default OHLCStrip;
