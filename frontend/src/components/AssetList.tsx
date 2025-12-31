/**
 * 资产列表组件
 * 功能：展示资产列表数据
 * @param props 组件属性
 */
import { Table } from 'antd';

interface AssetListProps {
  assets?: Array<{
    id: string;
    name: string;
    symbol: string;
    price: number;
    change: number;
    changePercent: number;
  }>;
}

const AssetList = (props: AssetListProps) => {
  const { assets = [] } = props;

  const columns = [
    {
      title: '资产名称',
      dataIndex: 'name',
      key: 'name',
      width: 150,
    },
    {
      title: '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 100,
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      width: 120,
      render: (price: number) => `$${price.toFixed(2)}`,
    },
    {
      title: '涨跌幅',
      dataIndex: 'change',
      key: 'change',
      width: 150,
      render: (change: number, record: any) => {
        const color = change >= 0 ? '#52c41a' : '#ff4d4f';
        return (
          <span style={{ color }}>
            {change >= 0 ? '+' : ''}{change.toFixed(2)} ({record.changePercent.toFixed(2)}%)
          </span>
        );
      },
    },
  ];

  return (
    <div className="asset-list-container">
      <h3>资产列表</h3>
      <Table
        columns={columns}
        dataSource={assets}
        rowKey="id"
        pagination={false}
        bordered
        size="middle"
      />
    </div>
  );
};

export default AssetList;
