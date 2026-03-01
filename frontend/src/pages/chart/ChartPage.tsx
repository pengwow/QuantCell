import { useEffect, useRef, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Input, Modal, Spin, message, Alert } from 'antd';

import { init, dispose, type Nullable, registerIndicator, registerOverlay, registerLocale } from 'klinecharts';
import { dataApi } from '../../api';
import * as realtimeApi from '../../api/realtimeApi';
import DrawingBar from '../../components/DrawingBar';
import IndicatorToolbar from '../../components/IndicatorToolbar';
import RealtimeToggleButton from '../../components/RealtimeToggleButton';
import TokenDisplay from '../../components/TokenDisplay';
import type { Indicator, ActiveIndicator } from '../../hooks/useIndicators';
// 导入自定义绘图工具扩展
import overlays from '../../extension/index';
import './ChartPage.css';

// 周期配置
const PERIODS = [
  { label: '1m', value: '1m', span: 1, type: 'minute' },
  { label: '5m', value: '5m', span: 5, type: 'minute' },
  { label: '15m', value: '15m', span: 15, type: 'minute' },
  { label: '30m', value: '30m', span: 30, type: 'minute' },
  { label: '1H', value: '1h', span: 60, type: 'minute' },
  { label: '4H', value: '4h', span: 240, type: 'minute' },
  { label: '1D', value: '1d', span: 1, type: 'day' },
  { label: '1W', value: '1w', span: 1, type: 'week' },
];

// 更多周期
const MORE_PERIODS = [
  { label: '2H', value: '2h', span: 120, type: 'minute' },
  { label: '1M', value: '1M', span: 1, type: 'month' },
  { label: '1Y', value: '1y', span: 1, type: 'year' },
];

// 内置指标映射
const builtInIndicatorMap: Record<string, string> = {
  'vol': 'VOL',
  'sma': 'MA',
  'ema': 'EMA',
  'rsi': 'RSI',
  'macd': 'MACD',
  'bb': 'BOLL',
  'atr': 'ATR',
  'cci': 'CCI',
  'wr': 'WR'
};

interface Symbol {
  code: string;
  name: string;
  exchange?: string;
  base?: string;
}

// KLineCharts实例类型
interface KLineChartInstance {
  setStyles: (styles: any) => void;
  setSymbol: (symbol: { ticker: string; name?: string }) => void;
  setPeriod: (period: { span: number; type: string }) => void;
  setDataLoader: (loader: { getBars: (params: { callback: (data: any[]) => void }) => void }) => void;
  createIndicator: (name: string, isStack?: boolean, options?: any) => void;
  removeIndicator: (options: { paneId?: string; indicatorName?: string }) => void;
  getIndicators: () => Array<{ name: string; paneId: string }>;
  createOverlay: (options: any) => void;
  removeOverlay: (options: { groupId?: string }) => void;
  overrideOverlay: (options: { id: string; [key: string]: any }) => void;
  getOverlays: (options?: { groupId?: string }) => Array<{ id: string; [key: string]: any }>;
  resize: () => void;
}

// 实时数据更新配置
const REALTIME_UPDATE_CONFIG = {
  throttleInterval: 100,
  maxVisibleBars: 200,
  batchThreshold: 5,
  batchInterval: 200,
};

// 本地存储key
const STORAGE_KEY = 'chart_user_preferences';

// 注册繁体中文语言包
registerLocale('zh-HK', {
  time: '時間：',
  open: '開：',
  high: '高：',
  low: '低：',
  close: '收：',
  volume: '成交量：',
  change: '漲跌：',
  turnover: '成交額：',
  second: '秒',
  minute: '分',
  hour: '時',
  day: '日',
  week: '週',
  month: '月',
  year: '年'
});

const ChartPage = () => {
  const { t } = useTranslation();
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<Nullable<KLineChartInstance>>(null);

  // 品种和周期状态
  const [currentSymbol, setCurrentSymbol] = useState<Symbol>({
    code: 'BTCUSDT',
    name: 'BTC/USDT',
    base: 'BTC'
  });
  const [currentPeriod, setCurrentPeriod] = useState('1h');
  const [isPeriodsExpanded, setIsPeriodsExpanded] = useState(false);

  // 加载状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 搜索弹窗状态
  const [searchVisible, setSearchVisible] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchResults, setSearchResults] = useState<Symbol[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // 指标状态
  const [activeIndicators, setActiveIndicators] = useState<ActiveIndicator[]>([]);



  // 实时数据状态
  const [, setIsRealtimeActive] = useState(false);
  const [systemConfig, setSystemConfig] = useState({
    realtime_enabled: false,
    data_mode: 'cache' as 'realtime' | 'cache',
  });

  // 实时数据引用
  const realtimeDataQueueRef = useRef<any[]>([]);
  const lastUpdateTimeRef = useRef<number>(0);
  const batchUpdateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const klineDataRef = useRef<any[]>([]);

  // 保存用户偏好
  const saveUserPreferences = (symbol: string, period: string) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ symbol, period }));
  };

  // 读取用户偏好
  const getUserPreferences = () => {
    const preferences = localStorage.getItem(STORAGE_KEY);
    return preferences ? JSON.parse(preferences) : null;
  };

  // 加载K线数据
  const loadKlineData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dataApi.getKlines({
        symbol: currentSymbol.code,
        interval: currentPeriod,
        limit: 500,
      });

      // API 返回的数据已经是正确的格式，直接使用
      if (data && Array.isArray(data)) {
        klineDataRef.current = data;

        if (chartInstanceRef.current) {
          chartInstanceRef.current.setDataLoader({
            getBars: ({ callback }: { callback: (data: any[]) => void }) => {
              callback(data);
            }
          });
        }
      }
    } catch (error) {
      setError('加载K线数据失败');
      message.error('加载K线数据失败');
      console.error('加载K线数据失败:', error);
    } finally {
      setLoading(false);
    }
  }, [currentSymbol, currentPeriod]);

  // 初始化图表
  useEffect(() => {
    // 注册自定义绘图工具扩展
    overlays.forEach(overlay => {
      registerOverlay(overlay);
    });

    if (chartRef.current && !chartInstanceRef.current) {
      const chart = init('language-k-line', {
        locale: 'zh-CN',
      }) as unknown as KLineChartInstance;

      chartInstanceRef.current = chart;

      // 设置图表样式
      chart.setStyles({
        grid: {
          show: true,
          horizontal: {
            show: true,
            size: 1,
            color: '#EDEDED',
            style: 'dashed',
          },
          vertical: {
            show: true,
            size: 1,
            color: '#EDEDED',
            style: 'dashed',
          },
        },
        candle: {
          bar: {
            upColor: '#26A69A',
            downColor: '#EF5350',
            noChangeColor: '#888888',
          },
        },
      });

      // 设置品种和周期
      const period = PERIODS.find(p => p.value === currentPeriod);
      chart.setSymbol({ ticker: currentSymbol.code, name: currentSymbol.name });
      chart.setPeriod({
        span: period?.span || 1,
        type: period?.type || 'minute',
      });

      // 设置数据加载器
      chart.setDataLoader({
        getBars: ({ callback }: { callback: (data: any[]) => void }) => {
          callback(klineDataRef.current);
        }
      });

      // 加载初始数据
      loadKlineData();

      // 自动添加VOL指标
      setTimeout(() => {
        try {
          const existingIndicators = chart.getIndicators() || [];
          const hasVolIndicator = existingIndicators.some((ind: any) => ind.name === 'VOL');
          if (!hasVolIndicator) {
            chart.createIndicator('VOL', true);
          }
        } catch (err) {
          console.error('创建VOL指标失败:', err);
        }
      }, 500);
    }

    return () => {
      if (chartInstanceRef.current) {
        dispose('language-k-line');
        chartInstanceRef.current = null;
      }
    };
  }, []);

  // 当品种或周期变化时重新加载数据
  useEffect(() => {
    if (chartInstanceRef.current) {
      const period = PERIODS.find(p => p.value === currentPeriod) ||
                     MORE_PERIODS.find(p => p.value === currentPeriod);
      chartInstanceRef.current.setSymbol({ ticker: currentSymbol.code, name: currentSymbol.name });
      chartInstanceRef.current.setPeriod({
        span: period?.span || 1,
        type: period?.type || 'minute',
      });
      loadKlineData();
      saveUserPreferences(currentSymbol.code, currentPeriod);
    }
  }, [currentSymbol, currentPeriod, loadKlineData]);

  // 组件挂载时读取用户偏好
  useEffect(() => {
    const preferences = getUserPreferences();
    if (preferences) {
      setCurrentPeriod(preferences.period);
      // 品种将在搜索后更新
    }
  }, []);

  // 组件挂载时获取系统配置并自动连接实时引擎
  useEffect(() => {
    const fetchSystemConfig = async () => {
      try {
        const config = await realtimeApi.getRealtimeConfig();
        if (config) {
          setSystemConfig({
            realtime_enabled: config.realtime_enabled,
            data_mode: config.data_mode,
          });

          // 如果系统配置启用了实时引擎，自动启动
          if (config.realtime_enabled) {
            console.log('[ChartPage] 系统配置启用了实时引擎，自动连接...');
            setTimeout(() => {
              handleAutoConnect();
            }, 1000);
          }
        }
      } catch (err) {
        console.error('获取系统配置失败:', err);
      }
    };
    fetchSystemConfig();
  }, []);

  // 自动连接实时引擎
  const handleAutoConnect = async () => {
    try {
      console.log('[ChartPage] 自动连接实时引擎...');

      // 1. 检查实时引擎状态
      const status = await realtimeApi.getRealtimeStatus();
      console.log('[ChartPage] 引擎状态:', status);

      // 2. 如果引擎未运行，启动引擎
      if (status.status !== 'running') {
        console.log('[ChartPage] 引擎未运行，启动引擎...');
        const startResult = await realtimeApi.startRealtimeEngine();
        if (!startResult.success) {
          console.error('[ChartPage] 启动引擎失败');
          return;
        }
      }

      // 3. 连接交易所
      if (!status.connected) {
        console.log('[ChartPage] 连接交易所...');
        const connectResult = await realtimeApi.connectExchange();
        if (!connectResult.success) {
          console.error('[ChartPage] 连接交易所失败');
          return;
        }
      }

      console.log('[ChartPage] 实时引擎自动连接成功');
    } catch (error) {
      console.error('[ChartPage] 自动连接实时引擎失败:', error);
    }
  };

  // 搜索品种
  const handleSearch = useCallback(async () => {
    setSearchLoading(true);
    try {
      const response: any = await dataApi.getProducts({
        filter: searchKeyword || undefined,
        limit: 100,
      });

      // API 返回 { products: [...] } 格式
      const productsList = response?.products || [];
      
      if (productsList.length > 0) {
        const products = productsList.map((item: any) => ({
          code: item.symbol,
          name: item.name || item.symbol,
          exchange: item.exchange,
          base: item.base,
        }));
        setSearchResults(products);

        // 如果有本地存储的偏好，检查是否需要更新默认品种
        const preferences = getUserPreferences();
        if (preferences && currentSymbol.code !== preferences.symbol) {
          const preferredProduct = products.find((p: Symbol) => p.code === preferences.symbol);
          if (preferredProduct) {
            setCurrentSymbol(preferredProduct);
          }
        }
      } else {
        setSearchResults([]);
      }
    } catch (error) {
      message.error('搜索失败');
      console.error('搜索品种失败:', error);
    } finally {
      setSearchLoading(false);
    }
  }, [searchKeyword, currentSymbol.code]);

  // 当搜索弹窗打开时自动搜索
  useEffect(() => {
    if (searchVisible) {
      handleSearch();
    }
  }, [searchVisible, handleSearch]);

  // 当搜索关键词变化时重新搜索
  useEffect(() => {
    if (searchVisible) {
      const timer = setTimeout(() => {
        handleSearch();
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [searchKeyword, searchVisible, handleSearch]);

  // 选择品种
  const handleSelectSymbol = (symbol: Symbol) => {
    setCurrentSymbol(symbol);
    setSearchVisible(false);
    setSearchKeyword('');
    saveUserPreferences(symbol.code, currentPeriod);
  };

  // 注册自定义指标到KLineCharts
  const registerCustomIndicator = (indicator: Indicator, data: any) => {
    const indicatorName = `custom_${indicator.id}`;

    registerIndicator({
      name: indicatorName,
      shortName: indicator.name,
      calc: (kLineDataList: any[]) => {
        return kLineDataList.map((kLine) => {
          const indicatorData = data?.find((d: any) => d.timestamp === kLine.timestamp);
          return {
            ...kLine,
            [indicatorName]: indicatorData?.value || null
          };
        });
      },
      figures: [
        {
          key: indicatorName,
          type: 'line'
        }
      ]
    });

    return indicatorName;
  };

  // 切换指标
  const handleToggleIndicator = useCallback(async (indicator: Indicator, params?: Record<string, any>) => {
    if (!chartInstanceRef.current) return;

    const builtInId = params?._builtInId;
    const indicatorId = builtInId ? String(builtInId) : String(indicator.id);
    const isActive = activeIndicators.some(ind => String(ind.id) === indicatorId);

    if (isActive) {
      // 停止指标
      const indicators = chartInstanceRef.current.getIndicators();
      indicators.forEach((ind: any) => {
        if (ind.name === indicatorId || ind.name === builtInIndicatorMap[indicatorId] || ind.name === `custom_${indicator.id}`) {
          chartInstanceRef.current?.removeIndicator({ paneId: ind.paneId, indicatorName: ind.name });
        }
      });
      setActiveIndicators(prev => prev.filter(ind => String(ind.id) !== indicatorId));
    } else {
      // 启动指标
      const builtInName = builtInIndicatorMap[indicatorId];

      if (builtInName) {
        // 内置指标
        const isOverlay = ['MA', 'EMA', 'BOLL', 'SAR', 'BBI', 'SMA'].includes(builtInName);
        chartInstanceRef.current.createIndicator(builtInName, !isOverlay, { calcParams: params || {} });
      } else {
        // 自定义指标
        try {
          const response = await fetch(`/api/indicators/${indicator.id}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              symbol: currentSymbol.code,
              period: currentPeriod,
              params: params || {}
            })
          });

          const result = await response.json();

          if (result.success && result.data) {
            const customIndicatorName = registerCustomIndicator(indicator, result.data);
            chartInstanceRef.current.createIndicator(customIndicatorName, true);
          } else {
            console.error('获取指标数据失败:', result.message);
          }
        } catch (err) {
          console.error('执行自定义指标失败:', err);
        }
      }

      setActiveIndicators(prev => [...prev, {
        id: indicatorId,
        name: indicator.name,
        params,
        isCustom: !builtInName,
      }]);
    }
  }, [activeIndicators, currentSymbol.code, currentPeriod]);

  // 处理绘图工具点击
  const handleDrawingItemClick = useCallback((overlay: { name: string; lock: boolean; mode: string }) => {
    if (!chartInstanceRef.current) return;
    chartInstanceRef.current.createOverlay({
      name: overlay.name,
      groupId: 'drawing_tools',
      lock: overlay.lock,
      mode: overlay.mode as 'normal' | 'weak_magnet' | 'strong_magnet',
      visible: true
    });
  }, []);

  // 处理模式变化
  const handleModeChange = useCallback((mode: string) => {
    console.log('Mode changed:', mode);
  }, []);

  // 处理锁定变化
  const handleLockChange = useCallback((lock: boolean) => {
    if (!chartInstanceRef.current) return;
    const overlays = chartInstanceRef.current.getOverlays({ groupId: 'drawing_tools' });
    overlays.forEach((overlay: any) => {
      chartInstanceRef.current?.overrideOverlay({ id: overlay.id, lock });
    });
  }, []);

  // 处理可见性变化
  const handleVisibleChange = useCallback((visible: boolean) => {
    if (!chartInstanceRef.current) return;
    const overlays = chartInstanceRef.current.getOverlays({ groupId: 'drawing_tools' });
    overlays.forEach((overlay: any) => {
      chartInstanceRef.current?.overrideOverlay({ id: overlay.id, visible });
    });
  }, []);

  // 处理删除
  const handleRemoveClick = useCallback((groupId: string) => {
    if (!chartInstanceRef.current) return;
    chartInstanceRef.current.removeOverlay({ groupId });
  }, []);

  // 批量处理实时数据更新
  const processBatchUpdate = useCallback(() => {
    if (!chartInstanceRef.current || realtimeDataQueueRef.current.length === 0) return;

    const queue = realtimeDataQueueRef.current;

    try {
      const currentData = klineDataRef.current || [];

      queue.forEach((data) => {
        let kline = data.k;

        if (!kline && data.data) {
          kline = data.data.k || data.data;
        }

        if (!kline && data.data && data.data.data) {
          kline = data.data.data.k || data.data.data;
        }

        if (!kline) {
          return;
        }

        const bar = {
          timestamp: kline.t,
          open: parseFloat(kline.o),
          high: parseFloat(kline.h),
          low: parseFloat(kline.l),
          close: parseFloat(kline.c),
          volume: parseFloat(kline.v),
        };

        const existingIndex = currentData.findIndex(
          (item: any) => item.timestamp === bar.timestamp
        );

        if (existingIndex >= 0) {
          currentData[existingIndex] = bar;
        } else {
          currentData.push(bar);
        }
      });

      if (currentData.length > REALTIME_UPDATE_CONFIG.maxVisibleBars) {
        const startIndex = currentData.length - REALTIME_UPDATE_CONFIG.maxVisibleBars;
        klineDataRef.current = currentData.slice(startIndex);
      } else {
        klineDataRef.current = currentData;
      }

      requestAnimationFrame(() => {
        if (!chartInstanceRef.current) return;

        chartInstanceRef.current.setDataLoader({
          getBars: ({ callback }: { callback: (data: any[]) => void }) => {
            callback(klineDataRef.current);
          }
        });

        chartInstanceRef.current.resize();
      });

      realtimeDataQueueRef.current = [];

      console.log(`[Realtime] 批量更新完成: 处理${queue.length}条, 总计${klineDataRef.current.length}条`);
    } catch (err) {
      console.error('[Realtime] 批量处理数据失败:', err);
    }
  }, []);

  // 处理实时数据更新
  const handleRealtimeData = useCallback((data: any) => {
    if (!data) {
      console.warn('[Realtime] 接收到空数据');
      return;
    }

    const now = Date.now();
    const timeSinceLastUpdate = now - lastUpdateTimeRef.current;

    let kline = data.k;
    if (!kline && data.data) {
      kline = data.data.k || data.data;
    }
    if (!kline && data.data && data.data.data) {
      kline = data.data.data.k || data.data.data;
    }

    if (kline) {
      console.log(`[Realtime] 收到K线: ${kline.s}@${kline.i}, close=${kline.c}, queue=${realtimeDataQueueRef.current.length + 1}`);
    }

    realtimeDataQueueRef.current.push(data);

    if (timeSinceLastUpdate >= REALTIME_UPDATE_CONFIG.throttleInterval) {
      if (batchUpdateTimerRef.current) {
        clearTimeout(batchUpdateTimerRef.current);
        batchUpdateTimerRef.current = null;
      }

      lastUpdateTimeRef.current = now;
      processBatchUpdate();
    } else {
      if (!batchUpdateTimerRef.current) {
        batchUpdateTimerRef.current = setTimeout(() => {
          lastUpdateTimeRef.current = Date.now();
          processBatchUpdate();
          batchUpdateTimerRef.current = null;
        }, REALTIME_UPDATE_CONFIG.batchInterval);
      }
    }

    if (realtimeDataQueueRef.current.length >= REALTIME_UPDATE_CONFIG.batchThreshold) {
      console.log(`[Realtime] 队列超过阈值 (${REALTIME_UPDATE_CONFIG.batchThreshold})，立即处理`);
      if (batchUpdateTimerRef.current) {
        clearTimeout(batchUpdateTimerRef.current);
        batchUpdateTimerRef.current = null;
      }
      lastUpdateTimeRef.current = now;
      processBatchUpdate();
    }
  }, [processBatchUpdate]);

  // 处理实时状态变化
  const handleRealtimeStatusChange = (isActive: boolean) => {
    setIsRealtimeActive(isActive);
  };

  // 监听图表容器大小变化
  useEffect(() => {
    const chartElement = document.getElementById('language-k-line');
    let resizeObserver: ResizeObserver | null = null;

    const handleResize = () => {
      if (chartInstanceRef.current) {
        chartInstanceRef.current.resize();
      }
    };

    if (chartElement && typeof ResizeObserver === 'function') {
      resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(chartElement);
    }

    window.addEventListener('resize', handleResize);

    return () => {
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  return (
    <div className="chart-page-fullscreen">
      <div className="chart-page">
        {/* 顶部工具栏 */}
        <div className="chart-toolbar">
          <div className="toolbar-left">
            {/* 品种选择按钮 - 显示图标和名称 */}
            <Button
              className="symbol-select-btn"
              onClick={() => setSearchVisible(true)}
            >
              <TokenDisplay symbol={currentSymbol.base || 'BTC'} size={20} />
              <span className="symbol-code">{currentSymbol.code}</span>
            </Button>

            {/* 周期选择 */}
            <div className="period-buttons-container" style={{ position: 'relative' }}>
              {PERIODS.map(period => (
                <Button
                  key={period.value}
                  type={currentPeriod === period.value ? 'primary' : 'default'}
                  size="small"
                  onClick={() => setCurrentPeriod(period.value)}
                >
                  {period.label}
                </Button>
              ))}
              <Button
                size="small"
                onClick={() => setIsPeriodsExpanded(!isPeriodsExpanded)}
              >
                {isPeriodsExpanded ? '收起' : '更多'}
              </Button>

              {/* 更多周期下拉 - 放在容器内部以便正确定位 */}
              {isPeriodsExpanded && (
                <div className="more-periods-dropdown">
                  {MORE_PERIODS.map(period => (
                    <Button
                      key={period.value}
                      type={currentPeriod === period.value ? 'primary' : 'default'}
                      size="small"
                      onClick={() => {
                        setCurrentPeriod(period.value);
                        setIsPeriodsExpanded(false);
                      }}
                    >
                      {period.label}
                    </Button>
                  ))}
                </div>
              )}
            </div>

            {/* 指标按钮 - 放在周期选择后面 */}
            <IndicatorToolbar
              activeIndicators={activeIndicators}
              onToggleIndicator={handleToggleIndicator}
            />
          </div>

          <div className="toolbar-right">
            {/* 实时数据按钮 */}
            <RealtimeToggleButton
              symbol={currentSymbol.code}
              period={currentPeriod.toLowerCase()}
              defaultRealtimeEnabled={systemConfig.realtime_enabled}
              onRealtimeData={handleRealtimeData}
              onStatusChange={handleRealtimeStatusChange}
            />
          </div>
        </div>

        {/* 主图表区域 - 包含常驻的左侧绘图工具栏 */}
        <div className="chart-main-with-toolbar">
          {/* 左侧常驻绘图工具栏 */}
          <div className="drawing-toolbar-vertical">
            <DrawingBar
              onDrawingItemClick={handleDrawingItemClick}
              onModeChange={handleModeChange}
              onLockChange={handleLockChange}
              onVisibleChange={handleVisibleChange}
              onRemoveClick={handleRemoveClick}
            />
          </div>

          {/* 图表区域 */}
          <div className="chart-area">
          {error && (
            <Alert
              message="错误"
              description={error}
              type="error"
              showIcon
              style={{ margin: 16 }}
            />
          )}
          <Spin spinning={loading} className="chart-spin">
            <div
              id="language-k-line"
              ref={chartRef}
              className="kline-chart"
            />
          </Spin>
        </div>
      </div>

        {/* 品种搜索弹窗 */}
        <Modal
          title={t('chart.searchSymbol', '搜索品种')}
          open={searchVisible}
          onCancel={() => {
            setSearchVisible(false);
            setSearchKeyword('');
            setSearchResults([]);
          }}
          footer={null}
          width={600}
        >
          <Input
            placeholder={t('chart.searchPlaceholder', '输入品种代码或名称')}
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            allowClear
            style={{ marginBottom: 16 }}
          />
          <div className="symbol-search-results">
            {searchLoading ? (
              <div className="search-loading">
                <Spin size="large" />
                <div>加载中...</div>
              </div>
            ) : searchResults.length === 0 ? (
              <div className="search-empty">
                未找到匹配的商品
              </div>
            ) : (
              searchResults.map((product) => (
                <div
                  key={product.code}
                  className="search-result-item"
                  onClick={() => handleSelectSymbol(product)}
                >
                  <div className="search-result-icon">
                    <TokenDisplay symbol={product.base || product.code.charAt(0)} size={32} />
                  </div>
                  <div className="search-result-info">
                    <div className="search-result-code">{product.code}</div>
                    <div className="search-result-name">{product.name}</div>
                  </div>
                  {product.exchange && (
                    <div className="search-result-exchange">{product.exchange}</div>
                  )}
                </div>
              ))
            )}
          </div>
        </Modal>
      </div>
    </div>
  );
};

export default ChartPage;
