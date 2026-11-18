/**
 * 右栏 ③ 绩效：GET /workers/{id}/stats/overview（窗口 24h/7d/30d/90d/all）。
 * KPI 行 + 累计收益曲线（含回撤阴影）。图表取自
 * WorkerOverviewTab 同源数据与同款 ECharts 画法（cum_pnl 曲线叠加峰值回撤面积）；
 * 组件 EquityChart 面向回测报告的 equity/balance 曲线（按初始资金算回撤%），
 * stats/overview 返回的是累计盈亏序列，直接套用会错标回撤口径，故不复用。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Empty, Segmented, Spin } from 'antd';
import type { TooltipComponentFormatterCallbackParams } from 'echarts';
import EChart from '@/components/EChart';
import { workerApi } from '@/api/workerApi';
import type { OverviewWindow } from '@/types/worker';
import { useWorkbenchStore } from '../../store/workbenchStore';
import { formatPercent, formatUSD } from '@/utils/format';
import { useQuantColors } from '@/utils/colors';

const WINDOWS: OverviewWindow[] = ['24h', '7d', '30d', '90d', 'all'];

export default function PerformanceTab() {
  const { t } = useTranslation();
  const qc = useQuantColors();
  const workerId = useWorkbenchStore((s) => s.workerId);
  const cached = useWorkbenchStore((s) => s.performance);
  const [window, setWindow] = useState<OverviewWindow>('90d');
  const [loading, setLoading] = useState(false);

  const fetchPerf = useCallback(
    async (win: OverviewWindow) => {
      if (!workerId) return;
      setLoading(true);
      try {
        const data = await workerApi.getOverview(workerId, win);
        if (data) {
          useWorkbenchStore.getState().setPerformance(workerId, {
            metrics: data.metrics,
            series: data.cumulative_pnl_series,
            window: data.window ?? win,
          });
        }
      } catch (err) {
        console.warn('[workbench] performance fetch failed:', err);
      } finally {
        setLoading(false);
      }
    },
    [workerId],
  );

  // 已拉取的 (worker, 窗口) 去重键：以请求参数为准，而依赖响应里的 window 字段
  // 判 stale 会因响应用口径与请求不同而永久 stale（曾致无限拉取循环）
  const fetchedRef = useRef<string>('');

  useEffect(() => {
    if (!workerId) return;
    const key = `${workerId}:${window}`;
    if (fetchedRef.current === key) return;
    fetchedRef.current = key;
    fetchPerf(window);
  }, [workerId, window, fetchPerf]);

  const active = !!cached && cached.workerId === workerId;
  const metrics = active ? cached.data.metrics : null;
  const series = active ? cached.data.series : null;

  const option = useMemo(() => {
    if (!series?.dates?.length) return null;
    const values = series.cumulative_pnl;
    let peak = values[0];
    const drawdownArea: (number | null)[] = [];
    const drawdownPeak: number[] = [];
    for (const v of values) {
      if (v > peak) peak = v;
      drawdownPeak.push(peak);
      drawdownArea.push(v < peak ? v : null);
    }
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: TooltipComponentFormatterCallbackParams) => {
          const items = Array.isArray(params) ? params : [params];
          const p = items.find((x) => x.seriesName === t('backtest_cum_pnl'));
          if (!p) return '';
          const value = typeof p.value === 'number' ? p.value : Number(p.value);
          return `${p.name}<br/>${t('backtest_cum_pnl')}: <b>${formatUSD(value, { showSign: true })}</b>`;
        },
      },
      grid: { left: '3%', right: '4%', bottom: '14%', top: '10%', containLabel: true },
      xAxis: {
        type: 'category',
        data: series.dates,
        axisLine: { lineStyle: { color: qc.chartAxis } },
        axisLabel: { color: qc.chartMark, formatter: (v: string) => v.slice(5), rotate: 30 },
      },
      yAxis: {
        type: 'value',
        axisLine: { lineStyle: { color: qc.chartAxis } },
        axisLabel: { color: qc.chartMark, formatter: (v: number) => `$${v.toFixed(0)}` },
        splitLine: { lineStyle: { color: qc.chartSplit } },
      },
      series: [
        {
          name: t('max_drawdown'),
          type: 'line',
          data: drawdownArea,
          symbol: 'none',
          lineStyle: { opacity: 0 },
          areaStyle: { color: qc.drawdownArea },
          stack: 'dd',
        },
        {
          name: 'peak',
          type: 'line',
          data: drawdownPeak,
          symbol: 'none',
          lineStyle: { opacity: 0 },
          stack: 'dd',
        },
        {
          name: t('backtest_cum_pnl'),
          type: 'line',
          data: values,
          smooth: true,
          symbol: 'none',
          lineStyle: { color: qc.chartLine, width: 2 },
          markLine: {
            symbol: 'none',
            data: [{ yAxis: 0, lineStyle: { color: qc.chartMark, type: 'dashed' } }],
          },
        },
      ],
    };
  }, [series, qc, t]);

  if (!workerId) {
    return <Empty description={t('wb_select_worker')} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div className="wb-performance">
      <div className="wb-perf-toolbar">
        <Segmented<OverviewWindow>
          size="small"
          value={window}
          onChange={(v) => setWindow(v)}
          options={WINDOWS.map((w) => ({ label: w, value: w }))}
        />
      </div>
      {!metrics || !active ? (
        <div className="wb-center-spin">
          <Spin size="small" />
        </div>
      ) : (
        <>
          <div className="wb-kpi-row">
            <div className="wb-kpi">
              <span>{t('backtest_metric_total_pnl')}</span>
              <b className={metrics.net_profit >= 0 ? 'up' : 'down'}>{formatUSD(metrics.net_profit, { showSign: true })}</b>
            </div>
            <div className="wb-kpi">
              <span>{t('return_rate')}</span>
              <b className={metrics.return_rate >= 0 ? 'up' : 'down'}>{formatPercent(metrics.return_rate, { showSign: true })}</b>
            </div>
            <div className="wb-kpi">
              <span>{t('win_rate')}</span>
              <b>{formatPercent(metrics.win_rate)}</b>
            </div>
            <div className="wb-kpi">
              <span>{t('sharpe_ratio')}</span>
              <b>{metrics.sharpe_ratio != null ? metrics.sharpe_ratio.toFixed(2) : '-'}</b>
            </div>
            <div className="wb-kpi">
              <span>{t('max_drawdown')}</span>
              <b className="down">{formatPercent(metrics.max_drawdown)}</b>
            </div>
            <div className="wb-kpi">
              <span>{t('total_trades')}</span>
              <b>{metrics.total_trades}</b>
            </div>
          </div>
          <div className="wb-section-title">{t('worker_cumulative_pnl_chart')}</div>
          {option ? (
            <EChart option={option} style={{ height: 260, width: '100%' }} opts={{ renderer: 'svg' }} />
          ) : (
            <Empty description={t('no_data')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
          {loading && (
            <div className="wb-per-refresh">
              <Spin size="small" />
            </div>
          )}
        </>
      )}
    </div>
  );
}
