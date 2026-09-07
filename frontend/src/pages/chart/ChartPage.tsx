import { useEffect, useRef, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Input, Modal, Spin, Alert, App } from 'antd';
import { init, dispose, type Nullable, registerIndicator, registerOverlay, registerLocale } from 'klinecharts';
import type {
  Chart,
  DataLoaderGetBarsParams,
  IndicatorFilter,
  IndicatorFigure,
  KLineData,
  OverlayCreateFiguresCallback,
  OverlayCreateFiguresCallbackParams,
  OverlayFigure,
  PaneOptions,
  PeriodType,
} from 'klinecharts';
import { dataApi } from '../../api';
import * as realtimeApi from '../../api/realtimeApi';
import DrawingBar from '../../components/DrawingBar';
import IndicatorToolbar from '../../components/IndicatorToolbar';
import RealtimeToggleButton from '../../components/RealtimeToggleButton';
import TokenDisplay from '../../components/TokenDisplay';
import type { Indicator, ActiveIndicator } from '../../hooks/useIndicators';
import { getAccessToken } from '../../utils/tokenManager';
// 导入自定义绘图工具扩展
import overlays from '../../extension/index';
import { setPageTitle } from '@/utils/pageTitle';
import './ChartPage.css';

// 周期类型（klinecharts PeriodType）
interface PeriodItem {
  label: string;
  value: string;
  span: number;
  type: PeriodType;
}

// 周期配置
const PERIODS: PeriodItem[] = [
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
const MORE_PERIODS: PeriodItem[] = [
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

// 信号标注 overlay 的扩展数据（由 createOverlay 传入）
interface SignalExtendData {
  text?: string;
  color?: string;
  side?: string;
}

// 信号标注点坐标（在基础坐标上附加 extendData）
type SignalTagCoordinate = { x: number; y: number; extendData?: SignalExtendData };

// 指标执行结果（对应后端 /api/indicators/:id/execute 返回的 data）
interface IndicatorExecuteResult {
  plots?: IndicatorPlot[];
  signals?: IndicatorSignal[];
  [key: string]: unknown;
}

// 指标输出的单个 plot
interface IndicatorPlot {
  name?: string;
  data?: Array<number | null | undefined>;
  type?: string;
  color?: string;
  [key: string]: unknown;
}

// 指标输出的信号（如买/卖点）
interface IndicatorSignal {
  type?: string;
  data?: Array<number | null | undefined>;
  color?: string;
  text?: string;
  [key: string]: unknown;
}

// 归一化后的 figure 配置（注册到 klinecharts 的 figures）
interface IndicatorFigureConfig {
  key: string;
  title?: string;
  type?: string;
  color?: string;
  [key: string]: unknown;
}

// 信号点位（K线坐标）
interface SignalPoint {
  timestamp: number;
  price: number;
  anchorPrice: number;
  side: string;
  color: string;
  text: string;
}

// 商品条目（后端 /data/products 返回的字段）
interface ProductItem {
  symbol: string;
  name?: string;
  exchange?: string;
  base?: string;
  [key: string]: unknown;
}

// 实时行情K线（交易所推送格式，o/h/l/c/v 为字符串）
interface RealtimeKline {
  t: number;
  s?: number | string;
  i?: number | string;
  o: string;
  h: string;
  l: string;
  c: string;
  v: string;
  [key: string]: unknown;
}

// 实时推送消息，data 可能多层嵌套
interface RealtimeMessage {
  k?: RealtimeKline;
  data?: unknown;
  [key: string]: unknown;
}

// 判断对象是否为实时K线（具备关键字段 t/o/c）
const isRealtimeKline = (value: unknown): value is RealtimeKline => {
  if (value === null || typeof value !== 'object') return false;
  const node = value as Record<string, unknown>;
  return typeof node.t === 'number' && typeof node.o === 'string' && typeof node.c === 'string';
};

// 从实时消息中解析K线，兼容多层 data 嵌套（保持原有 3 层解析逻辑）
const extractRealtimeKline = (message: unknown): RealtimeKline | null => {
  let current: unknown = message;
  for (let depth = 0; depth < 3; depth++) {
    if (!current || typeof current !== 'object') return null;
    const node = current as RealtimeMessage;
    if (node.k) return node.k;
    if (isRealtimeKline(node)) return node;
    current = node.data;
  }
  return null;
};

// 创建 signalTag 覆盖物图形：矩形标签 + 文字 + 圆点 + 连线
const createSignalTagPointFigures: OverlayCreateFiguresCallback<unknown> = ({ coordinates }: OverlayCreateFiguresCallbackParams<unknown>) => {
  const coord0 = coordinates[0];
  const coord1 = coordinates[1] as SignalTagCoordinate;
  if (!coord0 || !coord1) return [] as OverlayFigure[];

  const { extendData = {} } = coord1;
  const text = extendData.text || '';
  const color = extendData.color || '#1890ff';
  const side = extendData.side || 'buy';

  const px = coord0.x ?? 0;
  const py = coord0.y ?? 0;
  const p1x = coord1.x ?? px;
  const p1y = coord1.y ?? py;

  return [
    {
      title: text,
      type: 'rect',
      attrs: {
        x: px - 18,
        y: py - (side === 'buy' ? 22 : 2),
        width: 36,
        height: 20,
        fill: color,
        borderRadius: 3,
      },
    },
    {
      type: 'text',
      attrs: {
        x: px,
        y: py + (side === 'buy' ? -10 : 14),
        text: String(text),
        fill: '#FFFFFF',
        fontSize: 11,
        textAlign: 'center',
        textBaseline: 'middle',
      },
    },
    {
      type: 'circle',
      attrs: {
        x: px,
        y: py,
        r: 4,
        fill: color,
      },
    },
    {
      type: 'line',
      attrs: {
        coordinates: [
          { x: px, y: py },
          { x: p1x, y: p1y },
        ],
        stroke: color,
        strokeWidth: 1,
        size: 1,
      },
    },
  ] as OverlayFigure[];
};

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
  const { message } = App.useApp();

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('chart'));
  }, [t]);

  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<Nullable<Chart>>(null);

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
  const realtimeDataQueueRef = useRef<unknown[]>([]);
  const lastUpdateTimeRef = useRef<number>(0);
  const batchUpdateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const klineDataRef = useRef<KLineData[]>([]);
  const volInitializedRef = useRef(false);
  const customIndicatorDataRef = useRef<Map<string, {
    plots: IndicatorPlot[];
    figures: IndicatorFigureConfig[];
    plotKeys: string[];
    plotDataMap: Record<string, number[]>;
  }>>(new Map());

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
        // types/data 的 KlineData 与 klinecharts KLineData 字段一致（后者多 volume?/turnover? 可选字段与索引签名），此处做受控断言
        klineDataRef.current = data as unknown as KLineData[];

        if (chartInstanceRef.current) {
          chartInstanceRef.current.setDataLoader({
            getBars: ({ callback }: DataLoaderGetBarsParams) => {
              callback(klineDataRef.current);
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
  }, [currentSymbol, currentPeriod, message]);

  // 初始化图表
  useEffect(() => {
    // 注册自定义绘图工具扩展
    overlays.forEach(overlay => {
      registerOverlay(overlay);
    });

    // 注册信号标注overlay（一次性注册）
    try {
      registerOverlay({
        name: 'signalTag',
        totalStep: 2,
        lock: true,
        needDefaultPointFigure: false,
        needDefaultXAxisFigure: false,
        needDefaultYAxisFigure: false,
        createPointFigures: createSignalTagPointFigures,
      });
    } catch (e) {
      console.warn('[Chart] 注册signalTag overlay失败:', e);
    }

    if (chartRef.current && !chartInstanceRef.current) {
      const chart = init('language-k-line', {
        locale: 'zh-CN',
      });
      if (!chart) return;

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
        getBars: ({ callback }: DataLoaderGetBarsParams) => {
          callback(klineDataRef.current);
        }
      });

      // 加载初始数据
      loadKlineData();

      // 自动添加VOL指标，并同步状态（只执行一次）
      if (!volInitializedRef.current) {
        volInitializedRef.current = true;
        // 延迟执行确保K线数据已加载
        setTimeout(() => {
          try {
            if (!chartInstanceRef.current) return;
            
            const existingIndicators = chartInstanceRef.current.getIndicators() || [];
            const hasVolIndicator = existingIndicators.some((ind) => ind.name === 'VOL');
            
            // 如果图表上还没有VOL，则创建
            if (!hasVolIndicator) {
              chartInstanceRef.current.createIndicator('VOL', true);
            }
            
            // 同步状态（无论是否刚创建）
            setActiveIndicators(prev => {
              const alreadyExists = prev.some(ind => String(ind.id) === 'vol');
              if (alreadyExists) return prev;
              return [...prev, {
                id: 'vol',
                name: 'VOL',
                params: {},
                isCustom: false,
              }];
            });
          } catch (err) {
            console.error('创建VOL指标失败:', err);
          }
        }, 800);
      }
    }

    return () => {
      if (chartInstanceRef.current) {
        dispose('language-k-line');
        chartInstanceRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性初始化
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
      const response = await dataApi.getProducts({
        filter: searchKeyword || undefined,
        limit: 100,
      });

      // API 返回 { products: [...] } 格式
      // 后端商品对象可能带 name/exchange 等额外字段，用 ProductItem 承载（CryptoSymbol 为前端最小类型）
      const productsList = (response?.products || []) as unknown as ProductItem[];
      
      if (productsList.length > 0) {
        const products = productsList.map((item: ProductItem) => ({
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
  }, [searchKeyword, currentSymbol.code, message]);

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

  // 默认指标颜色序列
const DEFAULT_PLOT_COLORS = [
    '#1890ff', '#f5222d', '#52c41a', '#faad14', '#722ed1',
    '#13c2c2', '#eb2f96', '#fa8c16', '#a0d911', '#2f54eb',
  ];

  // 安全的figure key（避免klinecharts特殊字符）
  const sanitizeFigureKey = (name: string): string => {
      return name.replace(/[^a-zA-Z0-9_]/g, '_').substring(0, 30);
  };

  // 注册自定义指标到KLineCharts（支持多plots + 多figures）
  // eslint-disable-next-line react-hooks/exhaustive-deps -- 指标函数每渲染重建，补 deps 会重复执行
  const registerCustomIndicator = (indicator: Indicator, executeResult: IndicatorExecuteResult): string | null => {
      if (!executeResult || !executeResult.plots || !Array.isArray(executeResult.plots)) {
          console.error('[Indicator] 无效的执行结果格式');
          return null;
      }

      const indicatorName = `custom_${indicator.id}`;
      const plots = executeResult.plots;

      if (plots.length === 0) {
          console.warn('[Indicator] 指标无plots数据，跳过注册');
          return null;
      }

      // 构建plot数据映射：{ figureKey -> number[] }，过滤无效值并双向填充确保无null
      const plotDataMap: Record<string, number[]> = {};
      const plotKeys: string[] = [];
      plots.forEach((plot: IndicatorPlot, idx: number) => {
          const key = sanitizeFigureKey(plot.name || `plot_${idx}`);
          plotKeys.push(key);
          const raw: Array<number | null> = (plot.data || []).map((v) => {
              if (v === null || v === undefined) return null;
              if (typeof v === 'number' && !isFinite(v)) return null;
              return v;
          });
          let lastValid: number | null = null;
          const ffilled = raw.map((v: number | null) => {
              if (v !== null) { lastValid = v; return v; }
              return lastValid;
          });
           const firstValid = ffilled.find((v: number | null): v is number => v !== null);
           const data: number[] = ffilled.map((v: number | null) => v ?? firstValid ?? 0);
          plotDataMap[key] = data;
          
          });

      // 构建figures配置
      const figures: IndicatorFigureConfig[] = plots.map((plot: IndicatorPlot, idx: number) => ({
          key: sanitizeFigureKey(plot.name || `plot_${idx}`),
          title: plot.name || `Plot${idx + 1}`,
          type: plot.type || 'line' as const,
          color: plot.color || DEFAULT_PLOT_COLORS[idx % DEFAULT_PLOT_COLORS.length],
      }));

      try {
              // 确保 figures 中的 key 和 plotDataMap 一致
              const invalidFigures: string[] = [];
              const validFigures = figures.filter((fig) => {
                  const data = plotDataMap[fig.key];
                  if (!data || !Array.isArray(data) || data.length === 0) {
                      invalidFigures.push(`${fig.key}(no data)`);
                      return false;
                  }
                  const badValues = data.filter((v) => v === null || v === undefined || typeof v !== 'number' || !isFinite(v));
                  if (badValues.length > 0) {
                      invalidFigures.push(`${fig.key}(bad=${badValues.length}/${data.length})`);
                      return false;
                  }
                  return true;
              });
              
              if (invalidFigures.length > 0) {
                  console.warn(`[Indicator] 无效figures: ${invalidFigures.join(', ')}`);
              }

              if (validFigures.length === 0) {
                  console.warn('[Indicator] 无有效figures数据');
                  return null;
              }

              // 深度清理 plotDataMap：确保所有值都是有效数字
              const cleanedPlotDataMap: Record<string, number[]> = {};
              for (const fig of validFigures) {
                  const original = plotDataMap[fig.key];
                  cleanedPlotDataMap[fig.key] = original.map((v: number) => {
                      const clean = (typeof v === 'number' && isFinite(v) && !isNaN(v)) ? v : 0;
                      return clean;
                  });
              }

              // 缓存指标数据到 ref
              customIndicatorDataRef.current.set(indicatorName, {
                  plots,
                  figures: validFigures,
                  plotKeys,
                  plotDataMap: cleanedPlotDataMap,
              });

              // 构建 klinecharts figures 配置
              const kcFigures: IndicatorFigure[] = validFigures.map((fig) => {
                  const config = {
                      key: fig.key,
                      title: fig.title || fig.key,
                      type: 'line' as const,
                      color: fig.color || '#1890ff',
                      baseValue: 0,
                  };
                  return config;
              });

              // 注册透传型指标
              registerIndicator({
                  name: indicatorName,
                  shortName: indicator.name || 'Custom',
                  calc: (kLineDataList: KLineData[]) => {
                      
                      if (!kLineDataList || !Array.isArray(kLineDataList) || kLineDataList.length === 0) {
                          return [];
                      }
                      const cached = customIndicatorDataRef.current.get(indicatorName);
                      if (!cached) {
                          return [];
                      }
                      const { plotDataMap: dataMap, figures: figs } = cached;
                      
                      const result: Record<string, number>[] = [];
                      for (let i = 0; i < kLineDataList.length; i++) {
                          const point: Record<string, number> = {};
                          for (let j = 0; j < figs.length; j++) {
                              const fig = figs[j];
                              const dataArray = dataMap?.[fig.key];
                              let value: number = 0;
                              if (dataArray && Array.isArray(dataArray) && dataArray.length > 0) {
                                  const idx = Math.min(i, Math.max(0, dataArray.length - 1));
                                  const raw = dataArray[idx];
                                  value = (typeof raw === 'number' && isFinite(raw) && !isNaN(raw)) ? raw : 0;
                              }
                              point[fig.key] = value;
                          }
                          result.push(point);
                      }
                      
                      return result;
                  },
                  figures: kcFigures,
              });

              // 渲染信号overlay
              if (executeResult.signals && Array.isArray(executeResult.signals) && chartInstanceRef.current) {
                  renderSignalOverlays(executeResult.signals, klineDataRef.current);
              }

              return indicatorName;
          } catch (err) {
              console.error('[Indicator] 注册失败:', err);
              return null;
          }
  };

  // 解析信号数据为overlay点位
  const parseSignalData = (signal: IndicatorSignal, klineData: KLineData[]): SignalPoint[] => {
      const points: SignalPoint[] = [];
      if (!signal.data || !Array.isArray(signal.data)) return points;

      const isBuy = signal.type === 'buy';
      for (let i = 0; i < Math.min(signal.data.length, klineData.length); i++) {
          const val = signal.data[i];
          if (val === null || val === undefined || isNaN(val)) continue;

          const bar = klineData[i];
          if (!bar) continue;

          // 确保时间戳是有效数值
          let timestamp: number = 0;
          if (typeof bar.timestamp === 'number' && isFinite(bar.timestamp)) {
              timestamp = bar.timestamp;
          } else if (typeof bar.time === 'number' && isFinite(bar.time)) {
              timestamp = bar.time;
          } else {
              continue;
          }

          // 价格必须使用K线实际价格，而非信号值（信号值只是布尔标记，如0/1，不是价格）
          let price: number = 0;
          if (isBuy) {
              price = (typeof bar.low === 'number' && isFinite(bar.low)) ? bar.low : 0;
          } else {
              price = (typeof bar.high === 'number' && isFinite(bar.high)) ? bar.high : 0;
          }
          // 如果没有有效的K线价格，使用 close
          if (price === 0 || !isFinite(price)) {
              price = (typeof bar.close === 'number' && isFinite(bar.close)) ? bar.close : 0;
          }
          
          let anchorPrice: number = 0;
          if (isBuy) {
              anchorPrice = (typeof bar.close === 'number' && isFinite(bar.close)) ? bar.close : price;
          } else {
              anchorPrice = (typeof bar.close === 'number' && isFinite(bar.close)) ? bar.close : price;
          }
          
          // 最终兜底：确保绝对不是 undefined/NaN，跳过无效点位
          if (!isFinite(price) || price === 0) continue;
          if (!isFinite(anchorPrice) || anchorPrice === 0) anchorPrice = price;

          points.push({
              timestamp,
              price,
              anchorPrice,
              side: isBuy ? 'buy' : 'sell',
              color: signal.color || (isBuy ? '#00E676' : '#FF5252'),
              text: signal.text || (isBuy ? 'B' : 'S'),
          });
      }
      return points;
  };

  // 渲染信号overlay到图表上
  const renderSignalOverlays = (signals: IndicatorSignal[], klineData: KLineData[]) => {
      if (!chartInstanceRef.current) return;

      signals.forEach((signal) => {
          const points = parseSignalData(signal, klineData);
          points.forEach((point) => {
              // 数据校验：确保点位数据有效后再创建overlay，防止klinecharts内部碰撞检测崩溃
              if (!point || !isFinite(point.timestamp) || !isFinite(point.price) || !isFinite(point.anchorPrice)) {
                  return;
              }
              try {
                  chartInstanceRef.current?.createOverlay({
                      name: 'signalTag',
                      points: [
                          { timestamp: point.timestamp, value: point.price },
                          { timestamp: point.timestamp, value: point.anchorPrice },
                      ],
                      extendData: {
                          text: point.text,
                          color: point.color,
                          side: point.side,
                      },
                      lock: true,
                  });
              } catch (e) {
                  console.warn('[Signal] 创建overlay失败:', e);
              }
          });
      });
  };

  // 切换指标
  const handleToggleIndicator = useCallback(async (indicator: Indicator, params?: Record<string, unknown>) => {
    if (!chartInstanceRef.current) return;

    const builtInId = params?._builtInId;
    const indicatorId = builtInId ? String(builtInId) : String(indicator.id);
    const isActive = activeIndicators.some(ind => String(ind.id) === indicatorId);

    if (isActive) {
      // 停止指标
      const indicators = chartInstanceRef.current.getIndicators();
      indicators.forEach((ind) => {
        if (ind.name === indicatorId || ind.name === builtInIndicatorMap[indicatorId] || ind.name === `custom_${indicator.id}`) {
          chartInstanceRef.current?.removeIndicator({ paneId: ind.paneId, indicatorName: ind.name } as unknown as IndicatorFilter);
        }
      });
      // 清理自定义指标缓存数据
      customIndicatorDataRef.current.delete(`custom_${indicator.id}`);
      setActiveIndicators(prev => prev.filter(ind => String(ind.id) !== indicatorId));
    } else {
      // 启动指标
      const builtInName = builtInIndicatorMap[indicatorId];

      if (builtInName) {
        // 内置指标
        const isOverlay = ['MA', 'EMA', 'BOLL', 'SAR', 'BBI', 'SMA'].includes(builtInName);
        chartInstanceRef.current.createIndicator(
          builtInName,
          !isOverlay,
          { calcParams: params || {} } as unknown as PaneOptions,
        );
        // 同步更新activeIndicators状态
        setActiveIndicators(prev => [...prev, {
          id: indicatorId,
          name: builtInName,
          params,
          isCustom: false,
        }]);
      } else {
        // 自定义指标
        try {
          const token = getAccessToken();
          const currentKlineData = klineDataRef.current || [];
          console.log(`[自定义指标] 发送请求: indicatorId=${indicator.id}, klineData长度=${currentKlineData.length}`);
          
          const response = await fetch(`/api/indicators/${indicator.id}/execute`, {
            method: 'POST',
            headers: { 
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({
              symbol: currentSymbol.code,
              period: currentPeriod,
              params: params || {},
              klineData: currentKlineData,
            })
          });

          if (!response.ok) {
            if (response.status === 401) {
              message.error(t('indicator.authError', '登录已过期，请重新登录'));
              return;
            }
            throw new Error(`HTTP ${response.status}`);
          }

          const result = await response.json();

          if ((result.code === 0 || result.success) && result.data) {
            const customIndicatorName = registerCustomIndicator(indicator, result.data);
            if (customIndicatorName) {
              chartInstanceRef.current.createIndicator(customIndicatorName, true);
              setActiveIndicators(prev => [...prev, {
                id: indicatorId,
                name: indicator.name,
                params,
                isCustom: true,
              }]);
            } else {
              message.warning(t('indicator.registerError', '指标注册失败，请检查代码格式'));
            }
          } else {
            message.error(t('indicator.executeError', '指标执行失败') + ': ' + (result.message || '未知错误'));
          }
        } catch (err) {
          console.error('执行自定义指标失败:', err);
          message.error(t('indicator.executeFailed', '自定义指标执行失败') + ': ' + (err instanceof Error ? err.message : String(err)));
        }
      }
    }
  }, [activeIndicators, currentSymbol.code, currentPeriod, message, registerCustomIndicator, t]);

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
    overlays.forEach((overlay) => {
      chartInstanceRef.current?.overrideOverlay({ id: overlay.id, lock });
    });
  }, []);

  // 处理可见性变化
  const handleVisibleChange = useCallback((visible: boolean) => {
    if (!chartInstanceRef.current) return;
    const overlays = chartInstanceRef.current.getOverlays({ groupId: 'drawing_tools' });
    overlays.forEach((overlay) => {
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
        // 从实时消息（可能嵌套多层）中解析K线
        const kline = extractRealtimeKline(data);
        if (!kline) {
          return;
        }

        const bar: KLineData = {
          timestamp: kline.t,
          open: parseFloat(kline.o),
          high: parseFloat(kline.h),
          low: parseFloat(kline.l),
          close: parseFloat(kline.c),
          volume: parseFloat(kline.v),
        };

        const existingIndex = currentData.findIndex(
          (item) => item.timestamp === bar.timestamp
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
          getBars: ({ callback }: DataLoaderGetBarsParams) => {
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
  const handleRealtimeData = useCallback((data: unknown) => {
    if (!data) {
      console.warn('[Realtime] 接收到空数据');
      return;
    }

    const now = Date.now();
    const timeSinceLastUpdate = now - lastUpdateTimeRef.current;

    // 从实时消息（可能嵌套多层）中解析K线
    const kline = extractRealtimeKline(data);

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
