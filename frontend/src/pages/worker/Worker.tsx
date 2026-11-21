import { useEffect, useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  Spin,
  Tooltip,
  Popconfirm,
  Row,
  Col,
  Space,
  Alert,
  Select,
  Modal,
  App,
  Dropdown,
  Checkbox,
  Flex,
  Pagination,
  type TablePaginationConfig,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  StopOutlined,
  EditOutlined,
  DeleteOutlined,
  CaretRightOutlined,
  FileTextOutlined,
  EyeOutlined,
  MoreOutlined,
  CheckSquareOutlined,
  BorderOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useWorkerStore } from '../../store/workerStore';
import { WorkerCreateModal, WorkerEditModal, WorkerLogsPanel } from '../../components/worker';
import { triggerOptimize } from '../../api/workerApi';
import type { Worker as WorkerType, ApiResponse } from '../../types/worker';
import { WorkerStatusText } from '../../types/worker';
import PageContainer from '@/components/PageContainer';
import PageToolbar from '@/components/ui/PageToolbar';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import { setPageTitle } from '@/utils/pageTitle';
import { QUANT_COLORS } from '@/utils/colors';
import { useGlobalPageSize } from '../../hooks/useGlobalPageSize';
import { useViewType } from '../../hooks/useViewType';
import { PAGE_SIZE_OPTIONS } from '../../constants/pagination';
import { workerStatusChip } from '../../components/worker/statusChip';

const Worker = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { message: apiMessage, modal } = App.useApp();

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
  // 视图类型：跟随系统设置「默认展示类型」，页面不提供切换
  const viewType = useViewType();
  // 列表/卡片共用一份分页状态（与策略管理一致）；pageSize 来自全局配置（条数切换器即全站开关）
  const [pageSize, setPageSize] = useGlobalPageSize();
  const [pagination, setPagination] = useState<TablePaginationConfig>(() => ({
    current: 1,
    pageSize,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    showTotal: (total) => t('total_items', { total }),
  }));

  // 全局条数变化（设置页/其他页面改动）实时同步到本页分页状态
  useEffect(() => {
    setPagination((p) => ({ ...p, pageSize }));
  }, [pageSize]);

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
    setPageTitle(t('strategy_agent'));
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
      const errorMsg = error instanceof Error ? error.message || error.toString() : error != null ? String(error) : t('unknown_error');

      if (
        errorMsg.includes('非法状态转换') ||
        errorMsg.includes('can_transition') ||
        errorMsg.includes('cannot transition')
      ) {
        apiMessage.warning({
          content: (
            <div>
              <div><strong>{worker.name}</strong> {t('worker_cannot_start_now')}</div>
              <div style={{ fontSize: 12, color: 'var(--qc-text-secondary)', marginTop: 4 }}>
                {t('worker_reason_label', { message: errorMsg })}
              </div>
            </div>
          ),
          duration: 5,
        });
      } else if (errorMsg.includes('already running') || errorMsg.includes('已在运行')) {
        apiMessage.info(t('worker_already_running', { name: worker.name }));
      } else {
        apiMessage.error(t('worker_start_failed', { message: errorMsg }));
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
      const errorMsg = error instanceof Error ? error.message || error.toString() : error != null ? String(error) : t('unknown_error');

      if (
        errorMsg.includes('非法状态转换') ||
        errorMsg.includes('can_transition') ||
        errorMsg.includes('cannot transition')
      ) {
        apiMessage.warning({
          content: (
            <div>
              <div><strong>{worker.name}</strong> {t('worker_cannot_stop_now')}</div>
              <div style={{ fontSize: 12, color: 'var(--qc-text-secondary)', marginTop: 4 }}>
                {t('worker_reason_label', { message: errorMsg })}
              </div>
            </div>
          ),
          duration: 5,
        });
      } else if (errorMsg.includes('already stopped') || errorMsg.includes('已停止')) {
        apiMessage.info(t('worker_already_stopped', { name: worker.name }));
      } else {
        apiMessage.error(t('worker_stop_failed', { message: errorMsg }));
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
      apiMessage.success(t('worker_optimize_success', { type: data?.data?.strategy_type || 'rule' }));
      fetchWorkers();
    } catch (error) {
      apiMessage.error(t('worker_optimize_failed', { message: error instanceof Error ? error.message : t('unknown_error') }));
    }
  }, [apiMessage, fetchWorkers, t]);

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
        apiMessage.success(t('worker_batch_start_success', { total: successCount }));
      } else {
        apiMessage.warning(
          t('worker_batch_start_partial', { success: successCount, fail: failCount }),
          5
        );
        // 注：BatchOperationResponse 仅含 success/failed/total，无 results 明细字段，
        // 失败详情由 failed 映射 (workerId -> 错误信息) 提供
      }
      setSelectedRowKeys([]);
    } catch (error) {
        apiMessage.error(t('worker_batch_start_failed', { message: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBatchOperationLoading(false);
    }
  }, [selectedRowKeys, batchStartWorkers, apiMessage, t]);

  const handleBatchStop = useCallback(async () => {
    if (selectedRowKeys.length === 0) return;
    setBatchOperationLoading(true);
    try {
      const result = await batchStopWorkers(selectedRowKeys.map(Number));
      const successCount = result?.success?.length || 0;
      const failCount = Object.keys(result?.failed || {}).length;

      if (failCount === 0) {
        apiMessage.success(t('worker_batch_stop_success', { total: successCount }));
      } else {
        apiMessage.warning(
          t('worker_batch_stop_partial', { success: successCount, fail: failCount }),
          5
        );
      }
      setSelectedRowKeys([]);
    } catch (error) {
      apiMessage.error(t('worker_batch_stop_failed', { message: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBatchOperationLoading(false);
    }
  }, [selectedRowKeys, batchStopWorkers, apiMessage, t]);

  const handleBatchRestart = useCallback(async () => {
    if (selectedRowKeys.length === 0) return;
    setBatchOperationLoading(true);
    try {
      const result = await batchRestartWorkers(selectedRowKeys.map(Number));
      const successCount = result?.success?.length || 0;
      const failCount = Object.keys(result?.failed || {}).length;

      if (failCount === 0) {
        apiMessage.success(t('worker_batch_restart_success', { total: successCount }));
      } else {
        apiMessage.warning(
          t('worker_batch_restart_partial', { success: successCount, fail: failCount }),
          5
        );
      }
      setSelectedRowKeys([]);
    } catch (error) {
      apiMessage.error(t('worker_batch_restart_failed', { message: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBatchOperationLoading(false);
    }
  }, [selectedRowKeys, batchRestartWorkers, apiMessage, t]);

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

  // Render statistics cards — §6.4 KPI：label 11 fg-4 → mono 22/650 → 真值副标；
  // 计数类恒中性，仅「总盈亏」按方向染涨跌色（幅度/计数不染色）
  const renderStatistics = () => (
    <div className="qc-kpi-grid" style={{ marginBottom: 12 }}>
      <div className="qc-kpi">
        <div className="qc-kpi-top"><span className="qc-kpi-lb">{t('total_tasks')}</span></div>
        <div className="qc-kpi-num">{statusStats.total}</div>
        <div className="qc-kpi-sub">
          {t('wt_kpi_sub_tasks', { running: statusStats.running, stopped: statusStats.stopped, error: statusStats.error })}
        </div>
      </div>
      <div className="qc-kpi">
        <div className="qc-kpi-top"><span className="qc-kpi-lb">{t('running')}</span></div>
        <div className="qc-kpi-num">{statusStats.running}</div>
      </div>
      <div className="qc-kpi">
        <div className="qc-kpi-top"><span className="qc-kpi-lb">{t('stopped')}</span></div>
        <div className="qc-kpi-num">{statusStats.stopped}</div>
      </div>
      <div className="qc-kpi">
        <div className="qc-kpi-top"><span className="qc-kpi-lb">{t('total_profit')}</span></div>
        <div className={`qc-kpi-num${statusStats.totalProfit > 0 ? ' up' : statusStats.totalProfit < 0 ? ' down' : ''}`}>
          {statusStats.totalProfit > 0 ? '+' : ''}${statusStats.totalProfit.toFixed(2)}
        </div>
        <div className="qc-kpi-sub">{t('wt_kpi_sub_pnl', { total: workers.length })}</div>
      </div>
    </div>
  );

  // 状态 → §6.2 chip（映射收口在 ./statusChip，详情页/交易 tab 共用）
  const renderStatusChip = (status: WorkerType['status']) =>
    workerStatusChip(status, t(WorkerStatusText[status]));

  // 工具栏：§6.6 PageToolbar（搜索 + 状态筛选 + 计数 + 操作）
  const renderToolbar = () => {
    const current = (pagination.current as number) || 1;
    const currentSize = (pagination.pageSize as number) || pageSize;
    const start = filteredWorkers.length === 0 ? 0 : (current - 1) * currentSize + 1;
    const end = Math.min(current * currentSize, filteredWorkers.length);
    return (
      <PageToolbar
        search={{
          value: searchKeyword,
          onChange: (value) => {
            setSearchKeyword(value);
            gotoPage1();
          },
          placeholder: t('search_worker'),
          ariaLabel: t('search_worker'),
        }}
        filters={
          <Select
            style={{ width: 120 }}
            aria-label={t('filter_by_status')}
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
        }
        count={t('shown_range', { start, end, total: filteredWorkers.length })}
        actions={
          <>
            <Button icon={<ReloadOutlined />} onClick={handleRefresh} style={{ height: 30 }}>
              {t('refresh')}
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)} style={{ height: 30 }}>
              {t('create_worker')}
            </Button>
          </>
        }
      />
    );
  };

  // 批量操作工具栏 - 仅在选中 Worker 时显示
  // 形制：选中态 primary 5% tint 底 + 45% 边（§2.3 表格选中行同源公式），不再用渐变信息蓝
  const renderBatchBar = () => (
    <div
      style={{
        marginBottom: 12,
        padding: '10px 14px',
        background: 'color-mix(in srgb, var(--qc-primary) 5%, var(--qc-surface))',
        border: '1px solid color-mix(in srgb, var(--qc-primary) 45%, transparent)',
        borderRadius: 10,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
        flexWrap: 'wrap',
      }}
    >
      <span style={{ fontSize: 12.5, color: 'var(--qc-text-secondary)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <CheckSquareOutlined style={{ color: 'var(--qc-primary)' }} />
        {t('worker_selected_prefix')}
        <span className="qc-count-chip">{selectedRowKeys.length}</span>
        {t('worker_selected_suffix')}
      </span>
      <Space size="small" wrap>
        <Button
          type="primary"
          size="small"
          icon={<PlayCircleOutlined />}
          loading={batchOperationLoading}
          onClick={handleBatchStart}
        >
          {t('worker_batch_start')}
        </Button>
        <Button
          danger
          size="small"
          icon={<StopOutlined />}
          loading={batchOperationLoading}
          onClick={handleBatchStop}
        >
          {t('worker_batch_stop')}
        </Button>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={batchOperationLoading}
          onClick={handleBatchRestart}
        >
          {t('worker_batch_restart')}
        </Button>
        <Button
          size="small"
          icon={<BorderOutlined />}
          onClick={() => setSelectedRowKeys([])}
        >
          {t('worker_cancel_selection')}
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

  // 卡片操作按钮：启停/详情/优化/重启/日志（§6.1 danger 变体：tint 描边而非实色填充）
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
            title={t('confirm_stop_worker')}
            onConfirm={() => handleStop(worker)}
            okText={t('yes')}
            cancelText={t('no')}
            disabled={submittingWorkerIds.has(worker.id)}
          >
            <Button
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
          {t('detail')}
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
            {t('auto_optimize')}
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
              {t('logs')}
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

  // 信息行：左标签（12px fg-3）右 mono 值（§6.5 标识 mono）
  const infoRow = (label: string, node: React.ReactNode) => (
    <Flex justify="space-between" align="center" gap={8}>
      <span style={{ color: 'var(--qc-text-tertiary)', fontSize: 12 }}>{label}</span>
      {node}
    </Flex>
  );

  // 卡片视图 — §6.3 卡片 + §6.2 chip + §6.7 分页条
  const renderCardView = () => {
    const current = (pagination.current as number) || 1;
    const currentSize = (pagination.pageSize as number) || pageSize;
    const pageData = filteredWorkers.slice((current - 1) * currentSize, current * currentSize);
    const pgChange = (page: number, size: number) => {
      if (size !== pageSize) setPageSize(size);
      setPagination((p) => ({ ...p, current: page, pageSize: size }));
    };

    if (!pageData.length) {
      return (
        <QcEmpty
          title={t('no_workers')}
          action={
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
              {t('create_worker')}
            </Button>
          }
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
                className="qc-card"
                title={
                  <span
                    title={worker.name}
                    className="qc-mono"
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
                    {worker.strategy_type === 'rl' && <span className="qc-chip pri">RL</span>}
                    {worker.strategy_type === 'rule' && <span className="qc-chip info">{t('worker_rule_tag')}</span>}
                    {renderStatusChip(worker.status)}
                  </Space>
                  {infoRow(t('exchange'), <span className="qc-mono" style={{ fontSize: 12 }}>{worker.trading_config?.exchange || '—'}</span>)}
                  {infoRow(t('timeframe'), <span className="qc-mono" style={{ fontSize: 12 }}>{worker.trading_config?.interval || '—'}</span>)}
                  {infoRow(
                    t('total_profit'),
                    <span
                      className="qc-mono"
                      style={{
                        fontSize: 12.5,
                        fontWeight: 600,
                        color: (worker.total_profit || 0) > 0 ? QUANT_COLORS.positive : (worker.total_profit || 0) < 0 ? QUANT_COLORS.negative : 'var(--qc-text)',
                      }}
                    >
                      {(worker.total_profit || 0) > 0 ? '+' : ''}
                      ${(worker.total_profit || 0).toFixed(2)}
                    </span>,
                  )}
                  <div style={{ borderTop: '1px solid var(--qc-border)' }} />
                  {renderCardActions(worker)}
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
        <div className="qc-pg-bar">
          <div className="qc-pg-info">
            <span>{t('total_items', { total: filteredWorkers.length })}</span>
            <span className="qc-pg-sep">·</span>
            <span>{t('per_page')}</span>
            <Select
              size="small"
              className="qc-pg-size"
              value={currentSize}
              popupMatchSelectWidth={false}
              aria-label={t('per_page')}
              onChange={(size) => pgChange(1, size)}
              options={PAGE_SIZE_OPTIONS.map((n) => ({ value: Number(n), label: n }))}
            />
          </div>
          <Pagination
            size="small"
            className="qc-pagination"
            showLessItems
            showQuickJumper
            showSizeChanger={false}
            current={current}
            pageSize={currentSize}
            total={filteredWorkers.length}
            onChange={pgChange}
            itemRender={(pg, type, node) =>
              type === 'jump-prev' || type === 'jump-next' ? (
                <span className="qc-pg-ellipsis">…</span>
              ) : (
                node
              )
            }
          />
        </div>
      </>
    );
  };

  // 列表操作列：详情跳转 + 更多下拉（启停/重启/编辑/删除）
  const renderListActions = (worker: WorkerType) => (
    <Space size="small">
      <Tooltip title={t('detail')}>
        <Button
          type="text"
          size="small"
          icon={<EyeOutlined />}
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

  // 列表视图 — §6.5/§6.6：DataTable（qc-table + 自绘 §6.7 分页条），名称 mono、状态 chip、盈亏涨跌色
  const renderListView = () => (
    <DataTable<WorkerType>
      dataSource={filteredWorkers}
      rowKey="id"
      emptyTitle={t('no_workers')}
      // 分页由共享 pagination 状态控制，卡片视图复用同一份页码；条数变化写回全局配置
      pagination={{
        current: (pagination.current as number) || 1,
        pageSize: (pagination.pageSize as number) || pageSize,
        showSizeChanger: true,
        pageSizeOptions: PAGE_SIZE_OPTIONS,
        onChange: (page, size) => {
          if (size !== pageSize) setPageSize(size);
          setPagination((p) => ({ ...p, current: page, pageSize: size }));
        },
      }}
      rowSelection={{
        selectedRowKeys,
        onChange: (keys) => setSelectedRowKeys(keys),
      }}
      columns={[
        {
          title: t('worker_name'),
          dataIndex: 'name',
          key: 'name',
          width: 220,
          render: (text: string, worker: WorkerType) => (
            <Space size={6}>
              <span className="qc-mono qc-cell-strat" title={text}>{text}</span>
              {renderStatusChip(worker.status)}
            </Space>
          ),
        },
        {
          title: t('exchange'),
          key: 'exchange',
          width: 90,
          render: (_: unknown, worker: WorkerType) => (
            <span className="qc-mono">{worker.trading_config?.exchange || '—'}</span>
          ),
        },
        {
          title: t('interval'),
          key: 'interval',
          width: 80,
          render: (_: unknown, worker: WorkerType) => (
            <span className="qc-mono">{worker.trading_config?.interval || '—'}</span>
          ),
        },
        {
          title: t('total_profit'),
          dataIndex: 'total_profit',
          key: 'total_profit',
          width: 110,
          align: 'right',
          render: (profit: number | undefined) => {
            const p = profit || 0;
            // 0 归中性：盈亏才染色，不是「非负即绿」
            return (
              <span className={`qc-mono${p > 0 ? ' qc-cell-up' : p < 0 ? ' qc-cell-down' : ''}`}>
                {p > 0 ? '+' : ''}${p.toFixed(2)}
              </span>
            );
          },
        },
        {
          title: t('action'),
          key: 'action',
          width: 100,
          fixed: 'right',
          render: (_: unknown, worker: WorkerType) => renderListActions(worker),
        },
      ]}
    />
  );

  // 页头副标（§5 page-sub）：mono 11 真值口径行——任务分布 + 累计盈亏（正负号带出）
  const pnlText = `${statusStats.totalProfit > 0 ? '+' : ''}$${statusStats.totalProfit.toFixed(2)}`;
  const pageSubtitle = t('wt_sub_list', {
    total: statusStats.total,
    running: statusStats.running,
    stopped: statusStats.stopped,
    error: statusStats.error,
    pnl: pnlText,
  });

  return (
    <PageContainer title={t('strategy_agent')} subtitle={pageSubtitle}>
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
          className="qc-modal"
          title={t('worker_logs')}
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
