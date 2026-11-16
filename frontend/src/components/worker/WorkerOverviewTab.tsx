/**
 * Worker Overview Tab
 *
 * 合并自原 WorkerPerformanceTab + WorkerTradingStatsTab，提供统一的总览 Dashboard：
 * - 8 个核心 KPI 卡片
 * - 时间范围切换 (24h/7d/30d/90d/all)
 * - 累计收益曲线（含最大回撤阴影 + 标注）
 * - 每日盈亏分布（横轴=时间，与累计曲线同源，盈绿亏红柱）
 * - CSV 导出
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Col, Empty, Row, Segmented, Skeleton, Statistic, Button, Space, theme } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import EChart from '@/components/EChart';
import type { TooltipComponentFormatterCallbackParams } from 'echarts';
import { useWorkerStore } from '../../store/workerStore';
import type { OverviewWindow, OverviewMetrics } from '../../types/worker';
import { formatUSD, formatPercent } from '../../utils/format';
import { useQuantColors } from '@/utils/colors';
import { downloadCsv, timestampedFilename } from '../../utils/exportCsv';
import WorkerRiskBanner from './WorkerRiskBanner';
import WorkerPositionSection from './WorkerPositionSection';

// 时间范围选项的固定档位；「全部」文案需 i18n，故在组件内构造（见下）
const WINDOW_OPTION_VALUES: OverviewWindow[] = ['24h', '7d', '30d', '90d', 'all'];
const WINDOW_LABEL_KEYS: Record<OverviewWindow, string> = {
  '24h': '24h',
  '7d': '7d',
  '30d': '30d',
  '90d': '90d',
  all: 'all',
};

interface KPICardSpec {
  key: keyof OverviewMetrics | 'return_rate';
  label: string;
  render: (m: OverviewMetrics) => { value: string; color: string };
}

const WorkerOverviewTab: React.FC<{ workerId: number; active?: boolean; onNavigate?: (tab: string) => void }> = ({ workerId, active = true, onNavigate }) => {
  const { token } = theme.useToken();
  const { t } = useTranslation();
  const qc = useQuantColors();
  const { overview, overviewWindow, loadingOverview, fetchOverview } = useWorkerStore();
  const [localWindow, setLocalWindow] = useState<OverviewWindow>(overviewWindow || '30d');

  // 时间范围选项：「全部」label 经 t() 翻译，其余档位为固定英文标记
  const WINDOW_OPTIONS = useMemo(
    () => WINDOW_OPTION_VALUES.map((value) => ({ label: t(WINDOW_LABEL_KEYS[value]), value })),
    [t],
  );

  // ponytail: KPI_CARDS 依赖 quantColors（跟随主题切换），必须放在 useMemo 里重建
  const KPI_CARDS = useMemo<KPICardSpec[]>(() => [
    { key: 'total_pnl', label: t('backtest_metric_total_pnl'), render: (m) => ({ value: formatUSD(m.total_pnl, { showSign: true }), color: m.total_pnl >= 0 ? qc.positive : qc.negative }) },
    { key: 'return_rate', label: t('return_rate'), render: (m) => ({ value: formatPercent(m.return_rate, { showSign: true }), color: m.return_rate >= 0 ? qc.positive : qc.negative }) },
    { key: 'win_rate', label: t('win_rate'), render: (m) => ({ value: formatPercent(m.win_rate), color: m.win_rate >= 50 ? qc.positive : qc.negative }) },
    { key: 'profit_loss_ratio', label: t('profit_loss_ratio'), render: (m) => ({ value: m.profit_loss_ratio?.toFixed(2) || '0.00', color: m.profit_loss_ratio >= 1 ? qc.positive : qc.negative }) },
    { key: 'profit_factor', label: 'Profit Factor', render: (m) => ({ value: m.profit_factor?.toFixed(2) || '0.00', color: m.profit_factor >= 1 ? qc.positive : qc.negative }) },
    { key: 'max_drawdown', label: t('max_drawdown'), render: (m) => ({ value: formatPercent(m.max_drawdown), color: qc.negative }) },
    { key: 'sharpe_ratio', label: 'Sharpe Ratio', render: (m) => ({ value: m.sharpe_ratio?.toFixed(2) || '0.00', color: m.sharpe_ratio >= 1 ? qc.positive : qc.warning }) },
    { key: 'total_trades', label: t('total_trades'), render: (m) => ({ value: String(m.total_trades ?? 0), color: qc.info }) },
  ], [qc, t]);

  // 首次挂载 / window 切换时拉取
  useEffect(() => {
    fetchOverview(workerId, localWindow);
  }, [workerId, localWindow, fetchOverview]);

  // 当 tab 重新激活时刷新（避免长时间停留过时）
  useEffect(() => {
    if (active) {
      fetchOverview(workerId, localWindow);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // KPI 卡片点击：委托类跳交易 tab（合并后首页即委托明细）。
  // 持仓类（unrealized_pnl/roe/positions）不跳转——持仓区已在总览页内，与其它指标一样停留刷新
  const handleKpiClick = (kpiKey: string) => {
    if (!onNavigate) return;
    if (kpiKey === 'open_orders' || kpiKey === 'orders') {
      onNavigate('trades');
    } else {
      fetchOverview(workerId, localWindow);
    }
  };

  const metrics = overview?.metrics;
  const series = overview?.cumulativePnlSeries;

  // ============ 累计收益曲线 ECharts 配置 ============
  // ponytail: 所有颜色从 theme token 派生的 quantColors 取，主题切换时自动重建；series 名经 t() 翻译后同色重建
  const cumulativePnlOption = useMemo(() => {
    if (!series?.dates?.length) {
      return {
        title: { text: t('no_data'), left: 'center', top: 'center', textStyle: { color: qc.neutral, fontSize: 14 } },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: [],
      };
    }

    const values = series.cumulative_pnl;
    let peak = values[0];
    const drawdownData: number[] = [];
    const drawdownArea: (number | null)[] = [];
    for (let i = 0; i < values.length; i++) {
      const v = values[i];
      if (v > peak) peak = v;
      drawdownData.push(peak);
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
      grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
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
        // 最大回撤阴影
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
          data: drawdownData,
          symbol: 'none',
          lineStyle: { opacity: 0 },
          stack: 'dd',
        },
        // 累计收益曲线
        {
          name: t('backtest_cum_pnl'),
          type: 'line',
          data: values,
          smooth: true,
          symbol: 'none',
          lineStyle: { color: qc.chartLine, width: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: qc.chartGradientStart },
                { offset: 1, color: qc.chartGradientEnd },
              ],
            },
          },
          markLine: {
            symbol: 'none',
            data: [{ yAxis: 0, lineStyle: { color: qc.chartMark, type: 'dashed' } }],
          },
        },
      ],
      dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        { start: 0, end: 100, height: 30, bottom: 10 },
      ],
    };
  }, [series, qc, t]);

  // ============ 每日盈亏分布（横轴=时间） ECharts 配置 ============
  // 与累计收益曲线同源（series.dates/daily_pnl），窗口切换自动跟随；
  // 有成交才有柱：盈=绿、亏=红
  const dailyPnlOption = useMemo(() => {
    if (!series?.dates?.length) {
      return {
        title: { text: t('no_data'), left: 'center', top: 'center', textStyle: { color: qc.neutral, fontSize: 14 } },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: [],
      };
    }

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: TooltipComponentFormatterCallbackParams) => {
          const items = Array.isArray(params) ? params : [params];
          const p = items[0];
          const idx = typeof p?.dataIndex === 'number' ? p.dataIndex : 0;
          const value = typeof p?.value === 'number' ? p.value : Number(p?.value ?? 0);
          return `${p?.name || ''}<br/>${t('worker_daily_pnl')}: <b>${formatUSD(value, { showSign: true })}</b><br/>${t('trade_count')}: ${series.trade_count[idx] ?? 0}`;
        },
      },
      grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
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
          name: t('worker_daily_pnl'),
          type: 'bar',
          data: series.daily_pnl,
          itemStyle: {
            color: (params: { dataIndex: number }) =>
              (series.daily_pnl[params.dataIndex] ?? 0) >= 0 ? qc.positive : qc.negative,
            borderRadius: [4, 4, 0, 0],
          },
          barWidth: '60%',
        },
      ],
    };
  }, [series, qc, t]);

  // ============ CSV 导出 ============
  const handleExport = () => {
    if (!metrics) return;
    downloadCsv(
      timestampedFilename('worker_overview', workerId, localWindow),
      [metrics as unknown as Record<string, unknown>],
      [
        { header: t('worker_metric'), accessor: (m) => Object.entries(m).map(([k, v]) => `${k}: ${v}`).join('; ') },
      ],
    );
  };

  if (loadingOverview && !overview) {
    return (
      <div>
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          {[...Array(8)].map((_, i) => (
            <Col xs={12} sm={12} md={6} key={i}>
              <Card size="small">
                <Skeleton active paragraph={false} />
              </Card>
            </Col>
          ))}
        </Row>
        <Card>
          <Skeleton active />
        </Card>
      </div>
    );
  }

  if (!metrics) {
    return (
      <Empty
        description={t('worker_no_overview_data')}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ marginTop: 100 }}
      >
        <Button type="primary" icon={<ReloadOutlined />} onClick={() => fetchOverview(workerId, localWindow)}>
          {t('retry')}
        </Button>
      </Empty>
    );
  }

  return (
    <div>
      {/* 熔断横幅：仅熔断时渲染块级 Alert，常态不占布局（spec 方案 A §4.1） */}
      <WorkerRiskBanner workerId={workerId} active={active} />

      {/* 顶部工具栏：时间范围 + 刷新 + 导出 */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <Segmented
          options={WINDOW_OPTIONS}
          value={localWindow}
          onChange={(v) => setLocalWindow(v as OverviewWindow)}
          disabled={loadingOverview}
        />
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => fetchOverview(workerId, localWindow)}
            loading={loadingOverview}
          >
            {t('refresh')}
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>
            {t('worker_export_csv')}
          </Button>
        </Space>
      </div>

      {/* 8 核心 KPI 卡片 */}
      {/* ponytail: 所有 KPI 卡片统一 hoverable + cursor:pointer，background 从 theme token 取 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {KPI_CARDS.map((card) => {
          const { value, color } = card.render(metrics);
          return (
            <Col xs={12} sm={12} md={6} key={card.key}>
              <Card
                size="small"
                variant="borderless"
                hoverable
                style={{ background: token.colorBgLayout, cursor: 'pointer' }}
                onClick={() => handleKpiClick(String(card.key))}
              >
                <Statistic
                  title={<span style={{ fontSize: 13, color: qc.neutral }}>{card.label}</span>}
                  value={value}
                  styles={{ content: { fontSize: 22, fontWeight: 'bold', color } }}
                />
              </Card>
            </Col>
          );
        })}
      </Row>

      {/* 累计收益曲线 */}
      <Card title={t('worker_cumulative_pnl_chart')} style={{ marginBottom: 16 }}>
        <EChart option={cumulativePnlOption} style={{ height: 400 }} opts={{ renderer: 'svg' }} />
      </Card>

      {/* 每日盈亏分布（横轴=时间） */}
      <Card title={t('worker_daily_pnl')}>
        <EChart option={dailyPnlOption} style={{ height: 400 }} opts={{ renderer: 'svg' }} />
      </Card>

      {/* 当前持仓：持仓 tab 并入总览（spec 2026-11-16 方案 A） */}
      <WorkerPositionSection workerId={workerId} active={active} />
    </div>
  );
};

export default WorkerOverviewTab;
