/**
 * 公开分享页（只读）
 *
 * 路径：/share/:token
 *
 * 特性：
 * - 顶部 hero：worker 名称 + 状态 + 交易标的 + 运行时间
 * - 8 个核心 KPI 卡片（复用 WorkerOverviewTab 的渲染逻辑）
 * - 累计收益曲线 + 盈亏分布
 * - 持仓概况表格（白名单字段）
 * - 不依赖登录，不使用 PageContainer / ConsoleLayout
 * - 响应式：KPI 在 xs/sm 上 2 列，md 及以上 4 列
 */

import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Result,
  Row,
  Skeleton,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { HomeOutlined, LockOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { getShareSnapshot } from '@/api/shareApi';
import { setPageTitle } from '@/utils/pageTitle';
import {
  QUANT_COLORS,
  formatPercent,
  formatQuantity,
  formatTimestamp,
  formatUSD,
} from '@/utils/format';
import type {
  OverviewMetrics,
  PositionSnapshot,
  ShareSnapshot,
} from '@/types/worker';

interface KPICardSpec {
  key: keyof OverviewMetrics | 'return_rate';
  label: string;
  render: (m: OverviewMetrics) => { value: string; color: string };
}

// 复用 WorkerOverviewTab 的 8 个 KPI 卡片定义
const buildKpiCards = (t: (key: string) => string): KPICardSpec[] => [
  {
    key: 'total_pnl',
    label: t('total_pnl') || '总盈亏',
    render: (m) => ({
      value: formatUSD(m.total_pnl, { showSign: true }),
      color: m.total_pnl >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
    }),
  },
  {
    key: 'return_rate',
    label: t('return_rate') || '收益率',
    render: (m) => ({
      value: formatPercent(m.return_rate, { showSign: true }),
      color: m.return_rate >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
    }),
  },
  {
    key: 'win_rate',
    label: t('win_rate') || '胜率',
    render: (m) => ({
      value: formatPercent(m.win_rate),
      color: m.win_rate >= 50 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
    }),
  },
  {
    key: 'profit_loss_ratio',
    label: t('profit_loss_ratio') || '盈亏比',
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
    label: t('max_drawdown') || '最大回撤',
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
    label: t('total_trades') || '总交易次数',
    render: (m) => ({
      value: String(m.total_trades ?? 0),
      color: QUANT_COLORS.info,
    }),
  },
];

const SharePage: React.FC = () => {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  const [snapshot, setSnapshot] = useState<ShareSnapshot | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // 拉取只读快照
  useEffect(() => {
    if (!token) {
      setError(t('share.invalid_token'));
      setLoading(false);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getShareSnapshot(token);
        if (!cancelled) {
          setSnapshot(data);
        }
      } catch (err: any) {
        // eslint-disable-next-line no-console
        console.error('获取分享快照失败:', err);
        if (!cancelled) {
          setError(t('share.invalid_token'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [token, t]);

  // 设置页面标题
  useEffect(() => {
    if (snapshot?.worker?.name) {
      setPageTitle(t('share.share_page_title', { name: snapshot.worker.name }));
    } else {
      setPageTitle(t('share.title') || '分享');
    }
  }, [snapshot, t]);

  const kpiCards = useMemo(() => buildKpiCards(t), [t]);

  // 累计收益曲线 ECharts 配置
  const cumulativePnlOption = useMemo(() => {
    const series = snapshot?.cumulative_pnl_series;
    if (!series?.dates?.length) {
      return {
        title: {
          text: t('no_data') || '暂无数据',
          left: 'center',
          top: 'center',
          textStyle: { color: '#999', fontSize: 14 },
        },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: [],
      };
    }

    // 计算最大回撤阴影
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
  }, [snapshot, t]);

  // 盈亏分布 ECharts 配置
  const pnlDistributionOption = useMemo(() => {
    const pnlDist = snapshot?.pnl_distribution;
    if (!pnlDist?.bins?.length) {
      return {
        title: {
          text: t('no_data') || '暂无数据',
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
  }, [snapshot, t]);

  // 持仓表格列（白名单字段）
  const positionColumns: ColumnsType<PositionSnapshot> = useMemo(
    () => [
      {
        title: t('symbol') || '交易对',
        dataIndex: 'symbol',
        key: 'symbol',
        width: 130,
        render: (v: string) => <Tag color="blue">{v}</Tag>,
      },
      {
        title: t('direction') || '方向',
        dataIndex: 'side',
        key: 'side',
        width: 90,
        render: (side: string) => {
          const isLong = String(side).toLowerCase() === 'long';
          return (
            <Tag color={isLong ? 'green' : 'red'}>
              {isLong ? t('long') || '做多' : t('short') || '做空'}
            </Tag>
          );
        },
      },
      {
        title: t('quantity') || '数量',
        dataIndex: 'quantity',
        key: 'quantity',
        width: 130,
        align: 'right',
        render: (v: number) => formatQuantity(v),
      },
      {
        title: t('entry_price') || '开仓价',
        dataIndex: 'entry_price',
        key: 'entry_price',
        width: 130,
        align: 'right',
        render: (v: number) => formatUSD(v),
      },
      {
        title: t('current_price') || '最新价',
        dataIndex: 'current_price',
        key: 'current_price',
        width: 130,
        align: 'right',
        render: (v: number) => formatUSD(v),
      },
      {
        title: t('unrealized_pnl') || '未实现盈亏',
        dataIndex: 'unrealized_pnl',
        key: 'unrealized_pnl',
        width: 150,
        align: 'right',
        render: (v: number) => (
          <span style={{ fontWeight: 600, color: v >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative }}>
            {formatUSD(v, { showSign: true })}
          </span>
        ),
      },
      {
        title: t('pnl_percentage') || '盈亏%',
        dataIndex: 'pnl_percentage',
        key: 'pnl_percentage',
        width: 110,
        align: 'right',
        render: (v: number) => (
          <span style={{ fontWeight: 600, color: v >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative }}>
            {formatPercent(v, { showSign: true })}
          </span>
        ),
      },
      {
        title: t('open_time') || '开仓时间',
        dataIndex: 'open_time',
        key: 'open_time',
        width: 170,
        render: (v: string | null) => (v ? formatTimestamp(v) : '-'),
      },
    ],
    [t],
  );

  // ============== 加载中 ==============
  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: '#f5f5f5', padding: '24px 16px' }}>
        <div style={{ maxWidth: 1280, margin: '0 auto' }}>
          <div style={{ textAlign: 'center', padding: '120px 0' }}>
            <Spin size="large" tip={t('loading')} />
          </div>
          <Row gutter={[16, 16]}>
            {[...Array(8)].map((_, i) => (
              <Col xs={12} sm={12} md={6} key={i}>
                <Card size="small">
                  <Skeleton active paragraph={false} />
                </Card>
              </Col>
            ))}
          </Row>
        </div>
      </div>
    );
  }

  // ============== 错误 / Token 无效 ==============
  if (error || !snapshot) {
    return (
      <div style={{ minHeight: '100vh', background: '#f5f5f5', padding: '24px 16px' }}>
        <div style={{ maxWidth: 720, margin: '80px auto' }}>
          <Result
            status="404"
            title={t('share.invalid_token')}
            subTitle={t('share.invalid_token_desc')}
            extra={
              <Button
                type="primary"
                icon={<HomeOutlined />}
                onClick={() => navigate('/')}
              >
                {t('share.back_home')}
              </Button>
            }
          />
        </div>
      </div>
    );
  }

  const { worker, metrics, positions, generated_at } = snapshot;

  return (
    <div style={{ minHeight: '100vh', background: '#f5f5f5', padding: '24px 16px' }}>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        {/* 顶部只读 banner */}
        <Alert
          type="info"
          showIcon
          icon={<LockOutlined />}
          message={t('share.readonly_banner')}
          style={{ marginBottom: 16 }}
        />

        {/* Hero 卡片：worker 概况 */}
        <Card style={{ marginBottom: 16 }}>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space size="middle" wrap>
              <span style={{ fontSize: 24, fontWeight: 600 }}>{worker.name}</span>
              <Tag color="blue">{worker.status}</Tag>
            </Space>

            <Row gutter={[16, 16]}>
              <Col xs={24} sm={12} md={6}>
                <div style={{ color: '#999', fontSize: 12 }}>
                  {t('timeframe') || '周期'}
                </div>
                <div style={{ fontSize: 16, fontWeight: 500, marginTop: 4 }}>
                  {worker.timeframe || '-'}
                </div>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <div style={{ color: '#999', fontSize: 12 }}>
                  {t('trading_target') || '交易标的'}
                </div>
                <div style={{ fontSize: 14, marginTop: 4 }}>
                  {worker.symbols?.length ? (
                    worker.symbols.map((s) => <Tag key={s} color="blue">{s}</Tag>)
                  ) : '-'}
                </div>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <div style={{ color: '#999', fontSize: 12 }}>
                  {t('created_at') || '创建时间'}
                </div>
                <div style={{ fontSize: 14, marginTop: 4 }}>
                  {worker.created_at ? formatTimestamp(worker.created_at) : '-'}
                </div>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <div style={{ color: '#999', fontSize: 12 }}>
                  {t('started_at') || '启动时间'}
                </div>
                <div style={{ fontSize: 14, marginTop: 4 }}>
                  {worker.started_at ? formatTimestamp(worker.started_at) : '-'}
                </div>
              </Col>
            </Row>
          </Space>
        </Card>

        {/* 8 个 KPI 卡片（xs/sm 2 列，md 及以上 4 列） */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          {kpiCards.map((card) => {
            const { value, color } = card.render(metrics);
            return (
              <Col xs={12} sm={12} md={6} key={String(card.key)}>
                <Card size="small" variant="borderless" style={{ background: '#fafafa' }}>
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
        <Card title={t('cumulative_pnl_curve') || '累计收益曲线'} style={{ marginBottom: 16 }}>
          <ReactECharts
            option={cumulativePnlOption}
            style={{ height: 400 }}
            opts={{ renderer: 'svg' }}
          />
        </Card>

        {/* 盈亏分布 */}
        <Card title={t('pnl_distribution') || '盈亏分布'} style={{ marginBottom: 16 }}>
          <ReactECharts
            option={pnlDistributionOption}
            style={{ height: 400 }}
            opts={{ renderer: 'svg' }}
          />
        </Card>

        {/* 持仓概况 */}
        <Card title={t('current_position') || '持仓概况'} style={{ marginBottom: 16 }}>
          {positions && positions.length > 0 ? (
            <Table
              rowKey={(record, index) => `${record.symbol}-${record.side}-${index}`}
              columns={positionColumns}
              dataSource={positions}
              pagination={false}
              size="middle"
              scroll={{ x: 'max-content' }}
            />
          ) : (
            <Empty description={t('no_position_data') || '暂无持仓数据'} />
          )}
        </Card>

        {/* 页脚：snapshot 生成时间 */}
        <div
          style={{
            textAlign: 'center',
            color: '#999',
            fontSize: 12,
            padding: '24px 0',
          }}
        >
          <Space split="·">
            <span>{t('share.share_page_subtitle')}</span>
            <span>
              Snapshot: {generated_at ? dayjs(generated_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
            </span>
            <Link to="/" style={{ color: '#999' }}>
              QuantCell
            </Link>
          </Space>
        </div>
      </div>
    </div>
  );
};

export default SharePage;
