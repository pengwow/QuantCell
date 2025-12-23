/**
 * 资产池管理组件
 * 功能：管理资产池的组件，包括列表展示、创建、编辑和删除功能
 */
import { useState } from 'react';
import AssetPoolCard from './AssetPoolCard';
import AssetPoolForm from './AssetPoolForm';

interface AssetPool {
  id: string;
  name: string;
  description: string;
  assetCount: number;
  createdAt: string;
}

const AssetPoolManager = () => {
  // 资产池列表数据
  const [assetPools, setAssetPools] = useState<AssetPool[]>([]);
  // 编辑模式状态
  const [isEditing, setIsEditing] = useState(false);
  // 当前编辑的资产池数据
  const [currentPool, setCurrentPool] = useState<AssetPool | null>(null);
  // 创建模式状态
  const [isCreating, setIsCreating] = useState(false);

  /**
   * 处理创建资产池
   * @param data 资产池数据
   */
  const handleCreatePool = (data: {
    name: string;
    description: string;
  }) => {
    const newPool: AssetPool = {
      id: Date.now().toString(),
      name: data.name,
      description: data.description,
      assetCount: 0,
      createdAt: new Date().toISOString()
    };
    setAssetPools(prev => [...prev, newPool]);
    setIsCreating(false);
  };

  /**
   * 处理编辑资产池
   * @param data 资产池数据
   */
  const handleEditPool = (data: {
    id?: string;
    name: string;
    description: string;
  }) => {
    if (!data.id) return;
    setAssetPools(prev => prev.map(pool => 
      pool.id === data.id 
        ? { ...pool, name: data.name, description: data.description } 
        : pool
    ));
    setIsEditing(false);
    setCurrentPool(null);
  };

  /**
   * 处理删除资产池
   * @param id 资产池ID
   */
  const handleDeletePool = (id: string) => {
    if (window.confirm('确定要删除这个资产池吗？')) {
      setAssetPools(prev => prev.filter(pool => pool.id !== id));
    }
  };

  /**
   * 开始编辑资产池
   * @param pool 资产池数据
   */
  const startEditPool = (pool: AssetPool) => {
    setCurrentPool(pool);
    setIsEditing(true);
  };

  return (
    <div className="asset-pool-manager">
      <div className="asset-pool-header">
        <h2>资产池管理</h2>
        <button 
          className="create-pool-button" 
          onClick={() => setIsCreating(true)}
        >
          创建资产池
        </button>
      </div>

      {/* 创建/编辑表单 */}
      {(isCreating || isEditing) && (
        <AssetPoolForm
          initialData={isEditing && currentPool ? currentPool : { name: '', description: '' }}
          onSubmit={isEditing ? handleEditPool : handleCreatePool}
          onCancel={() => {
            setIsCreating(false);
            setIsEditing(false);
            setCurrentPool(null);
          }}
        />
      )}

      {/* 资产池列表 */}
      <div className="asset-pool-list">
        {assetPools.length === 0 ? (
          <div className="empty-state">
            <p>暂无资产池，请点击"创建资产池"按钮添加</p>
          </div>
        ) : (
          assetPools.map(pool => (
            <AssetPoolCard
              key={pool.id}
              pool={pool}
              onEdit={() => startEditPool(pool)}
              onDelete={handleDeletePool}
            />
          ))
        )}
      </div>
    </div>
  );
};

export default AssetPoolManager;
