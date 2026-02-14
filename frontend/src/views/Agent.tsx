/**
 * Agent页面组件 - 量化交易专业界面
 *
 * 功能特性：
 * 1. 左右分栏布局：左侧策略列表，右侧详情面板
 * 2. 策略卡片展示：收益率、状态、操作按钮
 * 3. 策略详情：概览、收益曲线、绩效指标、交易记录
 * 4. 完整的Agent生命周期管理
 */

import React, { useEffect, useState, useCallback, lazy, Suspense } from 'react';
import {
  Card,
  Button,
  Table,
  Tag,
  Space,
  Typography,
  Row,
  Col,
  Statistic,
  Spin,
  Empty
} from 'antd';
import {
  ReloadOutlined,
  PlusOutlined,
  DownloadOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  StopOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAgentStore } from '../store/agentStore';
import { AgentStatus, AgentStatusText, AgentStatusTagColor } from '../types/agent';
import type { AgentWithPerformance, ReturnRateDataPoint, AgentPerformanceMetrics } from '../types/agent';
import '../styles/Agent.css';

const { Title, Text } = Typography;

// 动态导入 ReactECharts
const ReactECharts = lazy(() => import('echarts-for-react'));

// Agent状态标签组件
const AgentStatusTag: React.FC<{ status: AgentStatus }> = React.memo(({ status }) => {
  const label = AgentStatusText[status] || status;
  const color = AgentStatusTagColor[status] || 'default';

  return (
    <Tag color={color} style={{ minWidth: 60, textAlign: 'center' }}>
      {label}
    </Tag>
  );
});

// 交易类型标签组件
const TradeActionTag: React.FC<{ action: 'buy' | 'sell' }> = React.memo(({ action }) => {
  const isBuy = action === 'buy';
  return (
    <Tag
      color={isBuy ? 'green' : 'red'}
      style={{
        color: isBuy ? '#52c41a' : '#ff4d4f',
        background: isBuy ? '#f6ffed' : '#fff2f0',
        borderColor: isBuy ? '#b7eb8f' : '#ffccc7'
      }}
    >
      {isBuy ? '买入' : '卖出'}
    </Tag>
  );
});

// 交易状态标签组件
const TradeStatusTag: React.FC<{ status: 'filled' | 'pending' | 'cancelled' }> = React.memo(({ status }) => {
  const colorMap = {
    filled: 'blue',
    pending: 'orange',
    cancelled: 'gray'
  };
  const textMap = {
    filled: '已成交',
    pending: '挂单中',
    cancelled: '已取消'
  };
  return <Tag color={colorMap[status]}>{textMap[status]}</Tag>;
});

// 收益曲线图表组件
const ReturnRateChart: React.FC<{ data: ReturnRateDataPoint[] }> = React.memo(({ data }) => {
  const isPositive = data.length > 0 && (data[data.length - 1]?.value ?? 0) >= 0;
  const lineColor = isPositive ? '#52c41a' : '#ff4d4f';
  const areaColorStart = isPositive ? 'rgba(82, 196, 26, 0.3)' : 'rgba(255, 77, 79, 0.3)';
  const areaColorEnd = isPositive ? 'rgba(82, 196, 26, 0.1)' : 'rgba(255, 77, 79, 0.1)';

  const option = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const item = params?.[0];
        const value = item?.value ?? 0;
        return `${item?.name ?? '-'}<br/>收益率: ${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
      }
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
      boundaryGap: false,
      data: data.map(item => item.timestamp),
      axisLabel: {
        color: '#8c8c8c',
        fontSize: 10
      },
      axisLine: {
        lineStyle: {
          color: '#e8e8e8'
        }
      }
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#8c8c8c',
        formatter: '{value}%'
      },
      axisLine: {
        lineStyle: {
          color: '#e8e8e8'
        }
      },
      splitLine: {
        lineStyle: {
          color: '#f0f0f0'
        }
      }
    },
    series: [
      {
        name: '收益率',
        type: 'line',
        smooth: true,
        data: data.map(item => item.value),
        lineStyle: {
          color: lineColor,
          width: 2
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: areaColorStart },
              { offset: 1, color: areaColorEnd }
            ]
          }
        },
        itemStyle: {
          color: lineColor
        }
      }
    ]
  };

  return (
    <Suspense fallback={
      <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    }>
      <ReactECharts option={option} style={{ height: 280, width: '100%' }} />
    </Suspense>
  );
});

// 策略卡片组件
const StrategyCard: React.FC<{
  agent: AgentWithPerformance;
  isSelected: boolean;
  onSelect: (agent: AgentWithPerformance) => void;
  onPause: (id: number) => void;
  onResume: (id: number) => void;
  onStop: (id: number) => void;
  loading?: boolean;
}> = React.memo(({ agent, isSelected, onSelect, onPause, onResume, onStop, loading }) => {
  const handlePause = (e: React.MouseEvent) => {
    e.stopPropagation();
    onPause(agent.id);
  };

  const handleResume = (e: React.MouseEvent) => {
    e.stopPropagation();
    onResume(agent.id);
  };

  const handleStop = (e: React.MouseEvent) => {
    e.stopPropagation();
    onStop(agent.id);
  };

  const renderActionButtons = () => {
    switch (agent.status) {
      case AgentStatus.RUNNING:
        return (
          <Space size="small" style={{ width: '100%' }}>
            <Button
              size="small"
              icon={<PauseCircleOutlined />}
              onClick={handlePause}
              loading={loading}
              style={{ flex: 1 }}
            >
              暂停
            </Button>
            <Button
              size="small"
              danger
              icon={<StopOutlined />}
              onClick={handleStop}
              loading={loading}
              style={{ flex: 1 }}
            >
              停止
            </Button>
          </Space>
        );
      case AgentStatus.PAUSED:
        return (
          <Space size="small" style={{ width: '100%' }}>
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleResume}
              loading={loading}
              style={{ flex: 1 }}
            >
              恢复
            </Button>
            <Button
              size="small"
              danger
              icon={<StopOutlined />}
              onClick={handleStop}
              loading={loading}
              style={{ flex: 1 }}
            >
              停止
            </Button>
          </Space>
        );
      default:
        return null;
    }
  };

  const totalReturn = agent.totalReturn ?? 0;
  const currentReturn = agent.currentReturn ?? 0;

  return (
    <Card
      className={`strategy-card ${isSelected ? 'selected' : ''}`}
      onClick={() => onSelect(agent)}
      hoverable
      size="small"
    >
      <div className="card-header">
        <Text strong className="strategy-name">{agent.name}</Text>
        <AgentStatusTag status={agent.status} />
      </div>

      {agent.description && (
        <Text type="secondary" className="strategy-description">
          {agent.description}
        </Text>
      )}

      <div className="returns-row">
        <div className="return-item">
          <span className="return-label">总收益率</span>
          <span className={`return-value ${totalReturn >= 0 ? 'positive' : 'negative'}`}>
            {totalReturn >= 0 ? '+' : ''}{totalReturn.toFixed(2)}%
          </span>
        </div>
        <div className="return-item">
          <span className="return-label">今日收益</span>
          <span className={`return-value ${currentReturn >= 0 ? 'positive' : 'negative'}`}>
            {currentReturn >= 0 ? '+' : ''}{currentReturn.toFixed(2)}%
          </span>
        </div>
      </div>

      <div className="card-actions">
        {renderActionButtons()}
      </div>
    </Card>
  );
});

// 绩效指标卡片组件
const PerformanceMetricsCard: React.FC<{ metrics: AgentPerformanceMetrics }> = React.memo(({ metrics }) => {
  const netProfit = (metrics.totalProfit ?? 0) - (metrics.totalLoss ?? 0);

  const metricItems = [
    { title: '胜率', value: metrics.winRate ?? 0, suffix: '%' },
    { title: '盈亏比', value: metrics.profitLossRatio ?? 0, suffix: '' },
    { title: '最大回撤', value: metrics.maxDrawdown ?? 0, suffix: '%' },
    { title: '夏普比率', value: metrics.sharpeRatio ?? 0, suffix: '' },
    { title: '总交易数', value: metrics.totalTrades ?? 0, suffix: '' },
    { title: '盈利交易', value: metrics.winningTrades ?? 0, suffix: '' },
    { title: '亏损交易', value: metrics.losingTrades ?? 0, suffix: '' },
    { title: '总收益', value: netProfit, suffix: '$', isCurrency: true }
  ];

  return (
    <Card title="绩效指标" className="performance-metrics-card">
      <Row gutter={[16, 16]}>
        {metricItems.map((item, index) => (
          <Col xs={12} md={6} key={index}>
            <div className={`metric-item ${item.isCurrency ? (item.value >= 0 ? 'positive' : 'negative') : ''}`}>
              <Statistic
                title={item.title}
                value={item.value}
                suffix={item.suffix}
                precision={item.suffix === '$' || item.title === '盈亏比' || item.title === '夏普比率' ? 2 : 0}
              />
            </div>
          </Col>
        ))}
      </Row>
    </Card>
  );
});

// 策略详情面板组件
const AgentDetailPanel: React.FC<{
  agent: AgentWithPerformance;
}> = React.memo(({ agent }) => {
  // 交易记录表格列定义
  const tradeColumns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (text: string) => text ? dayjs(text).format('YYYY-MM-DD HH:mm:ss') : '-'
    },
    {
      title: '交易对',
      dataIndex: 'symbol',
      key: 'symbol'
    },
    {
      title: '类型',
      dataIndex: 'action',
      key: 'action',
      render: (action: 'buy' | 'sell') => <TradeActionTag action={action} />
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      render: (price: number) => `$${(price ?? 0).toFixed(2)}`
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      render: (quantity: number) => (quantity ?? 0).toFixed(4)
    },
    {
      title: '金额',
      dataIndex: 'amount',
      key: 'amount',
      render: (amount: number) => `$${(amount ?? 0).toFixed(2)}`
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: 'filled' | 'pending' | 'cancelled') => <TradeStatusTag status={status} />
    }
  ];

  return (
    <div className="agent-detail-container">
      {/* 策略概览卡片 */}
      <Card className="strategy-overview-card">
        <Row gutter={[16, 16]}>
          <Col xs={24} md={8}>
            <div className="overview-header">
              <Title level={4} className="strategy-title">{agent.name}</Title>
              {agent.description && (
                <Text type="secondary" className="strategy-desc">{agent.description}</Text>
              )}
              <div className="overview-meta">
                <div className="meta-item">
                  <span className="meta-label">状态:</span>
                  <AgentStatusTag status={agent.status} />
                </div>
                {agent.startTime && (
                  <div className="meta-item">
                    <span className="meta-label">启动时间:</span>
                    <span className="meta-value">{dayjs(agent.startTime).format('YYYY-MM-DD HH:mm:ss')}</span>
                  </div>
                )}
                <div className="meta-item">
                  <span className="meta-label">最后交易:</span>
                  <span className="meta-value">
                    {agent.lastTradeTime ? dayjs(agent.lastTradeTime).format('YYYY-MM-DD HH:mm:ss') : '暂无交易'}
                  </span>
                </div>
              </div>
            </div>
          </Col>
          <Col xs={24} md={16}>
            <div className="return-chart-container">
              <ReturnRateChart data={agent.returnRateData} />
            </div>
          </Col>
        </Row>
      </Card>

      {/* 绩效指标卡片 */}
      <PerformanceMetricsCard metrics={agent.performance} />

      {/* 交易记录卡片 */}
      <Card title="交易记录" className="trade-records-card">
        <Table
          columns={tradeColumns}
          dataSource={agent.tradeRecords}
          rowKey="id"
          pagination={{ pageSize: 5 }}
          scroll={{ x: 'max-content' }}
          size="small"
        />
      </Card>
    </div>
  );
});

// 空状态组件
const EmptyState: React.FC = React.memo(() => (
  <Card className="empty-state-card">
    <Empty
      description="请选择一个策略查看详细信息"
      image={Empty.PRESENTED_IMAGE_SIMPLE}
    />
  </Card>
));

// 主页面组件
const Agent: React.FC = () => {
  // Store状态
  const {
    agents,
    selectedAgent,
    listStatus,
    lifecycleStatus,
    fetchAgents,
    selectAgent,
    pauseAgent,
    resumeAgent,
    stopAgent,
    fetchAgentPerformanceMetrics,
    fetchAgentTradeRecords,
    fetchAgentReturnRateData
  } = useAgentStore();

  // 本地状态
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);

  // 计算加载状态
  const isListLoading = listStatus === 'loading';
  const isLifecycleLoading = lifecycleStatus === 'loading';

  // 获取Agent列表
  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // 加载选中策略的详细数据
  useEffect(() => {
    if (selectedAgent) {
      fetchAgentPerformanceMetrics(selectedAgent.id);
      fetchAgentTradeRecords(selectedAgent.id);
      fetchAgentReturnRateData(selectedAgent.id);
    }
  }, [selectedAgent, fetchAgentPerformanceMetrics, fetchAgentTradeRecords, fetchAgentReturnRateData]);

  // 处理策略选择
  const handleSelectAgent = useCallback((agent: AgentWithPerformance) => {
    setSelectedAgentId(agent.id);
    selectAgent(agent);
  }, [selectAgent]);

  // 处理暂停策略
  const handlePauseAgent = useCallback(async (id: number) => {
    try {
      await pauseAgent(id);
    } catch {
      // 错误已在store中处理
    }
  }, [pauseAgent]);

  // 处理恢复策略
  const handleResumeAgent = useCallback(async (id: number) => {
    try {
      await resumeAgent(id);
    } catch {
      // 错误已在store中处理
    }
  }, [resumeAgent]);

  // 处理停止策略
  const handleStopAgent = useCallback(async (id: number) => {
    try {
      await stopAgent(id);
    } catch {
      // 错误已在store中处理
    }
  }, [stopAgent]);

  // 处理刷新
  const handleRefresh = useCallback(() => {
    fetchAgents();
  }, [fetchAgents]);

  // 处理新建策略
  const handleCreateStrategy = useCallback(() => {
    // TODO: 打开新建策略对话框
    console.log('新建策略');
  }, []);

  // 处理导出报告
  const handleExportReport = useCallback(() => {
    // TODO: 导出报告功能
    console.log('导出报告');
  }, []);

  return (
    <div style={{ padding: 24 }}>
      {/* 页面头部 */}
      <div className="agent-page-header">
        <Title level={2} className="header-title">策略代理</Title>
        <Space className="header-actions">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreateStrategy}
          >
            新建策略
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={isListLoading}
          >
            刷新
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExportReport}
            disabled={!selectedAgent}
          >
            导出报告
          </Button>
        </Space>
      </div>

      {/* 主布局 */}
      <Row gutter={[16, 16]} className="agent-page-layout">
        {/* 左侧策略列表 */}
        <Col xs={24} lg={6}>
          <div className="agent-list-container">
            <Spin spinning={isListLoading}>
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {agents.map(agent => (
                  <StrategyCard
                    key={agent.id}
                    agent={agent}
                    isSelected={selectedAgentId === agent.id}
                    onSelect={handleSelectAgent}
                    onPause={handlePauseAgent}
                    onResume={handleResumeAgent}
                    onStop={handleStopAgent}
                    loading={isLifecycleLoading}
                  />
                ))}
                {agents.length === 0 && !isListLoading && (
                  <Empty description="暂无策略" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Space>
            </Spin>
          </div>
        </Col>

        {/* 右侧详情面板 */}
        <Col xs={24} lg={18}>
          {selectedAgent ? (
            <AgentDetailPanel agent={selectedAgent} />
          ) : (
            <EmptyState />
          )}
        </Col>
      </Row>
    </div>
  );
};

export default Agent;
