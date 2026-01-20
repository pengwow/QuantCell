/**
 * 数据池管理页面组件
 */
import DataPoolManager from '../../components/DataPoolManager';

const DataPoolPage = () => {
  return (
    <div className="data-management-main">
      <div className="data-panel">
        <div className="data-section">
          <DataPoolManager />
        </div>
      </div>
    </div>
  );
};

export default DataPoolPage;