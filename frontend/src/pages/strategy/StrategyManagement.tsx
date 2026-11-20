import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Card,
  Button,
  Space,
  Tooltip,
  Modal,
  App,
  Select,
  Row,
  Col,
  Tabs,
  Pagination,
} from 'antd';
import {
  EditOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  AppstoreOutlined,
  HistoryOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import { strategyApi, backtestApi } from '../../api';
import type { Strategy } from '../../types';
import type { BacktestTask } from '../../types/backtest';
import { useTranslation } from 'react-i18next';
import { useGuestRestriction } from '../../hooks/useGuestRestriction';
import { setPageTitle } from '@/utils/pageTitle';
import PageContainer from '@/components/PageContainer';
import DataTable from '@/components/ui/DataTable';
import PageToolbar from '@/components/ui/PageToolbar';
import type { TablePaginationConfig, TableProps } from 'antd';
import dayjs from 'dayjs';
import { useConfigStore } from '@/store';
import { useGlobalPageSize } from '../../hooks/useGlobalPageSize';
import { useViewType } from '../../hooks/useViewType';
import { PAGE_SIZE_OPTIONS } from '../../constants/pagination';
import { QUANT_COLORS } from '@/utils/colors';

const { confirm } = Modal;

// 排序字段
type SortField = 'name' | 'created_at' | 'updated_at';
type SortOrder = 'asc' | 'desc';

// Tab 类型
type TabType = 'strategies' | 'backtests';

// 策略后端返回的 snake_case 扩展字段，仅用于类型读取时的最小收窄
type StrategyBackendFields = {
  created_at?: string;
  updated_at?: string;
  version?: string;
};

/**
 * 策略管理页面组件
 * 功能：展示策略列表，支持编辑、删除、回测等操作
 * 布局参考策略回测页面
 */
const StrategyManagement = () => {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { isGuest } = useGuestRestriction();
  const [searchParams, setSearchParams] = useSearchParams();
  const { message } = App.useApp();

  // 从 URL 参数读取 Tab 状态
  const tabFromUrl = searchParams.get('tab') as TabType;
  const validTab = tabFromUrl === 'strategies' || tabFromUrl === 'backtests' ? tabFromUrl : 'strategies';

  // 视图类型状态 - 策略列表（跟随系统设置「默认展示类型」，页面不提供切换）
  const viewType = useViewType();

  // Tab 状态 - 从 URL 参数初始化
  const [activeTab, setActiveTab] = useState<TabType>(validTab);

  // 筛选状态 - 策略列表
  const [searchText, setSearchText] = useState<string>('');
  const [sortField, setSortField] = useState<SortField>('updated_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  // 回测相关状态
  const [backtests, setBacktests] = useState<BacktestTask[]>([]);
  const [backtestLoading, setBacktestLoading] = useState<boolean>(false);
  const [selectedStrategy, setSelectedStrategy] = useState<string>('');

  // 列表视图行选中（点击行打 primary tint，操作按钮阻止冒泡）
  const [selectedRowKey, setSelectedRowKey] = useState<React.Key>('');
  // 回测列表视图类型（跟随系统设置「默认展示类型」，页面不提供切换）
  const backtestViewType = useViewType();
  const [backtestSelectedRowKeys, setBacktestSelectedRowKeys] = useState<React.Key[]>([]);

  // 回测筛选状态
  const [backtestSearchText, setBacktestSearchText] = useState<string>('');
  const [backtestStatusFilter, setBacktestStatusFilter] = useState<string>('all');
  const [backtestSortField, setBacktestSortField] = useState<string>('created_at');
  const [backtestSortOrder, setBacktestSortOrder] = useState<string>('desc');

  // 全局分页大小（条数切换器即全站开关，切换后跨页面实时同步并持久化）
  const [pageSize, setPageSize] = useGlobalPageSize();

  // 分页配置 - 策略列表（pageSize 跟随全局配置；「共 N 条」由 DataTable 默认提供）
  const [pagination, setPagination] = useState<TableProps<Strategy>['pagination']>(() => ({
    current: 1,
    pageSize,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
  }));

  // 分页配置 - 回测列表；state 恒为对象，false/undefined 只在 Table 的 props 上有意义
  const [backtestPagination, setBacktestPagination] = useState<TablePaginationConfig>(() => ({
    current: 1,
    pageSize,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
  }));

  // 全局条数变化（设置页/其他页面改动）实时同步到两个列表的分页状态
  useEffect(() => {
    setPagination(prev => ({ ...prev, pageSize }));
    setBacktestPagination(prev => ({ ...prev, pageSize }));
  }, [pageSize]);

  // 页面加载时输出全局配置（用于调试）
  useEffect(() => {
    console.log('[StrategyManagement] page loaded, global config state:', useConfigStore.getState());
  }, []);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('strategy_management'));
  }, [t]);

  // 加载策略列表
  const loadStrategies = async () => {
    try {
      setLoading(true);
      const response = await strategyApi.getStrategies();
      if (response && response.strategies) {
        // 后端仅返回精简字段，页面消费 name/description 等子集，富模型字段有兜底
        setStrategies(response.strategies as unknown as Strategy[]);
      }
    } catch (error) {
      console.error('Failed to load strategy list:', error);
      message.error(t('load_strategy_list_failed_generic'));
    } finally {
      setLoading(false);
    }
  };

  // 组件挂载时加载策略列表
  useEffect(() => {
    loadStrategies();

    // 从 URL 参数恢复状态
    const taskIdFromUrl = searchParams.get('taskId');
    const strategyFromUrl = searchParams.get('strategy');
    const searchFromUrl = searchParams.get('search');
    const statusFromUrl = searchParams.get('status');
    const sortFieldFromUrl = searchParams.get('sortField');
    const sortOrderFromUrl = searchParams.get('sortOrder');

    // 如果是从详情页返回（有 returnUrl 相关参数），恢复搜索和筛选状态
    if (searchFromUrl !== null || statusFromUrl !== null || sortFieldFromUrl !== null || sortOrderFromUrl !== null) {
      console.log('[StrategyManagement] returning from detail page, restoring search and filter state:', {
        search: searchFromUrl,
        strategy: strategyFromUrl,
        status: statusFromUrl,
        sortField: sortFieldFromUrl,
        sortOrder: sortOrderFromUrl,
      });

      // 恢复搜索文本
      if (searchFromUrl) {
        setBacktestSearchText(searchFromUrl);
      }

      // 恢复策略筛选
      if (strategyFromUrl) {
        setSelectedStrategy(strategyFromUrl);
      }

      // 恢复状态筛选
      if (statusFromUrl) {
        setBacktestStatusFilter(statusFromUrl);
      }

      // 恢复排序
      if (sortFieldFromUrl) {
        setBacktestSortField(sortFieldFromUrl);
      }
      if (sortOrderFromUrl) {
        setBacktestSortOrder(sortOrderFromUrl);
      }

      // 自动切换到回测记录 tab
      setActiveTab('backtests');
    }

    // 如果是从回测完成跳转过来（有 taskId）
    if (taskIdFromUrl || strategyFromUrl) {
      console.log('[StrategyManagement] params from URL:', { taskId: taskIdFromUrl, strategy: strategyFromUrl });

      // 如果有 taskId，填充到回测搜索框
      if (taskIdFromUrl) {
        setBacktestSearchText(taskIdFromUrl);
      }

      // 如果有 strategy，设置选中的策略
      if (strategyFromUrl) {
        setSelectedStrategy(strategyFromUrl);
      }

      // 自动切换到回测记录 tab
      setActiveTab('backtests');

      // 清除 URL 参数（避免刷新页面时重复填充）
      const newParams = new URLSearchParams(searchParams);
      newParams.delete('taskId');
      newParams.delete('strategy');
      if (newParams.toString()) {
        setSearchParams(newParams);
      } else {
        // 如果没有其他参数，移除所有参数
        setSearchParams({});
      }
    }

    // 首次加载：上面的 setXxx 不立即生效，必须把 URL 恢复值显式传给请求
    loadBacktests({
      keyword: taskIdFromUrl || searchFromUrl || '',
      strategy: strategyFromUrl || '',
      status: statusFromUrl || 'all',
      sortBy: sortFieldFromUrl || 'created_at',
      sortOrder: sortOrderFromUrl || 'desc',
      page: 1,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 路由参数初始化时一次性执行
  }, []);

  // 加载回测列表（服务端分页/筛选/排序）
  // overrides：setState 异步生效前需要用新值发起请求时的显式传值入口
  const loadBacktests = async (overrides?: {
    page?: number;
    pageSize?: number;
    status?: string;
    keyword?: string;
    strategy?: string;
    sortBy?: string;
    sortOrder?: string;
  }) => {
    try {
      setBacktestLoading(true);
      const status = overrides?.status ?? backtestStatusFilter;
      const response = await backtestApi.getBacktestList({
        page: overrides?.page ?? ((backtestPagination.current as number) || 1),
        page_size: overrides?.pageSize ?? ((backtestPagination.pageSize as number) || 10),
        // 'all' 表示不筛选状态，不传给后端
        status: status === 'all' ? undefined : status,
        keyword: (overrides?.keyword ?? backtestSearchText) || undefined,
        strategy: (overrides?.strategy ?? selectedStrategy) || undefined,
        sort_by: overrides?.sortBy ?? backtestSortField,
        sort_order: overrides?.sortOrder ?? backtestSortOrder,
      });
      if (response.backtests && Array.isArray(response.backtests)) {
        setBacktests(response.backtests);
        setBacktestPagination((prev) => ({
          ...prev,
          current: overrides?.page ?? (prev.current as number),
          pageSize: overrides?.pageSize ?? (prev.pageSize as number),
          total: response.total ?? 0,
        }));
      }
    } catch (error) {
      console.error('Failed to load backtest list:', error);
      message.error(t('load_backtest_list_failed_generic'));
    } finally {
      setBacktestLoading(false);
    }
  };

  // 查看策略回测记录
  const handleViewBacktests = (strategyName: string) => {
    setSelectedStrategy(strategyName);
    setActiveTab('backtests');
    // 切换时按策略过滤重新拉取（setState 不立即生效，显式传值）
    loadBacktests({ strategy: strategyName, page: 1 });
  };

  // 构建返回 URL，保留当前的搜索和筛选状态
  const buildReturnUrl = () => {
    const params = new URLSearchParams();
    params.set('tab', 'backtests');

    // 保留搜索和筛选状态
    if (backtestSearchText) {
      params.set('search', backtestSearchText);
    }
    if (selectedStrategy) {
      params.set('strategy', selectedStrategy);
    }
    if (backtestStatusFilter && backtestStatusFilter !== 'all') {
      params.set('status', backtestStatusFilter);
    }
    if (backtestSortField && backtestSortField !== 'created_at') {
      params.set('sortField', backtestSortField);
    }
    if (backtestSortOrder && backtestSortOrder !== 'desc') {
      params.set('sortOrder', backtestSortOrder);
    }

    return encodeURIComponent(`/strategy-management?${params.toString()}`);
  };

  // 跳转到回放页面 - 添加返回 URL 参数
  const handleReplay = (backtestId: string) => {
    const returnUrl = buildReturnUrl();
    navigate(`/backtest/replay/${backtestId}?returnUrl=${returnUrl}`);
  };

  // 跳转到详情页面 - 添加返回 URL 参数
  const handleViewDetail = (backtestId: string) => {
    const returnUrl = buildReturnUrl();
    navigate(`/backtest/detail/${backtestId}?returnUrl=${returnUrl}`);
  };

  // 删除单条回测记录
  const handleDeleteBacktest = (backtestId: string) => {
    // 访客用户无法删除
    if (isGuest) {
      message.warning(t('guest_delete_restricted'));
      return;
    }

    confirm({
      title: t('confirm_delete_backtest'),
      content: t('delete_backtest_confirm_msg'),
      okText: t('delete'),
      okType: 'danger',
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          await backtestApi.deleteBacktest(backtestId);
          message.success(t('backtest_delete_success'));
          loadBacktests();
          // 如果删除的是已选中的，清空选择
          if (backtestSelectedRowKeys.includes(backtestId)) {
            setBacktestSelectedRowKeys([]);
          }
        } catch (error) {
          console.error('Failed to delete backtest record:', error);
          message.error(t('backtest_delete_failed'));
        }
      },
    });
  };

  // 批量删除回测记录
  const handleBatchDeleteBacktests = () => {
    // 访客用户无法删除
    if (isGuest) {
      message.warning(t('guest_batch_delete_restricted'));
      return;
    }

    if (backtestSelectedRowKeys.length === 0) {
      message.warning(t('please_select_backtest'));
      return;
    }

    confirm({
      title: t('confirm_batch_delete_backtest'),
      content: t('batch_delete_backtest_confirm_msg', { count: backtestSelectedRowKeys.length }),
      okText: t('delete'),
      okType: 'danger',
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          // 并行删除所有选中的回测记录
          await Promise.all(
            backtestSelectedRowKeys.map((id) => backtestApi.deleteBacktest(id as string))
          );
          message.success(t('batch_backtest_delete_success'));
          setBacktestSelectedRowKeys([]);
          loadBacktests();
        } catch (error) {
          console.error('Failed to batch delete backtest records:', error);
          message.error(t('batch_backtest_delete_failed'));
        }
      },
    });
  };

  // 创建新策略
  const handleCreateStrategy = () => {
    navigate('/strategy-editor');
  };

  // 编辑策略
  const handleEditStrategy = (strategy: Strategy) => {
    navigate(`/strategy-editor/${strategy.name}`);
  };

  // 删除策略
  const handleDeleteStrategy = (strategy: Strategy) => {
    confirm({
      title: t('confirm_delete_strategy'),
      content: t('delete_strategy_confirm_msg', { name: strategy.name }),
      okText: t('delete'),
      okType: 'danger',
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          setLoading(true);
          await strategyApi.deleteStrategy(strategy.name);
          message.success(t('strategy_delete_success'));
          loadStrategies();
        } catch (error) {
          console.error('Failed to delete strategy:', error);
          message.error(t('strategy_delete_failed'));
        } finally {
          setLoading(false);
        }
      },
    });
  };

  // 回测策略
  const handleBacktestStrategy = (strategy: Strategy) => {
    navigate('/backtest/config', { state: { strategy, showConfig: true } });
  };

  // 安全的日期格式化函数
  const formatDate = (dateString: string | undefined): string => {
    if (!dateString) {
      return '';
    }
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) {
        return '';
      }
      return date.toLocaleString();
    } catch (error) {
      console.error('Date parsing error:', error);
      return '';
    }
  };

  // 工具栏计数「显示 x-y / 共 z」：按当前页与页大小折算，空数据归 0
  const shownRange = (current: number, size: number, total: number) => {
    const start = total === 0 ? 0 : (current - 1) * size + 1;
    const end = Math.min(current * size, total);
    return t('shown_range', { start, end, total });
  };

  // 回测状态 → §6.2 chip（视觉迁移，不改状态语义；运行中带 pulse 圆点）
  const renderStatusChip = (status: string) => {
    const text = getStatusText(status);
    switch (status) {
      case 'completed':
        return <span className="qc-chip ok">{text}</span>;
      case 'running':
      case 'in_progress':
        return <span className="qc-chip ok"><span className="qc-pdot" />{text}</span>;
      case 'failed':
        return <span className="qc-chip down">{text}</span>;
      case 'pending':
        return <span className="qc-chip quiet">{text}</span>;
      default:
        return <span className="qc-chip quiet">{status}</span>;
    }
  };

  // 过滤和排序后的数据
  const filteredStrategies = useMemo(() => {
    let result = [...strategies];

    // 搜索过滤
    if (searchText) {
      const lowerSearch = searchText.toLowerCase();
      result = result.filter(
        (strategy) =>
          strategy.name?.toLowerCase().includes(lowerSearch) ||
          strategy.description?.toLowerCase().includes(lowerSearch)
      );
    }

    // 排序
    result.sort((a, b) => {
      let aVal: string = '';
      let bVal: string = '';

      switch (sortField) {
        case 'name':
          aVal = a.name || '';
          bVal = b.name || '';
          break;
        case 'created_at':
          aVal = (a as unknown as StrategyBackendFields).created_at || '';
          bVal = (b as unknown as StrategyBackendFields).created_at || '';
          break;
        case 'updated_at':
        default:
          aVal = (a as unknown as StrategyBackendFields).updated_at || '';
          bVal = (b as unknown as StrategyBackendFields).updated_at || '';
          break;
      }

      return sortOrder === 'asc'
        ? aVal.localeCompare(bVal)
        : bVal.localeCompare(aVal);
    });

    return result;
  }, [strategies, searchText, sortField, sortOrder]);

  // 表格列定义 — §6.5：策略名 mono + 类型/版本 chip；时间列 mono 11px；操作 .qc-mini-btn 图标钮
  const columns: TableProps<Strategy>['columns'] = [
    {
      title: t('strategy_name'),
      dataIndex: 'name',
      key: 'name',
      width: 220,
      ellipsis: {
        showTitle: false,
      },
      render: (text: string, record: Strategy) => (
        <Tooltip title={text} placement="topLeft">
          <span className="qc-cell-strat-wrap">
            <span className="qc-cell-strat" style={{ maxWidth: 140 }}>{text}</span>
            {record.strategy_type === 'rl' && <span className="qc-chip pri">RL</span>}
            {record.strategy_type === 'rule' && <span className="qc-chip info">{t('sm_tag_rule')}</span>}
            <span className="qc-chip quiet qc-mono">v{(record as unknown as StrategyBackendFields).version || '1.0.0'}</span>
          </span>
        </Tooltip>
      ),
    },
    {
      title: t('description'),
      dataIndex: 'description',
      key: 'description',
      width: 260,
      ellipsis: {
        showTitle: false,
      },
      render: (text: string) => (
        <Tooltip title={text || t('no_description')} placement="topLeft">
          <span style={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block', verticalAlign: 'middle' }}>
            {text || t('no_description')}
          </span>
        </Tooltip>
      ),
    },
    {
      title: t('create_time'),
      key: 'created_at',
      width: 150,
      render: (_, record: Strategy) => (
        <span className="qc-cell-time qc-mono">{formatDate((record as unknown as StrategyBackendFields).created_at)}</span>
      ),
    },
    {
      title: t('update_time'),
      key: 'updated_at',
      width: 150,
      render: (_, record: Strategy) => (
        <span className="qc-cell-time qc-mono">{formatDate((record as unknown as StrategyBackendFields).updated_at)}</span>
      ),
    },
    {
      title: t('action'),
      key: 'action',
      width: 152,
      fixed: 'right',
      render: (_, record: Strategy) => (
        <div className="qc-row-actions" onClick={(e) => e.stopPropagation()}>
          <Tooltip title={t('edit_strategy')}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only"
              aria-label={t('edit_strategy')}
              onClick={() => handleEditStrategy(record)}
            >
              <EditOutlined />
            </button>
          </Tooltip>
          <Tooltip title={t('backtest_strategy')}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only"
              aria-label={t('backtest_strategy')}
              onClick={() => handleBacktestStrategy(record)}
            >
              <PlayCircleOutlined />
            </button>
          </Tooltip>
          <Tooltip title={t('backtest_records')}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only"
              aria-label={t('backtest_records')}
              onClick={() => handleViewBacktests(record.name)}
            >
              <HistoryOutlined />
            </button>
          </Tooltip>
          <Tooltip title={isGuest ? t('guest_save_restricted') : (t('delete_strategy'))}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only danger"
              aria-label={isGuest ? t('guest_save_restricted') : (t('delete_strategy'))}
              onClick={() => handleDeleteStrategy(record)}
              disabled={isGuest}
            >
              <DeleteOutlined />
            </button>
          </Tooltip>
        </div>
      ),
    },
  ];

  // 渲染列表视图 — §6.5/§6.6：PageToolbar + DataTable，行点击选中（primary tint）
  const renderListView = () => {
    const paginationCfg = (pagination ?? {}) as TablePaginationConfig;
    const current = (paginationCfg.current as number) || 1;
    const currentSize = (paginationCfg.pageSize as number) || pageSize;
    return (
      <>
        <PageToolbar
          search={{
            value: searchText,
            onChange: (value) => {
              setSearchText(value);
              // §6.6 过滤联动：搜索变化页码归 1（历史雷区：搜索不重置页码）
              setPagination((prev) => ({ ...(prev || {}), current: 1 }));
            },
            placeholder: t('search_strategy'),
            ariaLabel: t('search_strategy'),
          }}
          filters={
            <Select
              aria-label={t('sort_by')}
              value={`${sortField}-${sortOrder}`}
              onChange={(value) => {
                const [field, order] = value.split('-');
                setSortField(field as SortField);
                setSortOrder(order as SortOrder);
              }}
              style={{ width: 150 }}
              options={[
                { value: 'updated_at-desc', label: t('sort_update_time_desc') },
                { value: 'updated_at-asc', label: t('sort_update_time_asc') },
                { value: 'created_at-desc', label: t('sort_create_time_backtest_desc') },
                { value: 'created_at-asc', label: t('sort_create_time_backtest_asc') },
                { value: 'name-asc', label: t('sort_name_asc') },
                { value: 'name-desc', label: t('sort_name_desc') },
              ]}
            />
          }
          count={shownRange(current, currentSize, filteredStrategies.length)}
        />
        <DataTable<Strategy>
          columns={columns}
          dataSource={filteredStrategies}
          pagination={{
            ...pagination,
            onChange: (pg, size) => {
              // 条数变化写回全局配置，全站生效
              if (size !== pageSize) setPageSize(size);
              setPagination({ ...pagination, current: pg, pageSize: size });
            },
          }}
          loading={loading}
          rowKey="name"
          rowClassName={(record) => (record.name === selectedRowKey ? 'qc-row-selected' : '')}
          onRow={(record) => ({
            onClick: () => setSelectedRowKey(record.name),
            style: { cursor: 'pointer' },
          })}
          onChange={(newPagination) => {
            // 条数变化写回全局配置，全站生效
            if (newPagination.pageSize && newPagination.pageSize !== pageSize) {
              setPageSize(newPagination.pageSize);
            }
            setPagination(newPagination);
          }}
          emptyTitle={searchText ? t('no_data') : t('no_strategies')}
        />
      </>
    );
  };

  // 渲染卡片视图
  const renderCardView = () => {
    const currentPage = typeof pagination === 'object' && pagination ? (pagination.current as number) || 1 : 1;
    const pageSize = typeof pagination === 'object' && pagination ? (pagination.pageSize as number) || 12 : 12;
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = startIndex + pageSize;
    const currentPageData = filteredStrategies.slice(startIndex, endIndex);

    return (
      <>
        <Row gutter={[16, 16]}>
          {currentPageData.length > 0 ? (
            currentPageData.map((strategy) => (
              <Col xs={24} sm={12} md={8} lg={6} key={strategy.name}>
                <Card
                  size="small"
                  title={
                    <span className="font-medium">{strategy.name}</span>
                  }
                  extra={
                    <Space size="small">
                      <Tooltip title={t('edit_strategy')}>
                        <Button
                          type="text"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => handleEditStrategy(strategy)}
                        />
                      </Tooltip>
                      <Tooltip title={isGuest ? t('guest_save_restricted') : (t('delete_strategy'))}>
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => handleDeleteStrategy(strategy)}
                          disabled={isGuest}
                        />
                      </Tooltip>
                    </Space>
                  }
                  hoverable
                  style={{
                    boxShadow: 'var(--qc-shadow-card)',
                  }}
                >
                  <div className="mb-3">
                    <div className="flex justify-between items-center mb-1">
                      <span style={{ color: 'var(--qc-text-tertiary)', fontSize: 13 }}>{t('strategy_description')}</span>
                      <Space size={4}>
                        {strategy.strategy_type === 'rl' && (
                          <span className="qc-chip pri">RL</span>
                        )}
                        {strategy.strategy_type === 'rule' && (
                          <span className="qc-chip info">{t('sm_tag_rule')}</span>
                        )}
                        <span className="qc-chip quiet qc-mono">v{(strategy as unknown as StrategyBackendFields).version || '1.0.0'}</span>
                      </Space>
                    </div>
                    <Tooltip title={strategy.description || t('no_description')} placement="topLeft">
                      <div
                        className="overflow-hidden text-ellipsis"
                        style={{
                          minHeight: 40,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                        }}
                      >
                        {strategy.description || t('no_description')}
                      </div>
                    </Tooltip>
                  </div>

                  <div className="text-xs space-y-1" style={{ color: 'var(--qc-text-tertiary)' }}>
                    <div className="flex justify-between">
                      <span>{t('create_time')}:</span>
                      <span className="qc-mono">{formatDate((strategy as unknown as StrategyBackendFields).created_at)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>{t('update_time')}:</span>
                      <span className="qc-mono">{formatDate((strategy as unknown as StrategyBackendFields).updated_at)}</span>
                    </div>
                  </div>

                  <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--qc-border)' }}>
                    <Row gutter={[8, 8]}>
                      <Col span={12}>
                        <Button
                          type="primary"
                          size="small"
                          icon={<PlayCircleOutlined />}
                          onClick={() => handleBacktestStrategy(strategy)}
                          style={{ width: '100%' }}
                        >
                          {t('backtest')}
                        </Button>
                      </Col>
                      <Col span={12}>
                        <Button
                          size="small"
                          icon={<HistoryOutlined />}
                          onClick={() => handleViewBacktests(strategy.name)}
                          style={{ width: '100%' }}
                        >
                          {t('records')}
                        </Button>
                      </Col>
                    </Row>
                  </div>
                </Card>
              </Col>
            ))
          ) : (
            <Col span={24}>
              <Card
                className="text-center"
                style={{
                  padding: '60px 0',
                }}
              >
                <div className="mb-4">{t('no_strategies')}</div>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateStrategy}>
                  {t('create_first_strategy')}
                </Button>
              </Card>
            </Col>
          )}
        </Row>
        <Row justify="center" style={{ marginTop: 16 }}>
          <Pagination
            current={currentPage}
            pageSize={pageSize}
            total={filteredStrategies.length}
            showSizeChanger
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            showTotal={(total) => `${t('total_items', { total })}`}
            onChange={(page, size) => {
              setPagination({
                ...pagination,
                current: page,
                pageSize: size,
              });
            }}
          />
        </Row>
      </>
    );
  };

  // 获取状态显示文本
  const getStatusText = (status: string) => {
    switch (status) {
      case 'completed':
        return t('status_completed');
      case 'running':
      case 'in_progress':
        return t('status_running');
      case 'failed':
        return t('status_failed');
      case 'pending':
        return t('status_pending');
      default:
        return status;
    }
  };

  // 重置回测筛选（筛选/排序已下沉服务端，重置后用默认参数重拉）
  const handleResetBacktestFilters = () => {
    setBacktestSearchText('');
    setBacktestStatusFilter('all');
    setBacktestSortField('created_at');
    setBacktestSortOrder('desc');
    loadBacktests({
      page: 1,
      status: 'all',
      keyword: '',
      strategy: '',
      sortBy: 'created_at',
      sortOrder: 'desc',
    });
  };

  // 回测列表表格列
  const backtestColumns: TableProps<BacktestTask>['columns'] = [
    {
      title: t('strategy_name'),
      dataIndex: 'strategy_name',
      key: 'strategy_name',
      width: 180,
      ellipsis: {
        showTitle: false,
      },
      render: (text: string) => (
        <Tooltip title={text} placement="topLeft">
          <span className="qc-cell-strat">{text}</span>
        </Tooltip>
      ),
    },
    {
      title: t('status'),
      dataIndex: 'status',
      key: 'status',
      width: 96,
      align: 'center',
      render: (status: string) => renderStatusChip(status),
    },
    {
      title: t('total_return'),
      dataIndex: 'total_return',
      key: 'total_return',
      width: 100,
      align: 'right',
      render: (value: number | undefined) => {
        if (value === undefined || value === null) return 'N/A';
        const isPositive = value >= 0;
        return (
          <span className="qc-mono" style={{ color: isPositive ? QUANT_COLORS.positive : QUANT_COLORS.negative }}>
            {isPositive ? '+' : ''}{value.toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: t('max_drawdown'),
      dataIndex: 'max_drawdown',
      key: 'max_drawdown',
      width: 100,
      align: 'right',
      render: (value: number | undefined) => {
        if (value === undefined || value === null) return 'N/A';
        return <span className="qc-mono" style={{ color: QUANT_COLORS.negative }}>{value.toFixed(2)}%</span>;
      },
    },
    {
      title: t('create_time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (value: string) => (
        <span className="qc-cell-time qc-mono">{dayjs(value).format('YYYY-MM-DD HH:mm:ss')}</span>
      ),
    },
    {
      title: t('action'),
      key: 'action',
      width: 122,
      fixed: 'right',
      render: (_, record: BacktestTask) => (
        <div className="qc-row-actions" onClick={(e) => e.stopPropagation()}>
          <Tooltip title={t('view_details')}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only"
              aria-label={t('view_details')}
              onClick={() => handleViewDetail(record.id)}
            >
              <LineChartOutlined />
            </button>
          </Tooltip>
          <Tooltip title={t('replay')}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only"
              aria-label={t('replay')}
              onClick={() => handleReplay(record.id)}
            >
              <PlayCircleOutlined />
            </button>
          </Tooltip>
          <Tooltip title={isGuest ? (t('guest_delete_restricted')) : (t('delete'))}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only danger"
              aria-label={isGuest ? (t('guest_delete_restricted')) : (t('delete'))}
              onClick={() => handleDeleteBacktest(record.id)}
              disabled={isGuest}
            >
              <DeleteOutlined />
            </button>
          </Tooltip>
        </div>
      ),
    },
  ];

  // 渲染回测列表视图 — 与策略列表同一套 DataTable 口径（行点击选中、双击进详情）
  const renderBacktestListView = () => (
    <>
      <PageToolbar
        search={{
          value: backtestSearchText,
          onChange: (value) => {
            setBacktestSearchText(value);
            // 点 clear 清空时同步重发服务端过滤，避免「界面已清、结果仍是旧过滤」
            if (value === '') {
              loadBacktests({ keyword: '', page: 1 });
            }
          },
          onPressEnter: (value) => loadBacktests({ keyword: value, page: 1 }),
          placeholder: t('search_backtest'),
          ariaLabel: t('search_backtest'),
        }}
        filters={
          <>
            <Select
              aria-label={t('select_strategy')}
              placeholder={t('select_strategy')}
              value={selectedStrategy || undefined}
              onChange={(value) => {
                setSelectedStrategy(value ?? '');
                loadBacktests({ strategy: value ?? '', page: 1 });
              }}
              allowClear
              style={{ width: 150 }}
              options={strategies.map((s) => ({ value: s.name, label: s.name }))}
            />
            <Select
              aria-label={t('status')}
              value={backtestStatusFilter}
              onChange={(value) => {
                setBacktestStatusFilter(value);
                loadBacktests({ status: value, page: 1 });
              }}
              style={{ width: 118 }}
              options={[
                { value: 'all', label: t('all_status_backtest') },
                { value: 'completed', label: t('status_completed') },
                { value: 'running', label: t('status_running') },
                { value: 'failed', label: t('status_failed') },
                { value: 'pending', label: t('status_pending') },
              ]}
            />
            <Select
              aria-label={t('sort_by')}
              value={`${backtestSortField}-${backtestSortOrder}`}
              onChange={(value) => {
                const [field, order] = value.split('-');
                setBacktestSortField(field);
                setBacktestSortOrder(order);
                loadBacktests({ sortBy: field, sortOrder: order, page: 1 });
              }}
              style={{ width: 150 }}
              options={[
                { value: 'created_at-desc', label: t('sort_create_time_desc') },
                { value: 'created_at-asc', label: t('sort_create_time_asc') },
                { value: 'total_return-desc', label: t('sort_return_desc') },
                { value: 'total_return-asc', label: t('sort_return_asc') },
                { value: 'max_drawdown-desc', label: t('sort_drawdown_desc') },
                { value: 'max_drawdown-asc', label: t('sort_drawdown_asc') },
                { value: 'strategy_name-asc', label: t('sort_name_asc') },
              ]}
            />
          </>
        }
        count={shownRange(
          (backtestPagination.current as number) || 1,
          (backtestPagination.pageSize as number) || pageSize,
          (backtestPagination.total as number) || 0
        )}
        actions={
          <>
            <Button icon={<ReloadOutlined />} onClick={handleResetBacktestFilters} style={{ height: 30 }}>
              {t('reset')}
            </Button>
            <Button type="primary" icon={<ReloadOutlined />} onClick={() => loadBacktests()} loading={backtestLoading} style={{ height: 30 }}>
              {t('refresh')}
            </Button>
            {backtestSelectedRowKeys.length > 0 && (
              <Button danger icon={<DeleteOutlined />} onClick={handleBatchDeleteBacktests} disabled={isGuest} style={{ height: 30 }}>
                {t('delete')} ({backtestSelectedRowKeys.length})
              </Button>
            )}
          </>
        }
      />
      <DataTable<BacktestTask>
        columns={backtestColumns}
        dataSource={backtests}
        loading={backtestLoading}
        rowKey="id"
        pagination={{
          ...backtestPagination,
          onChange: (pg, size) => {
            // 分页事件下沉服务端重新拉取
            setBacktestPagination({ ...backtestPagination, current: pg, pageSize: size });
            loadBacktests({ page: pg, pageSize: size });
          },
        }}
        remote
        rowSelection={{
          selectedRowKeys: backtestSelectedRowKeys,
          onChange: (newSelectedRowKeys: React.Key[]) => {
            setBacktestSelectedRowKeys(newSelectedRowKeys);
          },
        }}
        onRow={(record) => ({
          onClick: () => {
            setBacktestSelectedRowKeys([record.id]);
          },
          onDoubleClick: () => {
            handleViewDetail(record.id);
          },
          style: {
            cursor: 'pointer',
          },
        })}
      />
    </>
  );

  // 渲染回测卡片视图
  const renderBacktestCardView = () => {
    const currentPage = (backtestPagination.current as number) || 1;
    const pageSize = (backtestPagination.pageSize as number) || 10;
    // backtests 即服务端返回的当前页数据，无需再本地切片
    const currentPageData = backtests;

    return (
      <>
        <Row gutter={[16, 16]}>
          {currentPageData.map((task: BacktestTask) => (
            <Col xs={24} sm={12} md={8} lg={6} key={task.id}>
              <Card
                size="small"
                title={
                  <div className="flex items-center justify-between">
                    <span className="font-medium truncate qc-mono" style={{ maxWidth: '70%' }}>
                      {task.strategy_name}
                    </span>
                    {renderStatusChip(task.status)}
                  </div>
                }
                extra={
                  // 删除统一放卡片右上角（与策略卡片一致）；卡片可点击需阻止冒泡
                  <Tooltip title={isGuest ? t('guest_delete_restricted') : (t('delete'))}>
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      disabled={isGuest}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteBacktest(task.id);
                      }}
                    />
                  </Tooltip>
                }
                className={backtestSelectedRowKeys.includes(task.id) ? 'qc-card-selected' : ''}
                onClick={() => setBacktestSelectedRowKeys([task.id])}
                onDoubleClick={() => handleViewDetail(task.id)}
                style={{ cursor: 'pointer', boxShadow: 'var(--qc-shadow-card)' }}
              >
                <div className="space-y-3" style={{ color: 'var(--qc-text-tertiary)' }}>
                  <div className="flex justify-between items-center">
                    <span>{t('total_return')}</span>
                    <span
                      style={{
                        color:
                          task.total_return === undefined || task.total_return === null
                            ? 'inherit'
                            : task.total_return >= 0
                              ? QUANT_COLORS.positive
                              : QUANT_COLORS.negative,
                        fontWeight: 'bold',
                      }}
                    >
                      {task.total_return === undefined || task.total_return === null
                        ? 'N/A'
                        : `${task.total_return >= 0 ? '+' : ''}${task.total_return.toFixed(2)}%`}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span>{t('max_drawdown')}</span>
                    <span style={{ color: QUANT_COLORS.negative, fontWeight: 'bold' }}>
                      {task.max_drawdown === undefined || task.max_drawdown === null
                        ? 'N/A'
                        : `${task.max_drawdown.toFixed(2)}%`}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span>{t('create_time')}</span>
                    <span className="qc-mono">{dayjs(task.created_at).format('YYYY-MM-DD HH:mm')}</span>
                  </div>
                  <div className="flex justify-end gap-2 pt-2" style={{ borderTop: '1px solid var(--qc-border)' }}>
                    <Button
                      type="link"
                      size="small"
                      icon={<LineChartOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleViewDetail(task.id);
                      }}
                    >
                      {t('view')}
                    </Button>
                    <Button
                      type="link"
                      size="small"
                      icon={<PlayCircleOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleReplay(task.id);
                      }}
                    >
                      {t('replay')}
                    </Button>
                  </div>
                </div>
              </Card>
            </Col>
          ))}
        </Row>
        <Row justify="center" style={{ marginTop: 16 }}>
          <Pagination
            current={currentPage}
            pageSize={pageSize}
            total={(backtestPagination.total as number) || 0}
            showSizeChanger
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            showTotal={(total) => `${t('total_items', { total })}`}
            onChange={(page, size) => {
              // 分页事件下沉服务端重新拉取；条数变化写回全局配置
              setPageSize(size);
              loadBacktests({ page, pageSize: size });
            }}
          />
        </Row>
      </>
    );
  };

  // Tab 切换项
  const tabItems = [
    {
      key: 'strategies',
      label: (
        <span>
          <AppstoreOutlined style={{ marginRight: 8 }} />
          {t('strategy_list')}
        </span>
      ),
      children: (
        <>
          {viewType === 'list' ? renderListView() : renderCardView()}
        </>
      ),
    },
    {
      key: 'backtests',
      label: (
        <span>
          <HistoryOutlined style={{ marginRight: 8 }} />
          {t('backtest_records')}
          {selectedStrategy && <span className="qc-chip info qc-mono" style={{ marginLeft: 8 }}>{selectedStrategy}</span>}
        </span>
      ),
      children: (
        <>
          {backtestViewType === 'list' ? renderBacktestListView() : renderBacktestCardView()}
        </>
      ),
    },
  ];

  // 处理 Tab 切换 - 更新 URL 参数
  const handleTabChange = (key: string) => {
    const newTab = key as TabType;
    setActiveTab(newTab);
    // 更新 URL 参数，保留其他参数
    const newParams = new URLSearchParams(searchParams);
    newParams.set('tab', newTab);
    setSearchParams(newParams);
  };

  return (
    <PageContainer
      title={t('strategy_management')}
      actions={
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleCreateStrategy}
          style={{ height: 30, padding: '0 14px', fontSize: 12 }}
        >
          {t('new_strategy')}
        </Button>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        items={tabItems}
      />
    </PageContainer>
  );
};

export default StrategyManagement;
