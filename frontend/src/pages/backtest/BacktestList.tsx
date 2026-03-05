import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Table, Button, Tag, Space, Popconfirm, message, Segmented, Row, Col, Pagination, Input, Select, DatePicker, Grid } from 'antd';
import type { TableProps } from 'antd';
import { AppstoreOutlined, UnorderedListOutlined, ReloadOutlined, FilterOutlined } from '@ant-design/icons';
import { backtestApi } from '../../api';
import { useTranslation } from 'react-i18next';
import { IconPlayerPlay, IconEye, IconTrash } from '@tabler/icons-react';
import { setPageTitle } from '@/router';
import type { BacktestTask } from '../../types/backtest';
import PageContainer from '@/components/PageContainer';
import dayjs from 'dayjs';

const { useBreakpoint } = Grid;

const { Search } = Input;
const { RangePicker } = DatePicker;

// 视图类型
type ViewType = 'list' | 'card';

// 筛选状态类型
type FilterStatus = 'all' | 'completed' | 'running' | 'failed' | 'pending';

// 排序字段
type SortField = 'created_at' | 'total_return' | 'max_drawdown' | 'strategy_name';
type SortOrder = 'asc' | 'desc';

const BacktestList = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // 回测任务数据
  const [backtestTasks, setBacktestTasks] = useState<BacktestTask[]>([]);
  // 加载状态
  const [loading, setLoading] = useState<boolean>(false);
  // 选中的行keys
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  // 视图类型状态
  const [viewType, setViewType] = useState<ViewType>(() => {
    // 从 localStorage 读取保存的视图偏好
    const savedView = localStorage.getItem('backtestListViewType');
    return (savedView as ViewType) || 'list';
  });

  // 筛选状态
  const [searchText, setSearchText] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<FilterStatus>('all');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  // 响应式断点
  const screens = useBreakpoint();

  // 分页配置
  const [pagination, setPagination] = useState<TableProps<BacktestTask>['pagination']>({
    current: 1,
    pageSize: 10,
    showSizeChanger: true,
    pageSizeOptions: ['10', '20', '50', '100'],
    showTotal: (total) => `${t('total') || '共'}: ${total}`,
  });

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('strategy_backtest') || '策略回测');
  }, [t]);

  // 加载回测任务列表
  const loadBacktestList = useCallback(async () => {
    setLoading(true);
    try {
      const response = await backtestApi.getBacktestList();
      if (response.backtests && Array.isArray(response.backtests)) {
        setBacktestTasks(response.backtests);
      }
    } catch (error) {
      console.error('加载回测任务列表失败:', error);
      message.error('加载回测任务列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // 组件挂载时加载数据
  useEffect(() => {
    loadBacktestList();
  }, [loadBacktestList]);

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

  // 删除回测任务
  const handleDelete = async (taskId: string) => {
    try {
      await backtestApi.deleteBacktest(taskId);
      message.success('删除成功');
      // 重新加载列表
      loadBacktestList();
      // 清除选中状态
      setSelectedRowKeys((prev) => prev.filter((key) => key !== taskId));
    } catch (error) {
      console.error('删除回测任务失败:', error);
      message.error('删除失败');
    }
  };

  // 查看回测详情
  const handleViewDetail = (backtestId: string) => {
    navigate('/backtest/detail/' + backtestId);
  };

  // 跳转到回测配置页面
  const handleStartBacktest = () => {
    navigate('/backtest/config');
  };

  // 处理视图切换
  const handleViewTypeChange = (value: ViewType) => {
    setViewType(value);
    localStorage.setItem('backtestListViewType', value);
  };

  // 表格列定义
  const columns: TableProps<BacktestTask>['columns'] = [
    {
      title: '策略名称',
      dataIndex: 'strategy_name',
      key: 'strategy_name',
      width: 200,
      minWidth: 120,
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
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'right',
      render: (_: any, record: BacktestTask) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<IconEye size={16} />}
            onClick={() => handleViewDetail(record.id)}
          >
            查看
          </Button>
          <Popconfirm
            title="确认删除"
            description="确定要删除这个回测任务吗？此操作不可恢复。"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<IconTrash size={16} />}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // 行选择配置
  const rowSelection: TableProps<BacktestTask>['rowSelection'] = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    },
  };

  // 表格数据（带key）
  const dataSource = backtestTasks.map((task) => ({
    ...task,
    key: task.id,
  }));

  // 过滤和排序后的数据
  const filteredDataSource = useMemo(() => {
    let result = [...dataSource];

    // 搜索过滤
    if (searchText) {
      const lowerSearch = searchText.toLowerCase();
      result = result.filter(
        (task) =>
          task.strategy_name?.toLowerCase().includes(lowerSearch) ||
          task.id?.toLowerCase().includes(lowerSearch)
      );
    }

    // 状态过滤
    if (statusFilter !== 'all') {
      result = result.filter((task) => {
        if (statusFilter === 'running') {
          return task.status === 'running' || task.status === 'in_progress';
        }
        return task.status === statusFilter;
      });
    }

    // 日期范围过滤
    if (dateRange && dateRange[0] && dateRange[1]) {
      const startDate = dateRange[0].startOf('day').valueOf();
      const endDate = dateRange[1].endOf('day').valueOf();
      result = result.filter((task) => {
        if (!task.created_at) return false;
        const taskDate = dayjs(task.created_at).valueOf();
        return taskDate >= startDate && taskDate <= endDate;
      });
    }

    // 排序
    result.sort((a, b) => {
      let aVal: number | string = '';
      let bVal: number | string = '';

      switch (sortField) {
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
        return sortOrder === 'asc'
          ? aVal.localeCompare(bVal as string)
          : (bVal as string).localeCompare(aVal);
      }
      return sortOrder === 'asc' ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
    });

    return result;
  }, [dataSource, searchText, statusFilter, dateRange, sortField, sortOrder]);

  // 重置筛选
  const handleResetFilters = () => {
    setSearchText('');
    setStatusFilter('all');
    setDateRange(null);
    setSortField('created_at');
    setSortOrder('desc');
    setPagination({
      ...pagination,
      current: 1,
    });
  };

  // 渲染列表视图
  const renderListView = () => (
    <Table
      columns={columns}
      dataSource={filteredDataSource}
      rowSelection={rowSelection}
      pagination={pagination}
      loading={loading}
      scroll={{ x: 'max-content' }}
      onChange={(newPagination) => {
        setPagination(newPagination);
      }}
      onRow={(record) => ({
        onClick: () => {
          setSelectedRowKeys([record.id]);
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

  // 渲染卡片视图
  const renderCardView = () => {
    // 获取当前页数据
    const currentPage = typeof pagination === 'object' && pagination ? (pagination.current as number) || 1 : 1;
    const pageSize = typeof pagination === 'object' && pagination ? (pagination.pageSize as number) || 10 : 10;
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = startIndex + pageSize;
    const currentPageData = filteredDataSource.slice(startIndex, endIndex);

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
                className={selectedRowKeys.includes(task.id) ? 'ring-2 ring-blue-500' : ''}
                onClick={() => setSelectedRowKeys([task.id])}
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
                    <span className="text-sm text-gray-600">{task.created_at}</span>
                  </div>
                  <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
                    <Button
                      type="link"
                      size="small"
                      icon={<IconEye size={14} />}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleViewDetail(task.id);
                      }}
                    >
                      查看
                    </Button>
                    <Popconfirm
                      title="确认删除"
                      description="确定要删除这个回测任务吗？此操作不可恢复。"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        handleDelete(task.id);
                      }}
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                    >
                      <Button
                        type="link"
                        size="small"
                        danger
                        icon={<IconTrash size={14} />}
                        onClick={(e) => e.stopPropagation()}
                      >
                        删除
                      </Button>
                    </Popconfirm>
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
            total={filteredDataSource.length}
            showSizeChanger
            pageSizeOptions={['10', '20', '50', '100']}
            showTotal={(total) => `${t('total') || '共'}: ${total}`}
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

  // 键盘导航处理
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 只有在有选中行时才处理键盘事件
      if (selectedRowKeys.length === 0) return;

      const currentIndex = filteredDataSource.findIndex(
        (item) => item.id === selectedRowKeys[0]
      );
      if (currentIndex === -1) return;

      switch (e.key) {
        case 'ArrowUp':
          e.preventDefault();
          if (currentIndex > 0) {
            const prevId = filteredDataSource[currentIndex - 1].id;
            setSelectedRowKeys([prevId]);
          }
          break;
        case 'ArrowDown':
          e.preventDefault();
          if (currentIndex < filteredDataSource.length - 1) {
            const nextId = filteredDataSource[currentIndex + 1].id;
            setSelectedRowKeys([nextId]);
          }
          break;
        case 'Enter':
          e.preventDefault();
          handleViewDetail(selectedRowKeys[0] as string);
          break;
        case 'Delete':
          e.preventDefault();
          // 显示确认弹窗
          if (selectedRowKeys.length > 0) {
            const taskId = selectedRowKeys[0] as string;
            // 使用Modal.confirm或直接调用删除
            handleDelete(taskId);
          }
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [selectedRowKeys, filteredDataSource]);

  // 渲染工具栏 - 优化小屏幕布局
  const renderToolbar = () => (
    <div style={{ marginBottom: 16 }}>
      {/* 第一行：搜索（左） + 视图切换（右） */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }} align="middle">
        <Col xs={16} sm={16} md={12} lg={10}>
          <Search
            placeholder="搜索策略名称或ID"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ width: '100%' }}
          />
        </Col>
        <Col xs={8} sm={8} md={12} lg={14} style={{ textAlign: 'right' }}>
          <Segmented
            value={viewType}
            onChange={(value) => handleViewTypeChange(value as ViewType)}
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
            <Col xs={8} sm={8} md={8}>
              <Select
                placeholder="状态"
                value={statusFilter}
                onChange={setStatusFilter}
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
            <Col xs={8} sm={8} md={8}>
              <RangePicker
                placeholder={['开始', '结束']}
                value={dateRange}
                onChange={setDateRange}
                style={{ width: '100%' }}
              />
            </Col>
            <Col xs={8} sm={8} md={8}>
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
                  { value: 'created_at-desc', label: '创建时间 ↓' },
                  { value: 'created_at-asc', label: '创建时间 ↑' },
                  { value: 'total_return-desc', label: '收益率 ↓' },
                  { value: 'total_return-asc', label: '收益率 ↑' },
                  { value: 'max_drawdown-desc', label: '最大回撤 ↓' },
                  { value: 'max_drawdown-asc', label: '最大回撤 ↑' },
                  { value: 'strategy_name-asc', label: '策略名称 A-Z' },
                  { value: 'strategy_name-desc', label: '策略名称 Z-A' },
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
                icon={<IconPlayerPlay size={16} />}
                onClick={handleStartBacktest}
                style={{ width: '100%' }}
              >
                开始回测
              </Button>
            </Col>
          </Row>
        </Col>
      </Row>

      {/* 筛选标签 */}
      {(searchText || statusFilter !== 'all' || (dateRange && dateRange[0] && dateRange[1])) && (
        <div style={{ marginTop: 12 }}>
          <Space>
            <FilterOutlined style={{ color: '#8c8c8c' }} />
            {searchText && <Tag closable onClose={() => setSearchText('')}>搜索: {searchText}</Tag>}
            {statusFilter !== 'all' && <Tag closable onClose={() => setStatusFilter('all')}>状态: {getStatusText(statusFilter)}</Tag>}
            {dateRange && dateRange[0] && dateRange[1] && (
              <Tag closable onClose={() => setDateRange(null)}>
                日期: {dateRange[0].format('MM-DD')} ~ {dateRange[1].format('MM-DD')}
              </Tag>
            )}
          </Space>
        </div>
      )}
    </div>
  );

  return (
    <PageContainer title={t('strategy_backtest')}>
      <Card>
        {renderToolbar()}
        {viewType === 'list' ? renderListView() : renderCardView()}
      </Card>
    </PageContainer>
  );
};

export default BacktestList;
