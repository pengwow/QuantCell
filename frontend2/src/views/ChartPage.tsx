/**
 * 图表页面组件
 * 功能：展示K线图表，支持多种指标和筛选条件
 */
import { useState, useEffect, useRef } from 'react';
import { init, dispose } from 'klinecharts';
import '../styles/ChartPage.css';

// 筛选参数类型定义
interface FilterParams {
  symbol: string;
  startTime: string;
  endTime: string;
  period: string;
  limit: number;
}

// 指标类型定义
interface Indicator {
  id: string;
  name: string;
  description: string;
}

// 指标配置类型定义
interface IndicatorConfig {
  [key: string]: any;
}

// K线数据类型定义
interface KlineData {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change: number;
  changePercent: number;
}

const ChartPage = () => {
  // 图表容器引用
  const chartRef = useRef<HTMLDivElement>(null);
  // 图表实例
  const chart = useRef<any>(null);

  // 筛选参数
  const [filterParams, setFilterParams] = useState<FilterParams>({
    symbol: 'BTCUSDT',
    startTime: '2024-01-01',
    endTime: new Date().toISOString().split('T')[0],
    period: '1d',
    limit: 500
  });

  // 图表数据
  const [chartData, setChartData] = useState<KlineData[]>([]);

  // 指标列表
  const [indicators] = useState<Indicator[]>([
    { id: 'ma', name: 'MA', description: '移动平均线' },
    { id: 'ema', name: 'EMA', description: '指数移动平均线' },
    { id: 'macd', name: 'MACD', description: '平滑异同移动平均线' },
    { id: 'rsi', name: 'RSI', description: '相对强弱指标' },
    { id: 'kdj', name: 'KDJ', description: '随机指标' },
    { id: 'boll', name: 'BOLL', description: '布林带' }
  ]);

  // 已选指标
  const [selectedIndicators, setSelectedIndicators] = useState<string[]>(['ma', 'macd']);

  // 指标配置
  const [indicatorConfigs, setIndicatorConfigs] = useState<IndicatorConfig>({
    ma: { period: 14, color: '#1890ff' },
    ema: { period: 20, color: '#52c41a' },
    macd: { fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 },
    rsi: { period: 14, color: '#faad14' },
    kdj: { kPeriod: 9, dPeriod: 3, jPeriod: 3 },
    boll: { period: 20, stdDev: 2 }
  });

  /**
   * 初始化图表
   */
  const initChart = () => {
    if (chartRef.current) {
      // 销毁现有图表
      if (chart.current) {
        dispose('kline-chart');
      }
      
      // 创建新图表
      chart.current = init('kline-chart');
      chart.current.setSymbol({ ticker: filterParams.symbol });
      chart.current.setPeriod({ span: 1, type: 'day' });
      
      // 设置数据加载器
      chart.current.setDataLoader({
        getBars: ({ callback }: { callback: (data: any[]) => void }) => {
          callback(chartData);
        }
      });
      
      // 应用初始指标
      applyIndicators();
    }
  };

  /**
   * 应用指标
   */
  const applyIndicators = () => {
    if (!chart.current) return;
    
    // 清除所有指标
    if (typeof chart.current.removeAllIndicators === 'function') {
      chart.current.removeAllIndicators();
    }
    
    // 应用选中的指标
    selectedIndicators.forEach(indicatorId => {
      const config = indicatorConfigs[indicatorId] || {};
      
      try {
        switch (indicatorId) {
          case 'ma':
            chart.current.addIndicator({
              name: 'ma',
              calcParams: [config.period || 14],
              styles: {
                color: config.color || '#1890ff'
              }
            });
            break;
          case 'ema':
            chart.current.addIndicator({
              name: 'ema',
              calcParams: [config.period || 20],
              styles: {
                color: config.color || '#52c41a'
              }
            });
            break;
          case 'macd':
            chart.current.addIndicator({
              name: 'macd',
              calcParams: [config.fastPeriod || 12, config.slowPeriod || 26, config.signalPeriod || 9]
            });
            break;
          case 'rsi':
            chart.current.addIndicator({
              name: 'rsi',
              calcParams: [config.period || 14],
              styles: {
                color: config.color || '#faad14'
              }
            });
            break;
          case 'kdj':
            chart.current.addIndicator({
              name: 'kdj',
              calcParams: [config.kPeriod || 9, config.dPeriod || 3, config.jPeriod || 3]
            });
            break;
          case 'boll':
            chart.current.addIndicator({
              name: 'boll',
              calcParams: [config.period || 20, config.stdDev || 2]
            });
            break;
        }
      } catch (error) {
        console.error(`Failed to add indicator ${indicatorId}:`, error);
      }
    });
  };

  /**
   * 生成模拟K线数据
   * @param symbol 货币对
   * @param count 数据数量
   * @returns K线数据数组
   */
  const generateDemoData = (symbol: string, count: number): KlineData[] => {
    // 不同货币对的基础价格
    const basePrices: Record<string, number> = {
      BTCUSDT: 50000,
      ETHUSDT: 3000,
      BNBUSDT: 300,
      SOLUSDT: 100
    };
    
    // 不同时间周期的毫秒数
    const intervals: Record<string, number> = {
      '1min': 60000,
      '5min': 300000,
      '15min': 900000,
      '30min': 1800000,
      '1h': 3600000,
      '4h': 14400000,
      '1d': 86400000,
      '1w': 604800000
    };
    
    const basePrice = basePrices[symbol] || 50000;
    const interval = intervals[filterParams.period] || 86400000;
    
    const data: KlineData[] = [];
    let currentPrice = basePrice;
    const now = Date.now();
    
    // 生成更真实的价格走势
    for (let i = count - 1; i >= 0; i--) {
      const timestamp = now - i * interval;
      
      // 添加一些趋势性
      const trendFactor = Math.sin(i / 20) * 0.1; // 周期性趋势
      const randomFactor = (Math.random() - 0.5) * 0.05; // 随机波动
      const volatility = Math.random() * 0.02; // 波动率
      
      const open = currentPrice;
      const close = open * (1 + trendFactor + randomFactor);
      const high = Math.max(open, close) * (1 + volatility);
      const low = Math.min(open, close) * (1 - volatility);
      const volume = Math.abs((close - open) / open) * 100000 * (0.5 + Math.random());
      
      const prevClose = data.length > 0 ? data[data.length - 1].close : open;
      const change = close - prevClose;
      const changePercent = (change / prevClose) * 100;
      
      data.push({
        timestamp,
        open: parseFloat(open.toFixed(2)),
        high: parseFloat(high.toFixed(2)),
        low: parseFloat(low.toFixed(2)),
        close: parseFloat(close.toFixed(2)),
        volume: parseFloat(volume.toFixed(2)),
        change: parseFloat(change.toFixed(2)),
        changePercent: parseFloat(changePercent.toFixed(2))
      });
      
      currentPrice = close;
    }
    
    return data;
  };

  /**
   * 获取图表数据
   */
  const fetchChartData = async () => {
    try {
      // 这里使用模拟数据，实际应该调用后端接口
      const mockData = generateDemoData(filterParams.symbol, filterParams.limit);
      setChartData(mockData);
      
      // 更新图表
      if (chart.current) {
        chart.current.resetData();
        applyIndicators();
      }
    } catch (error) {
      console.error('获取图表数据失败:', error);
      alert('获取数据失败');
    }
  };

  /**
   * 重置筛选条件
   */
  const resetFilters = () => {
    setFilterParams({
      symbol: 'BTCUSDT',
      startTime: '2024-01-01',
      endTime: new Date().toISOString().split('T')[0],
      period: '1d',
      limit: 500
    });
  };

  /**
   * 切换指标选择
   * @param indicatorId 指标ID
   */
  const toggleIndicator = (indicatorId: string) => {
    setSelectedIndicators(prev => {
      const index = prev.indexOf(indicatorId);
      let newSelected;
      if (index > -1) {
        newSelected = prev.filter(id => id !== indicatorId);
      } else {
        newSelected = [...prev, indicatorId];
      }
      
      // 应用指标变化
      setTimeout(() => applyIndicators(), 0);
      return newSelected;
    });
  };

  /**
   * 更新指标配置
   * @param indicatorId 指标ID
   * @param key 配置键
   * @param value 配置值
   */
  const updateIndicatorConfig = (indicatorId: string, key: string, value: any) => {
    setIndicatorConfigs(prev => {
      const newConfigs = {
        ...prev,
        [indicatorId]: {
          ...prev[indicatorId],
          [key]: value
        }
      };
      
      // 应用指标配置变化
      setTimeout(() => applyIndicators(), 0);
      return newConfigs;
    });
  };

  // 监听筛选参数变化
  useEffect(() => {
    // 如果symbol或period变化，重新获取数据
    fetchChartData();
  }, [filterParams.symbol, filterParams.period]);

  // 初始化
  useEffect(() => {
    initChart();
    fetchChartData();

    // 组件卸载时销毁图表
    return () => {
      if (chart.current) {
        dispose('kline-chart');
        chart.current = null;
      }
    };
  }, []);

  return (
    <div className="chart-page-container">
      <h1>K线图表</h1>
      
      {/* 筛选条件区域 */}
      <div className="filter-section">
        <div className="filter-row">
          <div className="filter-item">
            <label>货币模式</label>
            <select 
              value={filterParams.symbol} 
              onChange={(e) => setFilterParams(prev => ({ ...prev, symbol: e.target.value }))}
            >
              <option value="BTCUSDT">BTCUSDT</option>
              <option value="ETHUSDT">ETHUSDT</option>
              <option value="BNBUSDT">BNBUSDT</option>
              <option value="SOLUSDT">SOLUSDT</option>
            </select>
          </div>
          
          <div className="filter-item">
            <label>开始时间</label>
            <input 
              value={filterParams.startTime} 
              type="date"
              onChange={(e) => setFilterParams(prev => ({ ...prev, startTime: e.target.value }))}
            />
          </div>
          
          <div className="filter-item">
            <label>结束时间</label>
            <input 
              value={filterParams.endTime} 
              type="date"
              onChange={(e) => setFilterParams(prev => ({ ...prev, endTime: e.target.value }))}
            />
          </div>
          
          <div className="filter-item">
            <label>时间周期</label>
            <select 
              value={filterParams.period}
              onChange={(e) => setFilterParams(prev => ({ ...prev, period: e.target.value }))}
            >
              <option value="1min">1分钟</option>
              <option value="5min">5分钟</option>
              <option value="15min">15分钟</option>
              <option value="30min">30分钟</option>
              <option value="1h">1小时</option>
              <option value="4h">4小时</option>
              <option value="1d">日线</option>
              <option value="1w">周线</option>
            </select>
          </div>
          
          <div className="filter-item">
            <label>数据周期数</label>
            <input 
              value={filterParams.limit} 
              type="number" 
              min="100" 
              max="2000" 
              step="100"
              onChange={(e) => setFilterParams(prev => ({ ...prev, limit: parseInt(e.target.value) }))}
            />
          </div>
          
          <div className="filter-actions">
            <button className="btn btn-primary" onClick={fetchChartData}>
              获取数据
            </button>
            <button className="btn btn-secondary" onClick={resetFilters}>
              重置
            </button>
          </div>
        </div>
        
        {/* 指标选择区域 */}
        <div className="indicator-section">
          <div className="indicator-header">
            <h3>指标选择</h3>
            <div className="indicator-info">
              <span>已选指标: {selectedIndicators.length}</span>
            </div>
          </div>
          
          <div className="indicator-list">
            {indicators.map(indicator => (
              <div 
                key={indicator.id}
                className={`indicator-item ${selectedIndicators.includes(indicator.id) ? 'active' : ''}`}
                onClick={() => toggleIndicator(indicator.id)}
              >
                <div className="indicator-name">{indicator.name}</div>
                <div className="indicator-desc">{indicator.description}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
      
      {/* 图表区域 */}
      <div className="chart-section">
        <div className="chart-header">
          <div className="chart-title">{filterParams.symbol} K线图</div>
          <div className="chart-stats">
            {chartData.length > 0 && (
              <span>
                最新价格: {chartData[chartData.length - 1].close.toFixed(2)} 
                ({chartData[chartData.length - 1].changePercent.toFixed(2)}%)
              </span>
            )}
          </div>
        </div>
        
        <div className="chart-container">
          <div id="kline-chart" ref={chartRef}></div>
        </div>
      </div>
      
      {/* 指标配置区域 */}
      {selectedIndicators.length > 0 && (
        <div className="indicator-config-section">
          <h3>指标配置</h3>
          <div className="indicator-config-list">
            {selectedIndicators.map(indicatorId => (
              <div key={indicatorId} className="indicator-config-item">
                <div className="config-header">
                  <span>{indicators.find(ind => ind.id === indicatorId)?.name}</span>
                  <button className="btn-remove" onClick={() => toggleIndicator(indicatorId)}>
                    ×
                  </button>
                </div>
                <div className="config-content">
                  {/* 这里可以根据指标类型动态生成配置项 */}
                  <div className="config-row">
                    <label>周期</label>
                    <input 
                      type="number" 
                      value={indicatorConfigs[indicatorId]?.period || 14} 
                      min="1" 
                      onChange={(e) => updateIndicatorConfig(indicatorId, 'period', parseInt(e.target.value))}
                    />
                  </div>
                  <div className="config-row">
                    <label>颜色</label>
                    <input 
                      type="color" 
                      value={indicatorConfigs[indicatorId]?.color || '#1890ff'} 
                      onChange={(e) => updateIndicatorConfig(indicatorId, 'color', e.target.value)}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ChartPage;