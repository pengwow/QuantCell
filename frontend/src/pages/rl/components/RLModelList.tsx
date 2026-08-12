import { Card, Table, Button, Space, Tag, Typography, Empty } from 'antd';
import { CodeOutlined, RestOutlined, BarChartOutlined } from '@ant-design/icons';

const { Text } = Typography;

export interface RLModel {
  name: string;
  path: string;
  size_kb: number;
}

interface RLModelListProps {
  models: RLModel[];
  selectedModel: string;
  onSelectModel: (path: string) => void;
  onDeleteModel: (name: string) => void;
  onRefresh: () => void;
  onBacktest: () => void;
  backtesting: boolean;
  training: boolean;
}

export default function RLModelList({
  models,
  selectedModel,
  onSelectModel,
  onDeleteModel,
  onRefresh,
  onBacktest,
  backtesting,
  training,
}: RLModelListProps) {
  return (
    <Card
      title={
        <Space>
          <CodeOutlined />
          已训练模型
          <Button type="text" icon={<RestOutlined />} onClick={onRefresh} />
        </Space>
      }
    >
      {models.length === 0 ? (
        <Empty description="暂无训练模型" />
      ) : (
        <Table
          dataSource={models}
          columns={[
            {
              title: '模型名称',
              dataIndex: 'name',
              key: 'name',
              render: (text: string) => (
                <Space>
                  <Tag>{text.split('_')[0]}</Tag>
                  <Tag color="blue">{text.split('_')[1] || 'unknown'}</Tag>
                  <Text>{text.split('_').slice(2).join('_')}</Text>
                </Space>
              ),
            },
            {
              title: '大小',
              dataIndex: 'size_kb',
              key: 'size_kb',
              render: (size: number) => `${size} KB`,
            },
            {
              title: '操作',
              key: 'action',
              render: (_, record: RLModel) => (
                <Space>
                  <Button
                    type="text"
                    onClick={() => onSelectModel(record.path)}
                    disabled={selectedModel === record.path}
                  >
                    {selectedModel === record.path ? '已选中' : '选择回测'}
                  </Button>
                  <Button
                    type="text"
                    danger
                    onClick={() => onDeleteModel(record.name)}
                  >
                    删除
                  </Button>
                </Space>
              ),
            },
          ]}
          pagination={false}
          size="small"
          rowSelection={{
            selectedRowKeys: [selectedModel],
            onChange: (keys) => onSelectModel(keys[0] as string),
            getCheckboxProps: (record) => ({
              value: record.path,
            }),
          }}
        />
      )}

      {selectedModel && (
        <div style={{ marginTop: 16 }}>
          <Button
            type="primary"
            icon={<BarChartOutlined />}
            loading={backtesting}
            onClick={onBacktest}
            disabled={training}
          >
            {backtesting ? '回测中...' : '回测选中模型'}
          </Button>
        </div>
      )}
    </Card>
  );
}
