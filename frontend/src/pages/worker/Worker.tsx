import { useEffect, useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  Tag,
  Table,
  Spin,
  Tooltip,
  Popconfirm,
  Row,
  Col,
  Statistic,
  Empty,
  Space,
  Badge,
  Alert,
  Input,
  Select,
  Modal,
  App,
  Dropdown,
  Checkbox,
  Flex,
  Grid,
  Segmented,
  Pagination,
  theme,
  type MenuProps,
  type TablePaginationConfig,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  StopOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  BarChartOutlined,
  PoweroffOutlined,
  CaretRightOutlined,
  FileTextOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  EyeOutlined,
  MoreOutlined,
  CheckSquareOutlined,
  BorderOutlined,
  ThunderboltOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import type { TooltipComponentFormatterCallbackParams } from 'echarts';
import { useWorkerStore } from '../../store/workerStore';
import { WorkerCreateModal, WorkerEditModal, WorkerLogsPanel } from '../../components/worker';
import { triggerOptimize } from '../../api/workerApi';
import type { Worker as WorkerType, ApiResponse } from '../../types/worker';
import { WorkerStatusColor, WorkerStatusText } from '../../types/worker';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import { QUANT_COLORS } from '@/utils/colors';
import { useConfigStore } from '@/store';

// 菜单项点击事件类型：antd v5 未直接导出 MenuInfo，从 MenuProps 推导
type MenuItemClickEvent = Parameters<NonNullable<MenuProps['onClick']>>[0];
type ViewType = 'card' | 'list';

// 分页选项（与策略管理等页面一致）
const PAGE_SIZE_OPTIONS = ['10', '15', '20', '30', '50', '100'];

const Worker = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { message: apiMessage, modal } = App.useApp();
  const { token } = theme.useToken();
  const screens = Grid.useBreakpoint();
  const getDefaultPageSize = useConfigStore((s) => s.getDefaultPageSize);

  // Store state and actions
  // 注意：详情展示已移交 /strategy-worker/:id 独立页（WorkerDetail），
  // 本页不再维护 selectedWorker / performance / trades 等右侧面板数据
  const {
    workers,
    loading,
    error,
    fetchWorkers,
    deleteWorker,
    startWorker,
    stopWorker,
    restartWorker,
    batchStartWorkers,
    batchStopWorkers,
    batchRestartWorkers,
    clearErrors,
  } = useWorkerStore();

  // Local state
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [workerToEdit, setWorkerToEdit] = useState<WorkerType | null>(null);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  // 视图类型状态 - 列表/卡片（与策略管理一致，默认卡片）
  const [viewType, setViewType] = useState<ViewType>('card');
  // 列表/卡片共用一份分页状态（与策略管理一致）；pageSize 取系统配置默认值
  const [pagination, setPagination] = useState<TablePaginationConfig>(() => ({
    current: 1,
    pageSize: getDefaultPageSize(),
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    showTotal: (total) => t('total_items', { total }),
  }));

  // 批量操作状态
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchOperationLoading, setBatchOperationLoading] = useState(false);

  // 单个 Worker 操作提交状态（防重复点击 + loading 反馈）
  const [submittingWorkerIds, setSubmittingWorkerIds] = useState<Set<number>>(new Set());

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

  // Filter workers based on search and status
  const filteredWorkers = useMemo(() => {
    return workers.filter((worker) => {
      const matchesSearch = !searchKeyword ||
        worker.name.toLowerCase().includes(searchKeyword.toLowerCase()) ||
        worker.trading_config?.symbols_config?.symbols?.some(
          (s: string) => s.toLowerCase().includes(searchKeyword.toLowerCase())
        );
      const matchesStatus = !statusFilter || worker.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [workers, searchKeyword, statusFilter]);

  // Status statistics
  const statusStats = useMemo(() => {
    const totalProfit = workers.reduce((sum, w) => sum + (w.total_profit || 0), 0);
    return {
      total: workers.length,
      running: workers.filter(w => w.status === 'running').length,
      stopped: workers.filter(w => w.status === 'stopped').length,
      error: workers.filter(w => w.status === 'error').length,
      totalProfit,
    };
  }, [workers]);

  // 筛选条件变化时回到第一页（避免过滤后停留在超出范围的页码）
  const gotoPage1 = () => setPagination((p) => ({ ...p, current: 1 }));

  // Event handlers
  const handleStart = useCallback(async (worker: WorkerType) => {
    // 防重复点击
    if (submittingWorkerIds.has(worker.id)) return;
    setSubmittingWorkerIds((prev) => new Set(prev).add(worker.id));

    try {
      await startWorker(worker.id);
      apiMessage.success(t('worker_start_success'));
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message || error.toString() : error != null ? String(error) : '未知错误';

      if (
        errorMsg.includes('非法状态转换') ||
        errorMsg.includes('can_transition') ||
        errorMsg.includes('cannot transition')
      ) {
        apiMessage.warning({
          content: (
            <div>
              <div><strong>{worker.name}</strong> 当前不允许启动</div>
              <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                原因: {errorMsg}
              </div>
            </div>
          ),
          duration: 5,
        });
      } else if (errorMsg.includes('already running') || errorMsg.includes('已在运行')) {
        apiMessage.info(`${worker.name} 已在运行中`);
      } else {
        apiMessage.error(`启动失败: ${errorMsg}`);
      }
    } finally {
      setSubmittingWorkerIds((prev) => {
        const next = new Set(prev);
        next.delete(worker.id);
        return next;
      });
    }
  }, [startWorker, t, apiMessage, submittingWorkerIds]);

  const handleStop = useCallback(async (worker: WorkerType) => {
    if (submittingWorkerIds.has(worker.id)) return;
    setSubmittingWorkerIds((prev) => new Set(prev).add(worker.id));

    try {
      await stopWorker(worker.id);
      apiMessage.success(t('worker_stop_success'));
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message || error.toString() : error != null ? String(error) : '未知错误';

      if (
        errorMsg.includes('非法状态转换') ||
        errorMsg.includes('can_transition') ||
        errorMsg.includes('cannot transition')
      ) {
        apiMessage.warning({
          content: (
            <div>
              <div><strong>{worker.name}</strong> 当前不允许停止</div>
              <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                原因: {errorMsg}
              </div>
            </div>
          ),
          duration: 5,
        });
      } else if (errorMsg.includes('already stopped') || errorMsg.includes('已停止')) {
        apiMessage.info(`${worker.name} 已停止`);
      } else {
        apiMessage.error(`停止失败: ${errorMsg}`);
      }
    } finally {
      setSubmittingWorkerIds((prev) => {
        const next = new Set(prev);
        next.delete(worker.id);
        return next;
      });
    }
  }, [stopWorker, t, apiMessage, submittingWorkerIds]);

  const handleRestart = useCallback(async (worker: WorkerType) => {
    const success = await restartWorker(worker.id);
    if (success) {
      apiMessage.success(t('worker_restart_success'));
    }
  }, [restartWorker, t, apiMessage]);

  const handleOptimize = useCallback(async (worker: WorkerType) => {
    try {
      const result = await triggerOptimize(worker.id);
      const data = result as ApiResponse<{ strategy_type?: string }>;
      apiMessage.success(`优化完成 (${data?.data?.strategy_type || 'rule'})`);
      fetchWorkers();
    } catch (error) {
      apiMessage.error(`优化失败: ${error instanceof Error ? error.message : '未知错误'}`);
    }
  }, [apiMessage, fetchWorkers]);

  // ============================================
  // 批量操作处理函数
  // ============================================

  const handleBatchStart = useCallback(async () => {
    if (selectedRowKeys.length === 0) return;
    setBatchOperationLoading(true);
    try {
      const result = await batchStartWorkers(selectedRowKeys.map(Number));
      const successCount = result?.success?.length || 0;
      const failCount = Object.keys(result?.failed || {}).length;

      if (failCount === 0) {
        apiMessage.success(`成功启动 ${successCount} 个 Worker`);
      } else {
        apiMessage.warning(
          `部分成功: ${successCount} 个启动成功, ${failCount} 个失败`,
          5
        );
        // 注：BatchOperationResponse 仅含 success/failed/total，无 results 明细字段，
        // 失败详情由 failed 映射 (workerId -> 错误信息) 提供
      }
      setSelectedRowKeys([]);
    } catch (error) {
        apiMessage.error(`批量启动失败: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBatchOperationLoading(false);
    }
  }, [selectedRowKeys, batchStartWorkers, apiMessage]);

  const handleBatchStop = useCallback(async () => {
    if (selectedRowKeys.length === 0) return;
    setBatchOperationLoading(true);
    try {
      const result = await batchStopWorkers(selectedRowKeys.map(Number));
      const successCount = result?.success?.length || 0;
      const failCount = Object.keys(result?.failed || {}).length;

      if (failCount === 0) {
        apiMessage.success(`成功停止 ${successCount} 个 Worker`);
      } else {
        apiMessage.warning(
          `部分成功: ${successCount} 个停止成功, ${failCount} 个失败`,
          5
        );
      }
      setSelectedRowKeys([]);
    } catch (error) {
      apiMessage.error(`批量停止失败: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBatchOperationLoading(false);
    }
  }, [selectedRowKeys, batchStopWorkers, apiMessage]);

  const handleBatchRestart = useCallback(async () => {
    if (selectedRowKeys.length === 0) return;
    setBatchOperationLoading(true);
    try {
      const result = await batchRestartWorkers(selectedRowKeys.map(Number));
      const successCount = result?.success?.length || 0;
      const failCount = Object.keys(result?.failed || {}).length;

      if (failCount === 0) {
        apiMessage.success(`成功重启 ${successCount} 个 Worker`);
      } else {
        apiMessage.warning(
          `部分成功: ${successCount} 个重启成功, ${failCount} 个失败`,
          5
        );
      }
      setSelectedRowKeys([]);
    } catch (error) {
      apiMessage.error(`批量重启失败: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBatchOperationLoading(false);
    }
  }, [selectedRowKeys, batchRestartWorkers, apiMessage]);

  const handleDelete = useCallback(async (worker: WorkerType) => {
    const success = await deleteWorker(worker.id);
    if (success) {
      apiMessage.success(t('worker_delete_success'));
    }
  }, [deleteWorker, t, apiMessage]);

  const handleEdit = useCallback((worker: WorkerType) => {
    setWorkerToEdit(worker);
    setEditModalVisible(true);
  }, []);

  const handleRefresh = useCallback(() => {
    fetchWorkers();
    apiMessage.success(t('refresh_success'));
  }, [fetchWorkers, t, apiMessage]);

  const handleCreateSuccess = useCallback(() => {
    setCreateModalVisible(false);
    fetchWorkers();
  }, [fetchWorkers]);

  const handleEditSuccess = useCallback(() => {
    setEditModalVisible(false);
    setWorkerToEdit(null);
    fetchWorkers();
  }, [fetchWorkers]);

  // 查看日志
  const handleViewLogs = useCallback((worker: WorkerType) => {
    setLogsWorkerId(worker.id);
    setLogsPanelVisible(true);
  }, []);

  // 关闭日志面板
  const handleCloseLogsPanel = useCallback(() => {
    setLogsPanelVisible(false);
    setLogsWorkerId(null);
  }, []);

  // 卡片批量勾选
  const toggleSelectRow = (id: number, checked: boolean) => {
    setSelectedRowKeys((prev) =>
      checked ? [...prev, id] : prev.filter((key) => key !== id),
    );
  };

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
            styles={{ content: { color: QUANT_COLORS.positive } }}
            prefix={<CheckCircleOutlined style={{ color: QUANT_COLORS.positive }} />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title={t('stopped')}
            value={statusStats.stopped}
            styles={{ content: { color: '#999' } }}
            prefix={<PoweroffOutlined style={{ color: '#999' }} />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title={t('total_profit') || '总盈利'}
            value={statusStats.totalProfit}
            precision={2}
            prefix={'$'}
            styles={{ content: { color: statusStats.totalProfit >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative } }}
          />
        </Card>
      </Col>
    </Row>
  );

  // 工具栏：与策略管理/因子库一致的「搜索+视图切换 / 筛选+操作」两行布局
  const renderToolbar = () => (
    <Space orientation="vertical" size="middle" style={{ display: 'flex', marginBottom: 8 }}>
      <Flex justify="space-between" align="center" gap="small" wrap="wrap">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          style={{ width: 260, maxWidth: '100%' }}
          placeholder={t('search_worker')}
          value={searchKeyword}
          onChange={(e) => {
            setSearchKeyword(e.target.value);
            gotoPage1();
          }}
        />
        <Segmented
          value={viewType}
          onChange={(v) => setViewType(v as ViewType)}
          options={[
            { value: 'list', icon: <UnorderedListOutlined />, label: screens.sm ? (t('list_view') || '列表') : undefined },
            { value: 'card', icon: <AppstoreOutlined />, label: screens.sm ? (t('card_view') || '卡片') : undefined },
          ]}
        />
      </Flex>
      <Flex justify="space-between" align="center" gap="small" wrap="wrap">
        <Select
          style={{ width: 120 }}
          placeholder={t('filter_by_status')}
          allowClear
          value={statusFilter || undefined}
          onChange={(v) => {
            setStatusFilter(v || '');
            gotoPage1();
          }}
          options={[
            { value: 'running', label: t('running') },
            { value: 'stopped', label: t('stopped') },
            { value: 'error', label: t('error') },
          ]}
        />
        <Space size="small" wrap>
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
            {t('refresh')}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
            {t('create_worker')}
          </Button>
        </Space>
      </Flex>
    </Space>
  );

  // 批量操作工具栏 - 仅在选中 Worker 时显示
  const renderBatchBar = () => (
    <div
      style={{
        marginBottom: 16,
        padding: '12px 16px',
        background: 'linear-gradient(135deg, #e6f7ff 0%, #bae0ff 100%)',
        borderRadius: 8,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}
    >
      <span style={{ fontSize: 14, color: QUANT_COLORS.info }}>
        <CheckSquareOutlined style={{ marginRight: 8 }} />
        已选择 <strong>{selectedRowKeys.length}</strong> 个 Worker
      </span>
      <Space>
        <Button
          type="primary"
          size="small"
          icon={<PlayCircleOutlined />}
          loading={batchOperationLoading}
          onClick={handleBatchStart}
        >
          批量启动
        </Button>
        <Button
          danger
          size="small"
          icon={<StopOutlined />}
          loading={batchOperationLoading}
          onClick={handleBatchStop}
        >
          批量停止
        </Button>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={batchOperationLoading}
          onClick={handleBatchRestart}
        >
          批量重启
        </Button>
        <Button
          size="small"
          icon={<BorderOutlined />}
          onClick={() => setSelectedRowKeys([])}
        >
          取消选择
        </Button>
      </Space>
    </div>
  );

  // 卡片右上角操作：勾选 + 编辑 + 删除（所有视图通用）
  const renderCardExtra = (worker: WorkerType) => (
    <Space size={4}>
      <Checkbox
        checked={selectedRowKeys.includes(worker.id)}
        onChange={(e) => toggleSelectRow(worker.id, e.target.checked)}
      />
      <Tooltip title={t('edit')}>
        <Button
          type="text"
          size="small"
          icon={<EditOutlined />}
          onClick={() => handleEdit(worker)}
        />
      </Tooltip>
      <Popconfirm
        title={t('confirm_delete_worker')}
        onConfirm={() => handleDelete(worker)}
        okText={t('yes')}
        cancelText={t('no')}
      >
        <Tooltip title={t('delete')}>
          <Button type="text" size="small" danger icon={<DeleteOutlined />} />
        </Tooltip>
      </Popconfirm>
    </Space>
  );

  // 卡片操作按钮：启停/详情/优化/重启/日志
  const renderCardActions = (worker: WorkerType) => (
    <Row gutter={[8, 8]}>
      <Col span={12}>
        {worker.status === 'stopped' ? (
          <Button
            type="primary"
            size="small"
            icon={<CaretRightOutlined />}
            loading={submittingWorkerIds.has(worker.id)}
            disabled={submittingWorkerIds.has(worker.id)}
            onClick={() => handleStart(worker)}
            style={{ width: '100%' }}
          >
            {t('start')}
          </Button>
        ) : (
          <Popconfirm
            title={t('confirm_stop_worker') || '确定停止此 Worker？'}
            onConfirm={() => handleStop(worker)}
            okText={t('yes')}
            cancelText={t('no')}
            disabled={submittingWorkerIds.has(worker.id)}
          >
            <Button
              type="primary"
              danger
              size="small"
              icon={<StopOutlined />}
              loading={submittingWorkerIds.has(worker.id)}
              style={{ width: '100%' }}
            >
              {t('stop')}
            </Button>
          </Popconfirm>
        )}
      </Col>
      <Col span={12}>
        <Button
          size="small"
          icon={<EyeOutlined />}
          onClick={() => navigate(`/strategy-worker/${worker.id}`)}
          style={{ width: '100%' }}
        >
          {t('detail') || '详情'}
        </Button>
      </Col>
      {worker.status === 'running' && (
        <Col span={24}>
          <Button
            size="small"
            type="dashed"
            icon={<ThunderboltOutlined />}
            onClick={() => handleOptimize(worker)}
            style={{ width: '100%' }}
          >
            {t('auto_optimize') || '自动优化'}
          </Button>
        </Col>
      )}
      {worker.status === 'running' ? (
        <>
          <Col span={12}>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => handleRestart(worker)}
              style={{ width: '100%' }}
            >
              {t('restart')}
            </Button>
          </Col>
          <Col span={12}>
            <Button
              size="small"
              icon={<FileTextOutlined />}
              onClick={() => handleViewLogs(worker)}
              style={{ width: '100%' }}
            >
              {t('logs') || '日志'}
            </Button>
          </Col>
        </>
      ) : (
        <Col span={24}>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => handleRestart(worker)}
            style={{ width: '100%' }}
          >
            {t('restart')}
          </Button>
        </Col>
      )}
    </Row>
  );

  // 信息行：左标签右内容（卡片指标区，与因子库卡片同风格）
  const infoRow = (label: string, node: React.ReactNode) => (
    <Flex justify="space-between" align="center">
      <span style={{ color: token.colorTextSecondary, fontSize: 13 }}>{label}</span>
      {node}
    </Flex>
  );

  const renderCardView = () => {
    const current = (pagination.current as number) || 1;
    const pageSize = (pagination.pageSize as number) || 10;
    const pageData = filteredWorkers.slice((current - 1) * pageSize, current * pageSize);

    if (!pageData.length) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('no_workers')}
          style={{ padding: '48px 0' }}
        />
      );
    }

    return (
      <>
        <Row gutter={[16, 16]}>
          {pageData.map((worker) => (
            <Col xs={24} sm={12} md={8} lg={6} key={worker.id}>
              <Card
                size="small"
                title={
                  <span
                    title={worker.name}
                    style={{
                      display: 'inline-block',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: '100%',
                      verticalAlign: 'bottom',
                    }}
                  >
                    {worker.name}
                  </span>
                }
                extra={renderCardExtra(worker)}
              >
                <Space orientation="vertical" size={8} style={{ display: 'flex' }}>
                  <Space size={4} wrap style={{ rowGap: 4 }}>
                    {worker.strategy_type === 'rl' && <Tag color="purple">RL</Tag>}
                    {worker.strategy_type === 'rule' && <Tag color="green">规则</Tag>}
                    <Tag color={WorkerStatusColor[worker.status]}>
                      {WorkerStatusText[worker.status]}
                    </Tag>
                  </Space>
                  {infoRow(t('exchange') || '交易所', <Tag>{worker.trading_config?.exchange}</Tag>)}
                  {infoRow(t('timeframe') || '周期', <Tag color="blue">{worker.trading_config?.timeframe}</Tag>)}
                  {infoRow(
                    t('total_profit') || '总收益',
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 500,
                        color: (worker.total_profit || 0) >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
                      }}
                    >
                      {(worker.total_profit || 0) >= 0 ? '+' : ''}
                      ${(worker.total_profit || 0).toFixed(2)}
                    </span>,
                  )}
                  <div style={{ borderTop: `1px solid ${token.colorBorderSecondary}` }} />
                  {renderCardActions(worker)}
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
        <Row justify="center" style={{ marginTop: 16 }}>
          <Pagination
            current={current}
            pageSize={pageSize}
            total={filteredWorkers.length}
            showSizeChanger
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            showTotal={(total) => t('total_items', { total })}
            onChange={(page, size) => setPagination((p) => ({ ...p, current: page, pageSize: size }))}
          />
        </Row>
      </>
    );
  };

  // 列表操作列：详情跳转 + 更多下拉（启停/重启/编辑/删除）
  const renderListActions = (worker: WorkerType) => (
    <Space size="small">
      <Tooltip title={t('detail') || '详情'}>
        <Button
          type="text"
          size="small"
          icon={<EyeOutlined style={{ color: QUANT_COLORS.info }} />}
          onClick={() => navigate(`/strategy-worker/${worker.id}`)}
        />
      </Tooltip>
      <Dropdown
        menu={{
          items: [
            ...(worker.status === 'stopped' ? [{
              key: 'start',
              label: t('start'),
              icon: <CaretRightOutlined />,
              disabled: submittingWorkerIds.has(worker.id),
            }] : []),
            ...(worker.status === 'running' ? [{
              key: 'stop',
              label: t('stop'),
              icon: <StopOutlined />,
              disabled: submittingWorkerIds.has(worker.id),
            }] : []),
            {
              key: 'restart',
              label: t('restart'),
              icon: <ReloadOutlined />,
            },
            {
              key: 'edit',
              label: t('edit'),
              icon: <EditOutlined />,
            },
            {
              key: 'delete',
              label: t('delete'),
              icon: <DeleteOutlined />,
              danger: true,
            },
          ],
          onClick: ({ key, domEvent }) => {
            // 菜单挂在表格行内，阻止事件冒泡污染表格行为
            domEvent.stopPropagation();
            if (key === 'start') handleStart(worker);
            else if (key === 'stop') handleStop(worker);
            else if (key === 'restart') handleRestart(worker);
            else if (key === 'edit') handleEdit(worker);
            else if (key === 'delete') {
              modal.confirm({
                title: t('confirm_delete_worker'),
                okText: t('yes'),
                cancelText: t('no'),
                okType: 'danger',
                onOk: () => handleDelete(worker),
              });
            }
          },
        }}
        trigger={['click']}
      >
        <Button type="text" size="small" icon={<MoreOutlined />} />
      </Dropdown>
    </Space>
  );

  const renderListView = () => (
    <Table
      dataSource={filteredWorkers}
      rowKey="id"
      size="small"
      // 分页由共享 pagination 状态控制，卡片视图复用同一份页码
      pagination={pagination}
      scroll={{ x: 800 }}
      rowSelection={{
        selectedRowKeys,
        onChange: (keys) => setSelectedRowKeys(keys),
      }}
      locale={{
        emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('no_workers')} />,
      }}
      onChange={setPagination}
      columns={[
        {
          title: t('worker_name') || '任务名称',
          dataIndex: 'name',
          key: 'name',
          width: 180,
          ellipsis: true,
          render: (text: string, worker: WorkerType) => (
            <Space size={4}>
              <span>{text}</span>
              <Tag color={WorkerStatusColor[worker.status]}>
                {WorkerStatusText[worker.status]}
              </Tag>
            </Space>
          ),
        },
        {
          title: t('exchange') || '交易所',
          dataIndex: 'exchange',
          key: 'exchange',
          width: 90,
        },
        {
          title: t('timeframe') || '周期',
          dataIndex: 'timeframe',
          key: 'timeframe',
          width: 70,
        },
        {
          title: t('total_profit') || '总收益',
          dataIndex: 'total_profit',
          key: 'total_profit',
          width: 100,
          render: (profit: number) => (
            <span style={{
              fontWeight: 500,
              color: (profit || 0) >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative
            }}>
              {(profit || 0) >= 0 ? '+' : ''}
              ${(profit || 0).toFixed(2)}
            </span>
          ),
        },
        {
          title: t('action') || '操作',
          key: 'action',
          width: 100,
          fixed: 'right',
          render: (_: unknown, worker: WorkerType) => renderListActions(worker),
        },
      ]}
    />
  );

  return (
    <PageContainer title={t('strategy_task')}>
      <Spin spinning={loading}>
        {/* Error Alert */}
        {error && (
          <Alert
            title={error}
            type="error"
            showIcon
            closable
            onClose={clearErrors}
            style={{ marginBottom: 16 }}
          />
        )}

        {/* Statistics */}
        {renderStatistics()}

        {/* Toolbar */}
        {renderToolbar()}

        {/* 批量操作工具栏 - 仅在选中 Worker 时显示 */}
        {selectedRowKeys.length > 0 && renderBatchBar()}

        {/* Main Content：全宽列表/卡片（详情入口跳转独立页） */}
        {viewType === 'list' ? renderListView() : renderCardView()}
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
          destroyOnHidden
        >
          <WorkerLogsPanel workerId={logsWorkerId} maxHeight={500} />
        </Modal>
      )}
    </PageContainer>
  );
};

export default Worker;
