import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Table, Button, Tag, Space, Popconfirm, message } from 'antd';
import type { TableProps } from 'antd';
import { backtestApi } from '../../api';
import { useTranslation } from 'react-i18next';
import { IconPlayerPlay, IconEye, IconTrash } from '@tabler/icons-react';
import { setPageTitle } from '@/router';
import type { BacktestTask } from '../../types/backtest';
import PageContainer from '@/components/PageContainer';

const BacktestList = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // 回测任务数据
  const [backtestTasks, setBacktestTasks] = useState<BacktestTask[]>([]);
  // 加载状态
  const [loading, setLoading] = useState<boolean>(false);
  // 选中的行keys
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

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

  // 表格列定义
  const columns: TableProps<BacktestTask>['columns'] = [
    {
      title: '策略名称',
      dataIndex: 'strategy_name',
      key: 'strategy_name',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={getStatusColor(status)}>{getStatusText(status)}</Tag>
      ),
    },
    {
      title: '收益率',
      dataIndex: 'total_return',
      key: 'total_return',
      width: 120,
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
      width: 120,
      render: (value: number | undefined) => {
        if (value === undefined || value === null) return 'N/A';
        return <span style={{ color: '#ff4d4f' }}>{value.toFixed(2)}%</span>;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
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

  // 键盘导航处理
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 只有在有选中行时才处理键盘事件
      if (selectedRowKeys.length === 0) return;

      const currentIndex = dataSource.findIndex(
        (item) => item.id === selectedRowKeys[0]
      );
      if (currentIndex === -1) return;

      switch (e.key) {
        case 'ArrowUp':
          e.preventDefault();
          if (currentIndex > 0) {
            const prevId = dataSource[currentIndex - 1].id;
            setSelectedRowKeys([prevId]);
          }
          break;
        case 'ArrowDown':
          e.preventDefault();
          if (currentIndex < dataSource.length - 1) {
            const nextId = dataSource[currentIndex + 1].id;
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
  }, [selectedRowKeys, dataSource]);

  return (
    <PageContainer title={t('strategy_backtest')}>
      <div className="space-y-6">
        {/* 页面操作按钮 */}
        <div className="flex justify-end">
          <Button
            type="primary"
            icon={<IconPlayerPlay size={16} />}
            onClick={handleStartBacktest}
          >
            {t('start_backtest') || '开始回测'}
          </Button>
        </div>

        {/* 回测任务列表 */}
        <Card>
          <Table
            columns={columns}
            dataSource={dataSource}
            rowSelection={rowSelection}
            pagination={pagination}
            loading={loading}
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
        </Card>
      </div>
    </PageContainer>
  );
};

export default BacktestList;
