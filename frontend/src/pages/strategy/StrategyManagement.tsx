import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Card,
  Button,
  Space,
  Tag,
  Tooltip,
  Modal,
  message,
  Spin,
  Input,
  Select,
  Row,
  Col,
  Segmented,
  Table,
  Grid,
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
  UnorderedListOutlined,
  HistoryOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import { strategyApi, backtestApi } from '../../api';
import type { Strategy } from '../../types';
import type { BacktestTask } from '../../types/backtest';
import { useTranslation } from 'react-i18next';
import { setPageTitle } from '@/router';
import PageContainer from '@/components/PageContainer';
import type { TableProps } from 'antd';
import dayjs from 'dayjs';
import { useConfigStore } from '@/store';

const { confirm } = Modal;
const { Search } = Input;
const { useBreakpoint } = Grid;

// 视图类型
type ViewType = 'list' | 'card';

// 排序字段
type SortField = 'name' | 'created_at' | 'updated_at';
type SortOrder = 'asc' | 'desc';

// Tab 类型
type TabType = 'strategies' | 'backtests';

// 分页选项（与系统配置一致）
const PAGE_SIZE_OPTIONS = ['10', '15', '20', '30', '50', '100'];

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
  const screens = useBreakpoint();
  const [searchParams, setSearchParams] = useSearchParams();
  const getDefaultPageSize = useConfigStore((state: { getDefaultPageSize: () => number }) => state.getDefaultPageSize);

  // 从 URL 参数读取 Tab 状态
  const tabFromUrl = searchParams.get('tab') as TabType;
  const validTab = tabFromUrl === 'strategies' || tabFromUrl === 'backtests' ? tabFromUrl : 'strategies';

  // 视图类型状态 - 策略列表
  const [viewType, setViewType] = useState<ViewType>('card');

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

  // 回测列表视图类型
  const [backtestViewType, setBacktestViewType] = useState<ViewType>('list');
  const [backtestSelectedRowKeys, setBacktestSelectedRowKeys] = useState<React.Key[]>([]);

  // 回测筛选状态
  const [backtestSearchText, setBacktestSearchText] = useState<string>('');
  const [backtestStatusFilter, setBacktestStatusFilter] = useState<string>('all');
  const [backtestSortField, setBacktestSortField] = useState<string>('created_at');
  const [backtestSortOrder, setBacktestSortOrder] = useState<string>('desc');

  // 分页配置 - 策略列表（使用系统配置）
  const [pagination, setPagination] = useState<TableProps<Strategy>['pagination']>({
    current: 1,
    pageSize: 10,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    showTotal: (total) => `${t('total') || '共'}: ${total}`,
  });

  // 分页配置 - 回测列表（使用系统配置）
  const [backtestPagination, setBacktestPagination] = useState<TableProps<BacktestTask>['pagination']>({
    current: 1,
    pageSize: 10,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    showTotal: (total) => `共 ${total} 条`,
  });

  // 从全局配置加载分页大小
  useEffect(() => {
    console.log('[StrategyManagement] 从全局配置加载分页大小');
    const defaultPageSize = getDefaultPageSize();
    console.log('[StrategyManagement] 获取到的默认分页大小:', defaultPageSize);
    setPagination(prev => ({
      ...prev,
      pageSize: defaultPageSize,
    }));
    setBacktestPagination(prev => ({
      ...prev,
      pageSize: defaultPageSize,
    }));
  }, [getDefaultPageSize]);

  // 页面加载时输出全局配置（用于调试）
  useEffect(() => {
    console.log('[StrategyManagement] 页面加载，当前全局配置状态:', useConfigStore.getState());
  }, []);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('strategy_management'));
  }, [t]);

  // 加载策略列表
  const loadStrategies = async () => {
    try {
      setLoading(true);
      const response = await strategyApi.getStrategies() as { strategies: Strategy[] };
      if (response && response.strategies) {
        setStrategies(response.strategies);
      }
    } catch (error) {
      console.error('加载策略列表失败:', error);
      message.error('加载策略列表失败');
    } finally {
      setLoading(false);
    }
  };

  // 组件挂载时加载策略列表
  useEffect(() => {
    loadStrategies();
    loadBacktests();

    // 从 URL 参数恢复状态
    const taskIdFromUrl = searchParams.get('taskId');
    const strategyFromUrl = searchParams.get('strategy');
    const searchFromUrl = searchParams.get('search');
    const statusFromUrl = searchParams.get('status');
    const sortFieldFromUrl = searchParams.get('sortField');
    const sortOrderFromUrl = searchParams.get('sortOrder');

    // 如果是从详情页返回（有 returnUrl 相关参数），恢复搜索和筛选状态
    if (searchFromUrl !== null || statusFromUrl !== null || sortFieldFromUrl !== null || sortOrderFromUrl !== null) {
      console.log('[StrategyManagement] 从详情页返回，恢复搜索和筛选状态:', {
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
      console.log('[StrategyManagement] 从 URL 获取参数:', { taskId: taskIdFromUrl, strategy: strategyFromUrl });

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
  }, []);

  // 加载回测列表
  const loadBacktests = async () => {
    try {
      setBacktestLoading(true);
      const response = await backtestApi.getBacktestList();
      if (response.backtests && Array.isArray(response.backtests)) {
        setBacktests(response.backtests);
      }
    } catch (error) {
      console.error('加载回测列表失败:', error);
      message.error('加载回测列表失败');
    } finally {
      setBacktestLoading(false);
    }
  };

  // 查看策略回测记录
  const handleViewBacktests = (strategyName: string) => {
    setSelectedStrategy(strategyName);
    setActiveTab('backtests');
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
      title: t('confirm_delete_strategy') || '确认删除策略',
      content: t('delete_strategy_confirm_msg', { name: strategy.name }) || `确定要删除策略 "${strategy.name}" 吗？`,
      okText: t('delete') || '删除',
      okType: 'danger',
      cancelText: t('cancel') || '取消',
      onOk: async () => {
        try {
          setLoading(true);
          await strategyApi.deleteStrategy(strategy.name);
          message.success('策略删除成功');
          loadStrategies();
        } catch (error) {
          console.error('删除策略失败:', error);
          message.error('删除策略失败');
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
      console.error('日期解析错误:', error);
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
          aVal = (a as any).created_at || '';
          bVal = (b as any).created_at || '';
          break;
        case 'updated_at':
        default:
          aVal = (a as any).updated_at || '';
          bVal = (b as any).updated_at || '';
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
      title: '策略名称',
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
            <Tag color="blue">v{(record as any).version || '1.0.0'}</Tag>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      width: 250,
      ellipsis: {
        showTitle: false,
      },
      render: (text: string) => (
        <Tooltip title={text || '暂无描述'} placement="topLeft">
          <span style={{ maxWidth: 230, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block' }}>
            {text || '暂无描述'}
          </span>
        </Tooltip>
      ),
    },
    {
      title: '创建时间',
      key: 'created_at',
      width: 160,
      render: (_: any, record: Strategy) => formatDate((record as any).created_at),
    },
    {
      title: '更新时间',
      key: 'updated_at',
      width: 160,
      render: (_: any, record: Strategy) => formatDate((record as any).updated_at),
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      fixed: 'right',
      render: (_: any, record: Strategy) => (
        <Space size="small">
          <Tooltip title={t('edit_strategy') || '编辑策略'}>
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEditStrategy(record)}
            />
          </Tooltip>
          <Tooltip title={t('delete_strategy') || '删除策略'}>
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDeleteStrategy(record)}
            />
          </Tooltip>
          <Tooltip title={t('backtest_strategy') || '回测策略'}>
            <Button
              type="text"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => handleBacktestStrategy(record)}
            />
          </Tooltip>
          <Tooltip title="回测记录">
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
      {/* 第一行：搜索（左） + 视图切换（右） */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }} align="middle">
        <Col xs={16} sm={16} md={12} lg={10}>
          <Search
            placeholder="搜索策略名称或描述"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ width: '100%' }}
          />
        </Col>
        <Col xs={8} sm={8} md={12} lg={14} style={{ textAlign: 'right' }}>
          <Segmented
            value={viewType}
            onChange={(value) => setViewType(value as ViewType)}
            options={[
              { value: 'list', icon: <UnorderedListOutlined />, label: screens.sm ? '列表' : undefined },
              { value: 'card', icon: <AppstoreOutlined />, label: screens.sm ? '卡片' : undefined },
            ]}
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
                placeholder="排序"
                value={`${sortField}-${sortOrder}`}
                onChange={(value) => {
                  const [field, order] = value.split('-');
                  setSortField(field as SortField);
                  setSortOrder(order as SortOrder);
                }}
                style={{ width: '100%' }}
                options={[
                  { value: 'updated_at-desc', label: '更新时间 ↓' },
                  { value: 'updated_at-asc', label: '更新时间 ↑' },
                  { value: 'created_at-desc', label: '创建时间 ↓' },
                  { value: 'created_at-asc', label: '创建时间 ↑' },
                  { value: 'name-asc', label: '名称 A-Z' },
                  { value: 'name-desc', label: '名称 Z-A' },
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
                重置
              </Button>
            </Col>
            <Col xs={12}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleCreateStrategy}
                style={{ width: '100%' }}
              >
                新建策略
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
                      <Tooltip title={t('edit_strategy') || '编辑策略'}>
                        <Button
                          type="text"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => handleEditStrategy(strategy)}
                        />
                      </Tooltip>
                      <Tooltip title={t('delete_strategy') || '删除策略'}>
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => handleDeleteStrategy(strategy)}
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
                      <span className="text-gray-500 text-sm">策略描述</span>
                      <Tag color="blue">v{(strategy as any).version || '1.0.0'}</Tag>
                    </div>
                    <Tooltip title={strategy.description || '暂无描述'} placement="topLeft">
                      <div
                        className="overflow-hidden text-ellipsis"
                        style={{
                          minHeight: 40,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                        }}
                      >
                        {strategy.description || '暂无描述'}
                      </div>
                    </Tooltip>
                  </div>

                  <div className="text-xs text-gray-500 space-y-1">
                    <div className="flex justify-between">
                      <span>创建时间:</span>
                      <span>{formatDate((strategy as any).created_at)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>更新时间:</span>
                      <span>{formatDate((strategy as any).updated_at)}</span>
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
                          回测
                        </Button>
                      </Col>
                      <Col span={12}>
                        <Button
                          size="small"
                          icon={<HistoryOutlined />}
                          onClick={() => handleViewBacktests(strategy.name)}
                          style={{ width: '100%' }}
                        >
                          记录
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
                <div className="mb-4">{t('no_strategies') || '暂无策略'}</div>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateStrategy}>
                  {t('create_first_strategy') || '创建第一个策略'}
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
            showTotal={(total) => `共 ${total} 个策略`}
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
        return '已完成';
      case 'running':
      case 'in_progress':
        return '运行中';
      case 'failed':
        return '失败';
      case 'pending':
        return '等待中';
      default:
        return status;
    }
  };

  // 过滤后的回测列表
  const filteredBacktests = useMemo(() => {
    let result = [...backtests];

    // 按策略筛选
    if (selectedStrategy) {
      result = result.filter((bt) => bt.strategy_name === selectedStrategy);
    }

    // 搜索过滤
    if (backtestSearchText) {
      const lowerSearch = backtestSearchText.toLowerCase();
      result = result.filter(
        (task) =>
          task.strategy_name?.toLowerCase().includes(lowerSearch) ||
          task.id?.toLowerCase().includes(lowerSearch)
      );
    }

    // 状态过滤
    if (backtestStatusFilter !== 'all') {
      result = result.filter((task) => {
        if (backtestStatusFilter === 'running') {
          return task.status === 'running' || task.status === 'in_progress';
        }
        return task.status === backtestStatusFilter;
      });
    }

    // 排序
    result.sort((a, b) => {
      let aVal: number | string = '';
      let bVal: number | string = '';

      switch (backtestSortField) {
        case 'strategy_name':
          aVal = a.strategy_name || '';
          bVal = b.strategy_name || '';
          break;
        case 'total_return':
          aVal = a.total_return ?? -Infinity;
          bVal = b.total_return ?? -Infinity;
          break;
        case 'max_drawdown':
          aVal = a.max_drawdown ?? Infinity;
          bVal = b.max_drawdown ?? Infinity;
          break;
        case 'created_at':
        default:
          aVal = a.created_at || '';
          bVal = b.created_at || '';
          break;
      }

      if (typeof aVal === 'string') {
        return backtestSortOrder === 'asc'
          ? aVal.localeCompare(bVal as string)
          : (bVal as string).localeCompare(aVal);
      }
      return backtestSortOrder === 'asc' ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
    });

    return result;
  }, [backtests, selectedStrategy, backtestSearchText, backtestStatusFilter, backtestSortField, backtestSortOrder]);

  // 重置回测筛选
  const handleResetBacktestFilters = () => {
    setBacktestSearchText('');
    setBacktestStatusFilter('all');
    setBacktestSortField('created_at');
    setBacktestSortOrder('desc');
    setBacktestPagination({
      ...backtestPagination,
      current: 1,
    });
  };

  // 回测列表表格列
  const backtestColumns: TableProps<BacktestTask>['columns'] = [
    {
      title: '策略名称',
      dataIndex: 'strategy_name',
      key: 'strategy_name',
      width: 150,
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      align: 'center',
      render: (status: string) => (
        <Tag color={getStatusColor(status)}>{getStatusText(status)}</Tag>
      ),
    },
    {
      title: '收益率',
      dataIndex: 'total_return',
      key: 'total_return',
      width: 100,
      align: 'right',
      render: (value: number | undefined) => {
        if (value === undefined || value === null) return 'N/A';
        const isPositive = value >= 0;
        return (
          <span style={{ color: isPositive ? '#52c41a' : '#ff4d4f' }}>
            {isPositive ? '+' : ''}{value.toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: '最大回撤',
      dataIndex: 'max_drawdown',
      key: 'max_drawdown',
      width: 100,
      align: 'right',
      render: (value: number | undefined) => {
        if (value === undefined || value === null) return 'N/A';
        return <span style={{ color: '#ff4d4f' }}>{value.toFixed(2)}%</span>;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      fixed: 'right',
      render: (_: any, record: BacktestTask) => (
        <Space size="small">
          <Tooltip title="查看详情">
            <Button
              type="text"
              size="small"
              icon={<LineChartOutlined />}
              onClick={() => handleViewDetail(record.id)}
            />
          </Tooltip>
          <Tooltip title="回放">
            <Button
              type="text"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => handleReplay(record.id)}
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
      dataSource={filteredBacktests}
      loading={backtestLoading}
      scroll={{ x: 'max-content' }}
      rowKey="id"
      pagination={backtestPagination}
      onChange={(newPagination) => {
        setBacktestPagination(newPagination);
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
    const currentPage = typeof backtestPagination === 'object' && backtestPagination ? (backtestPagination.current as number) || 1 : 1;
    const pageSize = typeof backtestPagination === 'object' && backtestPagination ? (backtestPagination.pageSize as number) || 10 : 10;
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = startIndex + pageSize;
    const currentPageData = filteredBacktests.slice(startIndex, endIndex);

    return (
      <>
        <Row gutter={[16, 16]}>
          {currentPageData.map((task) => (
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
                className={backtestSelectedRowKeys.includes(task.id) ? 'ring-2 ring-blue-500' : ''}
                onClick={() => setBacktestSelectedRowKeys([task.id])}
                onDoubleClick={() => handleViewDetail(task.id)}
                style={{ cursor: 'pointer' }}
              >
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">收益率</span>
                    <span
                      style={{
                        color:
                          task.total_return === undefined || task.total_return === null
                            ? 'inherit'
                            : task.total_return >= 0
                              ? '#52c41a'
                              : '#ff4d4f',
                        fontWeight: 'bold',
                      }}
                    >
                      {task.total_return === undefined || task.total_return === null
                        ? 'N/A'
                        : `${task.total_return >= 0 ? '+' : ''}${task.total_return.toFixed(2)}%`}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">最大回撤</span>
                    <span style={{ color: '#ff4d4f', fontWeight: 'bold' }}>
                      {task.max_drawdown === undefined || task.max_drawdown === null
                        ? 'N/A'
                        : `${task.max_drawdown.toFixed(2)}%`}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">创建时间</span>
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
                      查看
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
                      回放
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
            total={filteredBacktests.length}
            showSizeChanger
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            showTotal={(total) => `共 ${total} 条`}
            onChange={(page, size) => {
              setBacktestPagination({
                ...backtestPagination,
                current: page,
                pageSize: size,
              });
            }}
          />
        </Row>
      </>
    );
  };

  // 渲染回测工具栏 - 参考策略回测页面风格
  const renderBacktestToolbar = () => (
    <div style={{ marginBottom: 16 }}>
      {/* 第一行：搜索（左） + 视图切换（右） */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }} align="middle">
        <Col xs={16} sm={16} md={12} lg={10}>
          <Search
            placeholder="搜索策略名称或ID"
            value={backtestSearchText}
            onChange={(e) => setBacktestSearchText(e.target.value)}
            allowClear
            style={{ width: '100%' }}
          />
        </Col>
        <Col xs={8} sm={8} md={12} lg={14} style={{ textAlign: 'right' }}>
          <Segmented
            value={backtestViewType}
            onChange={(value) => setBacktestViewType(value as ViewType)}
            options={[
              { value: 'list', icon: <UnorderedListOutlined />, label: screens.sm ? '列表' : undefined },
              { value: 'card', icon: <AppstoreOutlined />, label: screens.sm ? '卡片' : undefined },
            ]}
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
                placeholder="选择策略"
                value={selectedStrategy || undefined}
                onChange={(value) => setSelectedStrategy(value)}
                style={{ width: '100%' }}
                allowClear
                options={strategies.map((s) => ({ value: s.name, label: s.name }))}
              />
            </Col>
            <Col xs={12} sm={8} md={8}>
              <Select
                placeholder="状态"
                value={backtestStatusFilter}
                onChange={setBacktestStatusFilter}
                style={{ width: '100%' }}
                options={[
                  { value: 'all', label: '全部状态' },
                  { value: 'completed', label: '已完成' },
                  { value: 'running', label: '运行中' },
                  { value: 'failed', label: '失败' },
                  { value: 'pending', label: '等待中' },
                ]}
              />
            </Col>
            <Col xs={12} sm={8} md={8}>
              <Select
                placeholder="排序"
                value={`${backtestSortField}-${backtestSortOrder}`}
                onChange={(value) => {
                  const [field, order] = value.split('-');
                  setBacktestSortField(field);
                  setBacktestSortOrder(order);
                }}
                style={{ width: '100%' }}
                options={[
                  { value: 'created_at-desc', label: '创建时间 ↓' },
                  { value: 'created_at-asc', label: '创建时间 ↑' },
                  { value: 'total_return-desc', label: '收益率 ↓' },
                  { value: 'total_return-asc', label: '收益率 ↑' },
                  { value: 'max_drawdown-desc', label: '最大回撤 ↓' },
                  { value: 'max_drawdown-asc', label: '最大回撤 ↑' },
                  { value: 'strategy_name-asc', label: '策略名称 A-Z' },
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
                onClick={handleResetBacktestFilters}
                style={{ width: '100%' }}
              >
                重置
              </Button>
            </Col>
            <Col xs={12}>
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={loadBacktests}
                loading={backtestLoading}
                style={{ width: '100%' }}
              >
                刷新
              </Button>
            </Col>
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
          策略列表
        </span>
      ),
      children: (
        <>
          {renderToolbar()}
          <Spin spinning={loading} tip={t('loading') || '加载中...'}>
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
          回测记录
          {selectedStrategy && <Tag color="blue" style={{ marginLeft: 8 }}>{selectedStrategy}</Tag>}
        </span>
      ),
      children: (
        <>
          {renderBacktestToolbar()}
          <Spin spinning={backtestLoading} tip="加载中...">
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
