/**
 * 资产池卡片组件
 * 功能：展示单个资产池的信息
 * @param props 组件属性
 */
interface AssetPoolCardProps {
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

const AssetPoolCard = (props: AssetPoolCardProps) => {
  const { pool, onEdit, onDelete } = props;

  const handleEdit = () => {
    onEdit?.(pool.id);
  };

  const handleDelete = () => {
    onDelete?.(pool.id);
  };

  return (
    <div className="asset-pool-card">
      <div className="asset-pool-header">
        <h4>{pool.name}</h4>
        <div className="asset-pool-actions">
          <button className="action-button edit" onClick={handleEdit}>
            编辑
          </button>
          <button className="action-button delete" onClick={handleDelete}>
            删除
          </button>
        </div>
      </div>
      <div className="asset-pool-content">
        <p className="asset-pool-description">{pool.description}</p>
        <div className="asset-pool-stats">
          <span className="stat-item">资产数量: {pool.assetCount}</span>
          <span className="stat-item">创建时间: {new Date(pool.createdAt).toLocaleString()}</span>
        </div>
      </div>
    </div>
  );
};

export default AssetPoolCard;
