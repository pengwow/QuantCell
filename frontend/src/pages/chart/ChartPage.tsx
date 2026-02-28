import { useEffect, useRef, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Select, Input, Modal, List, Spin, message } from 'antd';
import { SearchOutlined, SettingOutlined } from '@ant-design/icons';
import { init, dispose, Nullable } from 'klinecharts';
import { dataApi } from '../../api';
import DrawingBar from '../../components/DrawingBar';
import IndicatorPanel from '../../components/IndicatorPanel';
import { Indicator, ActiveIndicator } from '../../hooks/useIndicators';
import PageContainer from '@/components/PageContainer';
import './ChartPage.css';

const { Option } = Select;

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
  createOverlay: (name: string) => void;
  removeOverlay: (options: { groupId?: string }) => void;
}

const ChartPage = () => {
  const { t } = useTranslation();
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<Nullable<KLineChartInstance>>(null);
  const [currentSymbol, setCurrentSymbol] = useState<Symbol>({ code: 'BTCUSDT', name: 'BTC/USDT' });
  const [currentPeriod, setCurrentPeriod] = useState('1h');
  const [loading, setLoading] = useState(false);
  const [searchVisible, setSearchVisible] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchResults, setSearchResults] = useState<Symbol[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [activeIndicators, setActiveIndicators] = useState<ActiveIndicator[]>([]);
  const [, setIndicatorEditorVisible] = useState(false);
  const [, setEditingIndicator] = useState<Indicator | null>(null);
  const klineDataRef = useRef<any[]>([]);

  // 加载K线数据
  const loadKlineData = useCallback(async () => {
    setLoading(true);
    try {
      const response = await dataApi.getKlines({
        symbol: currentSymbol.code,
        interval: currentPeriod,
        limit: 500,
      });

      if (response && Array.isArray(response)) {
        const klineData = response.map((item: any) => ({
          timestamp: item[0],
          open: parseFloat(item[1]),
          high: parseFloat(item[2]),
          low: parseFloat(item[3]),
          close: parseFloat(item[4]),
          volume: parseFloat(item[5]),
        }));
        klineDataRef.current = klineData;

        // 如果图表已初始化，刷新数据
        if (chartInstanceRef.current) {
          chartInstanceRef.current.setDataLoader({
            getBars: ({ callback }: { callback: (data: any[]) => void }) => {
              callback(klineData);
            }
          });
        }
      }
    } catch (error) {
      message.error('加载K线数据失败');
      console.error('加载K线数据失败:', error);
    } finally {
      setLoading(false);
    }
  }, [currentSymbol, currentPeriod]);

  // 初始化图表
  useEffect(() => {
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
      const period = PERIODS.find(p => p.value === currentPeriod);
      chartInstanceRef.current.setSymbol({ ticker: currentSymbol.code, name: currentSymbol.name });
      chartInstanceRef.current.setPeriod({
        span: period?.span || 1,
        type: period?.type || 'minute',
      });
      loadKlineData();
    }
  }, [currentSymbol, currentPeriod, loadKlineData]);

  // 搜索品种
  const handleSearch = useCallback(async () => {
    if (!searchKeyword.trim()) return;

    setSearchLoading(true);
    try {
      const response = await dataApi.getProducts({
        filter: searchKeyword,
        limit: 20,
      });

      if (response && Array.isArray(response)) {
        setSearchResults(response.map((item: any) => ({
          code: item.symbol,
          name: item.name || item.symbol,
          exchange: item.exchange,
        })));
      }
    } catch (error) {
      message.error('搜索失败');
    } finally {
      setSearchLoading(false);
    }
  }, [searchKeyword]);

  // 选择品种
  const handleSelectSymbol = (symbol: Symbol) => {
    setCurrentSymbol(symbol);
    setSearchVisible(false);
    setSearchKeyword('');
    setSearchResults([]);
  };

  // 切换指标
  const handleToggleIndicator = useCallback((indicator: Indicator, params?: Record<string, any>) => {
    if (!chartInstanceRef.current) return;

    const indicatorId = indicator.id.toString();
    const isActive = activeIndicators.some(ind => ind.id === indicatorId);

    if (isActive) {
      // 停止指标
      const indicators = chartInstanceRef.current.getIndicators();
      indicators.forEach((ind: any) => {
        if (ind.name === indicator.name || ind.name === builtInIndicatorMap[indicatorId] || ind.name === `custom_${indicator.id}`) {
          chartInstanceRef.current?.removeIndicator({ paneId: ind.paneId, indicatorName: ind.name });
        }
      });
      setActiveIndicators(prev => prev.filter(ind => ind.id !== indicatorId));
    } else {
      // 启动指标
      const builtInKey = Object.keys(builtInIndicatorMap).find(
        key => builtInIndicatorMap[key] === indicator.name || key === indicatorId
      );

      if (builtInKey && builtInIndicatorMap[builtInKey]) {
        // 内置指标
        const builtInName = builtInIndicatorMap[builtInKey];
        const isOverlay = ['MA', 'EMA', 'BOLL', 'SAR', 'BBI', 'SMA'].includes(builtInName);
        chartInstanceRef.current.createIndicator(builtInName, !isOverlay, { calcParams: params || {} });
      } else {
        // 自定义指标
        chartInstanceRef.current.createIndicator('CUSTOM', true, { calcParams: params || {} });
      }

      setActiveIndicators(prev => [...prev, {
        id: indicatorId,
        name: indicator.name,
        params,
        isCustom: !builtInKey,
      }]);
    }
  }, [activeIndicators]);

  // 处理绘图工具点击
  const handleDrawingItemClick = useCallback((overlay: { name: string; lock: boolean; mode: string }) => {
    if (!chartInstanceRef.current) return;
    chartInstanceRef.current.createOverlay(overlay.name);
  }, []);

  // 处理模式变化
  const handleModeChange = useCallback((mode: string) => {
    console.log('Mode changed:', mode);
  }, []);

  // 处理锁定变化
  const handleLockChange = useCallback((lock: boolean) => {
    console.log('Lock changed:', lock);
  }, []);

  // 处理可见性变化
  const handleVisibleChange = useCallback((visible: boolean) => {
    console.log('Visible changed:', visible);
  }, []);

  // 处理删除
  const handleRemoveClick = useCallback((groupId: string) => {
    if (!chartInstanceRef.current) return;
    chartInstanceRef.current.removeOverlay({ groupId });
  }, []);

  // 打开指标编辑器
  const handleOpenEditor = useCallback(() => {
    setEditingIndicator(null);
    setIndicatorEditorVisible(true);
  }, []);

  // 编辑指标
  const handleEditIndicator = useCallback((indicator: Indicator) => {
    setEditingIndicator(indicator);
    setIndicatorEditorVisible(true);
  }, []);

  return (
    <PageContainer title={t('chart')}>
    <div className="chart-page">
      {/* 顶部工具栏 */}
      <div className="chart-toolbar">
        <div className="toolbar-left">
          <Button
            icon={<SearchOutlined />}
            onClick={() => setSearchVisible(true)}
          >
            {currentSymbol.name}
          </Button>
          <Select
            value={currentPeriod}
            onChange={setCurrentPeriod}
            style={{ width: 80 }}
          >
            {PERIODS.map(period => (
              <Option key={period.value} value={period.value}>
                {period.label}
              </Option>
            ))}
          </Select>
        </div>
        <div className="toolbar-right">
          <Button icon={<SettingOutlined />}>
            {t('chart.settings', '设置')}
          </Button>
        </div>
      </div>

      {/* 绘图工具栏 */}
      <DrawingBar
        onDrawingItemClick={handleDrawingItemClick}
        onModeChange={handleModeChange}
        onLockChange={handleLockChange}
        onVisibleChange={handleVisibleChange}
        onRemoveClick={handleRemoveClick}
      />

      {/* 主图表区域 */}
      <div className="chart-main">
        <div className="chart-container">
          <Spin spinning={loading}>
            <div
              id="language-k-line"
              ref={chartRef}
              className="kline-chart"
              style={{ width: '100%', height: 'calc(100vh - 200px)' }}
            />
          </Spin>
        </div>

        {/* 指标面板 */}
        <div className="indicator-sidebar">
          <IndicatorPanel
            activeIndicators={activeIndicators}
            onToggleIndicator={handleToggleIndicator}
            onOpenEditor={handleOpenEditor}
            onEditIndicator={handleEditIndicator}
          />
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
      >
        <Input.Search
          placeholder={t('chart.searchPlaceholder', '输入品种代码或名称')}
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          onSearch={handleSearch}
          loading={searchLoading}
          enterButton
        />
        <List
          className="search-results"
          loading={searchLoading}
          dataSource={searchResults}
          renderItem={(item) => (
            <List.Item
              className="search-result-item"
              onClick={() => handleSelectSymbol(item)}
            >
              <div className="symbol-info">
                <span className="symbol-code">{item.code}</span>
                <span className="symbol-name">{item.name}</span>
                {item.exchange && (
                  <span className="symbol-exchange">{item.exchange}</span>
                )}
              </div>
            </List.Item>
          )}
          locale={{ emptyText: t('chart.noResults', '暂无搜索结果') }}
        />
      </Modal>
    </div>
    </PageContainer>
  );
};

export default ChartPage;
