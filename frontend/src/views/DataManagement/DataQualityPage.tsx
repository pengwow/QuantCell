/**
 * 数据质量页面组件
 */
import DataQuality from '../../components/DataQuality';

const DataQualityPage = () => {
  // 系统配置
  const systemConfig = {
    current_market_type: 'crypto',
    exchange: 'binance',
    crypto_trading_mode: 'spot'
  };

  return (
    <>
      <h2>数据质量</h2>
      <div className="data-section">
        <DataQuality systemConfig={systemConfig} />
      </div>
    </>
  );
};

export default DataQualityPage;