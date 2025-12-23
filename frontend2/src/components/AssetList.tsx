/**
 * 资产列表组件
 * 功能：展示资产列表数据
 * @param props 组件属性
 */
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

  return (
    <div className="asset-list-container">
      <h3>资产列表</h3>
      <div className="asset-list">
        {assets.map((asset) => (
          <div key={asset.id} className="asset-item">
            <div className="asset-info">
              <div className="asset-name">{asset.name}</div>
              <div className="asset-symbol">{asset.symbol}</div>
            </div>
            <div className="asset-price">${asset.price.toFixed(2)}</div>
            <div className={`asset-change ${asset.change >= 0 ? 'positive' : 'negative'}`}>
              {asset.change >= 0 ? '+' : ''}{asset.change.toFixed(2)} ({asset.changePercent.toFixed(2)}%)
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AssetList;
