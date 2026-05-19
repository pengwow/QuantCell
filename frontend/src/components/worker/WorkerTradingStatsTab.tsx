import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Spin,
  Empty,
  Button,
  Skeleton,
  message,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { getTradingSummary, getPnLDistribution, getTradeHistoryChart } from '../../api/workerApi';
import type { TradingSummary, PnLDistribution, TradeHistoryChart } from '../../types/worker';

interface WorkerTradingStatsTabProps {
  workerId: number;
}

const WorkerTradingStatsTab: React.FC<WorkerTradingStatsTabProps> = ({ workerId }) => {
  const [loading, setLoading] = useState(false);
  const [tradingSummary, setTradingSummary] = useState<TradingSummary | null>(null);
  const [pnlDistribution, setPnlDistribution] = useState<PnLDistribution | null>(null);
  const [tradeHistoryChart, setTradeHistoryChart] = useState<TradeHistoryChart | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryRes, pnlRes, historyRes] = await Promise.all([
        getTradingSummary(workerId),
        getPnLDistribution(workerId),
        getTradeHistoryChart(workerId),
      ]);

      if (summaryRes.data) {
        setTradingSummary(summaryRes.data);
      }
      if (pnlRes.data) {
        setPnlDistribution(pnlRes.data);
      }
      if (historyRes.data) {
        setTradeHistoryChart(historyRes.data);
      }
    } catch (err: any) {
      setError(err?.message || '获取数据失败');
      message.error('获取交易统计数据失败');
    } finally {
      setLoading(false);
    }
  }, [workerId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const cumulativePnlOption = useMemo(() => {
    if (!tradeHistoryChart?.dates?.length) {
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

    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const param = params[0];
          return `${param.name}<br/>累计盈亏: ${param.value.toFixed(2)}`;
        },
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: '10%',
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: tradeHistoryChart.dates,
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: {
          color: '#666',
          formatter: (value: string) => value.slice(5, 10),
          rotate: 30,
        },
      },
      yAxis: {
        type: 'value',
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: {
          color: '#666',
          formatter: '{value}',
        },
        splitLine: { lineStyle: { color: '#eee' } },
      },
      series: [
        {
          name: '累计盈亏',
          type: 'line',
          data: tradeHistoryChart.cumulative_pnl,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            color: '#1890ff',
            width: 2,
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(24, 144, 255, 0.3)' },
                { offset: 1, color: 'rgba(24, 144, 255, 0.05)' },
              ],
            },
          },
        },
      ],
      dataZoom: [
        {
          type: 'inside',
          start: 0,
          end: 100,
        },
        {
          start: 0,
          end: 100,
          height: 30,
          bottom: 10,
        },
      ],
    };
  }, [tradeHistoryChart]);

  const pnlDistributionOption = useMemo(() => {
    if (!pnlDistribution?.bins?.length) {
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

    const binLabels = pnlDistribution.bins.map((bin, index) => {
      if (index < pnlDistribution.bins.length - 1) {
        return `${bin.toFixed(0)}~${pnlDistribution.bins[index + 1].toFixed(0)}`;
      }
      return `${bin.toFixed(0)}+`;
    });

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any) => {
          const param = params[0];
          return `${param.name}<br/>交易次数: ${param.value}`;
        },
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: '10%',
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: binLabels.slice(0, -1),
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: {
          color: '#666',
          rotate: 30,
        },
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
          data: pnlDistribution.counts,
          itemStyle: {
            color: (params: any) => {
              const binIndex = params.dataIndex;
              const binStart = pnlDistribution.bins[binIndex];
              return binStart >= 0 ? '#52c41a' : '#ff4d4f';
            },
            borderRadius: [4, 4, 0, 0],
          },
          barWidth: '60%',
        },
      ],
    };
  }, [pnlDistribution]);

  if (loading && !tradingSummary) {
    return (
      <div>
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          {[...Array(4)].map((_, i) => (
            <Col span={6} key={i}>
              <Skeleton active paragraph={false} />
            </Col>
          ))}
        </Row>
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          {[...Array(4)].map((_, i) => (
            <Col span={6} key={i}>
              <Skeleton active paragraph={false} />
            </Col>
          ))}
        </Row>
        <Card>
          <Skeleton active />
        </Card>
      </div>
    );
  }

  if (error && !tradingSummary) {
    return (
      <Empty
        description={error}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ marginTop: 100 }}
      >
        <Button type="primary" icon={<ReloadOutlined />} onClick={fetchData}>
          重试
        </Button>
      </Empty>
    );
  }

  if (!tradingSummary) {
    return (
      <Empty
        description="暂无交易统计数据"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ marginTop: 100 }}
      />
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Button
          icon={<ReloadOutlined />}
          onClick={fetchData}
          loading={loading}
        >
          刷新
        </Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={12} md={6}>
          <Card size="small" variant="borderless" style={{ background: '#fafafa' }}>
            <Statistic
              title={<span style={{ fontSize: 13, color: '#666' }}>总交易次数</span>}
              value={tradingSummary.total_trades}
              styles={{
                content: {
                  fontSize: 22,
                  fontWeight: 'bold',
                  color: '#1890ff',
                },
              }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card size="small" variant="borderless" style={{ background: '#fafafa' }}>
            <Statistic
              title={<span style={{ fontSize: 13, color: '#666' }}>胜率</span>}
              value={`${tradingSummary.win_rate?.toFixed(2) || 0}%`}
              styles={{
                content: {
                  fontSize: 22,
                  fontWeight: 'bold',
                  color: (tradingSummary.win_rate || 0) >= 50 ? '#52c41a' : '#ff4d4f',
                },
              }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card size="small" variant="borderless" style={{ background: '#fafafa' }}>
            <Statistic
              title={<span style={{ fontSize: 13, color: '#666' }}>盈亏比</span>}
              value={tradingSummary.profit_factor?.toFixed(2) || '0.00'}
              styles={{
                content: {
                  fontSize: 22,
                  fontWeight: 'bold',
                  color: (tradingSummary.profit_factor || 0) >= 1 ? '#52c41a' : '#ff4d4f',
                },
              }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card size="small" variant="borderless" style={{ background: '#fafafa' }}>
            <Statistic
              title={<span style={{ fontSize: 13, color: '#666' }}>总盈亏</span>}
              value={`$${tradingSummary.total_pnl?.toFixed(2) || '0.00'}`}
              styles={{
                content: {
                  fontSize: 22,
                  fontWeight: 'bold',
                  color: (tradingSummary.total_pnl || 0) >= 0 ? '#52c41a' : '#ff4d4f',
                },
              }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="最大盈利"
              value={`$${tradingSummary.largest_profit?.toFixed(2) || '0.00'}`}
              styles={{ content: { color: '#52c41a' } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="最大亏损"
              value={`$${Math.abs(tradingSummary.largest_loss || 0).toFixed(2)}`}
              styles={{ content: { color: '#ff4d4f' } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="总交易量"
              value={`$${tradingSummary.total_volume?.toFixed(2) || '0.00'}`}
              styles={{ content: { color: '#1890ff' } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="总手续费"
              value={`$${tradingSummary.total_fees?.toFixed(2) || '0.00'}`}
              styles={{ content: { color: '#faad14' } }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="累计收益曲线" style={{ marginBottom: 16 }}>
        <ReactECharts
          option={cumulativePnlOption}
          style={{ height: 400 }}
          opts={{ renderer: 'svg' }}
        />
      </Card>

      <Card title="盈亏分布">
        <ReactECharts
          option={pnlDistributionOption}
          style={{ height: 400 }}
          opts={{ renderer: 'svg' }}
        />
      </Card>
    </div>
  );
};

export default WorkerTradingStatsTab;