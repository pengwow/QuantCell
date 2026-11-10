import { useState } from 'react';
import { Card, Table, Button, Space, Tag, Typography } from 'antd';
import type { TableProps } from 'antd';
import { CodeOutlined, RestOutlined, BarChartOutlined } from '@ant-design/icons';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';
import { PAGE_SIZE_OPTIONS } from '@/constants/pagination';
import dayjs from 'dayjs';

const { Text } = Typography;

export interface RLModel {
  name: string;
  path: string;
  size_mb: number;
  created: number; // 秒级 unix 时间戳（后端 st_ctime）
}

interface RLModelListProps {
  models: RLModel[];
  loading?: boolean;
  selectedModel: string;
  onSelectModel: (path: string) => void;
  onDeleteModel: (name: string) => void;
  onRefresh: () => void;
  onBacktest: () => void;
  backtesting: boolean;
  training: boolean;
}

// 命名格式为 {tag}_{timesteps}_{algo}_{unix_ts}.zip，从名称中提取算法缩写（ppo/sac/a2c/dqn）打标签
const ALGO_SET = new Set(['ppo', 'sac', 'a2c', 'dqn']);
const parseAlgo = (name: string) => name.split('_').find((p) => ALGO_SET.has(p.toLowerCase()));

export default function RLModelList({
  models,
  loading = false,
  selectedModel,
  onSelectModel,
  onDeleteModel,
  onRefresh,
  onBacktest,
  backtesting,
  training,
}: RLModelListProps) {
  // 分页 pageSize 走全局配置（条数切换器即全站开关，与回测列表等页面一致）
  const [pageSize, setPageSize] = useGlobalPageSize();
  const [current, setCurrent] = useState(1);

  const columns: TableProps<RLModel>['columns'] = [
    {
      title: '模型名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (text: string) => {
        const algo = parseAlgo(text);
        return (
          <Space size="small">
            {algo && <Tag color="blue">{algo.toUpperCase()}</Tag>}
            {/* 名称可能很长（tag_步数_算法_时间戳），截断保证表格不撑开 */}
            <Text style={{ maxWidth: 240 }} ellipsis={{ tooltip: text }}>
              {text}
            </Text>
          </Space>
        );
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created',
      key: 'created',
      width: 170,
      render: (ts: number) => (ts ? dayjs(ts * 1000).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '大小',
      dataIndex: 'size_mb',
      key: 'size_mb',
      width: 90,
      align: 'right',
      render: (size: number) => `${size} MB`,
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_, record: RLModel) => (
        <Button type="link" size="small" danger onClick={() => onDeleteModel(record.name)}>
          删除
        </Button>
      ),
    },
  ];

  return (
    <Card
      title={
        <Space size="small">
          <CodeOutlined />
          已训练模型
        </Space>
      }
      extra={
        <Button type="text" icon={<RestOutlined />} onClick={onRefresh} title="刷新列表" />
      }
    >
      <Table
        rowKey="name"
        dataSource={models}
        columns={columns}
        loading={loading}
        size="small"
        scroll={{ x: 'max-content' }}
        rowSelection={{
          selectedRowKeys: selectedModel ? [selectedModel] : [],
          onChange: (keys) => onSelectModel(keys[0] as string),
        }}
        onRow={(record) => ({
          onClick: () => onSelectModel(record.name),
          style: { cursor: 'pointer' },
        })}
        pagination={{
          current,
          pageSize,
          showSizeChanger: true,
          pageSizeOptions: PAGE_SIZE_OPTIONS,
          showTotal: (total) => `共 ${total} 个模型`,
          onChange: (page, size) => {
            // 条数变化写回全局配置，全站生效（与回测列表一致）
            if (size !== pageSize) setPageSize(size);
            setCurrent(page);
          },
        }}
      />

      {selectedModel && (
        <Button
          type="primary"
          icon={<BarChartOutlined />}
          loading={backtesting}
          onClick={onBacktest}
          disabled={training}
          block
          style={{ marginTop: 16 }}
        >
          {backtesting ? '回测中...' : `回测选中模型：${selectedModel}`}
        </Button>
      )}
    </Card>
  );
}
