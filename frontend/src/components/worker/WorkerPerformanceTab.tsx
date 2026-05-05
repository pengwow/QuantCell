import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Row,
  Col,
  Statistic,
  Empty,
  Spin,
  Skeleton,
} from 'antd';
import ReactECharts from 'echarts-for-react';
import { useWorkerStore } from '../../store/workerStore';

const WorkerPerformanceTab: React.FC = () => {
  const { t } = useTranslation();

  const {
    performance,
    returnRateData,
    loadingPerformance,
  } = useWorkerStore();

  // 计算盈亏比
  const profitLossRatio = useMemo(() => {
    if (!performance || performance.total_loss === 0) return 0;
    return Math.abs(performance.total_profit / performance.total_loss);
  }, [performance]);

  // 核心指标
  const metrics = useMemo(() => {
    if (!performance) return [];

    return [
      {
        label: t('win_rate') || '胜率',
        value: `${performance.win_rate?.toFixed(2) || 0}%`,
        color: (performance.win_rate || 0) >= 50 ? '#52c41a' : '#ff4d4f',
      },
      {
        label: t('profit_loss_ratio') || '盈亏比',
        value: profitLossRatio.toFixed(2),
        color: profitLossRatio >= 1 ? '#52c41a' : '#ff4d4f',
      },
      {
        label: t('max_drawdown') || '最大回撤',
        value: `${performance.max_drawdown?.toFixed(2) || 0}%`,
        color: '#ff4d4f',
      },
      {
        label: t('sharpe_ratio') || '夏普比率',
        value: performance.sharpe_ratio?.toFixed(2) || '0.00',
        color: (performance.sharpe_ratio || 0) >= 1 ? '#52c41a' : '#faad14',
      },
    ];
  }, [performance, profitLossRatio, t]);

  // 收益曲线图表配置
  const chartOption = useMemo(() => {
    if (!returnRateData?.length) {
      return {
        title: {
          text: t('no_data') || '暂无数据',
          left: 'center',
          top: 'center',
          textStyle: { color: '#999', fontSize: 14 }
        },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: [],
      };
    }

    const values = returnRateData.map(d => d.value);
    const minValue = Math.min(...values, 0);
    const maxValue = Math.max(...values, 0);

    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const param = params[0];
          return `${param.name}<br/>${t('return_rate') || '收益率'}: ${param.value.toFixed(2)}%`;
        },
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: '10%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: returnRateData.map(d => d.timestamp),
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: {
          color: '#666',
          formatter: (value: string) => value.slice(0, 10),
          rotate: 30,
        },
      },
      yAxis: {
        type: 'value',
        min: Math.floor(minValue - 5),
        max: Math.ceil(maxValue + 5),
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: {
          color: '#666',
          formatter: '{value}%'
        },
        splitLine: { lineStyle: { color: '#eee' } },
      },
      series: [
        {
          name: t('return_rate') || '收益率',
          type: 'line',
          data: values,
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
  }, [returnRateData, t]);

  if (loadingPerformance) {
    return (
      <div>
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          {[...Array(4)].map((_, i) => (
            <Col span={12} key={i}>
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

  if (!performance && !returnRateData?.length) {
    return (
      <Empty
        description={t('no_performance_data') || '暂无绩效数据'}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ marginTop: 100 }}
      />
    );
  }

  return (
    <div>
      {/* 核心指标卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {metrics.map((metric) => (
          <Col xs={12} sm={12} md={6} key={metric.label}>
            <Card size="small" bordered={false} style={{ background: '#fafafa' }}>
              <Statistic
                title={<span style={{ fontSize: 13, color: '#666' }}>{metric.label}</span>}
                value={metric.value}
                valueStyle={{
                  fontSize: 22,
                  fontWeight: 'bold',
                  color: metric.color,
                }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* 补充指标（可选） */}
      {performance && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={8}>
            <Card size="small">
              <Statistic
                title={t('total_trades') || '交易次数'}
                value={performance.total_trades || 0}
                valueStyle={{ color: '#1890ff' }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8}>
            <Card size="small">
              <Statistic
                title={t('total_profit') || '总盈利'}
                value={`$${(performance.total_profit || 0).toFixed(2)}`}
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8}>
            <Card size="small">
              <Statistic
                title={t('total_loss') || '总亏损'}
                value={`$${Math.abs(performance.total_loss || 0).toFixed(2)}`}
                valueStyle={{ color: '#ff4d4f' }}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* 收益曲线图表 */}
      <Card title={t('return_rate_chart') || '收益曲线'}>
        <ReactECharts
          option={chartOption}
          style={{ height: 400 }}
          opts={{ renderer: 'svg' }}
        />
      </Card>
    </div>
  );
};

export default WorkerPerformanceTab;
