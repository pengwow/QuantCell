/**
 * 数据池卡片组件
 * 功能：展示单个数据池的信息
 * @param props 组件属性
 */
import { Card, Button } from 'antd';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons';

interface DataPoolCardProps {
  pool: {
    id: string;
    name: string;
    description: string;
    assetCount: number;
    createdAt: string;
  };
  onEdit?: (id: string) => void;
  onDelete?: (id: string) => void;
}

const DataPoolCard = (props: DataPoolCardProps) => {
  const { pool, onEdit, onDelete } = props;

  const handleEdit = () => {
    onEdit?.(pool.id);
  };

  const handleDelete = () => {
    onDelete?.(pool.id);
  };

  return (
    <Card
      title={pool.name}
      bordered
      size="small"
      actions={[
        <Button
          type="text"
          icon={<EditOutlined />}
          onClick={handleEdit}
          className="edit-button"
        >
          编辑
        </Button>,
        <Button
          type="text"
          danger
          icon={<DeleteOutlined />}
          onClick={handleDelete}
          className="delete-button"
        >
          删除
        </Button>,
      ]}
    >
      <div className="data-pool-content">
        <p className="data-pool-description">{pool.description}</p>
        <div className="data-pool-stats">
          <span className="stat-item">资产数量: {pool.assetCount}</span>
          <span className="stat-item">创建时间: {new Date(pool.createdAt).toLocaleString()}</span>
        </div>
      </div>
    </Card>
  );
};

export default DataPoolCard;