/**
 * 数据管理页面组件
 * 功能：展示和管理加密货币与股票数据
 */
import { useState, useEffect } from 'react';
import { useDataManagementStore } from '../store';
import { dataApi } from '../api';
import AssetPoolManager from '../components/AssetPoolManager';
import '../styles/DataManagement.css';

const DataManagement = () => {
  // 从状态管理中获取数据和操作方法
  const {
    currentTab,
    cryptoData,
    stockData,
    tasks,
    isLoading,
    refreshCryptoData,
    refreshStockData,
    getTasks
  } = useDataManagementStore();

  // 当前选中的标签页
  const [selectedTab, setSelectedTab] = useState(currentTab);
  // 显示成功消息标志
  const [showSuccessMessage, setShowSuccessMessage] = useState(false);
  // 成功消息内容
  const [successMessage, setSuccessMessage] = useState('');
  // 导入进度
  const [importProgress, setImportProgress] = useState(0);
  // 导入日志
  const [importLog, setImportLog] = useState<string[]>([]);
  // K线数据
  const [klineData, setKlineData] = useState<any[]>([]);
  // K线数据加载状态
  const [isLoadingKline, setIsLoadingKline] = useState(false);
  // K线数据错误信息
  const [klineError, setKlineError] = useState<string | null>(null);
  // 当前K线配置
  const [klineConfig, setKlineConfig] = useState({
    symbol: 'BTCUSDT',
    interval: '15m',
    limit: 500
  });

  // 菜单项列表
  const menuItems = [
    { id: 'crypto', title: '加密货币', icon: 'icon-crypto' },
    { id: 'stock', title: '股票', icon: 'icon-stock' },
    { id: 'import', title: '数据导入', icon: 'icon-import' },
    { id: 'collection', title: 'crypto数据采集', icon: 'icon-collection' },
    { id: 'quality', title: '数据质量', icon: 'icon-quality' },
    { id: 'visualization', title: '数据可视化', icon: 'icon-visualization' },
    { id: 'asset-pools', title: '资产池管理', icon: 'icon-asset-pool' }
  ];

  // 组件挂载时获取任务列表
  useEffect(() => {
    getTasks();
  }, [getTasks]);

  /**
   * 格式化大数字
   * @param num 要格式化的数字
   * @returns 格式化后的字符串
   */
  const formatNumber = (num: number): string => {
    if (num >= 1000000000) {
      return (num / 1000000000).toFixed(2) + 'B';
    } else if (num >= 1000000) {
      return (num / 1000000).toFixed(2) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(2) + 'K';
    }
    return num.toString();
  };

  /**
   * 显示操作成功消息
   * @param message 要显示的消息内容
   */
  const showMessage = (message: string): void => {
    setSuccessMessage(message);
    setShowSuccessMessage(true);
    // 3秒后隐藏成功提示
    setTimeout(() => {
      setShowSuccessMessage(false);
    }, 3000);
  };

  /**
   * 开始导入数据
   */
  const startImport = (): void => {
    setImportProgress(0);
    setImportLog(['开始导入数据...']);
    
    // 模拟导入过程
    const interval = setInterval(() => {
      setImportProgress(prev => {
        const newProgress = prev + 10;
        if (newProgress <= 100) {
          setImportLog(prevLog => [...prevLog, `导入进度: ${newProgress}%`]);
        } else {
          clearInterval(interval);
          setImportLog(prevLog => [...prevLog, '数据导入完成！']);
          showMessage('数据导入成功');
        }
        return newProgress;
      });
    }, 500);
  };

  /**
   * 获取K线数据
   */
  const fetchKlineData = async (): Promise<void> => {
    setIsLoadingKline(true);
    setKlineError(null);
    
    try {
      const response = await dataApi.getKlines(klineConfig);
      setKlineData(response.data);
    } catch (error) {
      console.error('获取K线数据失败:', error);
      setKlineError('获取K线数据失败，请稍后重试');
      // 生成模拟数据作为fallback
      generateMockKlineData();
    } finally {
      setIsLoadingKline(false);
    }
  };

  /**
   * 生成模拟K线数据
   */
  const generateMockKlineData = (): void => {
    const mockData: any[] = [];
    let currentPrice = 50000;
    const now = Date.now();
    const intervalMs = 15 * 60 * 1000; // 15分钟
    
    for (let i = 500; i >= 0; i--) {
      const timestamp = now - i * intervalMs;
      const open = currentPrice;
      const change = (Math.random() - 0.5) * 2000;
      const close = open + change;
      const high = Math.max(open, close) + Math.random() * 500;
      const low = Math.min(open, close) - Math.random() * 500;
      const volume = Math.random() * 1000 + 500;
      
      mockData.push({
        timestamp,
        open: parseFloat(open.toFixed(2)),
        high: parseFloat(high.toFixed(2)),
        low: parseFloat(low.toFixed(2)),
        close: parseFloat(close.toFixed(2)),
        volume: parseFloat(volume.toFixed(2))
      });
      
      currentPrice = close;
    }
    
    setKlineData(mockData);
  };

  return (
    <div className="data-management-container">
      <header className="page-header">
        <h1>数据管理</h1>
      </header>

      <div className="data-management-content">
        {/* 侧边栏导航 */}
        <aside className="data-management-sidebar">
          <nav className="data-management-nav">
            <ul>
              {menuItems.map(menu => (
                <li 
                  key={menu.id}
                  className={selectedTab === menu.id ? 'active' : ''}
                  onClick={() => setSelectedTab(menu.id)}
                >
                  <i className={menu.icon}></i>
                  <span>{menu.title}</span>
                </li>
              ))}
            </ul>
          </nav>
        </aside>

        {/* 主内容区域 */}
        <main className="data-management-main">
          {/* 加密货币数据 */}
          {selectedTab === 'crypto' && (
            <div className="data-panel">
              <h2>加密货币数据</h2>
              <div className="data-section">
                <div className="data-actions">
                  <button className="btn btn-primary" onClick={refreshCryptoData}>刷新数据</button>
                  <button className="btn btn-secondary">导出数据</button>
                </div>
                
                <div className="data-table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>名称</th>
                        <th>符号</th>
                        <th>当前价格</th>
                        <th>24h变化</th>
                        <th>市值</th>
                        <th>交易量</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cryptoData.map(crypto => (
                        <tr key={crypto.id}>
                          <td>{crypto.name}</td>
                          <td>{crypto.symbol}</td>
                          <td>${crypto.currentPrice.toLocaleString()}</td>
                          <td className={crypto.priceChange24h > 0 ? 'price-up' : 'price-down'}>
                            {crypto.priceChange24h > 0 ? '+' : ''}{crypto.priceChange24h.toFixed(2)}%
                          </td>
                          <td>${formatNumber(crypto.marketCap)}</td>
                          <td>${formatNumber(crypto.tradingVolume)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* 股票数据 */}
          {selectedTab === 'stock' && (
            <div className="data-panel">
              <h2>股票数据</h2>
              <div className="data-section">
                <div className="data-actions">
                  <button className="btn btn-primary" onClick={refreshStockData}>刷新数据</button>
                  <button className="btn btn-secondary">导出数据</button>
                </div>
                
                <div className="data-table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>公司名称</th>
                        <th>股票代码</th>
                        <th>当前价格</th>
                        <th>今日变化</th>
                        <th>开盘价</th>
                        <th>最高价</th>
                        <th>最低价</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stockData.map(stock => (
                        <tr key={stock.symbol}>
                          <td>{stock.companyName}</td>
                          <td>{stock.symbol}</td>
                          <td>${stock.currentPrice.toFixed(2)}</td>
                          <td className={stock.priceChange > 0 ? 'price-up' : 'price-down'}>
                            {stock.priceChange > 0 ? '+' : ''}{stock.priceChange.toFixed(2)} ({stock.priceChangePercent.toFixed(2)}%)
                          </td>
                          <td>${stock.openPrice.toFixed(2)}</td>
                          <td>${stock.highPrice.toFixed(2)}</td>
                          <td>${stock.lowPrice.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* 数据导入 */}
          {selectedTab === 'import' && (
            <div className="data-panel">
              <h2>数据导入</h2>
              <div className="data-section">
                <div className="import-form">
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="dataType">数据类型</label>
                      <select id="dataType" className="form-control">
                        <option value="crypto">加密货币</option>
                        <option value="stock">股票</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label htmlFor="exchange">交易所</label>
                      <select id="exchange" className="form-control">
                        <option value="binance">Binance</option>
                        <option value="okx">OKX</option>
                      </select>
                    </div>
                  </div>
                  
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="startDate">开始日期</label>
                      <input type="date" id="startDate" className="form-control" />
                    </div>
                    <div className="form-group">
                      <label htmlFor="endDate">结束日期</label>
                      <input type="date" id="endDate" className="form-control" />
                    </div>
                  </div>
                  
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="interval">时间间隔</label>
                      <select id="interval" className="form-control">
                        <option value="1d">日线</option>
                        <option value="1h">小时线</option>
                        <option value="30m">30分钟线</option>
                        <option value="15m">15分钟线</option>
                        <option value="5m">5分钟线</option>
                        <option value="1m">1分钟线</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label htmlFor="symbols">交易对</label>
                      <input 
                        type="text" 
                        id="symbols" 
                        className="form-control" 
                        placeholder="如: BTCUSDT,ETHUSDT" 
                      />
                    </div>
                  </div>
                  
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="fileUpload">或上传文件</label>
                      <input type="file" id="fileUpload" className="form-control-file" multiple />
                    </div>
                  </div>
                  
                  <div className="data-actions">
                    <button className="btn btn-primary" onClick={startImport}>开始导入</button>
                    <button className="btn btn-secondary">重置</button>
                  </div>
                </div>
                
                {importProgress > 0 && (
                  <div className="import-progress">
                    <div className="progress-bar-container">
                      <div className="progress-bar" style={{ width: `${importProgress}%` }}></div>
                    </div>
                    <div className="progress-text">{importProgress}%</div>
                  </div>
                )}
                
                {importLog.length > 0 && (
                  <div className="import-log">
                    <h3>导入日志</h3>
                    <div className="log-content">
                      {importLog.map((log, index) => (
                        <div key={index} className="log-item">{log}</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 数据采集 */}
          {selectedTab === 'collection' && (
            <div className="data-panel">
              <h2>数据采集</h2>
              <div className="data-section">
                <h3>数据获取</h3>
                <div className="import-form">
                  {/* 第一行：品种和周期 */}
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="symbols">品种</label>
                      <select id="symbols" className="form-control" multiple>
                        <option value="BTCUSDT">BTCUSDT</option>
                        <option value="ETHUSDT">ETHUSDT</option>
                        <option value="BNBUSDT">BNBUSDT</option>
                        <option value="SOLUSDT">SOLUSDT</option>
                        <option value="ADAUSDT">ADAUSDT</option>
                      </select>
                    </div>
                    
                    <div className="form-group">
                      <label htmlFor="interval">周期</label>
                      <select id="interval" className="form-control" multiple>
                        <option value="1m">1分钟</option>
                        <option value="5m">5分钟</option>
                        <option value="15m">15分钟</option>
                        <option value="30m">30分钟</option>
                        <option value="1h">1小时</option>
                        <option value="4h">4小时</option>
                        <option value="1d">1天</option>
                      </select>
                    </div>
                  </div>
                  
                  {/* 第二行：开始时间和结束时间 */}
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="start">开始时间</label>
                      <input type="datetime-local" id="start" className="form-control" />
                    </div>
                    
                    <div className="form-group">
                      <label htmlFor="end">结束时间</label>
                      <input type="datetime-local" id="end" className="form-control" />
                    </div>
                  </div>
                  
                  {/* 操作按钮 */}
                  <div className="data-actions">
                    <button className="btn btn-primary">开始下载</button>
                    <button className="btn btn-secondary">刷新数据</button>
                  </div>
                </div>
              </div>
              
              {/* 任务管理 */}
              <div className="data-section">
                <h3>任务管理</h3>
                
                {/* 最近任务列表 */}
                <div className="recent-tasks-section">
                  <h4>最近任务</h4>
                  {isLoading ? (
                    <div className="loading-state">加载中...</div>
                  ) : tasks.length === 0 ? (
                    <div className="empty-state">暂无任务记录</div>
                  ) : (
                    <div className="recent-tasks-container">
                      {tasks.map(task => (
                        <div key={task.task_id} className="task-card">
                          <div className="task-header">
                            <div className="task-id-info">
                              <span className="label">任务ID:</span>
                              <span className="value">{task.task_id}</span>
                            </div>
                            <div className={`task-status-badge status-${task.status}`}>
                              {task.status === 'running' ? '运行中' : 
                               task.status === 'completed' ? '已完成' : 
                               task.status === 'failed' ? '失败' : '等待中'}
                            </div>
                          </div>
                          <div className="task-details">
                            <div className="task-params-info">
                              <div className="param-item">
                                <span className="label">品种:</span>
                                <span className="value">
                                  {Array.isArray(task.params?.symbols) ? task.params.symbols.join(', ') : task.params?.symbols || '未指定'}
                                </span>
                              </div>
                              <div className="param-item">
                                <span className="label">周期:</span>
                                <span className="value">{task.params?.interval || '未指定'}</span>
                              </div>
                              <div className="param-item">
                                <span className="label">来源:</span>
                                <span className="value">{task.params?.exchange || '未指定'}</span>
                              </div>
                            </div>
                            <div className="task-progress-info">
                              <span className="label">进度:</span>
                              <div className="progress-bar-container">
                                <div 
                                  className="progress-bar" 
                                  style={{ width: `${task.progress?.percentage || 0}%` }}
                                ></div>
                              </div>
                              <span className="progress-value">{task.progress?.percentage || 0}%</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 数据可视化 */}
          {selectedTab === 'visualization' && (
            <div className="data-panel">
              <h2>数据可视化</h2>
              
              {/* K线图表配置 */}
              <div className="data-section">
                <div className="import-form">
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="klineSymbol">交易对</label>
                      <select 
                        id="klineSymbol" 
                        className="form-control"
                        value={klineConfig.symbol}
                        onChange={(e) => setKlineConfig(prev => ({ ...prev, symbol: e.target.value }))}
                      >
                        <option value="BTCUSDT">BTCUSDT</option>
                        <option value="ETHUSDT">ETHUSDT</option>
                        <option value="BNBUSDT">BNBUSDT</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label htmlFor="klineInterval">时间周期</label>
                      <select 
                        id="klineInterval" 
                        className="form-control"
                        value={klineConfig.interval}
                        onChange={(e) => setKlineConfig(prev => ({ ...prev, interval: e.target.value }))}
                      >
                        <option value="1m">1分钟</option>
                        <option value="5m">5分钟</option>
                        <option value="15m">15分钟</option>
                        <option value="30m">30分钟</option>
                        <option value="1h">1小时</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label htmlFor="klineLimit">数据数量</label>
                      <input 
                        type="number" 
                        id="klineLimit" 
                        className="form-control"
                        value={klineConfig.limit}
                        min="100"
                        max="2000"
                        step="100"
                        onChange={(e) => setKlineConfig(prev => ({ ...prev, limit: parseInt(e.target.value) }))}
                      />
                    </div>
                    <div className="form-group">
                      <label>操作</label>
                      <div className="data-actions">
                        <button 
                          className="btn btn-primary"
                          onClick={fetchKlineData}
                          disabled={isLoadingKline}
                        >
                          {isLoadingKline ? '加载中...' : '获取数据'}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              {/* K线图表 */}
              <div className="data-section">
                <h3>K线图表</h3>
                {klineError && (
                  <div className="error-message">
                    {klineError}
                  </div>
                )}
                <div className="kline-chart-container">
                  {isLoadingKline ? (
                    <div className="loading-state">
                      加载中...
                    </div>
                  ) : (
                    <div className="kline-chart">
                      <div className="chart-header">
                        <div className="chart-title">
                          {klineConfig.symbol} {klineConfig.interval} K线图
                        </div>
                        <div className="chart-stats">
                          {klineData.length > 0 && (
                            <div>
                              <span className="stat-item">
                                <span className="label">最新价格: </span>
                                <span className="value">{klineData[klineData.length - 1].close.toLocaleString()}</span>
                              </span>
                              <span className="stat-item">
                                <span className="label">交易量: </span>
                                <span className="value">{klineData[klineData.length - 1].volume.toLocaleString()}</span>
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="chart-content">
                        {klineData.length > 0 ? (
                          <div className="kline-table-container">
                            <table className="kline-table">
                              <thead>
                                <tr>
                                  <th>时间</th>
                                  <th>开盘</th>
                                  <th>最高</th>
                                  <th>最低</th>
                                  <th>收盘</th>
                                  <th>成交量</th>
                                </tr>
                              </thead>
                              <tbody>
                                {klineData.slice(-50).map((kline) => (
                                  <tr key={kline.timestamp}>
                                    <td>{new Date(kline.timestamp).toLocaleString()}</td>
                                    <td>{kline.open}</td>
                                    <td>{kline.high}</td>
                                    <td>{kline.low}</td>
                                    <td className={kline.close >= kline.open ? 'price-up' : 'price-down'}>
                                      {kline.close}
                                    </td>
                                    <td>{kline.volume}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <div className="empty-state">
                            暂无数据，请点击"获取数据"按钮加载
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 资产池管理 */}
          {selectedTab === 'asset-pools' && (
            <div className="data-panel">
              <h2>资产池管理</h2>
              <div className="data-section">
                {/* 资产池管理组件 */}
                <AssetPoolManager />
              </div>
            </div>
          )}
        </main>
      </div>

      {/* 操作成功提示 */}
      {showSuccessMessage && (
        <div className="success-message">
          {successMessage}
        </div>
      )}
    </div>
  );
};

export default DataManagement;