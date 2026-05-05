import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Table,
  Row,
  Col,
  Statistic,
  Tag,
  Empty,
  Spin,
} from 'antd';

interface Position {
  id: number;
  symbol: string;
  side: 'long' | 'short';
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  pnl_percentage: number;
  margin_used: number;
  leverage: number;
  open_time: string;
}

interface WorkerPositionTabProps {
  workerId: number;
}

const WorkerPositionTab: React.FC<WorkerPositionTabProps> = ({ workerId }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [positions, setPositions] = useState<Position[]>([]);

  useEffect(() => {
    // TODO: 调用实际API获取持仓数据
    // 暂时使用模拟数据或显示空状态
    fetchPositionData();
  }, [workerId]);

  const fetchPositionData = async () => {
    setLoading(true);
    try {
      // TODO: 替换为实际的API调用
      // const data = await workerApi.getPosition(workerId);
      // setPositions(data);

      // 临时：显示空状态，等待后端API
      setPositions([]);
    } catch (error) {
      console.error('获取持仓数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 使用 any 类型避免复杂的 Table columns 类型推断问题
  const columns: any = [
    {
      title: t('symbol') || '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (symbol: string) => <Tag color="blue">{symbol}</Tag>,
    },
    {
      title: t('direction') || '方向',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: 'long' | 'short') => (
        <Tag color={side === 'long' ? 'green' : 'red'}>
          {side === 'long' ? (t('long') || '做多') : (t('short') || '做空')}
        </Tag>
      ),
    },
    {
      title: t('quantity') || '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
    },
    {
      title: t('entry_price') || '开仓价格',
      dataIndex: 'entry_price',
      key: 'entry_price',
      align: 'right',
      render: (price: number) => `$${price.toFixed(2)}`,
    },
    {
      title: t('current_price') || '当前价格',
      dataIndex: 'current_price',
      key: 'current_price',
      align: 'right',
      render: (price: number) => `$${price.toFixed(2)}`,
    },
    {
      title: t('unrealized_pnl') || '未实现盈亏',
      dataIndex: 'unrealized_pnl',
      key: 'unrealized_pnl',
      align: 'right',
      render: (pnl: number) => (
        <span style={{ fontWeight: 600, color: pnl >= 0 ? '#52c41a' : '#ff4d4f' }}>
          {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
        </span>
      ),
    },
    {
      title: t('pnl_percentage') || '盈亏%',
      dataIndex: 'pnl_percentage',
      key: 'pnl_percentage',
      align: 'right',
      width: 100,
      render: (pct: number) => (
        <span style={{ fontWeight: 600, color: pct >= 0 ? '#52c41a' : '#ff4d4f' }}>
          {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
        </span>
      ),
    },
    {
      title: t('leverage') || '杠杆',
      dataIndex: 'leverage',
      key: 'leverage',
      width: 70,
      align: 'center',
      render: (lev: number) => <Tag color="orange">{lev}x</Tag>,
    },
    {
      title: t('open_time') || '开仓时间',
      dataIndex: 'open_time',
      key: 'open_time',
      width: 160,
      render: (time: string) => new Date(time).toLocaleString(),
    },
  ];

  // 计算汇总数据
  const totalPositionValue = positions.reduce((sum, pos) => sum + (pos.quantity * pos.current_price), 0);
  const totalUnrealizedPnL = positions.reduce((sum, pos) => sum + pos.unrealized_pnl, 0);
  const totalMarginUsed = positions.reduce((sum, pos) => sum + pos.margin_used, 0);

  if (loading) {
    return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div>
      {/* 持仓汇总卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic
              title={t('total_position_value') || '总持仓价值'}
              value={totalPositionValue}
              precision={2}
              prefix="$"
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic
              title={t('unrealized_pnl') || '总未实现盈亏'}
              value={totalUnrealizedPnL}
              precision={2}
              prefix="$"
              valueStyle={{ color: totalUnrealizedPnL >= 0 ? '#52c41a' : '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic
              title={t('margin_used') || '保证金占用'}
              value={totalMarginUsed}
              precision={2}
              prefix="$"
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 持仓列表 */}
      <Card title={t('current_position') || '当前持仓'}>
        {positions.length === 0 ? (
          <Empty
            description={t('no_position_data') || '暂无持仓数据'}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Table
            columns={columns}
            dataSource={positions}
            rowKey="id"
            pagination={false}
            size="middle"
            scroll={{ x: 'max-content' }}
          />
        )}
      </Card>
    </div>
  );
};

export default WorkerPositionTab;
