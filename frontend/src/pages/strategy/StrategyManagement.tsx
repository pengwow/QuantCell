import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Card,
  Button,
  Space,
  Tag,
  Tooltip,
  Modal,
  App,
  Spin,
  Input,
  Select,
  Row,
  Col,
  Table,
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
import type { TablePaginationConfig, TableProps } from 'antd';
import dayjs from 'dayjs';
import { useConfigStore } from '@/store';
import { useGlobalPageSize } from '../../hooks/useGlobalPageSize';
import { useViewType } from '../../hooks/useViewType';
import { PAGE_SIZE_OPTIONS } from '../../constants/pagination';
import { QUANT_COLORS } from '@/utils/colors';

const { confirm } = Modal;
const { Search } = Input;

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

  // 分页配置 - 策略列表（pageSize 跟随全局配置）
  const [pagination, setPagination] = useState<TableProps<Strategy>['pagination']>(() => ({
    current: 1,
    pageSize,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    showTotal: (total) => `${t('total_items', { total })}`,
  }));

  // 分页配置 - 回测列表；state 恒为对象，false/undefined 只在 Table 的 props 上有意义
  const [backtestPagination, setBacktestPagination] = useState<TablePaginationConfig>(() => ({
    current: 1,
    pageSize,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    showTotal: (total) => `${t('total_items', { total })}`,
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

  // 重置筛选
  const handleResetFilters = () => {
    setSearchText('');
    setSortField('updated_at');
    setSortOrder('desc');
    setPagination({
      ...pagination,
      current: 1,
    });
  };

  // 表格列定义
  const columns: TableProps<Strategy>['columns'] = [
    {
      title: t('strategy_name'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: {
        showTitle: false,
      },
      render: (text: string, record: Strategy) => (
        <Tooltip title={text} placement="topLeft">
          <Space>
            <span className="font-medium" style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block' }}>{text}</span>
            {record.strategy_type === 'rl' && <Tag color="purple">RL</Tag>}
            {record.strategy_type === 'rule' && <Tag color="green">{t('sm_tag_rule')}</Tag>}
            <Tag color="blue">v{(record as unknown as StrategyBackendFields).version || '1.0.0'}</Tag>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: t('description'),
      dataIndex: 'description',
      key: 'description',
      width: 250,
      ellipsis: {
        showTitle: false,
      },
      render: (text: string) => (
        <Tooltip title={text || t('no_description')} placement="topLeft">
          <span style={{ maxWidth: 230, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block' }}>
            {text || t('no_description')}
          </span>
        </Tooltip>
      ),
    },
    {
      title: t('create_time'),
      key: 'created_at',
      width: 160,
      render: (_, record: Strategy) => formatDate((record as unknown as StrategyBackendFields).created_at),
    },
    {
      title: t('update_time'),
      key: 'updated_at',
      width: 160,
      render: (_, record: Strategy) => formatDate((record as unknown as StrategyBackendFields).updated_at),
    },
    {
      title: t('action'),
      key: 'action',
      width: 180,
      fixed: 'right',
      render: (_, record: Strategy) => (
        <Space size="small">
          <Tooltip title={t('edit_strategy')}>
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEditStrategy(record)}
            />
          </Tooltip>
          <Tooltip title={isGuest ? t('guest_save_restricted') : (t('delete_strategy'))}>
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDeleteStrategy(record)}
              disabled={isGuest}
            />
          </Tooltip>
          <Tooltip title={t('backtest_strategy')}>
            <Button
              type="text"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => handleBacktestStrategy(record)}
            />
          </Tooltip>
          <Tooltip title={t('backtest_records')}>
            <Button
              type="text"
              size="small"
              icon={<HistoryOutlined />}
              onClick={() => handleViewBacktests(record.name)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  // 渲染工具栏 - 参考策略回测页面风格
  const renderToolbar = () => (
    <div style={{ marginBottom: 16 }}>
      {/* 第一行：搜索 */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }} align="middle">
        <Col xs={24}>
          <Search
            placeholder={t('search_strategy')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ width: '100%' }}
          />
        </Col>
      </Row>

      {/* 第二行：排序（左） + 操作按钮（右） */}
      <Row gutter={[12, 12]} align="middle">
        {/* 排序 - 左侧 */}
        <Col xs={24} md={16} lg={14}>
          <Row gutter={[8, 8]}>
            <Col xs={12} sm={12} md={8}>
              <Select
                placeholder={t('sort_by')}
                value={`${sortField}-${sortOrder}`}
                onChange={(value) => {
                  const [field, order] = value.split('-');
                  setSortField(field as SortField);
                  setSortOrder(order as SortOrder);
                }}
                style={{ width: '100%' }}
                options={[
                  { value: 'updated_at-desc', label: t('sort_update_time_desc') },
                  { value: 'updated_at-asc', label: t('sort_update_time_asc') },
                  { value: 'created_at-desc', label: t('sort_create_time_backtest_desc') },
                  { value: 'created_at-asc', label: t('sort_create_time_backtest_asc') },
                  { value: 'name-asc', label: t('sort_name_asc') },
                  { value: 'name-desc', label: t('sort_name_desc') },
                ]}
              />
            </Col>
          </Row>
        </Col>

        {/* 操作按钮 - 右侧 */}
        <Col xs={24} md={8} lg={10}>
          <Row gutter={[8, 8]}>
            <Col xs={12}>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleResetFilters}
                style={{ width: '100%' }}
              >
                {t('reset')}
              </Button>
            </Col>
            <Col xs={12}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleCreateStrategy}
                style={{ width: '100%' }}
              >
                {t('new_strategy')}
              </Button>
            </Col>
          </Row>
        </Col>
      </Row>
    </div>
  );

  // 渲染列表视图
  const renderListView = () => (
    <Table
      columns={columns}
      dataSource={filteredStrategies}
      pagination={pagination}
      loading={loading}
      scroll={{ x: 'max-content' }}
      rowKey="name"
      onChange={(newPagination) => {
        // 条数变化写回全局配置，全站生效
        if (newPagination.pageSize && newPagination.pageSize !== pageSize) {
          setPageSize(newPagination.pageSize);
        }
        setPagination(newPagination);
      }}
    />
  );

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
                    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
                  }}
                >
                  <div className="mb-3">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-gray-500 text-sm">{t('strategy_description')}</span>
                      <Space size={4}>
                        {strategy.strategy_type === 'rl' && (
                          <Tag color="purple">RL</Tag>
                        )}
                        {strategy.strategy_type === 'rule' && (
                          <Tag color="green">{t('sm_tag_rule')}</Tag>
                        )}
                        <Tag color="blue">v{(strategy as unknown as StrategyBackendFields).version || '1.0.0'}</Tag>
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

                  <div className="text-xs text-gray-500 space-y-1">
                    <div className="flex justify-between">
                      <span>{t('create_time')}:</span>
                      <span>{formatDate((strategy as unknown as StrategyBackendFields).created_at)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>{t('update_time')}:</span>
                      <span>{formatDate((strategy as unknown as StrategyBackendFields).updated_at)}</span>
                    </div>
                  </div>

                  <div className="mt-3 pt-3 border-t border-gray-100">
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

  // 获取状态标签颜色
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'success';
      case 'running':
      case 'in_progress':
        return 'processing';
      case 'failed':
        return 'error';
      default:
        return 'default';
    }
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
      width: 150,
      ellipsis: true,
    },
    {
      title: t('status'),
      dataIndex: 'status',
      key: 'status',
      width: 90,
      align: 'center',
      render: (status: string) => (
        <Tag color={getStatusColor(status)}>{getStatusText(status)}</Tag>
      ),
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
          <span style={{ color: isPositive ? QUANT_COLORS.positive : QUANT_COLORS.negative }}>
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
        return <span style={{ color: QUANT_COLORS.negative }}>{value.toFixed(2)}%</span>;
      },
    },
    {
      title: t('create_time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: t('action'),
      key: 'action',
      width: 150,
      fixed: 'right',
      render: (_, record: BacktestTask) => (
        <Space size="small">
          <Tooltip title={t('view_details')}>
            <Button
              type="text"
              size="small"
              icon={<LineChartOutlined />}
              onClick={() => handleViewDetail(record.id)}
            />
          </Tooltip>
          <Tooltip title={t('replay')}>
            <Button
              type="text"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => handleReplay(record.id)}
            />
          </Tooltip>
          <Tooltip title={isGuest ? (t('guest_delete_restricted')) : (t('delete'))}>
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDeleteBacktest(record.id)}
              disabled={isGuest}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  // 渲染回测列表视图
  const renderBacktestListView = () => (
    <Table
      columns={backtestColumns}
      dataSource={backtests}
      loading={backtestLoading}
      scroll={{ x: 'max-content' }}
      rowKey="id"
      pagination={backtestPagination}
      onChange={(newPagination) => {
        // 分页事件下沉服务端重新拉取
        setBacktestPagination((prev) => ({ ...prev, ...newPagination }));
        loadBacktests({
          page: newPagination.current ?? 1,
          pageSize: newPagination.pageSize ?? 10,
        });
      }}
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
                    <span className="font-medium truncate" style={{ maxWidth: '70%' }}>
                      {task.strategy_name}
                    </span>
                    <Tag color={getStatusColor(task.status)}>
                      {getStatusText(task.status)}
                    </Tag>
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
                className={backtestSelectedRowKeys.includes(task.id) ? 'ring-2 ring-blue-500' : ''}
                onClick={() => setBacktestSelectedRowKeys([task.id])}
                onDoubleClick={() => handleViewDetail(task.id)}
                style={{ cursor: 'pointer' }}
              >
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">{t('total_return')}</span>
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
                    <span className="text-gray-500">{t('max_drawdown')}</span>
                    <span style={{ color: QUANT_COLORS.negative, fontWeight: 'bold' }}>
                      {task.max_drawdown === undefined || task.max_drawdown === null
                        ? 'N/A'
                        : `${task.max_drawdown.toFixed(2)}%`}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">{t('create_time')}</span>
                    <span className="text-sm text-gray-600">{dayjs(task.created_at).format('YYYY-MM-DD HH:mm')}</span>
                  </div>
                  <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
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

  // 渲染回测工具栏 - 参考策略回测页面风格
  const renderBacktestToolbar = () => (
    <div style={{ marginBottom: 16 }}>
      {/* 第一行：搜索 */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }} align="middle">
        <Col xs={24}>
          <Search
            placeholder={t('search_backtest')}
            value={backtestSearchText}
            onChange={(e) => setBacktestSearchText(e.target.value)}
            onSearch={(value) => loadBacktests({ keyword: value, page: 1 })}
            allowClear
            style={{ width: '100%' }}
          />
        </Col>
      </Row>

      {/* 第二行：筛选工具（左） + 操作按钮（右） */}
      <Row gutter={[12, 12]} align="middle">
        {/* 筛选工具 - 左侧 */}
        <Col xs={24} md={16} lg={14}>
          <Row gutter={[8, 8]}>
            <Col xs={12} sm={8} md={8}>
              <Select
                placeholder={t('select_strategy')}
                value={selectedStrategy || undefined}
                onChange={(value) => {
                  setSelectedStrategy(value ?? '');
                  loadBacktests({ strategy: value ?? '', page: 1 });
                }}
                style={{ width: '100%' }}
                allowClear
                options={strategies.map((s) => ({ value: s.name, label: s.name }))}
              />
            </Col>
            <Col xs={12} sm={8} md={8}>
              <Select
                placeholder={t('status')}
                value={backtestStatusFilter}
                onChange={(value) => {
                  setBacktestStatusFilter(value);
                  loadBacktests({ status: value, page: 1 });
                }}
                style={{ width: '100%' }}
                options={[
                  { value: 'all', label: t('all_status_backtest') },
                  { value: 'completed', label: t('status_completed') },
                  { value: 'running', label: t('status_running') },
                  { value: 'failed', label: t('status_failed') },
                  { value: 'pending', label: t('status_pending') },
                ]}
              />
            </Col>
            <Col xs={12} sm={8} md={8}>
              <Select
                placeholder={t('sort_by')}
                value={`${backtestSortField}-${backtestSortOrder}`}
                onChange={(value) => {
                  const [field, order] = value.split('-');
                  setBacktestSortField(field);
                  setBacktestSortOrder(order);
                  loadBacktests({ sortBy: field, sortOrder: order, page: 1 });
                }}
                style={{ width: '100%' }}
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
            </Col>
          </Row>
        </Col>

        {/* 操作按钮 - 右侧 */}
        <Col xs={24} md={8} lg={10}>
          <Row gutter={[8, 8]}>
            <Col xs={backtestSelectedRowKeys.length > 0 ? 8 : 12}>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleResetBacktestFilters}
                style={{ width: '100%' }}
              >
                {t('reset')}
              </Button>
            </Col>
            <Col xs={backtestSelectedRowKeys.length > 0 ? 8 : 12}>
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={() => loadBacktests()}
                loading={backtestLoading}
                style={{ width: '100%' }}
              >
                {t('refresh')}
              </Button>
            </Col>
            {backtestSelectedRowKeys.length > 0 && (
              <Col xs={8}>
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleBatchDeleteBacktests}
                  disabled={isGuest}
                  style={{ width: '100%' }}
                >
                  {t('delete')} ({backtestSelectedRowKeys.length})
                </Button>
              </Col>
            )}
          </Row>
        </Col>
      </Row>
    </div>
  );

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
          {renderToolbar()}
          <Spin spinning={loading} description={t('loading')}>
            {viewType === 'list' ? renderListView() : renderCardView()}
          </Spin>
        </>
      ),
    },
    {
      key: 'backtests',
      label: (
        <span>
          <HistoryOutlined style={{ marginRight: 8 }} />
          {t('backtest_records')}
          {selectedStrategy && <Tag color="blue" style={{ marginLeft: 8 }}>{selectedStrategy}</Tag>}
        </span>
      ),
      children: (
        <>
          {renderBacktestToolbar()}
          <Spin spinning={backtestLoading} description={t('loading')}>
            {backtestViewType === 'list' ? renderBacktestListView() : renderBacktestCardView()}
          </Spin>
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
    <PageContainer title={t('strategy_management')}>
      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        items={tabItems}
        type="card"
      />
    </PageContainer>
  );
};

export default StrategyManagement;
