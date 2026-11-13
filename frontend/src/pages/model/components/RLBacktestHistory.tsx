import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, App, Button, Empty, Flex, Input, Select, Space, Table, Tag } from 'antd';
import type { TableProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { IconEye } from '@tabler/icons-react';
import { backtestApi } from '@/api';
import type { BacktestTask } from '@/types/backtest';
import { QUANT_COLORS } from '@/utils/colors';

const { Search } = Input;

// 状态选项与后端口径一致：'running' 由后端同时匹配 in_progress；
// label 复用 BacktestList 同款 status_* 词条
const STATUS_OPTIONS = [
  { value: 'completed', labelKey: 'status_completed' },
  { value: 'running', labelKey: 'status_running' },
  { value: 'failed', labelKey: 'status_failed' },
  { value: 'pending', labelKey: 'status_pending' },
];

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

const getStatusText = (status: string, t: (k: string) => string) => {
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

// RL 回测历史（模型中心只读 Tab）：服务端 source=rl 过滤 + 分页/搜索/排序，
// 点击「查看详情」跳回测详情页——与回测中心列表、临时 Drawer 汇合到同一详情
const RLBacktestHistory = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { message } = App.useApp();

  const [rows, setRows] = useState<BacktestTask[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string>();
  const [sort, setSort] = useState<{ by: string; order: 'asc' | 'desc' }>({
    by: 'created_at',
    order: 'desc',
  });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await backtestApi.getBacktestList({
        page,
        page_size: pageSize,
        keyword: keyword || undefined,
        status: status || undefined,
        sort_by: sort.by,
        sort_order: sort.order,
        source: 'rl',
      });
      setRows(resp.backtests ?? []);
      setTotal(resp.total ?? 0);
    } catch (error) {
      console.error('Failed to load RL backtest history:', error);
      message.error(
        t('backtest_list_load_failed', {
          message: error instanceof Error ? error.message : String(error),
        }),
      );
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, keyword, status, sort, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [keyword, status, sort]);

  const columns: TableProps<BacktestTask>['columns'] = [
    {
      // 与 BacktestList 同款来源 Tag 配色：RL 模型-紫 / RL 集成-蓝
      title: t('backtest_strategy_name'),
      dataIndex: 'strategy_name',
      key: 'strategy_name',
      width: 220,
      ellipsis: true,
      render: (name: string) => {
        if (name?.startsWith('rl_model:') || name?.startsWith('rl_ensemble:')) {
          const [prefix, ...rest] = name.split(':');
          return (
            <Space size={4}>
              <Tag color={prefix === 'rl_model' ? 'purple' : 'geekblue'} style={{ marginRight: 0 }}>
                {t(prefix === 'rl_model' ? 'backtest_source_rl_model' : 'backtest_source_rl_ensemble')}
              </Tag>
              <span>{rest.join(':')}</span>
            </Space>
          );
        }
        return name || '-';
      },
    },
    { title: t('symbols'), dataIndex: 'symbols', key: 'symbols', ellipsis: true },
    { title: t('timeframe'), dataIndex: 'timeframes', key: 'timeframes', width: 110, ellipsis: true },
    {
      title: t('status'),
      dataIndex: 'status',
      key: 'status',
      width: 90,
      align: 'center',
      render: (s: string) => <Tag color={getStatusColor(s)}>{getStatusText(s, t)}</Tag>,
    },
    {
      title: t('return_rate'),
      dataIndex: 'total_return',
      key: 'total_return',
      width: 100,
      align: 'right',
      sorter: true,
      render: (value: number | undefined) => {
        if (value === undefined || value === null) return 'N/A';
        const isPositive = value >= 0;
        return (
          <span style={{ color: isPositive ? QUANT_COLORS.positive : QUANT_COLORS.negative }}>
            {isPositive ? '+' : ''}
            {value.toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: t('max_drawdown'),
      dataIndex: 'max_drawdown',
      key: 'max_drawdown',
      width: 110,
      align: 'right',
      sorter: true,
      render: (value: number | undefined) => {
        if (value === undefined || value === null) return 'N/A';
        return <span style={{ color: QUANT_COLORS.negative }}>{value.toFixed(2)}%</span>;
      },
    },
    { title: t('create_time'), dataIndex: 'created_at', key: 'created_at', width: 170, ellipsis: true, sorter: true },
    {
      title: t('action'),
      key: 'action',
      width: 110,
      render: (_, record: BacktestTask) => (
        <Button
          type="link"
          size="small"
          icon={<IconEye size={16} />}
          onClick={() => navigate('/backtest/detail/' + record.id)}
        >
          {t('view')}
        </Button>
      ),
    },
  ];

  return (
    <Flex gap="middle" vertical>
      <Alert type="info" showIcon title={t('rl_history_hint')} />
      <Flex gap="small" wrap>
        <Search
          allowClear
          placeholder={t('search')}
          style={{ width: 240 }}
          onSearch={(v) => setKeyword(v.trim())}
        />
        <Select
          allowClear
          placeholder={t('status')}
          style={{ width: 140 }}
          options={STATUS_OPTIONS.map((s) => ({ value: s.value, label: t(s.labelKey) }))}
          onChange={(v) => setStatus(v)}
        />
      </Flex>
      <Table<BacktestTask>
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={rows}
        rowClassName={() => 'cursor-pointer'}
        onRow={(record) => ({
          onClick: () => navigate('/backtest/detail/' + record.id),
        })}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (n) => `${t('total_items', { total: n })}`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
        onChange={(_pagination, _filters, sorter) => {
          // 服务端排序：清空排序时回落创建时间倒序
          const s = Array.isArray(sorter) ? sorter[0] : sorter;
          if (s?.field && s?.order) {
            setSort({ by: String(s.field), order: s.order === 'ascend' ? 'asc' : 'desc' });
          } else {
            setSort({ by: 'created_at', order: 'desc' });
          }
        }}
        locale={{
          emptyText: (
            <Empty description={t('rl_history_empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ),
        }}
      />
    </Flex>
  );
};

export default RLBacktestHistory;
