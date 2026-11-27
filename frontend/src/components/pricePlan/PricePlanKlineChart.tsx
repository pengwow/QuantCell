/**
 * 价格计划真实K线图（K1）：klinecharts v10 裸实例 + 单个自定义 indicator 画全档位线。
 *
 * 坐标换算结论（klinecharts ^10.0.3 实测类型定义）：
 * - draw 回调形参是 { ctx, chart, indicator, bounding, xAxis, yAxis }（不是 v9 的 dataObj）；
 * - 价格→像素用 yAxis.convertToPixel(price)，与库内部画线同款 API；
 * - draw 返回 true 表示自定义已覆盖、跳过默认 figure 绘制（我们没有任何 figure）。
 *
 * 数据注入：v10 没有 applyNewData，用 setDataLoader({ getBars }) 喂数，setDataLoader 内部即触发 resetData。
 * ⚠️ 还必须显式 setSymbol：Store 初始 _symbol=null，_processDataLoad 要求 symbol/period/loader
 * 三者都有效才发 getBars，漏 setSymbol 画布只剩网格线（2026-11-27 实测踩坑）。
 *
 * 档位线用单一 indicator 一次性画全所有档（spec §4：25 档不逐档挂 overlay）。
 * plan 的读取走模块级 Map<chartId, state>：draw 回调不携带业务数据，只能按实例 id 取最新快照，
 * 这样多个图实例（创建弹窗 + 启动确认）并存时不会互相串档。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Empty, Segmented, Space, Spin } from 'antd';
import { useDebounceFn } from 'ahooks';
import { dispose, init, registerIndicator, type Chart } from 'klinecharts';
import { fetchKlines, KLINE_INTERVALS, type KlineBar, type KlineInterval } from '../../api/pricePlanApi';
import type { PricePlan } from '../../types/pricePlan';

const PLAN_INDICATOR_NAME = 'PRICE_PLAN_LEVELS';

// 档位色：antd 橙/蓝（与 demo token 一致，canvas 内联）
const COLOR_BUY = '#fa8c16';
const COLOR_SELL = '#1677ff';
const COLOR_TP = '#faad14';
const COLOR_MID = 'rgba(128,128,128,0.75)';
const COLOR_REF = '#1677ff';

interface LevelDraw {
  price: number;
  action: string;
  triggered: boolean;
}
interface PlanDrawState {
  levels: LevelDraw[];
  refPrice: number | null;
}

// draw 回调只能按 chart.id 取业务快照（见文件头说明）
const planStateByChart = new Map<string, PlanDrawState>();

let indicatorRegistered = false;

function ensureLevelIndicator(): void {
  if (indicatorRegistered) return;
  indicatorRegistered = true;
  registerIndicator({
    name: PLAN_INDICATOR_NAME,
    figures: [],
    calc: () => [],
    draw: ({ ctx, chart, bounding, yAxis }) => {
      const state = planStateByChart.get(chart.id);
      if (!state) return true;

      const x0 = 0;
      const x1 = bounding.width;
      const strokeLine = (y: number) => {
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(x1, y);
        ctx.stroke();
      };

      // 档位线：buy 橙 / sell 蓝 / tp 金 / mid 灰；已触发实线加粗，未触发虚线
      state.levels.forEach((lv) => {
        const y = yAxis.convertToPixel(lv.price);
        if (!isFinite(y)) return;
        ctx.strokeStyle =
          lv.action === 'sell' ? COLOR_SELL : lv.action === 'buy' ? COLOR_BUY : lv.action === 'tp' ? COLOR_TP : COLOR_MID;
        ctx.lineWidth = lv.triggered ? 2 : 1;
        ctx.setLineDash(lv.action === 'mid' ? [] : lv.triggered ? [] : [4, 4]);
        strokeLine(y);
      });

      // 参考价强调线 + 右侧价签
      if (state.refPrice != null) {
        const y = yAxis.convertToPixel(state.refPrice);
        if (isFinite(y)) {
          ctx.strokeStyle = COLOR_REF;
          ctx.lineWidth = 1.4;
          ctx.setLineDash([]);
          strokeLine(y);
          const label = state.refPrice.toFixed(2);
          ctx.fillStyle = COLOR_REF;
          ctx.fillRect(bounding.width - 48, y - 7, 48, 14);
          ctx.fillStyle = '#fff';
          ctx.font = '10px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(label, bounding.width - 24, y);
        }
      }

      return true;
    },
  });
}

const INTERVAL_LABEL_KEY: Record<KlineInterval, string> = {
  '1m': 'period_1m',
  '5m': 'period_5m',
  '15m': 'period_15m',
  '1h': 'period_1h',
  '4h': 'period_4h',
  '1d': 'period_1d',
};

function periodOf(interval: KlineInterval): { span: number; type: 'minute' | 'hour' | 'day' } {
  switch (interval) {
    case '1h':
      return { span: 1, type: 'hour' };
    case '4h':
      return { span: 4, type: 'hour' };
    case '1d':
      return { span: 1, type: 'day' };
    default:
      return { span: Number(interval.replace('m', '')), type: 'minute' };
  }
}

export interface PricePlanKlineChartProps {
  symbol: string | null | undefined;
  exchange?: string | null | undefined;
  marketType?: string | null | undefined;
  /** null → 只画K线不画档位 */
  plan: PricePlan | null;
  /** 参考价强调线 */
  refPrice?: number | null;
  /** 已触发档：index 命中画实线加粗 */
  triggeredIndexes?: number[];
  /** 画布高，默认 320 */
  height?: number;
}

export default function PricePlanKlineChart({
  symbol,
  exchange,
  marketType,
  plan,
  refPrice,
  triggeredIndexes,
  height = 320,
}: PricePlanKlineChartProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<Chart | null>(null);
  const [ready, setReady] = useState(false);

  const [interval, setInterval] = useState<KlineInterval>('15m');
  const [bars, setBars] = useState<KlineBar[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);

  // 详情页快照接口不含交易所/市场类型：缺省按 binance/spot 近似回源
  // （档位线是主角，价格轴量级一致即可；需要精确时由调用方透传 exchange/marketType）
  const exchangeValue = exchange ?? 'binance';
  const marketTypeValue = marketType ?? 'spot';

  const drawState = useMemo<PlanDrawState>(
    () => ({
      levels: (plan?.levels ?? []).map((lv) => ({
        price: lv.price,
        action: lv.action,
        triggered: triggeredIndexes?.includes(lv.index) ?? false,
      })),
      refPrice: refPrice ?? null,
    }),
    [plan, refPrice, triggeredIndexes],
  );

  const syncIndicator = useCallback(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.removeIndicator({ name: PLAN_INDICATOR_NAME });
    chart.createIndicator({ name: PLAN_INDICATOR_NAME }, true);
  }, []);

  // 容器仅在 symbol 存在时渲染，故 init 依赖 canRender：标的从无到有时才建实例
  const canRender = !!symbol;

  // 1. 初始化图表（单实例）
  useEffect(() => {
    if (!canRender || !containerRef.current || chartRef.current) return;
    ensureLevelIndicator();
    const chart = init(containerRef.current, {
      styles: {
        grid: {
          show: true,
          horizontal: { color: 'rgba(128,128,128,0.12)' },
          vertical: { color: 'rgba(128,128,128,0.08)' },
        },
      },
    });
    if (!chart) return;
    chartRef.current = chart;
    setReady(true);
    // 弹窗/布局首帧宽度可能未稳定，隔两帧强制重绘
    requestAnimationFrame(() => requestAnimationFrame(() => chart.resize()));

    return () => {
      planStateByChart.delete(chart.id);
      dispose(chart);
      chartRef.current = null;
      setReady(false);
    };
  }, [canRender]);

  // 2. plan/触发态变化 → 更新快照并按需重建 indicator（强制重绘 draw）
  useEffect(() => {
    if (!ready) return;
    const chart = chartRef.current;
    if (!chart) return;
    planStateByChart.set(chart.id, drawState);
    syncIndicator();
  }, [ready, drawState, syncIndicator]);

  // 3. 数据落图（setDataLoader 内部会 resetData 并重算 indicator）
  // 必须先 setSymbol：v10 的 Store 初始 _symbol=null，_processDataLoad 的守卫是
  // "symbol/period/dataLoader 三者都有效才发 getBars"，漏 setSymbol 时 getBars
  // 永不被调用、画布只剩网格线（档位线也因无数据无价格轴而画不出来）。
  // 三个 setter 各触发一次 resetData，最后一次（setDataLoader）拿到完整三要素才真正加载。
  useEffect(() => {
    if (!ready || !symbol) return;
    const chart = chartRef.current;
    if (!chart) return;
    chart.setSymbol({ ticker: symbol });
    chart.setPeriod(periodOf(interval));
    chart.setDataLoader({
      getBars: ({ callback }) =>
        callback(
          bars.map((b) => ({
            timestamp: b.ts,
            open: b.open,
            high: b.high,
            low: b.low,
            close: b.close,
            volume: b.volume,
          })),
        ),
    });
    syncIndicator();
  }, [ready, symbol, bars, interval, syncIndicator]);

  // 4. 拉取真实K线（260ms 防抖 + seq 竞态保护）
  const doFetch = useCallback(async (sym: string, ex: string, mt: string, itv: KlineInterval) => {
    const seq = ++seqRef.current;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchKlines({ symbol: sym, market_type: mt, exchange: ex, interval: itv, limit: 120 });
      if (seq !== seqRef.current) return;
      setBars(res);
    } catch (err) {
      if (seq !== seqRef.current) return;
      setBars([]);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  }, []);

  const { run } = useDebounceFn(
    (sym: string, ex: string, mt: string, itv: KlineInterval) => {
      void doFetch(sym, ex, mt, itv);
    },
    { wait: 260 },
  );

  useEffect(() => {
    if (!symbol) {
      seqRef.current += 1; // 在途响应作废
      setBars([]);
      setError(null);
      setLoading(false);
      return;
    }
    run(symbol, exchangeValue, marketTypeValue, interval);
    // 只依赖拉数入参；防抖 run 引用稳定
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, exchangeValue, marketTypeValue, interval]);

  const retry = useCallback(() => {
    if (symbol) void doFetch(symbol, exchangeValue, marketTypeValue, interval);
  }, [symbol, exchangeValue, marketTypeValue, interval, doFetch]);

  return (
    <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
      <Segmented
        size="small"
        value={interval}
        onChange={(v) => setInterval(v as KlineInterval)}
        options={KLINE_INTERVALS.map((v) => ({ label: t(INTERVAL_LABEL_KEY[v]), value: v }))}
      />
      {error && (
        <Alert
          type="warning"
          showIcon
          message={t('pricePlan.kline_load_failed', { message: error })}
          action={
            <Button size="small" onClick={retry}>
              {t('pricePlan.auto_retry')}
            </Button>
          }
        />
      )}
      {!symbol ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('pricePlan.auto_need_symbol')} />
      ) : (
        <div style={{ position: 'relative', width: '100%', height }}>
          <div ref={containerRef} style={{ width: '100%', height }} />
          {loading && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'rgba(0,0,0,0.04)',
                pointerEvents: 'none',
              }}
            >
              <Spin size="small" />
            </div>
          )}
        </div>
      )}
    </Space>
  );
}
