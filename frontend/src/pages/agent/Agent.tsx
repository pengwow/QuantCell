import { useEffect, useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Button,
  Card,
  Tag,
  Table,
  Spin,
  message,
  Tooltip,
  Popconfirm,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  ExportOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  RobotOutlined,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { useAgentStore } from '../../store';
import { AgentStatusTagColor, AgentStatusDisplayText, type AgentWithPerformance } from '../../types/agent';
import PageContainer from '@/components/PageContainer';
import './Agent.css';

const Agent = () => {
  const { t } = useTranslation();
  const {
    agents,
    selectedAgent,
    loading,
    fetchAgents,
    selectAgent,
    startAgent,
    stopAgent,
    pauseAgent,
  } = useAgentStore();

  const [tradePagination, setTradePagination] = useState({ current: 1, pageSize: 10 });

  // 初始加载
  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // 收益曲线图配置
  const chartOption = useMemo(() => {
    if (!selectedAgent?.returnRateData?.length) {
      return {
        title: { text: '暂无数据', left: 'center', top: 'center' },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: [],
      };
    }

    const data = selectedAgent.returnRateData;
    const values = data.map(d => d.value);
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);

    return {
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: data.map(d => d.timestamp),
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: { color: '#666' },
      },
      yAxis: {
        type: 'value',
        min: Math.floor(minValue - 5),
        max: Math.ceil(maxValue + 5),
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: { color: '#666', formatter: '{value}%' },
        splitLine: { lineStyle: { color: '#eee' } },
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const param = params[0];
          return `${param.name}<br/>收益率: ${param.value}%`;
        },
      },
      series: [
        {
          name: '收益率',
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
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(24, 144, 255, 0.3)' },
                { offset: 1, color: 'rgba(24, 144, 255, 0.05)' },
              ],
            },
          },
        },
      ],
    };
  }, [selectedAgent?.returnRateData]);

  // 交易记录表格列
  const tradeColumns = [
    {
      title: t('agent.tradeTime', '交易时间'),
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (text: string) => new Date(text).toLocaleString(),
    },
    {
      title: t('agent.symbol', '交易品种'),
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: t('agent.action', '操作'),
      dataIndex: 'action',
      key: 'action',
      render: (action: 'buy' | 'sell') => (
        <Tag color={action === 'buy' ? 'red' : 'green'}>
          {action === 'buy' ? t('agent.buy', '买入') : t('agent.sell', '卖出')}
        </Tag>
      ),
    },
    {
      title: t('agent.price', '价格'),
      dataIndex: 'price',
      key: 'price',
      render: (price: number) => `$${price.toFixed(2)}`,
    },
    {
      title: t('agent.quantity', '数量'),
      dataIndex: 'quantity',
      key: 'quantity',
    },
    {
      title: t('agent.amount', '金额'),
      dataIndex: 'amount',
      key: 'amount',
      render: (amount: number) => `$${amount.toFixed(2)}`,
    },
    {
      title: t('agent.status', '状态'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap: Record<string, { text: string; color: string }> = {
          filled: { text: t('agent.filled', '已成交'), color: 'success' },
          pending: { text: t('agent.pending', '待成交'), color: 'warning' },
          cancelled: { text: t('agent.cancelled', '已取消'), color: 'default' },
        };
        const { text, color } = statusMap[status] || { text: status, color: 'default' };
        return <Tag color={color}>{text}</Tag>;
      },
    },
  ];

  // 处理启动
  const handleStart = async (agent: AgentWithPerformance, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await startAgent(agent.id);
      message.success(t('agent.startSuccess', '策略代理启动成功'));
    } catch {
      message.error(t('agent.startError', '策略代理启动失败'));
    }
  };

  // 处理停止
  const handleStop = async (agent: AgentWithPerformance, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await stopAgent(agent.id);
      message.success(t('agent.stopSuccess', '策略代理停止成功'));
    } catch {
      message.error(t('agent.stopError', '策略代理停止失败'));
    }
  };

  // 处理暂停
  const handlePause = async (agent: AgentWithPerformance, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await pauseAgent(agent.id);
      message.success(t('agent.pauseSuccess', '策略代理暂停成功'));
    } catch {
      message.error(t('agent.pauseError', '策略代理暂停失败'));
    }
  };

  // 处理导出
  const handleExport = () => {
    message.info(t('agent.exportComingSoon', '导出功能即将上线'));
  };

  // 绩效指标数据
  const metricsData = useMemo(() => {
    if (!selectedAgent?.performance) return [];
    const p = selectedAgent.performance;
    return [
      { label: t('agent.winRate', '胜率'), value: `${p.winRate.toFixed(2)}%`, positive: p.winRate >= 50 },
      { label: t('agent.profitLossRatio', '盈亏比'), value: p.profitLossRatio.toFixed(2), positive: p.profitLossRatio >= 1 },
      { label: t('agent.maxDrawdown', '最大回撤'), value: `${p.maxDrawdown.toFixed(2)}%`, positive: false },
      { label: t('agent.sharpeRatio', '夏普比率'), value: p.sharpeRatio.toFixed(2), positive: p.sharpeRatio >= 1 },
      { label: t('agent.totalTrades', '总交易数'), value: p.totalTrades.toString(), positive: true },
      { label: t('agent.winningTrades', '盈利交易'), value: p.winningTrades.toString(), positive: true },
      { label: t('agent.losingTrades', '亏损交易'), value: p.losingTrades.toString(), positive: false },
      { label: t('agent.totalProfit', '总收益'), value: `$${p.totalProfit.toFixed(2)}`, positive: p.totalProfit > 0 },
    ];
  }, [selectedAgent?.performance, t]);

  return (
    <PageContainer title={t('agent')}>
    <div className="agent-page">
      {/* 页面头部 */}
      <div className="agent-page-header">
        <h1>{t('agent.title', '策略代理')}</h1>
        <div className="agent-page-actions">
          <Button type="primary" icon={<PlusOutlined />}>
            {t('agent.new', '新建')}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={fetchAgents} loading={loading}>
            {t('agent.refresh', '刷新')}
          </Button>
          <Button icon={<ExportOutlined />} onClick={handleExport}>
            {t('agent.export', '导出')}
          </Button>
        </div>
      </div>

      {/* 页面内容 */}
      <div className="agent-page-content">
        <Spin spinning={loading}>
          {/* 左侧策略列表 */}
          <div className="agent-list">
            {agents.map((agent) => (
              <div
                key={agent.id}
                className={`agent-card ${selectedAgent?.id === agent.id ? 'selected' : ''}`}
                onClick={() => selectAgent(agent)}
              >
                <div className="agent-card-header">
                  <h3 className="agent-card-title">{agent.name}</h3>
                  <Tag color={AgentStatusTagColor[agent.status]}>
                    {AgentStatusDisplayText[agent.status]}
                  </Tag>
                </div>
                <p className="agent-card-desc">{agent.description}</p>
                <div className="agent-card-footer">
                  <span
                    className={`agent-card-return ${agent.totalReturn >= 0 ? 'positive' : 'negative'}`}
                  >
                    {agent.totalReturn >= 0 ? '+' : ''}
                    {agent.totalReturn.toFixed(2)}%
                  </span>
                  <div className="agent-card-actions">
                    {agent.status === 'stopped' && (
                      <Tooltip title={t('agent.start', '启动')}>
                        <Button
                          type="text"
                          size="small"
                          icon={<PlayCircleOutlined />}
                          onClick={(e) => handleStart(agent, e)}
                        />
                      </Tooltip>
                    )}
                    {agent.status === 'running' && (
                      <>
                        <Tooltip title={t('agent.pause', '暂停')}>
                          <Button
                            type="text"
                            size="small"
                            icon={<PauseCircleOutlined />}
                            onClick={(e) => handlePause(agent, e)}
                          />
                        </Tooltip>
                        <Tooltip title={t('agent.stop', '停止')}>
                          <Button
                            type="text"
                            size="small"
                            icon={<StopOutlined />}
                            onClick={(e) => handleStop(agent, e)}
                          />
                        </Tooltip>
                      </>
                    )}
                    {agent.status === 'paused' && (
                      <>
                        <Tooltip title={t('agent.resume', '恢复')}>
                          <Button
                            type="text"
                            size="small"
                            icon={<PlayCircleOutlined />}
                            onClick={(e) => handleStart(agent, e)}
                          />
                        </Tooltip>
                        <Tooltip title={t('agent.stop', '停止')}>
                          <Button
                            type="text"
                            size="small"
                            icon={<StopOutlined />}
                            onClick={(e) => handleStop(agent, e)}
                          />
                        </Tooltip>
                      </>
                    )}
                    <Tooltip title={t('agent.edit', '编辑')}>
                      <Button type="text" size="small" icon={<EditOutlined />} />
                    </Tooltip>
                    <Popconfirm
                      title={t('agent.deleteConfirm', '确定要删除此策略代理吗？')}
                      okText={t('common.yes', '是')}
                      cancelText={t('common.no', '否')}
                    >
                      <Tooltip title={t('agent.delete', '删除')}>
                        <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                      </Tooltip>
                    </Popconfirm>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* 右侧详情面板 */}
          <div className="agent-detail">
            {!selectedAgent ? (
              <div className="agent-detail-empty">
                <RobotOutlined />
                <p>{t('agent.selectPrompt', '请从左侧选择一个策略代理查看详情')}</p>
              </div>
            ) : (
              <>
                {/* 策略概览 */}
                <Card className="agent-overview">
                  <div className="agent-overview-header">
                    <div>
                      <h2 className="agent-overview-title">{selectedAgent.name}</h2>
                      <p className="agent-overview-desc">{selectedAgent.description}</p>
                    </div>
                    <div className="agent-overview-actions">
                      {selectedAgent.status === 'stopped' && (
                        <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => startAgent(selectedAgent.id)}>
                          {t('agent.start', '启动')}
                        </Button>
                      )}
                      {selectedAgent.status === 'running' && (
                        <>
                          <Button icon={<PauseCircleOutlined />} onClick={() => pauseAgent(selectedAgent.id)}>
                            {t('agent.pause', '暂停')}
                          </Button>
                          <Button danger icon={<StopOutlined />} onClick={() => stopAgent(selectedAgent.id)}>
                            {t('agent.stop', '停止')}
                          </Button>
                        </>
                      )}
                      {selectedAgent.status === 'paused' && (
                        <>
                          <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => startAgent(selectedAgent.id)}>
                            {t('agent.resume', '恢复')}
                          </Button>
                          <Button danger icon={<StopOutlined />} onClick={() => stopAgent(selectedAgent.id)}>
                            {t('agent.stop', '停止')}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="agent-overview-info">
                    <div className="agent-overview-info-item">
                      <span className="agent-overview-info-label">{t('agent.status', '状态')}</span>
                      <span className="agent-overview-info-value">
                        <Tag color={AgentStatusTagColor[selectedAgent.status]}>
                          {AgentStatusDisplayText[selectedAgent.status]}
                        </Tag>
                      </span>
                    </div>
                    <div className="agent-overview-info-item">
                      <span className="agent-overview-info-label">{t('agent.exchange', '交易所')}</span>
                      <span className="agent-overview-info-value">{selectedAgent.exchange}</span>
                    </div>
                    <div className="agent-overview-info-item">
                      <span className="agent-overview-info-label">{t('agent.symbol', '交易品种')}</span>
                      <span className="agent-overview-info-value">{selectedAgent.symbol}</span>
                    </div>
                    <div className="agent-overview-info-item">
                      <span className="agent-overview-info-label">{t('agent.timeframe', '时间周期')}</span>
                      <span className="agent-overview-info-value">{selectedAgent.timeframe}</span>
                    </div>
                    <div className="agent-overview-info-item">
                      <span className="agent-overview-info-label">{t('agent.createdAt', '创建时间')}</span>
                      <span className="agent-overview-info-value">
                        {new Date(selectedAgent.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </Card>

                {/* 收益曲线图 */}
                <Card className="agent-chart" title={t('agent.returnRateChart', '收益率曲线')}>
                  <div className="agent-chart-container">
                    <ReactECharts option={chartOption} style={{ height: '100%', width: '100%' }} />
                  </div>
                </Card>

                {/* 绩效指标 */}
                <Card className="agent-metrics" title={t('agent.performanceMetrics', '绩效指标')}>
                  <div className="agent-metrics-grid">
                    {metricsData.map((metric, index) => (
                      <div key={index} className="agent-metric-card">
                        <div className="agent-metric-label">{metric.label}</div>
                        <div className={`agent-metric-value ${metric.positive ? 'positive' : 'negative'}`}>
                          {metric.value}
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>

                {/* 交易记录 */}
                <Card className="agent-trades" title={t('agent.tradeRecords', '交易记录')}>
                  <Table
                    columns={tradeColumns}
                    dataSource={selectedAgent.tradeRecords}
                    rowKey="id"
                    pagination={{
                      ...tradePagination,
                      onChange: (page, pageSize) => setTradePagination({ current: page, pageSize: pageSize || 10 }),
                    }}
                    size="small"
                  />
                </Card>
              </>
            )}
          </div>
        </Spin>
      </div>
    </div>
    </PageContainer>
  );
};

export default Agent;
