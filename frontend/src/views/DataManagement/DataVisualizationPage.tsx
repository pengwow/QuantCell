/**
 * 数据可视化页面组件
 */
import { useState, useEffect, useRef } from 'react';
import { dataApi } from '../../api';
import { init, dispose } from 'klinecharts';
import {
  Select,
  InputNumber,
  Button,
  Spin,
  Space
} from 'antd';
import {
  ReloadOutlined
} from '@ant-design/icons';

const DataVisualizationPage = () => {

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

  // 图表实例
  const chartRef = useRef<any>(null);
  // 图表容器引用
  const chartContainerRef = useRef<HTMLDivElement>(null);

  /**
   * 获取K线数据
   */
  const fetchKlineData = async (): Promise<void> => {
    setIsLoadingKline(true);
    setKlineError(null);
    
    try {
      const data = await dataApi.getKlines(klineConfig);
      
      setKlineData(data);
      
      // 更新图表数据
      if (chartRef.current) {
        chartRef.current.setDataLoader({
          getBars: ({ callback }: { callback: (data: any[]) => void }) => {
            callback(data);
          }
        });
      }
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
   * 初始化和清理图表
   */
  useEffect(() => {
    // 初始化图表
    const initChart = async () => {
      try {
        if (chartContainerRef.current) {
          // 检查容器尺寸
          const container = chartContainerRef.current;
          const rect = container.getBoundingClientRect();
          
          // 确保容器有正确的尺寸
          if (rect.width === 0 || rect.height === 0) {
            console.warn('图表容器尺寸为0，等待容器可见后重试');
            return;
          }
          
          // 简化图表初始化，使用默认配置
          const chart = init(container);
          
          if (chart) {
            chartRef.current = chart;
            
            // 设置图表信息
            chart.setSymbol({ ticker: klineConfig.symbol });
            chart.setPeriod({ span: parseInt(klineConfig.interval.replace('m', '')), type: 'minute' });
            
            // 添加默认指标
            chart.createIndicator('MA');
            
            // 设置数据加载器
            chart.setDataLoader({
              getBars: async (params) => {
                try {
                  if (klineData.length > 0) {
                    params.callback(klineData);
                  } else {
                    // 如果没有数据，尝试获取数据
                    await fetchKlineData();
                    params.callback(klineData);
                  }
                } catch (error) {
                  console.error('获取K线数据失败:', error);
                  params.callback([]);
                }
              }
            });
            
            // 如果已有数据，直接更新图表
            if (klineData.length > 0) {
              chart.setDataLoader({
                getBars: ({ callback }) => {
                  callback(klineData);
                }
              });
            }
          } else {
            console.error('图表初始化失败，返回null');
          }
        }
      } catch (error) {
        console.error('图表初始化过程中发生错误:', error);
      }
    };
    
    initChart();
    
    // 清理函数
    return () => {
      try {
        if (chartRef.current) {
          dispose(chartRef.current);
          chartRef.current = null;
        }
      } catch (error) {
        console.error('销毁图表过程中发生错误:', error);
      }
    };
  }, [klineConfig.symbol, klineConfig.interval, klineData]);

  /**
   * 当K线数据变化时更新图表
   */
  useEffect(() => {
    if (chartRef.current && klineData.length > 0) {
      // 直接更新图表数据
      try {
        // 使用setDataLoader更新数据
        chartRef.current.setDataLoader({
          getBars: ({ callback }: { callback: (data: any[]) => void }) => {
            callback(klineData);
          }
        });
      } catch (error) {
        console.error('更新图表数据失败:', error);
      }
    }
  }, [klineData]);

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
    <>
      <h2>数据可视化</h2>
      
      {/* K线图表配置 */}
      <div className="data-section">
        <div className="import-form">
          <Space.Compact style={{ width: '100%' }}>
            <div style={{ flex: 1, marginRight: 16 }}>
              <div style={{ marginBottom: 8 }}>交易对</div>
              <Select
                value={klineConfig.symbol}
                onChange={(value) => setKlineConfig(prev => ({ ...prev, symbol: value }))}
              >
                <Select.Option value="BTCUSDT">BTCUSDT</Select.Option>
                <Select.Option value="ETHUSDT">ETHUSDT</Select.Option>
                <Select.Option value="BNBUSDT">BNBUSDT</Select.Option>
              </Select>
            </div>
            <div style={{ flex: 1, marginRight: 16 }}>
              <div style={{ marginBottom: 8 }}>时间周期</div>
              <Select
                value={klineConfig.interval}
                onChange={(value) => setKlineConfig(prev => ({ ...prev, interval: value }))}
              >
                <Select.Option value="1m">1分钟</Select.Option>
                <Select.Option value="5m">5分钟</Select.Option>
                <Select.Option value="15m">15分钟</Select.Option>
                <Select.Option value="30m">30分钟</Select.Option>
                <Select.Option value="1h">1小时</Select.Option>
              </Select>
            </div>
            <div style={{ flex: 1, marginRight: 16 }}>
              <div style={{ marginBottom: 8 }}>数据数量</div>
              <InputNumber
                value={klineConfig.limit}
                min={100}
                max={2000}
                step={100}
                onChange={(value: number | null) => setKlineConfig(prev => ({ ...prev, limit: value || 500 }))}
              />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ marginBottom: 8 }}>操作</div>
              <Button 
                type="primary"
                onClick={fetchKlineData}
                disabled={isLoadingKline}
                icon={<ReloadOutlined />}
                block
              >
                {isLoadingKline ? '加载中...' : '获取数据'}
              </Button>
            </div>
          </Space.Compact>
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
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '600px' }}>
              <Spin tip="加载中..." size="large" />
            </div>
          ) : (
            <div className="kline-chart" ref={chartContainerRef} style={{ height: '600px', width: '100%' }}>
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default DataVisualizationPage;