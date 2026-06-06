/**
 * Worker Overview Tab
 *
 * 合并自原 WorkerPerformanceTab + WorkerTradingStatsTab，提供统一的总览 Dashboard：
 * - 8 个核心 KPI 卡片
 * - 时间范围切换 (24h/7d/30d/90d/all)
 * - 累计收益曲线（含最大回撤阴影 + 标注）
 * - 盈亏分布直方图（按 ROI 分桶 + 均值/中位数参考线）
 * - CSV 导出
 */

import { useEffect, useMemo, useState } from 'react';
import { Card, Col, Empty, Row, Segmented, Skeleton, Statistic, Button, Space } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { useWorkerStore } from '../../store/workerStore';
import type { OverviewWindow, OverviewMetrics } from '../../types/worker';
import { formatUSD, formatPercent, QUANT_COLORS } from '../../utils/format';
import { downloadCsv, timestampedFilename } from '../../utils/exportCsv';

const WINDOW_OPTIONS: { label: string; value: OverviewWindow }[] = [
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' },
  { label: '90d', value: '90d' },
  { label: '全部', value: 'all' },
];

interface KPICardSpec {
  key: keyof OverviewMetrics | 'return_rate';
  label: string;
  render: (m: OverviewMetrics) => { value: string; color: string };
}

const KPI_CARDS: KPICardSpec[] = [
  {
    key: 'total_pnl',
    label: '总盈亏',
    render: (m) => ({
      value: formatUSD(m.total_pnl, { showSign: true }),
      color: m.total_pnl >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
    }),
  },
  {
    key: 'return_rate',
    label: '收益率',
    render: (m) => ({
      value: formatPercent(m.return_rate, { showSign: true }),
      color: m.return_rate >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
    }),
  },
  {
    key: 'win_rate',
    label: '胜率',
    render: (m) => ({
      value: formatPercent(m.win_rate),
      color: m.win_rate >= 50 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
    }),
  },
  {
    key: 'profit_loss_ratio',
    label: '盈亏比',
    render: (m) => ({
      value: m.profit_loss_ratio?.toFixed(2) || '0.00',
      color: m.profit_loss_ratio >= 1 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
    }),
  },
  {
    key: 'profit_factor',
    label: 'Profit Factor',
    render: (m) => ({
      value: m.profit_factor?.toFixed(2) || '0.00',
      color: m.profit_factor >= 1 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
    }),
  },
  {
    key: 'max_drawdown',
    label: '最大回撤',
    render: (m) => ({
      value: formatPercent(m.max_drawdown),
      color: QUANT_COLORS.negative,
    }),
  },
  {
    key: 'sharpe_ratio',
    label: 'Sharpe Ratio',
    render: (m) => ({
      value: m.sharpe_ratio?.toFixed(2) || '0.00',
      color: m.sharpe_ratio >= 1 ? QUANT_COLORS.positive : QUANT_COLORS.warning,
    }),
  },
  {
    key: 'total_trades',
    label: '总交易次数',
    render: (m) => ({
      value: String(m.total_trades ?? 0),
      color: QUANT_COLORS.info,
    }),
  },
];

const WorkerOverviewTab: React.FC<{ workerId: number; active?: boolean; onNavigate?: (tab: string) => void }> = ({ workerId, active = true, onNavigate }) => {
  const { overview, overviewWindow, loadingOverview, fetchOverview } = useWorkerStore();
  const [localWindow, setLocalWindow] = useState<OverviewWindow>(overviewWindow || '30d');

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

  // KPI 卡片点击跳转：总盈亏、收益率、胜率、Profit Factor 等都跳总览本身（刷新）
  // 未实现盈亏、ROE 等跳持仓 tab
  const handleKpiClick = (kpiKey: string) => {
    if (!onNavigate) return;
    if (kpiKey === 'unrealized_pnl' || kpiKey === 'roe' || kpiKey === 'positions') {
      onNavigate('positions');
    } else if (kpiKey === 'open_orders' || kpiKey === 'orders') {
      onNavigate('orders');
    } else {
      // 总盈亏、收益率、胜率、盈亏比、Profit Factor、最大回撤、Sharpe、总交易次数
      // 都停留在总览 tab
      fetchOverview(workerId, localWindow);
    }
  };

  const metrics = overview?.metrics;
  const series = overview?.cumulativePnlSeries;
  const pnlDist = overview?.pnlDistribution;

  // ============ 累计收益曲线 ECharts 配置 ============
  const cumulativePnlOption = useMemo(() => {
    if (!series?.dates?.length) {
      return {
        title: {
          text: '暂无数据',
          left: 'center',
          top: 'center',
          textStyle: { color: '#999', fontSize: 14 },
        },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: [],
      };
    }

    // 计算最大回撤阴影：从峰值到当前值的负向填充
    // 使用 IIFE 构建可变 peak 变量以避免 const 不可重新赋值问题
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
        formatter: (params: any) => {
          const p = params.find((x: any) => x.seriesName === '累计盈亏');
          if (!p) return '';
          return `${p.name}<br/>累计盈亏: <b>${formatUSD(p.value, { showSign: true })}</b>`;
        },
      },
      grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
      xAxis: {
        type: 'category',
        data: series.dates,
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: { color: '#666', formatter: (v: string) => v.slice(5), rotate: 30 },
      },
      yAxis: {
        type: 'value',
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: { color: '#666', formatter: (v: number) => `$${v.toFixed(0)}` },
        splitLine: { lineStyle: { color: '#eee' } },
      },
      series: [
        // 最大回撤阴影
        {
          name: '最大回撤',
          type: 'line',
          data: drawdownArea,
          symbol: 'none',
          lineStyle: { opacity: 0 },
          areaStyle: { color: 'rgba(255, 77, 79, 0.15)' },
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
          name: '累计盈亏',
          type: 'line',
          data: values,
          smooth: true,
          symbol: 'none',
          lineStyle: { color: '#1890ff', width: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(24, 144, 255, 0.3)' },
                { offset: 1, color: 'rgba(24, 144, 255, 0.05)' },
              ],
            },
          },
          markLine: {
            symbol: 'none',
            data: [{ yAxis: 0, lineStyle: { color: '#999', type: 'dashed' } }],
          },
        },
      ],
      dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        { start: 0, end: 100, height: 30, bottom: 10 },
      ],
    };
  }, [series]);

  // ============ 盈亏分布直方图 ECharts 配置 ============
  const pnlDistributionOption = useMemo(() => {
    if (!pnlDist?.bins?.length) {
      return {
        title: {
          text: '暂无数据',
          left: 'center',
          top: 'center',
          textStyle: { color: '#999', fontSize: 14 },
        },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: [],
      };
    }

    const binLabels = pnlDist.bins.map((bin, index) => {
      if (index < pnlDist.bins.length - 1) {
        return `${bin.toFixed(0)}~${pnlDist.bins[index + 1].toFixed(0)}`;
      }
      return `${bin.toFixed(0)}+`;
    });

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any) => {
          const p = params[0];
          return `${p.name}<br/>交易次数: <b>${p.value}</b>`;
        },
      },
      grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
      xAxis: {
        type: 'category',
        data: binLabels.slice(0, -1),
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: { color: '#666', rotate: 30 },
      },
      yAxis: {
        type: 'value',
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: { color: '#666' },
        splitLine: { lineStyle: { color: '#eee' } },
      },
      series: [
        {
          name: '交易次数',
          type: 'bar',
          data: pnlDist.counts,
          itemStyle: {
            color: (params: any) => {
              const start = pnlDist.bins[params.dataIndex];
              return start >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative;
            },
            borderRadius: [4, 4, 0, 0],
          },
          barWidth: '60%',
        },
      ],
    };
  }, [pnlDist]);

  // ============ CSV 导出 ============
  const handleExport = () => {
    if (!metrics) return;
    downloadCsv(
      timestampedFilename('worker_overview', workerId, localWindow),
      [metrics as unknown as Record<string, unknown>],
      [
        { header: '指标', accessor: (m: any) => Object.entries(m).map(([k, v]) => `${k}: ${v}`).join('; ') },
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
        description="暂无总览数据"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ marginTop: 100 }}
      >
        <Button type="primary" icon={<ReloadOutlined />} onClick={() => fetchOverview(workerId, localWindow)}>
          重试
        </Button>
      </Empty>
    );
  }

  return (
    <div>
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
            刷新
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>
            导出 CSV
          </Button>
        </Space>
      </div>

      {/* 8 核心 KPI 卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {KPI_CARDS.map((card) => {
          const { value, color } = card.render(metrics);
          return (
            <Col xs={12} sm={12} md={6} key={card.key}>
              <Card
                size="small"
                variant="borderless"
                style={{ background: '#fafafa', cursor: onNavigate ? 'pointer' : 'default' }}
                onClick={() => handleKpiClick(String(card.key))}
                hoverable={!!onNavigate}
              >
                <Statistic
                  title={<span style={{ fontSize: 13, color: '#666' }}>{card.label}</span>}
                  value={value}
                  styles={{ content: { fontSize: 22, fontWeight: 'bold', color } }}
                />
              </Card>
            </Col>
          );
        })}
      </Row>

      {/* 累计收益曲线 */}
      <Card title="累计收益曲线" style={{ marginBottom: 16 }}>
        <ReactECharts option={cumulativePnlOption} style={{ height: 400 }} opts={{ renderer: 'svg' }} />
      </Card>

      {/* 盈亏分布 */}
      <Card title="盈亏分布">
        <ReactECharts option={pnlDistributionOption} style={{ height: 400 }} opts={{ renderer: 'svg' }} />
      </Card>
    </div>
  );
};

export default WorkerOverviewTab;
