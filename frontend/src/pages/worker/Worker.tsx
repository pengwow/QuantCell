import { useEffect, useState, useMemo, useCallback } from 'react';
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
  Badge,
  Skeleton,
  Alert,
  Input,
  Select,
  Modal,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  PauseOutlined,
  BarChartOutlined,
  PoweroffOutlined,
  CaretRightOutlined,
  FileTextOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { useWorkerStore } from '../../store/workerStore';
import { WorkerCreateModal, WorkerEditModal, WorkerLogsPanel } from '../../components/worker';
import type { Worker as WorkerType } from '../../types/worker';
import { WorkerStatusColor, WorkerStatusText } from '../../types/worker';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/router';

const { Option } = Select;
const { Search } = Input;

const Worker = () => {
  const { t } = useTranslation();

  // Store state and actions
  const {
    workers,
    selectedWorker,
    performance,
    trades,
    returnRateData,
    loading,
    loadingPerformance,
    loadingTrades,
    error,
    fetchWorkers,
    setSelectedWorker,
    fetchPerformance,
    fetchTrades,
    fetchReturnRateData,
    deleteWorker,
    startWorker,
    stopWorker,
    pauseWorker,
    resumeWorker,
    restartWorker,
    clearErrors,
  } = useWorkerStore();

  // Local state
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [workerToEdit, setWorkerToEdit] = useState<WorkerType | null>(null);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [tradePagination, setTradePagination] = useState({ current: 1, pageSize: 10 });
  
  // 视图类型状态 - 卡片/列表
  const [viewType, setViewType] = useState<'card' | 'list'>('card');
  
  // 日志面板状态
  const [logsPanelVisible, setLogsPanelVisible] = useState(false);
  const [logsWorkerId, setLogsWorkerId] = useState<number | null>(null);

  // Set page title
  useEffect(() => {
    setPageTitle(t('strategy_task'));
  }, [t]);

  // Initial data fetch
  useEffect(() => {
    fetchWorkers();
    // Set up auto-refresh interval
    const interval = setInterval(() => {
      fetchWorkers();
    }, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [fetchWorkers]);

  // Fetch detail data when worker is selected
  useEffect(() => {
    if (selectedWorker) {
      fetchPerformance(selectedWorker.id);
      fetchTrades(selectedWorker.id);
      fetchReturnRateData(selectedWorker.id);
    }
  }, [selectedWorker, fetchPerformance, fetchTrades, fetchReturnRateData]);

  // Filter workers based on search and status
  const filteredWorkers = useMemo(() => {
    return workers.filter((worker) => {
      const matchesSearch = !searchKeyword ||
        worker.name.toLowerCase().includes(searchKeyword.toLowerCase()) ||
        worker.symbols?.some((s: string) => s.toLowerCase().includes(searchKeyword.toLowerCase()));
      const matchesStatus = !statusFilter || worker.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [workers, searchKeyword, statusFilter]);

  // Status statistics
  const statusStats = useMemo(() => {
    return {
      total: workers.length,
      running: workers.filter(w => w.status === 'running').length,
      stopped: workers.filter(w => w.status === 'stopped').length,
      paused: workers.filter(w => w.status === 'paused').length,
      error: workers.filter(w => w.status === 'error').length,
    };
  }, [workers]);

  // Chart option for return rate
  const chartOption = useMemo(() => {
    if (!returnRateData?.length) {
      return {
        title: { text: t('no_data'), left: 'center', top: 'center', textStyle: { color: '#999' } },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: [],
      };
    }

    const values = returnRateData.map(d => d.value);
    const minValue = Math.min(...values, 0);
    const maxValue = Math.max(...values, 0);

    return {
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: returnRateData.map(d => d.timestamp),
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: { color: '#666', formatter: (value: string) => value.slice(0, 10) },
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
          return `${param.name}<br/>${t('return_rate')}: ${param.value.toFixed(2)}%`;
        },
      },
      series: [
        {
          name: t('return_rate'),
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
  }, [returnRateData, t]);

  // Trade columns
  const tradeColumns = useMemo(() => [
    {
      title: t('trade_time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => new Date(text).toLocaleString(),
    },
    {
      title: t('symbol'),
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: t('action'),
      dataIndex: 'side',
      key: 'side',
      render: (side: 'buy' | 'sell') => (
        <Tag color={side === 'buy' ? 'red' : 'green'}>
          {side === 'buy' ? t('buy') : t('sell')}
        </Tag>
      ),
    },
    {
      title: t('price'),
      dataIndex: 'price',
      key: 'price',
      render: (price: number) => `$${price.toFixed(2)}`,
    },
    {
      title: t('quantity'),
      dataIndex: 'quantity',
      key: 'quantity',
    },
    {
      title: t('amount'),
      dataIndex: 'amount',
      key: 'amount',
      render: (amount: number) => `$${amount.toFixed(2)}`,
    },
    {
      title: t('status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap: Record<string, { text: string; color: string }> = {
          filled: { text: t('filled'), color: 'success' },
          pending: { text: t('pending'), color: 'warning' },
          cancelled: { text: t('cancelled'), color: 'default' },
        };
        const { text, color } = statusMap[status] || { text: status, color: 'default' };
        return <Tag color={color}>{text}</Tag>;
      },
    },
  ], [t]);

  // Event handlers
  const handleStart = useCallback(async (worker: WorkerType, e: React.MouseEvent) => {
    e.stopPropagation();
    const success = await startWorker(worker.id);
    if (success) {
      message.success(t('worker_start_success'));
    }
  }, [startWorker, t]);

  const handleStop = useCallback(async (worker: WorkerType, e: React.MouseEvent) => {
    e.stopPropagation();
    const success = await stopWorker(worker.id);
    if (success) {
      message.success(t('worker_stop_success'));
    }
  }, [stopWorker, t]);

  const handlePause = useCallback(async (worker: WorkerType, e: React.MouseEvent) => {
    e.stopPropagation();
    const success = await pauseWorker(worker.id);
    if (success) {
      message.success(t('worker_pause_success'));
    }
  }, [pauseWorker, t]);

  const handleResume = useCallback(async (worker: WorkerType, e: React.MouseEvent) => {
    e.stopPropagation();
    const success = await resumeWorker(worker.id);
    if (success) {
      message.success(t('worker_resume_success'));
    }
  }, [resumeWorker, t]);

  const handleRestart = useCallback(async (worker: WorkerType, e: React.MouseEvent) => {
    e.stopPropagation();
    const success = await restartWorker(worker.id);
    if (success) {
      message.success(t('worker_restart_success'));
    }
  }, [restartWorker, t]);

  const handleDelete = useCallback(async (worker: WorkerType, e: React.MouseEvent) => {
    e.stopPropagation();
    const success = await deleteWorker(worker.id);
    if (success) {
      message.success(t('worker_delete_success'));
      if (selectedWorker?.id === worker.id) {
        setSelectedWorker(null);
      }
    }
  }, [deleteWorker, selectedWorker, setSelectedWorker, t]);

  const handleEdit = useCallback((worker: WorkerType, e: React.MouseEvent) => {
    e.stopPropagation();
    setWorkerToEdit(worker);
    setEditModalVisible(true);
  }, []);

  const handleRefresh = useCallback(() => {
    fetchWorkers();
    message.success(t('refresh_success'));
  }, [fetchWorkers, t]);

  const handleCreateSuccess = useCallback(() => {
    setCreateModalVisible(false);
    fetchWorkers();
  }, [fetchWorkers]);

  const handleEditSuccess = useCallback(() => {
    setEditModalVisible(false);
    setWorkerToEdit(null);
    fetchWorkers();
    if (selectedWorker && workerToEdit?.id === selectedWorker.id) {
      fetchPerformance(selectedWorker.id);
    }
  }, [fetchWorkers, fetchPerformance, selectedWorker, workerToEdit]);

  // 查看日志
  const handleViewLogs = useCallback((worker: WorkerType, e: React.MouseEvent) => {
    e.stopPropagation();
    setLogsWorkerId(worker.id);
    setLogsPanelVisible(true);
  }, []);

  // 关闭日志面板
  const handleCloseLogsPanel = useCallback(() => {
    setLogsPanelVisible(false);
    setLogsWorkerId(null);
  }, []);

  // Render statistics cards
  const renderStatistics = () => (
    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title={t('total_tasks')}
            value={statusStats.total}
            prefix={<BarChartOutlined />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title={t('running')}
            value={statusStats.running}
            valueStyle={{ color: '#52c41a' }}
            prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title={t('paused')}
            value={statusStats.paused}
            valueStyle={{ color: '#faad14' }}
            prefix={<PauseOutlined style={{ color: '#faad14' }} />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title={t('stopped')}
            value={statusStats.stopped}
            valueStyle={{ color: '#999' }}
            prefix={<PoweroffOutlined style={{ color: '#999' }} />}
          />
        </Card>
      </Col>
    </Row>
  );

  // Render performance metrics
  const renderPerformanceMetrics = () => {
    if (loadingPerformance) {
      return (
        <Row gutter={[16, 16]}>
          {[...Array(4)].map((_, i) => (
            <Col span={12} key={i}>
              <Skeleton active paragraph={false} />
            </Col>
          ))}
        </Row>
      );
    }

    if (!performance) {
      return (
        <Empty description={t('no_performance_data')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      );
    }

    // 计算盈亏比
    const profitLossRatio = performance.total_loss !== 0
      ? Math.abs(performance.total_profit / performance.total_loss)
      : 0;

    const metrics = [
      { label: t('win_rate'), value: `${performance.win_rate?.toFixed(2) || 0}%`, color: performance.win_rate >= 50 ? '#52c41a' : '#ff4d4f' },
      { label: t('profit_loss_ratio'), value: profitLossRatio.toFixed(2), color: profitLossRatio >= 1 ? '#52c41a' : '#ff4d4f' },
      { label: t('max_drawdown'), value: `${performance.max_drawdown?.toFixed(2) || 0}%`, color: '#ff4d4f' },
      { label: t('sharpe_ratio'), value: performance.sharpe_ratio?.toFixed(2) || '0.00', color: performance.sharpe_ratio >= 1 ? '#52c41a' : '#faad14' },
    ];

    return (
      <Row gutter={[16, 16]}>
        {metrics.map((metric) => (
          <Col span={12} key={metric.label}>
            <Card size="small" bordered={false} style={{ background: '#f5f5f5' }}>
              <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>{metric.label}</div>
              <div style={{ fontSize: 20, fontWeight: 'bold', color: metric.color }}>{metric.value}</div>
            </Card>
          </Col>
        ))}
      </Row>
    );
  };

  return (
    <PageContainer title={t('strategy_task')}>
      <Spin spinning={loading}>
        {/* Error Alert */}
        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            closable
            onClose={clearErrors}
            style={{ marginBottom: 16 }}
          />
        )}

        <div style={{ position: 'relative' }}>
          {/* Statistics */}
          {renderStatistics()}

          {/* Toolbar */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col flex="auto">
              <Space>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => setCreateModalVisible(true)}
                >
                  {t('create_worker')}
                </Button>
                <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
                  {t('refresh')}
                </Button>
              </Space>
            </Col>
            <Col>
              <Space>
                <Search
                  placeholder={t('search_worker')}
                  allowClear
                  onSearch={setSearchKeyword}
                  onChange={(e) => setSearchKeyword(e.target.value)}
                  style={{ width: 200 }}
                />
                <Select
                  placeholder={t('filter_by_status')}
                  allowClear
                  style={{ width: 120 }}
                  value={statusFilter}
                  onChange={setStatusFilter}
                >
                  <Option value="running">{t('running')}</Option>
                  <Option value="paused">{t('paused')}</Option>
                  <Option value="stopped">{t('stopped')}</Option>
                  <Option value="error">{t('error')}</Option>
                </Select>
                {/* 视图切换 */}
                <Button.Group>
                  <Button
                    type={viewType === 'card' ? 'primary' : 'default'}
                    icon={<AppstoreOutlined />}
                    onClick={() => setViewType('card')}
                  >
                    {t('card_view') || '卡片'}
                  </Button>
                  <Button
                    type={viewType === 'list' ? 'primary' : 'default'}
                    icon={<UnorderedListOutlined />}
                    onClick={() => setViewType('list')}
                  >
                    {t('list_view') || '列表'}
                  </Button>
                </Button.Group>
              </Space>
            </Col>
          </Row>

          {/* Main Content */}
          <Row gutter={[16, 16]}>
            {/* Worker List */}
            <Col xs={24} lg={8}>
              <Card
                title={
                  <Space>
                    <FileTextOutlined />
                    {t('worker_list')}
                    <Badge count={filteredWorkers.length} style={{ backgroundColor: '#1890ff' }} />
                  </Space>
                }
                bodyStyle={{ padding: 0 }}
              >
                {filteredWorkers.length === 0 ? (
                  <Empty description={t('no_workers')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : viewType === 'card' ? (
                  // 卡片视图 - 参考策略管理页面样式
                  // 响应式布局：大屏幕(lg以上)一行一个，中等屏幕一行两个，小屏幕一行一个
                  <Row gutter={[16, 16]} style={{ margin: 0, padding: 16 }}>
                    {filteredWorkers.map((worker) => (
                      <Col xs={24} sm={12} md={12} lg={24} xl={24} key={worker.id}>
                        <Card
                          size="small"
                          hoverable
                          onClick={() => setSelectedWorker(worker)}
                          style={{
                            boxShadow: selectedWorker?.id === worker.id ? '0 0 0 2px #1890ff' : '0 2px 8px rgba(0, 0, 0, 0.1)',
                            borderColor: selectedWorker?.id === worker.id ? '#1890ff' : undefined,
                          }}
                          extra={
                            <Space size={4}>
                              <Tooltip title={t('edit')}>
                                <Button
                                  type="text"
                                  size="small"
                                  icon={<EditOutlined />}
                                  onClick={(e) => { e.stopPropagation(); handleEdit(worker, e); }}
                                />
                              </Tooltip>
                              <Popconfirm
                                title={t('confirm_delete_worker')}
                                onConfirm={(e) => handleDelete(worker, e as React.MouseEvent)}
                                okText={t('yes')}
                                cancelText={t('no')}
                              >
                                <Tooltip title={t('delete')}>
                                  <Button
                                    type="text"
                                    size="small"
                                    danger
                                    icon={<DeleteOutlined />}
                                    onClick={(e) => e.stopPropagation()}
                                  />
                                </Tooltip>
                              </Popconfirm>
                            </Space>
                          }
                        >
                          {/* 头部：名称和状态 */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                            <span style={{ fontWeight: 500, fontSize: 16 }}>{worker.name}</span>
                            <Tag color={WorkerStatusColor[worker.status]}>
                              {WorkerStatusText[worker.status]}
                            </Tag>
                          </div>

                          {/* 信息区域 */}
                          <div style={{ marginBottom: 12 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                              <span style={{ color: '#666', fontSize: 13 }}>{t('exchange') || '交易所'}</span>
                              <Tag size="small">{worker.exchange}</Tag>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                              <span style={{ color: '#666', fontSize: 13 }}>{t('timeframe') || '周期'}</span>
                              <Tag size="small" color="blue">{worker.timeframe}</Tag>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <span style={{ color: '#666', fontSize: 13 }}>{t('total_profit') || '总收益'}</span>
                              <span style={{
                                fontSize: 13,
                                fontWeight: 500,
                                color: (worker.total_profit || 0) >= 0 ? '#52c41a' : '#ff4d4f'
                              }}>
                                {(worker.total_profit || 0) >= 0 ? '+' : ''}
                                ${(worker.total_profit || 0).toFixed(2)}
                              </span>
                            </div>
                          </div>

                          {/* 分割线 */}
                          <div style={{ borderTop: '1px solid #f0f0f0', margin: '12px 0' }} />

                          {/* 操作按钮区域 */}
                          <Row gutter={[8, 8]}>
                            <Col span={12}>
                              {worker.status === 'stopped' ? (
                                <Button
                                  type="primary"
                                  size="small"
                                  icon={<CaretRightOutlined />}
                                  onClick={(e) => { e.stopPropagation(); handleStart(worker, e); }}
                                  style={{ width: '100%' }}
                                >
                                  {t('start')}
                                </Button>
                              ) : worker.status === 'running' ? (
                                <Button
                                  type="primary"
                                  danger
                                  size="small"
                                  icon={<PauseCircleOutlined />}
                                  onClick={(e) => { e.stopPropagation(); handlePause(worker, e); }}
                                  style={{ width: '100%' }}
                                >
                                  {t('pause')}
                                </Button>
                              ) : (
                                <Button
                                  type="primary"
                                  size="small"
                                  icon={<PlayCircleOutlined />}
                                  onClick={(e) => { e.stopPropagation(); handleResume(worker, e); }}
                                  style={{ width: '100%' }}
                                >
                                  {t('resume')}
                                </Button>
                              )}
                            </Col>
                            <Col span={12}>
                              <Button
                                size="small"
                                icon={<EyeOutlined />}
                                onClick={(e) => { e.stopPropagation(); handleViewLogs(worker, e); }}
                                style={{ width: '100%' }}
                              >
                                {t('view_logs') || '日志'}
                              </Button>
                            </Col>
                            {worker.status !== 'stopped' && (
                              <Col span={12}>
                                <Button
                                  danger
                                  size="small"
                                  icon={<StopOutlined />}
                                  onClick={(e) => { e.stopPropagation(); handleStop(worker, e); }}
                                  style={{ width: '100%' }}
                                >
                                  {t('stop')}
                                </Button>
                              </Col>
                            )}
                            <Col span={worker.status !== 'stopped' ? 12 : 24}>
                              <Tooltip title={t('restart')}>
                                <Button
                                  size="small"
                                  icon={<ReloadOutlined />}
                                  onClick={(e) => { e.stopPropagation(); handleRestart(worker, e); }}
                                  style={{ width: '100%' }}
                                >
                                  {t('restart')}
                                </Button>
                              </Tooltip>
                            </Col>
                          </Row>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                ) : (
                  // 列表视图 - 使用 Table 组件
                  <Table
                    dataSource={filteredWorkers}
                    rowKey="id"
                    size="small"
                    pagination={false}
                    onRow={(worker) => ({
                      onClick: () => setSelectedWorker(worker),
                      style: { cursor: 'pointer', backgroundColor: selectedWorker?.id === worker.id ? '#e6f7ff' : undefined }
                    })}
                    columns={[
                      {
                        title: t('worker_name') || '任务名称',
                        dataIndex: 'name',
                        key: 'name',
                        ellipsis: true,
                        render: (text: string, worker: WorkerType) => (
                          <Space>
                            <span>{text}</span>
                            <Tag color={WorkerStatusColor[worker.status]} size="small">
                              {WorkerStatusText[worker.status]}
                            </Tag>
                          </Space>
                        ),
                      },
                      {
                        title: t('exchange') || '交易所',
                        dataIndex: 'exchange',
                        key: 'exchange',
                        width: 100,
                      },
                      {
                        title: t('timeframe') || '周期',
                        dataIndex: 'timeframe',
                        key: 'timeframe',
                        width: 80,
                      },
                      {
                        title: t('total_profit') || '总收益',
                        dataIndex: 'total_profit',
                        key: 'total_profit',
                        width: 100,
                        render: (profit: number) => (
                          <span style={{
                            fontWeight: 500,
                            color: (profit || 0) >= 0 ? '#52c41a' : '#ff4d4f'
                          }}>
                            {(profit || 0) >= 0 ? '+' : ''}
                            ${(profit || 0).toFixed(2)}
                          </span>
                        ),
                      },
                      {
                        title: t('action') || '操作',
                        key: 'action',
                        width: 200,
                        fixed: 'right',
                        render: (_: any, worker: WorkerType) => (
                          <Space size="small">
                            {worker.status === 'stopped' && (
                              <Tooltip title={t('start')}>
                                <Button
                                  type="text"
                                  size="small"
                                  icon={<CaretRightOutlined style={{ color: '#52c41a' }} />}
                                  onClick={(e) => handleStart(worker, e as React.MouseEvent)}
                                />
                              </Tooltip>
                            )}
                            {worker.status === 'running' && (
                              <>
                                <Tooltip title={t('pause')}>
                                  <Button
                                    type="text"
                                    size="small"
                                    icon={<PauseCircleOutlined style={{ color: '#faad14' }} />}
                                    onClick={(e) => handlePause(worker, e as React.MouseEvent)}
                                  />
                                </Tooltip>
                                <Tooltip title={t('stop')}>
                                  <Button
                                    type="text"
                                    size="small"
                                    icon={<StopOutlined style={{ color: '#ff4d4f' }} />}
                                    onClick={(e) => handleStop(worker, e as React.MouseEvent)}
                                  />
                                </Tooltip>
                              </>
                            )}
                            {worker.status === 'paused' && (
                              <>
                                <Tooltip title={t('resume')}>
                                  <Button
                                    type="text"
                                    size="small"
                                    icon={<PlayCircleOutlined style={{ color: '#52c41a' }} />}
                                    onClick={(e) => handleResume(worker, e as React.MouseEvent)}
                                  />
                                </Tooltip>
                                <Tooltip title={t('stop')}>
                                  <Button
                                    type="text"
                                    size="small"
                                    icon={<StopOutlined style={{ color: '#ff4d4f' }} />}
                                    onClick={(e) => handleStop(worker, e as React.MouseEvent)}
                                  />
                                </Tooltip>
                              </>
                            )}
                            <Tooltip title={t('restart')}>
                              <Button
                                type="text"
                                size="small"
                                icon={<ReloadOutlined />}
                                onClick={(e) => handleRestart(worker, e as React.MouseEvent)}
                              />
                            </Tooltip>
                            <Tooltip title={t('view_logs') || '查看日志'}>
                              <Button
                                type="text"
                                size="small"
                                icon={<EyeOutlined style={{ color: '#1890ff' }} />}
                                onClick={(e) => handleViewLogs(worker, e as React.MouseEvent)}
                              />
                            </Tooltip>
                            <Tooltip title={t('edit')}>
                              <Button
                                type="text"
                                size="small"
                                icon={<EditOutlined />}
                                onClick={(e) => handleEdit(worker, e as React.MouseEvent)}
                              />
                            </Tooltip>
                            <Popconfirm
                              title={t('confirm_delete_worker')}
                              onConfirm={(e) => handleDelete(worker, e as React.MouseEvent)}
                              okText={t('yes')}
                              cancelText={t('no')}
                            >
                              <Tooltip title={t('delete')}>
                                <Button
                                  type="text"
                                  size="small"
                                  danger
                                  icon={<DeleteOutlined />}
                                  onClick={(e) => { e.stopPropagation(); }}
                                />
                              </Tooltip>
                            </Popconfirm>
                          </Space>
                        ),
                      },
                    ]}
                  />
                )}
              </Card>
            </Col>

            {/* Worker Detail */}
            <Col xs={24} lg={16}>
              {selectedWorker ? (
                <>
                  {/* Performance Metrics */}
                  <Card title={t('performance_metrics')} style={{ marginBottom: 16 }}>
                    {renderPerformanceMetrics()}
                  </Card>

                  {/* Return Rate Chart */}
                  <Card title={t('return_rate_chart')} style={{ marginBottom: 16 }}>
                    <ReactECharts
                      option={chartOption}
                      style={{ height: 250 }}
                      opts={{ renderer: 'svg' }}
                    />
                  </Card>

                  {/* Trade Records */}
                  <Card
                    title={
                      <Space>
                        <span>{t('trade_records')}</span>
                        {loadingTrades && <Spin size="small" />}
                      </Space>
                    }
                  >
                    <Table
                      columns={tradeColumns}
                      dataSource={trades}
                      rowKey="id"
                      pagination={{
                        ...tradePagination,
                        total: trades.length,
                        showSizeChanger: true,
                        showTotal: (total) => t('total_items', { total }),
                      }}
                      onChange={(pagination) => setTradePagination({
                        current: pagination.current || 1,
                        pageSize: pagination.pageSize || 10,
                      })}
                      size="small"
                      scroll={{ x: 'max-content' }}
                    />
                  </Card>
                </>
              ) : (
                <Empty description={t('select_worker_to_view')} style={{ marginTop: 100 }} />
              )}
            </Col>
          </Row>
        </div>
      </Spin>

      {/* Create Modal */}
      <WorkerCreateModal
        visible={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        onSuccess={handleCreateSuccess}
      />

      {/* Edit Modal */}
      <WorkerEditModal
        visible={editModalVisible}
        worker={workerToEdit}
        onCancel={() => {
          setEditModalVisible(false);
          setWorkerToEdit(null);
        }}
        onSuccess={handleEditSuccess}
      />

      {/* Logs Panel Modal */}
      {logsWorkerId && (
        <Modal
          title={t('worker_logs') || 'Worker 日志'}
          open={logsPanelVisible}
          onCancel={handleCloseLogsPanel}
          footer={null}
          width={900}
          destroyOnClose
        >
          <WorkerLogsPanel workerId={logsWorkerId} maxHeight={500} />
        </Modal>
      )}
    </PageContainer>
  );
};

export default Worker;
