/**
 * 数据管理页面组件
 * 功能：作为数据管理相关页面的入口
 */
import '../styles/DataManagement.css';

const DataManagement = () => {
  return (
    <div className="data-management-main">
      <div className="data-panel">
        <h2>数据管理</h2>
        <div className="data-section">
          <p>请从左侧菜单选择具体的数据管理功能</p>
        </div>
      </div>
    </div>
  );
};

export default DataManagement;