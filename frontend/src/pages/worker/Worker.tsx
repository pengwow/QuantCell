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
import { useWorkerStore } from '../../store';
import { WorkerStatusTagColor, WorkerStatusDisplayText, type WorkerWithPerformance } from '../../types/worker';
import PageContainer from '@/components/PageContainer';
import './Worker.css';

const { useBreakpoint } = Grid;

const Worker = () => {
  const { t } = useTranslation();
  const screens = useBreakpoint();
  const {
    workers,
    selectedWorker,
    loading,
    fetchWorkers,
    selectWorker,
    startWorker,
    stopWorker,
    pauseWorker,
  } = useWorkerStore();

  const [tradePagination, setTradePagination] = useState({ current: 1, pageSize: 10 });

  // 初始加载
  useEffect(() => {
    fetchWorkers();
  }, [fetchWorkers]);

  // 默认选中第一个任务
  useEffect(() => {
    if (workers.length > 0 && !selectedWorker) {
      selectWorker(workers[0]);
    }
  }, [workers, selectedWorker, selectWorker]);

  // 统计各状态的任务数量
  const statusStats = useMemo(() => {
    return {
      total: workers.length,
      running: workers.filter(w => w.status === 'running').length,
      stopped: workers.filter(w => w.status === 'stopped').length,
      paused: workers.filter(w => w.status === 'paused').length,
    };
  }, [workers]);

  // 收益曲线图配置
  const chartOption = useMemo(() => {
    if (!selectedWorker?.returnRateData?.length) {
      return {
        title: { text: '暂无数据', left: 'center', top: 'center' },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: [],
      };
    }

    const data = selectedWorker.returnRateData;
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
  }, [selectedWorker?.returnRateData]);

  // 交易记录表格列
  const tradeColumns = [
    {
      title: t('worker.tradeTime', '交易时间'),
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 160,
      render: (text: string) => new Date(text).toLocaleString(),
    },
    {
      title: t('worker.symbol', '交易品种'),
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: t('worker.action', '操作'),
      dataIndex: 'action',
      key: 'action',
      render: (action: 'buy' | 'sell') => (
        <Tag color={action === 'buy' ? 'red' : 'green'}>
          {action === 'buy' ? t('worker.buy', '买入') : t('worker.sell', '卖出')}
        </Tag>
      ),
    },
    {
      title: t('worker.price', '价格'),
      dataIndex: 'price',
      key: 'price',
      render: (price: number) => `$${price.toFixed(2)}`,
    },
    {
      title: t('worker.quantity', '数量'),
      dataIndex: 'quantity',
      key: 'quantity',
    },
    {
      title: t('worker.amount', '金额'),
      dataIndex: 'amount',
      key: 'amount',
      render: (amount: number) => `$${amount.toFixed(2)}`,
    },
    {
      title: t('worker.status', '状态'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap: Record<string, { text: string; color: string }> = {
          filled: { text: t('worker.filled', '已成交'), color: 'success' },
          pending: { text: t('worker.pending', '待成交'), color: 'warning' },
          cancelled: { text: t('worker.cancelled', '已取消'), color: 'default' },
        };
        const { text, color } = statusMap[status] || { text: status, color: 'default' };
        return <Tag color={color}>{text}</Tag>;
      },
    },
  ];

  // 处理启动
  const handleStart = async (worker: WorkerWithPerformance, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await startWorker(worker.id);
      message.success(t('worker.startSuccess', '策略任务启动成功'));
    } catch {
      message.error(t('worker.startError', '策略任务启动失败'));
    }
  };

  // 处理停止
  const handleStop = async (worker: WorkerWithPerformance, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await stopWorker(worker.id);
      message.success(t('worker.stopSuccess', '策略任务停止成功'));
    } catch {
      message.error(t('worker.stopError', '策略任务停止失败'));
    }
  };

  // 处理暂停
  const handlePause = async (worker: WorkerWithPerformance, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await pauseWorker(worker.id);
      message.success(t('worker.pauseSuccess', '策略任务暂停成功'));
    } catch {
      message.error(t('worker.pauseError', '策略任务暂停失败'));
    }
  };

  // 处理导出
  const handleExport = () => {
    message.info(t('worker.exportComingSoon', '导出功能即将上线'));
  };

  // 绩效指标数据
  const metricsData = useMemo(() => {
    if (!selectedWorker?.performance) return [];
    const p = selectedWorker.performance;
    return [
      { label: t('worker.winRate', '胜率'), value: `${p.winRate.toFixed(2)}%`, positive: p.winRate >= 50 },
      { label: t('worker.profitLossRatio', '盈亏比'), value: p.profitLossRatio.toFixed(2), positive: p.profitLossRatio >= 1 },
      { label: t('worker.maxDrawdown', '最大回撤'), value: `${p.maxDrawdown.toFixed(2)}%`, positive: false },
      { label: t('worker.sharpeRatio', '夏普比率'), value: p.sharpeRatio.toFixed(2), positive: p.sharpeRatio >= 1 },
      { label: t('worker.totalTrades', '总交易数'), value: p.totalTrades.toString(), positive: true },
      { label: t('worker.winningTrades', '盈利交易'), value: p.winningTrades.toString(), positive: true },
      { label: t('worker.losingTrades', '亏损交易'), value: p.losingTrades.toString(), positive: false },
      { label: t('worker.totalProfit', '总收益'), value: `$${p.totalProfit.toFixed(2)}`, positive: p.totalProfit > 0 },
    ];
  }, [selectedWorker?.performance, t]);

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
            {t('worker.new', '新建任务')}
          </Button>
        </Space>
      </Col>
      <Col xs={24} md={12} lg={8} style={{ textAlign: screens.md ? 'right' : 'left' }}>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={fetchWorkers} loading={loading}>
            {t('worker.refresh', '刷新')}
          </Button>
          <Button icon={<ExportOutlined />} onClick={handleExport}>
            {t('worker.export', '导出')}
          </Button>
        </Space>
      </Col>
    </Row>
  );

  // 渲染任务列表
  const renderTaskList = () => (
    <Card 
      title={t('worker.taskList', '任务列表')} 
      size="small"
      bodyStyle={{ padding: 0, maxHeight: 600, overflow: 'auto' }}
    >
      {workers.length === 0 ? (
        <Empty description="暂无策略任务" style={{ padding: 40 }} />
      ) : (
        <div className="worker-list-container">
          {workers.map((worker) => (
            <div
              key={worker.id}
              className={`worker-list-item ${selectedWorker?.id === worker.id ? 'selected' : ''}`}
              onClick={() => selectWorker(worker)}
            >
              <div className="worker-list-item-header">
                <span className="worker-list-item-name">{worker.name}</span>
                <Tag color={WorkerStatusTagColor[worker.status]}>
                  {WorkerStatusDisplayText[worker.status]}
                </Tag>
              </div>
              <div className="worker-list-item-info">
                <span>{worker.symbol}</span>
                <span className="worker-list-item-timeframe">{worker.timeframe}</span>
              </div>
              <div className="worker-list-item-footer">
                <span className={`worker-list-item-return ${worker.totalReturn >= 0 ? 'positive' : 'negative'}`}>
                  {worker.totalReturn >= 0 ? '+' : ''}{worker.totalReturn.toFixed(2)}%
                </span>
                <Space size="small" onClick={(e) => e.stopPropagation()}>
                  {worker.status === 'stopped' && (
                    <Tooltip title={t('worker.start', '启动')}>
                      <Button
                        type="text"
                        size="small"
                        icon={<PlayCircleOutlined />}
                        onClick={(e) => handleStart(worker, e)}
                      />
                    </Tooltip>
                  )}
                  {worker.status === 'running' && (
                    <>
                      <Tooltip title={t('worker.pause', '暂停')}>
                        <Button
                          type="text"
                          size="small"
                          icon={<PauseCircleOutlined />}
                          onClick={(e) => handlePause(worker, e)}
                        />
                      </Tooltip>
                      <Tooltip title={t('worker.stop', '停止')}>
                        <Button
                          type="text"
                          size="small"
                          icon={<StopOutlined />}
                          onClick={(e) => handleStop(worker, e)}
                        />
                      </Tooltip>
                    </>
                  )}
                  {worker.status === 'paused' && (
                    <>
                      <Tooltip title={t('worker.resume', '恢复')}>
                        <Button
                          type="text"
                          size="small"
                          icon={<PlayCircleOutlined />}
                          onClick={(e) => handleStart(worker, e)}
                        />
                      </Tooltip>
                      <Tooltip title={t('worker.stop', '停止')}>
                        <Button
                          type="text"
                          size="small"
                          icon={<StopOutlined />}
                          onClick={(e) => handleStop(worker, e)}
                        />
                      </Tooltip>
                    </>
                  )}
                  <Tooltip title={t('worker.edit', '编辑')}>
                    <Button type="text" size="small" icon={<EditOutlined />} />
                  </Tooltip>
                  <Popconfirm
                    title={t('worker.deleteConfirm', '确定要删除此策略任务吗？')}
                    okText={t('common.yes', '是')}
                    cancelText={t('common.no', '否')}
                  >
                    <Tooltip title={t('worker.delete', '删除')}>
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
    if (!selectedWorker) {
      return (
        <Card style={{ height: '100%', minHeight: 400 }}>
          <Empty
            image={<RobotOutlined style={{ fontSize: 64, opacity: 0.3 }} />}
            description={t('worker.selectPrompt', '请从左侧选择一个策略任务查看详情')}
            style={{ paddingTop: 100 }}
          />
        </Card>
      );
    }

    return (
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {/* 策略概览 */}
        <Card size="small" title={selectedWorker.name}>
          <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
            <Col>
              <Space>
                <Tag color={WorkerStatusTagColor[selectedWorker.status]}>
                  {WorkerStatusDisplayText[selectedWorker.status]}
                </Tag>
                <span>{selectedWorker.symbol} | {selectedWorker.timeframe}</span>
              </Space>
            </Col>
            <Col>
              <Space>
                {selectedWorker.status === 'stopped' && (
                  <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => startWorker(selectedWorker.id)}>
                    {t('worker.start', '启动')}
                  </Button>
                )}
                {selectedWorker.status === 'running' && (
                  <>
                    <Button icon={<PauseCircleOutlined />} onClick={() => pauseWorker(selectedWorker.id)}>
                      {t('worker.pause', '暂停')}
                    </Button>
                    <Button danger icon={<StopOutlined />} onClick={() => stopWorker(selectedWorker.id)}>
                      {t('worker.stop', '停止')}
                    </Button>
                  </>
                )}
                {selectedWorker.status === 'paused' && (
                  <>
                    <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => startWorker(selectedWorker.id)}>
                      {t('worker.resume', '恢复')}
                    </Button>
                    <Button danger icon={<StopOutlined />} onClick={() => stopWorker(selectedWorker.id)}>
                      {t('worker.stop', '停止')}
                    </Button>
                  </>
                )}
              </Space>
            </Col>
          </Row>
          <p style={{ color: '#666', marginBottom: 16 }}>{selectedWorker.description}</p>
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <Statistic title={t('worker.exchange', '交易所')} value={selectedWorker.exchange} />
            </Col>
            <Col span={8}>
              <Statistic title={t('worker.createdAt', '创建时间')} value={new Date(selectedWorker.created_at).toLocaleDateString()} />
            </Col>
            <Col span={8}>
              <Statistic 
                title={t('worker.totalReturn', '总收益')} 
                value={`${selectedWorker.totalReturn >= 0 ? '+' : ''}${selectedWorker.totalReturn.toFixed(2)}%`}
                valueStyle={{ color: selectedWorker.totalReturn >= 0 ? '#52c41a' : '#f5222d' }}
              />
            </Col>
          </Row>
        </Card>

        {/* 收益曲线图 */}
        <Card size="small" title={t('worker.returnRateChart', '收益率曲线')}>
          <div style={{ height: 300 }}>
            <ReactECharts option={chartOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </Card>

        {/* 绩效指标 */}
        <Card size="small" title={t('worker.performanceMetrics', '绩效指标')}>
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
        <Card size="small" title={t('worker.tradeRecords', '交易记录')}>
          <Table
            columns={tradeColumns}
            dataSource={selectedWorker.tradeRecords}
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
        {/* 开发中遮盖层 */}
        <div style={{ position: 'relative' }}>
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(255, 255, 255, 0.6)',
              backdropFilter: 'blur(1px)',
              zIndex: 1000,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              pointerEvents: 'none',
            }}
          >
            <div
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.9)',
                padding: '24px 48px',
                borderRadius: 8,
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
                textAlign: 'center',
                pointerEvents: 'auto',
              }}
            >
              <RobotOutlined style={{ fontSize: 48, color: '#1890ff', marginBottom: 16 }} />
              <h3 style={{ margin: '0 0 8px 0', color: '#262626' }}>功能开发中</h3>
              <p style={{ margin: 0, color: '#8c8c8c' }}>策略任务功能正在开发，敬请期待</p>
            </div>
          </div>

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
        </div>
      </Spin>
    </PageContainer>
  );
};

export default Worker;
