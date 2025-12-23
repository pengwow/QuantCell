/**
 * 策略代理页面组件
 * 功能：策略代理功能的主页面
 */
import { useEffect } from 'react';
import { useStrategyStore } from '../store';
import '../styles/StrategyAgent.css';

const StrategyAgent = () => {
  // 从状态管理中获取数据和操作方法
  const {
    strategies,
    selectedStrategy,
    totalExecutions,
    successfulExecutions,
    failedExecutions,
    activeStrategies,
    showDetailModal,
    isLoading,
    loadStrategies,
    loadExecutionStats,
    viewStrategyDetail,
    closeDetailModal,
    editStrategy,
    toggleStrategyStatus,
    createNewStrategy,
    refreshData
  } = useStrategyStore();

  // 组件挂载时加载数据
  useEffect(() => {
    loadStrategies();
    loadExecutionStats();
  }, [loadStrategies, loadExecutionStats]);

  return (
    <div className="strategy-agent-container">
      <header className="page-header">
        <h1>策略代理</h1>
        <div className="header-actions">
          <button className="btn btn-primary" onClick={createNewStrategy}>新建策略</button>
          <button className="btn btn-secondary" onClick={refreshData}>刷新</button>
        </div>
      </header>

      <main className="main-content">
        {/* 策略列表 */}
        <div className="strategy-list">
          <h2>已配置的策略</h2>
          {isLoading ? (
            <div className="loading-state">加载中...</div>
          ) : (
            <div className="strategy-cards">
              {strategies.map(strategy => (
                <div 
                  key={strategy.id} 
                  className="strategy-card"
                  onClick={() => viewStrategyDetail(strategy.id)}
                >
                  <div className="card-header">
                    <h3>{strategy.name}</h3>
                    <span className={`status-badge status-${strategy.status}`}>
                      {strategy.statusText}
                    </span>
                  </div>
                  <div className="card-body">
                    <p className="description">{strategy.description}</p>
                    <div className="strategy-meta">
                      <span className="meta-item">
                        <i className="icon-calendar"></i>
                        {strategy.createdAt}
                      </span>
                      <span className="meta-item">
                        <i className="icon-author"></i>
                        {strategy.createdBy}
                      </span>
                    </div>
                  </div>
                  <div className="card-footer">
                    <button className="btn btn-sm btn-primary" onClick={(e) => { e.stopPropagation(); editStrategy(strategy.id); }}>
                      编辑
                    </button>
                    <button 
                      className={`btn btn-sm ${strategy.status === 'active' ? 'btn-danger' : 'btn-success'}`}
                      onClick={(e) => { e.stopPropagation(); toggleStrategyStatus(strategy.id); }}
                    >
                      {strategy.status === 'active' ? '禁用' : '启用'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 策略执行统计 */}
        <div className="execution-stats">
          <h2>执行统计</h2>
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-number">{totalExecutions}</div>
              <div className="stat-label">总执行次数</div>
            </div>
            <div className="stat-card">
              <div className="stat-number">{successfulExecutions}</div>
              <div className="stat-label">成功执行</div>
            </div>
            <div className="stat-card">
              <div className="stat-number">{failedExecutions}</div>
              <div className="stat-label">失败执行</div>
            </div>
            <div className="stat-card">
              <div className="stat-number">{activeStrategies}</div>
              <div className="stat-label">活跃策略数</div>
            </div>
          </div>
        </div>
      </main>

      {/* 策略详情模态框 */}
      {showDetailModal && (
        <div className="modal-overlay" onClick={closeDetailModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>策略详情</h3>
              <button className="close-btn" onClick={closeDetailModal}>&times;</button>
            </div>
            <div className="modal-body">
              {selectedStrategy && (
                <div className="strategy-detail">
                  <h4>{selectedStrategy.name}</h4>
                  <p className="detail-description">{selectedStrategy.description}</p>
                  <div className="detail-info">
                    <p><strong>状态：</strong><span className={`status-${selectedStrategy.status}`}>{selectedStrategy.statusText}</span></p>
                    <p><strong>创建时间：</strong>{selectedStrategy.createdAt}</p>
                    <p><strong>创建人：</strong>{selectedStrategy.createdBy}</p>
                    <p><strong>最近更新：</strong>{selectedStrategy.updatedAt}</p>
                    <p><strong>执行频率：</strong>{selectedStrategy.executionFrequency}</p>
                    <p><strong>规则数量：</strong>{selectedStrategy.ruleCount}</p>
                  </div>
                  <div className="execution-history">
                    <h5>最近执行记录</h5>
                    {selectedStrategy.executionHistory.length > 0 ? (
                      <ul>
                        {selectedStrategy.executionHistory.map((record, index) => (
                          <li key={index}>
                            {record.timestamp} - {record.status === 'success' ? '成功' : '失败'}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>暂无执行记录</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StrategyAgent;
