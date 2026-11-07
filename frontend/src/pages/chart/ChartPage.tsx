import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Input, Modal, Spin, Alert, App, Tooltip, theme } from 'antd';
import { CloseOutlined, SettingOutlined } from '@ant-design/icons';
import { init, dispose, type Nullable, registerIndicator, registerOverlay, registerLocale } from 'klinecharts';
import { calcLocalBuiltIn } from '../../utils/taBuiltins';
import { IndicatorParamModal } from '../../components/IndicatorParamModal';
import type {
  Chart,
  DataLoaderGetBarsParams,
  IndicatorFilter,
  IndicatorFigure,
  KLineData,
  OverlayCreateFiguresCallback,
  OverlayCreateFiguresCallbackParams,
  OverlayFigure,
  PeriodType,
} from 'klinecharts';
import { dataApi } from '../../api/dataApi';
import * as realtimeApi from '../../api/realtimeApi';
import DrawingBar from '../../components/DrawingBar';
import ChartPeriodBar, { type ChartPeriodItem } from '../../components/chart/ChartPeriodBar';
import { CHART_SETTING_DEFS } from '../../components/chart/ChartSettingModal';
import { setStyleValue } from '../../components/chart/chartStyles';
import RealtimeToggleButton from '../../components/RealtimeToggleButton';
import TokenDisplay from '../../components/TokenDisplay';
import { builtInIndicators, type Indicator, type ActiveIndicator, type IndicatorParams } from '../../hooks/useIndicators';
import { getAccessToken } from '../../utils/tokenManager';
// 导入自定义绘图工具扩展
import overlays from '../../extension/index';
import { setPageTitle } from '@/utils/pageTitle';
import { QUANT_COLORS } from '@/utils/colors';
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

// 上方工具栏平铺展示的全部周期（原「更多」里的 2H/1M/1Y 一并铺开）
const PERIOD_BAR_ITEMS: ChartPeriodItem[] = [...PERIODS, ...MORE_PERIODS].map(p => ({
  label: p.label,
  value: p.value,
}));

// 内置指标映射（id → klinecharts v10 内置指标名）
// 注意：该版本 klinecharts 无独立 ADX/ATR/MFI/AD/ADOSC 内置；
// ADX 由 DMI 承载（输出 PDI/MDI/ADX/ADXR），MFI/AD/ADOSC/ATR 走 utils/taBuiltins 本地计算
const builtInIndicatorMap: Record<string, string> = {
  'vol': 'VOL',
  'sma': 'MA',
  'ema': 'EMA',
  'rsi': 'RSI',
  'macd': 'MACD',
  'bb': 'BOLL',
  'cci': 'CCI',
  'wr': 'WR',
  'adx': 'DMI',
  'kdj': 'KDJ',
  'obv': 'OBV'
};

// 指标参数 localStorage 记忆（按 品种×指标 维度；用户调整过的参数刷新/切图后仍生效）
const indicatorParamsKey = (symbolCode: string, indicatorId: string) =>
  `qc:indicator-params:${symbolCode}:${indicatorId}`;

const loadStoredIndicatorParams = (symbolCode: string, indicatorId: string): Record<string, unknown> | null => {
  try {
    const raw = localStorage.getItem(indicatorParamsKey(symbolCode, indicatorId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const saveStoredIndicatorParams = (symbolCode: string, indicatorId: string, params: Record<string, unknown>) => {
  try {
    localStorage.setItem(indicatorParamsKey(symbolCode, indicatorId), JSON.stringify(params));
  } catch {
    // 隐私模式等场景写入失败可忽略，不影响本会话使用
  }
};

// params（含 _builtInId 标记）→ klinecharts calcParams 数值数组；依赖 defaultParams 键声明顺序与内置指标 calcParams 顺序一致
const toCalcParamArray = (params?: Record<string, unknown>): number[] =>
  Object.values(params || {}).filter((v): v is number => typeof v === 'number');

// 参数摘要（hover 工具条 chip 展示）：只拼数值参数，如 "12 26 9"
const paramSummary = (params?: Record<string, unknown>): string =>
  toCalcParamArray(params).join(' ');

// 参数编辑表单的 schema：内置/本地指标用 defaultParams 键；后端自定义指标无静态 schema，用当前参数键兜底
const getParamSchema = (active: ActiveIndicator | null): IndicatorParams => {
  if (!active) return {};
  const def = builtInIndicators.find(b => b.id === String(active.id));
  return def ? def.defaultParams : (active.params || {});
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

// 指标执行结果（对应后端 /api/v1/indicators/:id/execute 返回的 data）
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
  const color = extendData.color || QUANT_COLORS.info;
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
  // ponytail: klinecharts 独立于 antd theme，需要从 token 派生主题感知的样式值
  const { token: themeToken } = theme.useToken();

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('chart'));
  }, [t]);

  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<Nullable<Chart>>(null);
  // 全屏目标：包含上方工具栏与图表的主体容器
  const fullscreenTargetRef = useRef<HTMLDivElement>(null);

  // 品种和周期状态
  const [currentSymbol, setCurrentSymbol] = useState<Symbol>({
    code: 'BTCUSDT',
    name: 'BTC/USDT',
    base: 'BTC'
  });
  const [currentPeriod, setCurrentPeriod] = useState('1h');

  // 上方工具栏状态：左侧绘图栏是否展开、图表时区、Y 轴是否反转
  const [spread, setSpread] = useState(true);
  const [timezone, setTimezone] = useState('Asia/Shanghai');
  // ponytail: v10 没有公开读取轴 reverse 的接口，这里自己记一份，供设置弹窗回显
  const [yAxisReverse, setYAxisReverse] = useState(false);

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

  // 指标 hover 工具条（TradingView 式）：当前悬停 pane、其相对 chart-area 的纵向偏移、参数弹窗正在编辑的指标
  const [hoveredPaneId, setHoveredPaneId] = useState<string | null>(null);
  const [hoveredPaneTop, setHoveredPaneTop] = useState(0);
  const [paramModalActive, setParamModalActive] = useState<ActiveIndicator | null>(null);
  const chartAreaRef = useRef<HTMLDivElement>(null);
  // 工具条 DOM：用于 leave 判断鼠标去向是否是浮层自身（防闪烁，见 hidePane）
  const toolbarRef = useRef<HTMLDivElement>(null);
  // 工具条消失延迟定时器：鼠标从 pane 移向浮层的间隙不立即隐藏
  const hoverHideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);



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

      // 兜底：init 时若容器处于布局过渡态（如侧边栏宽度恢复/首帧 flex 计算），
      // 量到的是过期宽度并会一直僵持；隔两帧按最终布局宽度强制重绘一次
      requestAnimationFrame(() => requestAnimationFrame(() => chart.resize()));

      // ponytail: 网格线和 K 线配色从 antd theme token 派生，主题切换时自动适配
      chart.setStyles({
        grid: {
          show: true,
          horizontal: {
            show: true,
            size: 1,
            color: themeToken.colorBorderSecondary,
            style: 'dashed',
          },
          vertical: {
            show: true,
            size: 1,
            color: themeToken.colorBorderSecondary,
            style: 'dashed',
          },
        },
        candle: {
          bar: {
            // ponytail: K 线配色保持 TradingView 行业惯例（绿涨红跌），
            // 但跟随暗/亮主题调整亮度，避免在暗色模式下刺眼
            upColor: themeToken.colorBgBase === '#17191c' ? '#52c7b8' : '#26A69A',
            downColor: themeToken.colorBgBase === '#17191c' ? '#ff8a80' : '#EF5350',
            noChangeColor: themeToken.colorTextTertiary ?? '#888888',
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

      // 自动添加 VOL 指标（只执行一次）：复用 startIndicator 的内置指标链路，
      // 补齐 paneId/params/original —— 旧实现手写 state 只有 id/name 且 params 为空，
      // 导致 VOL 没有 hover 工具条（paneId 为空匹配不到 pane）、⚙ 参数弹窗也无法落盘
      if (!volInitializedRef.current) {
        volInitializedRef.current = true;
        // 延迟执行确保K线数据已加载
        setTimeout(() => {
          try {
            const chart = chartInstanceRef.current;
            if (!chart) return;
            // 图表上已存在 VOL 时跳过（避免重复 createIndicator，幂等防御）
            const hasVol = (chart.getIndicators() || []).some((ind) => ind.name === 'VOL');
            const volDef = builtInIndicators.find(b => b.id === 'vol');
            if (hasVol || !volDef) return;
            void startIndicator(volDef as unknown as Indicator, volDef.defaultParams);
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

  // ponytail: 指标调色板从 antd theme token 派生（涨跌语义色），
  // 剩余 4 个饱和色（紫/粉/亮绿/靛蓝）是区分多条指标线的 palette，
  // 保留硬编码不跟随主题——用户习惯用这些颜色区分不同指标。
  const DEFAULT_PLOT_COLORS = useMemo(() => [
    themeToken.colorInfo,
    themeToken.colorError,
    themeToken.colorSuccess,
    themeToken.colorWarning,
    '#722ed1',  // 紫
    themeToken.colorInfo,
    '#eb2f96',  // 粉
    themeToken.colorWarning,
    '#a0d911',  // 亮绿
    '#2f54eb',  // 靛蓝
  ], [themeToken.colorInfo, themeToken.colorError, themeToken.colorSuccess, themeToken.colorWarning]);

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
                      color: fig.color || themeToken.colorInfo,
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

  // ===== 指标生命周期：启动 / 停止 / 切换 / 改参数 =====
  // 拆成独立函数而非在单一 toggle 里判断"当前是否激活"：同一次 render 闭包中连续
  // stop→start 会读到旧的 activeIndicators 快照（stale closure），按 id 配对才可靠

  // 请求后端执行自定义指标，返回执行结果；失败时提示并返回 null
  const executeBackendIndicator = useCallback(async (indicator: Indicator, params?: Record<string, unknown>): Promise<IndicatorExecuteResult | null> => {
    try {
      const token = getAccessToken();
      const response = await fetch(`/api/v1/indicators/${indicator.id}/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          symbol: currentSymbol.code,
          period: currentPeriod,
          params: params || {},
          klineData: klineDataRef.current || [],
        })
      });

      if (!response.ok) {
        if (response.status === 401) {
          message.error(t('indicator.authError', '登录已过期，请重新登录'));
          return null;
        }
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      if ((result.code === 0 || result.success) && result.data) {
        return result.data as IndicatorExecuteResult;
      }
      message.error(t('indicator.executeError', '指标执行失败') + ': ' + (result.message || '未知错误'));
      return null;
    } catch (err) {
      console.error('执行自定义指标失败:', err);
      message.error(t('indicator.executeFailed', '自定义指标执行失败') + ': ' + (err instanceof Error ? err.message : String(err)));
      return null;
    }
  }, [currentSymbol.code, currentPeriod, message, t]);

  // 启动指标（不判断是否已激活）。params 缺省时优先使用该品种的 localStorage 记忆参数
  const startIndicator = useCallback(async (indicator: Indicator, params?: Record<string, unknown>) => {
    const chart = chartInstanceRef.current;
    if (!chart) return;

    const indicatorId = String(indicator.id);
    const storedParams = loadStoredIndicatorParams(currentSymbol.code, indicatorId);
    // 记忆参数优先于调用方传入的 defaultParams
    const effectiveParams = storedParams ? { ...params, ...storedParams } : params;
    const builtInName = builtInIndicatorMap[indicatorId];

    if (builtInName) {
      // 内置指标（v10：参数并入 createIndicator 的 value 对象，isStack 作为第二参）
      const isOverlay = ['MA', 'EMA', 'BOLL', 'SAR', 'BBI', 'SMA'].includes(builtInName);
      // v10 的 calcParams 必须是数值数组（内置指标 calc 内部会调用 params.map），
      // 而 modal 传来的是对象（如 { fast:12, slow:26, signal:9, _builtInId:'macd' }）；
      // defaultParams 的键声明顺序与 klinecharts 内置指标默认 calcParams 顺序一致，
      // 按声明顺序展开并剔除 _builtInId 标记字段与非数值即可。
      chart.createIndicator({ name: builtInName, calcParams: toCalcParamArray(effectiveParams) }, !isOverlay);
      // createIndicator 返回的是指标 id 而非 paneId，按注册名反查所在 pane 供 hover 工具条定位
      const paneId = chart.getIndicators().find(ind => ind.name === builtInName)?.paneId;
      setActiveIndicators(prev => [...prev, {
        id: indicatorId,
        name: builtInName,
        params: effectiveParams,
        isCustom: false,
        paneId,
        original: indicator,
      }]);
      return;
    }

    // 自定义指标；klinecharts 未内置的常用指标（MFI/AD/ADOSC/ATR）先走本地计算，
    // 未命中再请求后端自定义指标执行接口（要求 int 指标 ID，内置字符串 ID 会 422）
    const localResult = calcLocalBuiltIn(indicatorId, klineDataRef.current || [], effectiveParams);
    const result = localResult ?? await executeBackendIndicator(indicator, effectiveParams);
    if (!result) return;

    const customIndicatorName = registerCustomIndicator(indicator, result);
    if (!customIndicatorName) {
      message.warning(t('indicator.registerError', '指标注册失败，请检查代码格式'));
      return;
    }
    chart.createIndicator(customIndicatorName, true);
    const paneId = chart.getIndicators().find(ind => ind.name === customIndicatorName)?.paneId;
    setActiveIndicators(prev => [...prev, {
      id: indicatorId,
      name: indicator.name,
      params: effectiveParams,
      isCustom: true,
      paneId,
      original: indicator,
    }]);
  }, [currentSymbol.code, executeBackendIndicator, message, registerCustomIndicator, t]);

  // 按 id 停止指标（幂等：已不存在时静默返回）
  const stopIndicatorById = useCallback((indicatorId: string) => {
    const chart = chartInstanceRef.current;
    if (!chart) return;
    const indicators = chart.getIndicators();
    indicators.forEach((ind) => {
      if (ind.name === indicatorId || ind.name === builtInIndicatorMap[indicatorId] || ind.name === `custom_${indicatorId}`) {
        chart.removeIndicator({ paneId: ind.paneId, indicatorName: ind.name } as unknown as IndicatorFilter);
      }
    });
    // 清理自定义指标缓存数据
    customIndicatorDataRef.current.delete(`custom_${indicatorId}`);
    setActiveIndicators(prev => prev.filter(ind => String(ind.id) !== indicatorId));
  }, []);

  // 切换指标：已激活则停止，未激活则启动
  const handleToggleIndicator = useCallback(async (indicator: Indicator, params?: Record<string, unknown>) => {
    const indicatorId = String(params?._builtInId ?? indicator.id);
    if (activeIndicators.some(ind => String(ind.id) === indicatorId)) {
      stopIndicatorById(indicatorId);
    } else {
      await startIndicator(indicator, params);
    }
  }, [activeIndicators, startIndicator, stopIndicatorById]);

  // 参数更新入口（图例 ⚙ → 弹窗确认）：确认后回写 localStorage 记忆。
  // 内置指标走 overrideIndicator 直接改 calcParams 重算；本地/后端自定义指标重算数据后
  // 更新缓存再触发一次重算（calc 闭包实时读 customIndicatorDataRef，无闪烁、不换 pane）
  const handleUpdateIndicatorParams = useCallback(async (active: ActiveIndicator, newParams: IndicatorParams) => {
    const chart = chartInstanceRef.current;
    const indicator = active.original;
    if (!chart || !indicator) return;

    const indicatorId = String(active.id);
    saveStoredIndicatorParams(currentSymbol.code, indicatorId, newParams);

    const builtInName = !active.isCustom ? builtInIndicatorMap[indicatorId] : undefined;
    if (builtInName) {
      chart.overrideIndicator({ name: builtInName, calcParams: toCalcParamArray(newParams) });
    } else {
      const localResult = calcLocalBuiltIn(indicatorId, klineDataRef.current || [], newParams);
      const result = localResult ?? await executeBackendIndicator(indicator, newParams);
      if (!result) return;
      registerCustomIndicator(indicator, result);
      // 用 overrideIndicator 触发实例重算，此时 calc 闭包读到的已是新缓存数据
      chart.overrideIndicator({ name: `custom_${indicatorId}` });
    }

    setActiveIndicators(prev => prev.map(ind => String(ind.id) === indicatorId ? { ...ind, params: newParams } : ind));
  }, [currentSymbol.code, executeBackendIndicator, registerCustomIndicator]);

  // ===== 图例 hover 工具条：pane 的 mouseenter/mouseleave 绑定 =====
  // 指标增删会创建/销毁 pane，故在 activeIndicators 变化后重新绑定
  useEffect(() => {
    const chart = chartInstanceRef.current;
    if (!chart) return;

    const showPane = (paneId: string, dom: HTMLElement) => {
      if (hoverHideTimerRef.current) {
        clearTimeout(hoverHideTimerRef.current);
        hoverHideTimerRef.current = null;
      }
      // 浮层挂在 chart-area 上，需把 pane 顶部换算为相对 chart-area 的偏移
      const areaTop = chartAreaRef.current?.getBoundingClientRect().top ?? 0;
      setHoveredPaneTop(dom.getBoundingClientRect().top - areaTop);
      setHoveredPaneId(paneId);
    };
    const hidePane = (e: MouseEvent) => {
      // 防闪烁（命中测试自噬）：浮层挂在 chart-area 而非 pane 内部，浮层挂载瞬间
      // 恰好盖住鼠标 → pane 触发 mouseleave 且 relatedTarget 是浮层自身；此时若启动
      // 隐藏 timer，会陷入「挂载→leave→卸载→重新挂载」的闪烁循环。鼠标移向浮层
      // 内部时直接忽略这次 leave，循环就此斩断。
      if (e.relatedTarget && toolbarRef.current?.contains(e.relatedTarget as Node)) return;
      if (hoverHideTimerRef.current) clearTimeout(hoverHideTimerRef.current);
      // 150ms 间隙：给鼠标从 pane 移到浮层留时间，浮层 onMouseEnter 会取消隐藏
      hoverHideTimerRef.current = setTimeout(() => {
        setHoveredPaneId(null);
        hoverHideTimerRef.current = null;
      }, 150);
    };

    const cleanups: Array<() => void> = [];
    const paneOptions = chart.getPaneOptions();
    const panes = Array.isArray(paneOptions) ? paneOptions : paneOptions ? [paneOptions] : [];
    panes.forEach(({ id }) => {
      const dom = chart.getDom(id);
      if (!dom) return;
      const enter = () => showPane(id, dom);
      dom.addEventListener('mouseenter', enter);
      dom.addEventListener('mouseleave', hidePane);
      cleanups.push(() => {
        dom.removeEventListener('mouseenter', enter);
        dom.removeEventListener('mouseleave', hidePane);
      });
    });

    return () => {
      cleanups.forEach((fn) => fn());
      if (hoverHideTimerRef.current) {
        clearTimeout(hoverHideTimerRef.current);
        hoverHideTimerRef.current = null;
      }
    };
  }, [activeIndicators]);

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

  // 设置项统一入口：样式路径走 setStyles；Y 轴反转在 v10 不属于 styles，需走 overrideYAxis
  const applyChartSetting = useCallback((path: string, value: unknown) => {
    const chart = chartInstanceRef.current;
    if (!chart) return;
    if (path === 'yAxis.reverse') {
      chart.overrideYAxis({ reverse: Boolean(value) });
      setYAxisReverse(Boolean(value));
      return;
    }
    // klinecharts setStyles 是深合并，局部路径更新即可
    const styles: Record<string, unknown> = {};
    setStyleValue(styles, path, value);
    chart.setStyles(styles as Parameters<Chart['setStyles']>[0]);
  }, []);

  // 读取当前样式，并把轴上的 reverse 补进去（设置弹窗回显用）
  const getChartSettings = useCallback(() => {
    const chart = chartInstanceRef.current;
    if (!chart) return {} as Record<string, unknown>;
    const styles = chart.getStyles() as unknown as Record<string, unknown>;
    return { ...styles, yAxis: { ...(styles.yAxis as object), reverse: yAxisReverse } };
  }, [yAxisReverse]);

  // 恢复默认：逐项还原为 klinecharts 默认值
  const handleRestoreDefaultSettings = useCallback(() => {
    CHART_SETTING_DEFS.forEach(({ path, defaultValue }) => applyChartSetting(path, defaultValue));
  }, [applyChartSetting]);

  // 切换时区
  const handleTimezoneSelect = useCallback((nextTimezone: string) => {
    chartInstanceRef.current?.setTimezone(nextTimezone);
    setTimezone(nextTimezone);
  }, []);

  // 截图：导出含 overlay 的 jpeg，底色跟随当前主题
  const getScreenshotUrl = useCallback(() => {
    const chart = chartInstanceRef.current;
    if (!chart) return '';
    const backgroundColor = document.documentElement.classList.contains('dark') ? '#151517' : '#ffffff';
    return chart.getConvertPictureUrl(true, 'jpeg', backgroundColor);
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

  // 当前悬停 pane 内的指标（决定 hover 工具条是否显示与显示内容）
  const paneIndicators = hoveredPaneId
    ? activeIndicators.filter(ind => ind.paneId === hoveredPaneId)
    : [];

  return (
    <div className="chart-page-fullscreen page-fullscreen">
      <div className="chart-page" ref={fullscreenTargetRef}>
        {/* 上方工具栏：复刻 klinecharts-pro 的 period-bar，最右接实时行情开关 */}
        <ChartPeriodBar
          spread={spread}
          onToggleSpread={() => setSpread(prev => !prev)}
          symbol={currentSymbol}
          periods={PERIOD_BAR_ITEMS}
          currentPeriod={currentPeriod}
          onChangePeriod={setCurrentPeriod}
          activeIndicators={activeIndicators}
          onToggleIndicator={handleToggleIndicator}
          realtimeSlot={
            <RealtimeToggleButton
              symbol={currentSymbol.code}
              period={currentPeriod.toLowerCase()}
              defaultRealtimeEnabled={systemConfig.realtime_enabled}
              onRealtimeData={handleRealtimeData}
              onStatusChange={handleRealtimeStatusChange}
            />
          }
          onOpenSymbolSearch={() => setSearchVisible(true)}
          currentTimezone={timezone}
          onTimezoneSelect={handleTimezoneSelect}
          getSettings={getChartSettings}
          onSettingChange={applyChartSetting}
          onRestoreDefaultSettings={handleRestoreDefaultSettings}
          getScreenshotUrl={getScreenshotUrl}
          fullscreenTarget={fullscreenTargetRef}
        />

        {/* 主图表区域 - 包含常驻的左侧绘图工具栏 */}
        <div className="chart-main-with-toolbar">
          {/* 左侧常驻绘图工具栏（菜单收起时隐藏） */}
          {spread && (
            <div className="drawing-toolbar-vertical">
              <DrawingBar
                onDrawingItemClick={handleDrawingItemClick}
                onModeChange={handleModeChange}
                onLockChange={handleLockChange}
                onVisibleChange={handleVisibleChange}
                onRemoveClick={handleRemoveClick}
              />
            </div>
          )}

          {/* 图表区域 */}
          <div className="chart-area" ref={chartAreaRef}>
          {error && (
            <Alert
              title="错误"
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

          {/* 指标图例 hover 工具条：贴 pane 顶部浮出，⚙ 改参数 / × 移除；无指标的 pane 不显示 */}
          {hoveredPaneId && paneIndicators.length > 0 && (
            <div
              ref={toolbarRef}
              className="indicator-hover-toolbar"
              style={{ top: hoveredPaneTop + 6 }}
              onMouseEnter={() => {
                if (hoverHideTimerRef.current) {
                  clearTimeout(hoverHideTimerRef.current);
                  hoverHideTimerRef.current = null;
                }
              }}
              onMouseLeave={() => {
                hoverHideTimerRef.current = setTimeout(() => setHoveredPaneId(null), 150);
              }}
            >
              {paneIndicators.map((ind) => (
                <div key={String(ind.id)} className="indicator-hover-chip">
                  <span className="chip-name">
                    {ind.name}
                    {paramSummary(ind.params) && (
                      <span className="chip-params">({paramSummary(ind.params)})</span>
                    )}
                  </span>
                  <Tooltip title="修改参数">
                    <Button
                      type="text"
                      size="small"
                      icon={<SettingOutlined />}
                      aria-label={`修改 ${ind.name} 参数`}
                      onClick={() => setParamModalActive(ind)}
                    />
                  </Tooltip>
                  <Tooltip title="移除指标">
                    <Button
                      type="text"
                      size="small"
                      icon={<CloseOutlined />}
                      aria-label={`移除 ${ind.name}`}
                      onClick={() => stopIndicatorById(String(ind.id))}
                    />
                  </Tooltip>
                </div>
              ))}
            </div>
          )}
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

        {/* 指标参数编辑弹窗（图例 hover 工具条的 ⚙ 触发） */}
        <IndicatorParamModal
          open={!!paramModalActive}
          indicatorName={paramModalActive?.name ?? ''}
          paramSchema={getParamSchema(paramModalActive)}
          initialValues={(paramModalActive?.params as IndicatorParams) || {}}
          onOk={(values) => {
            if (paramModalActive) {
              handleUpdateIndicatorParams(paramModalActive, values);
            }
            setParamModalActive(null);
          }}
          onCancel={() => setParamModalActive(null)}
        />
      </div>
    </div>
  );
};

export default ChartPage;
