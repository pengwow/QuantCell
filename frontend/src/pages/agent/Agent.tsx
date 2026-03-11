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
  Row,
  Col,
  Statistic,
  Empty,
  Space,
  Grid,
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
  CheckCircleOutlined,
  CloseCircleOutlined,
  PauseOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { useAgentStore } from '../../store';
import { AgentStatusTagColor, AgentStatusDisplayText, type AgentWithPerformance } from '../../types/agent';
import PageContainer from '@/components/PageContainer';
import './Agent.css';

const { useBreakpoint } = Grid;

const Agent = () => {
  const { t } = useTranslation();
  const screens = useBreakpoint();
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

  // 统计各状态的任务数量
  const statusStats = useMemo(() => {
    return {
      total: agents.length,
      running: agents.filter(a => a.status === 'running').length,
      stopped: agents.filter(a => a.status === 'stopped').length,
      paused: agents.filter(a => a.status === 'paused').length,
    };
  }, [agents]);

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
      width: 160,
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
      message.success(t('agent.startSuccess', '策略任务启动成功'));
    } catch {
      message.error(t('agent.startError', '策略任务启动失败'));
    }
  };

  // 处理停止
  const handleStop = async (agent: AgentWithPerformance, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await stopAgent(agent.id);
      message.success(t('agent.stopSuccess', '策略任务停止成功'));
    } catch {
      message.error(t('agent.stopError', '策略任务停止失败'));
    }
  };

  // 处理暂停
  const handlePause = async (agent: AgentWithPerformance, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await pauseAgent(agent.id);
      message.success(t('agent.pauseSuccess', '策略任务暂停成功'));
    } catch {
      message.error(t('agent.pauseError', '策略任务暂停失败'));
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

  // 渲染统计卡片
  const renderStatistics = () => (
    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title="总任务"
            value={statusStats.total}
            prefix={<BarChartOutlined />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title="运行中"
            value={statusStats.running}
            valueStyle={{ color: '#52c41a' }}
            prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title="已暂停"
            value={statusStats.paused}
            valueStyle={{ color: '#faad14' }}
            prefix={<PauseOutlined style={{ color: '#faad14' }} />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title="已停止"
            value={statusStats.stopped}
            valueStyle={{ color: '#999' }}
            prefix={<CloseCircleOutlined style={{ color: '#999' }} />}
          />
        </Card>
      </Col>
    </Row>
  );

  // 渲染工具栏
  const renderToolbar = () => (
    <Row gutter={[12, 12]} style={{ marginBottom: 16 }} align="middle">
      <Col xs={24} md={12} lg={16}>
        <Space>
          <Button type="primary" icon={<PlusOutlined />}>
            {t('agent.new', '新建任务')}
          </Button>
        </Space>
      </Col>
      <Col xs={24} md={12} lg={8} style={{ textAlign: screens.md ? 'right' : 'left' }}>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={fetchAgents} loading={loading}>
            {t('agent.refresh', '刷新')}
          </Button>
          <Button icon={<ExportOutlined />} onClick={handleExport}>
            {t('agent.export', '导出')}
          </Button>
        </Space>
      </Col>
    </Row>
  );

  // 渲染任务列表
  const renderTaskList = () => (
    <Card 
      title={t('agent.taskList', '任务列表')} 
      size="small"
      bodyStyle={{ padding: 0, maxHeight: 600, overflow: 'auto' }}
    >
      {agents.length === 0 ? (
        <Empty description="暂无策略任务" style={{ padding: 40 }} />
      ) : (
        <div className="agent-list-container">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className={`agent-list-item ${selectedAgent?.id === agent.id ? 'selected' : ''}`}
              onClick={() => selectAgent(agent)}
            >
              <div className="agent-list-item-header">
                <span className="agent-list-item-name">{agent.name}</span>
                <Tag color={AgentStatusTagColor[agent.status]}>
                  {AgentStatusDisplayText[agent.status]}
                </Tag>
              </div>
              <div className="agent-list-item-info">
                <span>{agent.symbol}</span>
                <span className="agent-list-item-timeframe">{agent.timeframe}</span>
              </div>
              <div className="agent-list-item-footer">
                <span className={`agent-list-item-return ${agent.totalReturn >= 0 ? 'positive' : 'negative'}`}>
                  {agent.totalReturn >= 0 ? '+' : ''}{agent.totalReturn.toFixed(2)}%
                </span>
                <Space size="small" onClick={(e) => e.stopPropagation()}>
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
                    title={t('agent.deleteConfirm', '确定要删除此策略任务吗？')}
                    okText={t('common.yes', '是')}
                    cancelText={t('common.no', '否')}
                  >
                    <Tooltip title={t('agent.delete', '删除')}>
                      <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                    </Tooltip>
                  </Popconfirm>
                </Space>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );

  // 渲染任务详情
  const renderTaskDetail = () => {
    if (!selectedAgent) {
      return (
        <Card style={{ height: '100%', minHeight: 400 }}>
          <Empty
            image={<RobotOutlined style={{ fontSize: 64, opacity: 0.3 }} />}
            description={t('agent.selectPrompt', '请从左侧选择一个策略任务查看详情')}
            style={{ paddingTop: 100 }}
          />
        </Card>
      );
    }

    return (
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {/* 策略概览 */}
        <Card size="small" title={selectedAgent.name}>
          <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
            <Col>
              <Space>
                <Tag color={AgentStatusTagColor[selectedAgent.status]}>
                  {AgentStatusDisplayText[selectedAgent.status]}
                </Tag>
                <span>{selectedAgent.symbol} | {selectedAgent.timeframe}</span>
              </Space>
            </Col>
            <Col>
              <Space>
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
              </Space>
            </Col>
          </Row>
          <p style={{ color: '#666', marginBottom: 16 }}>{selectedAgent.description}</p>
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <Statistic title={t('agent.exchange', '交易所')} value={selectedAgent.exchange} />
            </Col>
            <Col span={8}>
              <Statistic title={t('agent.createdAt', '创建时间')} value={new Date(selectedAgent.created_at).toLocaleDateString()} />
            </Col>
            <Col span={8}>
              <Statistic 
                title={t('agent.totalReturn', '总收益')} 
                value={`${selectedAgent.totalReturn >= 0 ? '+' : ''}${selectedAgent.totalReturn.toFixed(2)}%`}
                valueStyle={{ color: selectedAgent.totalReturn >= 0 ? '#52c41a' : '#f5222d' }}
              />
            </Col>
          </Row>
        </Card>

        {/* 收益曲线图 */}
        <Card size="small" title={t('agent.returnRateChart', '收益率曲线')}>
          <div style={{ height: 300 }}>
            <ReactECharts option={chartOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </Card>

        {/* 绩效指标 */}
        <Card size="small" title={t('agent.performanceMetrics', '绩效指标')}>
          <Row gutter={[16, 16]}>
            {metricsData.map((metric, index) => (
              <Col xs={12} sm={8} md={6} key={index}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>{metric.label}</div>
                  <div style={{ 
                    fontSize: 20, 
                    fontWeight: 600,
                    color: metric.positive ? '#52c41a' : '#f5222d'
                  }}>
                    {metric.value}
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
        </Card>

        {/* 交易记录 */}
        <Card size="small" title={t('agent.tradeRecords', '交易记录')}>
          <Table
            columns={tradeColumns}
            dataSource={selectedAgent.tradeRecords}
            rowKey="id"
            pagination={{
              ...tradePagination,
              onChange: (page, pageSize) => setTradePagination({ current: page, pageSize: pageSize || 10 }),
            }}
            size="small"
            scroll={{ x: 800 }}
          />
        </Card>
      </Space>
    );
  };

  return (
    <PageContainer title={t('strategy_task')}>
      <Spin spinning={loading}>
        {/* 统计卡片 */}
        {renderStatistics()}

        {/* 工具栏 */}
        {renderToolbar()}

        {/* 主内容区 */}
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={8} xl={6}>
            {renderTaskList()}
          </Col>
          <Col xs={24} lg={16} xl={18}>
            {renderTaskDetail()}
          </Col>
        </Row>
      </Spin>
    </PageContainer>
  );
};

export default Agent;
