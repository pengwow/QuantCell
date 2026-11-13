/**
 * 共享图表壳：从 ChartPage 抽取的「纯图表」部分。
 *
 * 职责（数据无关，/chart 与行情回放页共用）：
 * - klinecharts 实例初始化/销毁、主题样式、语言包、绘图扩展注册
 * - 上方周期栏（周期/品种显示/指标/时区/设置/截图/全屏）
 * - 指标生命周期（内置 + 本地计算自定义指标；indicatorScope 控制是否开放后端自定义指标）
 * - 左侧绘图工具栏与画图事件
 * - 指标图例 hover 工具条与参数编辑弹窗
 *
 * 职责外（由页面持有）：行情数据加载、实时订阅队列、品种搜索弹窗、页面标题。
 * 页面通过 `getBars()` 提供当前数据数组，壳只读不缓存；数据更新后调用
 * `refreshData()` 重新喂数（内部重新 setDataLoader + resize）。
 */

import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, forwardRef } from 'react';
import { Alert, App, Button, Spin, Tooltip, theme } from 'antd';
import { CloseOutlined, SettingOutlined } from '@ant-design/icons';
import {
  init,
  dispose,
  registerIndicator,
  registerOverlay,
  registerLocale,
  type Nullable,
  type Chart,
  type CandleStyle,
  type DataLoaderGetBarsParams,
  type IndicatorFilter,
  type IndicatorFigure,
  type KLineData,
  type OverlayCreateFiguresCallback,
  type OverlayCreateFiguresCallbackParams,
  type OverlayFigure,
} from 'klinecharts';
import { calcLocalBuiltIn } from '../../utils/taBuiltins';
import {
  buildHeikinAshiRows,
  buildHlcAreaRows,
  buildRenkoBricks,
  buildRangeBars,
} from '../../utils/priceChartTransforms';
import { getAccessToken } from '../../utils/tokenManager';
import { QUANT_COLORS } from '@/utils/colors';
import { builtInIndicators, type Indicator, type ActiveIndicator, type IndicatorParams } from '../../hooks/useIndicators';
// 导入自定义绘图工具扩展
import overlays from '../../extension/index';
import ChartPeriodBar, { type ChartPeriodItem } from './ChartPeriodBar';
import { CHART_SETTING_DEFS } from './ChartSettingModal';
import { setStyleValue } from './chartStyles';
import { findPeriodItem } from './chartConstants';
import {
  cancelPendingSaves,
  loadChartPrefs,
  loadIndicatorParams,
  restorePriceStyle,
  saveIndicatorParams,
  savePriceStyleValue,
  saveUiPrefs,
} from '../../services/chartPreferences';
import DrawingBar from '../DrawingBar';
import { IndicatorParamModal } from '../IndicatorParamModal';
// 样式沿用 ChartPage 的图表布局 CSS（chart-page/period-bar/hover 工具条等类名）
import '../../pages/chart/ChartPage.css';

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

// ===== 蜡烛图类型扩展 =====
// v10 原生只有 6 种 candle shape，其余类型通过下面两条路径补充：
// 1. 复用 area 渲染：line（纯线，面积背景透明）、hlc_area（三角均值 + 渐变背景）
// 2. 复用 candle_solid 渲染 + 数据变换：heikin_ashi/renko/range（变换见 utils/priceChartTransforms）
const CANDLE_TYPE_TO_NATIVE: Record<string, CandleStyle['type']> = {
  line: 'area',
  hlc_area: 'area',
  heikin_ashi: 'candle_solid',
  renko: 'candle_solid',
  range: 'candle_solid',
};

// 需要把原始 K 线变换为派生 bar 后再喂数的类型（其余类型直接透传原始数据）
const DERIVED_PRICE_TYPES = new Set(['heikin_ashi', 'hlc_area', 'renko', 'range']);

// v10 默认 area 渐变背景（klinecharts 内置 Color.BLUE 派生，离开纯线形时按此值恢复渐变）
const AREA_DEFAULT_BG = [
  { offset: 0, color: 'rgba(22, 119, 255, 0.01)' },
  { offset: 1, color: 'rgba(22, 119, 255, 0.2)' },
];
const AREA_TRANSPARENT_BG = 'rgba(22, 119, 255, 0)';

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

// 壳接收的品种描述（code 必填）
export interface ChartShellSymbol {
  code: string;
  name?: string;
  base?: string;
}

// 指标能力范围：all = 内置 + 本地 + 后端自定义；builtin-local = 只允许内置 + 本地计算
export type IndicatorScope = 'all' | 'builtin-local';

export interface ChartShellHandle {
  getChart: () => Nullable<Chart>;
  /** 数据更新后统一喂数入口：重新 setDataLoader + resize（等价原页面散落的 setDataLoader 调用） */
  refreshData: () => void;
  /** 用最新 getBars() 数据重算所有本地/自定义指标（内置指标由 klinecharts 基于新数据自算，无需处理） */
  recalculateIndicators: () => void;
  /** 重算「需后端执行」的自定义指标（回放页逐 bar 喂新数据后调用；内部 1s 尾沿节流 + 在途门闩） */
  recalcBackendIndicators: () => void;
}

export interface ChartShellProps {
  /** klinecharts 容器 DOM id（页面间不能重复，如 /chart 用 'language-k-line'） */
  chartId: string;
  symbol: ChartShellSymbol;
  /** 上方周期栏平铺项 */
  periods: ChartPeriodItem[];
  currentPeriod: string;
  onChangePeriod: (period: string) => void;
  /** 页面提供当前K线数组（供 dataLoader 回调与指标重算），壳不持有数据 */
  getBars: () => KLineData[];
  onOpenSymbolSearch?: () => void;
  /** 工具栏最右的插槽（/chart 放实时开关；回放页不传） */
  realtimeSlot?: React.ReactNode;
  /** 左侧绘图工具栏常驻不收起（回放页使用；/chart 缺省可收起） */
  drawingBarLocked?: boolean;
  indicatorScope: IndicatorScope;
  loading?: boolean;
  error?: string | null;
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

// 注册繁体中文语言包（模块级一次性注册）
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

const ChartShell = forwardRef<ChartShellHandle, ChartShellProps>(({
  chartId,
  symbol,
  periods,
  currentPeriod,
  onChangePeriod,
  getBars,
  onOpenSymbolSearch,
  realtimeSlot,
  drawingBarLocked = false,
  indicatorScope,
  loading = false,
  error = null,
}, ref) => {
  const { message } = App.useApp();
  // ponytail: klinecharts 独立于 antd theme，需要从 token 派生主题感知的样式值
  const { token: themeToken } = theme.useToken();

  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<Nullable<Chart>>(null);
  // 全屏目标：包含上方工具栏与图表的主体容器
  const fullscreenTargetRef = useRef<HTMLDivElement>(null);

  // 上方工具栏状态：左侧绘图栏是否展开、图表时区、Y 轴是否反转
  // 绘图工具栏默认收起（点周期栏汉堡按钮展开）；行情回放页 drawingBarLocked 恒显不受此影响
  const [spread, setSpread] = useState(false);
  const [timezone, setTimezone] = useState('Asia/Shanghai');
  // ponytail: v10 没有公开读取轴 reverse 的接口，这里自己记一份，供设置弹窗回显
  const [yAxisReverse, setYAxisReverse] = useState(false);

  // 指标状态
  const [activeIndicators, setActiveIndicators] = useState<ActiveIndicator[]>([]);
  // recalculateIndicators 等 imperative 接口需要读最新指标列表，用 ref 桥接
  const activeIndicatorsRef = useRef<ActiveIndicator[]>([]);
  activeIndicatorsRef.current = activeIndicators;

  // 指标 hover 工具条（TradingView 式）：当前悬停 pane、其相对 chart-area 的纵向偏移、参数弹窗正在编辑的指标
  const [hoveredPaneId, setHoveredPaneId] = useState<string | null>(null);
  const [hoveredPaneTop, setHoveredPaneTop] = useState(0);
  const [paramModalActive, setParamModalActive] = useState<ActiveIndicator | null>(null);
  const chartAreaRef = useRef<HTMLDivElement>(null);
  // 工具条 DOM：用于 leave 判断鼠标去向是否是浮层自身（防闪烁，见 hidePane）
  const toolbarRef = useRef<HTMLDivElement>(null);
  // 工具条消失延迟定时器：鼠标从 pane 移向浮层的间隙不立即隐藏
  const hoverHideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 页面数据通过 getBars() 注入；用 ref 保存最新引用，避免 dataLoader/imperative 闭包读到过期页面数据
  const getBarsRef = useRef(getBars);
  getBarsRef.current = getBars;

  // 自定义指标数据缓存：calc 闭包实时读取（重算数据只需更新缓存 + overrideIndicator）
  const customIndicatorDataRef = useRef<Map<string, {
    plots: IndicatorPlot[];
    figures: IndicatorFigureConfig[];
    plotKeys: string[];
    plotDataMap: Record<string, number[]>;
  }>>(new Map());
  // 自动添加 VOL 指标（只执行一次）
  const volInitializedRef = useRef(false);

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

  // 构建 plot 数据映射：{ figureKey -> number[] }，过滤无效值并双向填充确保无null。
  // 从 registerCustomIndicator 拆出：register 与 recalculate 共用同一份清洗逻辑，
  // 重算时只更新缓存再触发 override，不重复注册指标。
  const buildCustomIndicatorCache = useCallback((executeResult: IndicatorExecuteResult) => {
    if (!executeResult || !executeResult.plots || !Array.isArray(executeResult.plots)) {
      console.error('[Indicator] 无效的执行结果格式');
      return null;
    }
    const plots = executeResult.plots;
    if (plots.length === 0) {
      console.warn('[Indicator] 指标无plots数据，跳过注册');
      return null;
    }

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

    return {
      plots,
      figures: validFigures,
      plotKeys,
      plotDataMap: cleanedPlotDataMap,
    };
  }, [DEFAULT_PLOT_COLORS]);

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

  // 注册自定义指标到KLineCharts（清洗数据 + 注册 + 渲染信号）
  const registerCustomIndicator = useCallback((indicator: Indicator, executeResult: IndicatorExecuteResult): string | null => {
    const indicatorName = `custom_${indicator.id}`;
    const cache = buildCustomIndicatorCache(executeResult);
    if (!cache) return null;

    // 缓存指标数据到 ref（calc 闭包实时读取）
    customIndicatorDataRef.current.set(indicatorName, cache);

    // 构建 klinecharts figures 配置
    const kcFigures: IndicatorFigure[] = cache.figures.map((fig) => {
      const config = {
        key: fig.key,
        title: fig.title || fig.key,
        type: 'line' as const,
        color: fig.color || themeToken.colorInfo,
        baseValue: 0,
      };
      return config;
    });

    try {
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
        renderSignalOverlays(executeResult.signals, getBarsRef.current());
      }

      return indicatorName;
    } catch (err) {
      console.error('[Indicator] 注册失败:', err);
      return null;
    }
    // themeToken 随主题变化，这里以注册时主题为准即可（figures 颜色为补充语义）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildCustomIndicatorCache]);

  // 请求后端执行自定义指标，返回执行结果；失败时提示并返回 null。
  // builtin-local 范围（回放页）直接拒绝——不允许回放场景触发自定义指标后端执行
  const executeBackendIndicator = useCallback(async (indicator: Indicator, params?: Record<string, unknown>): Promise<IndicatorExecuteResult | null> => {
    if (indicatorScope === 'builtin-local') {
      return null;
    }
    try {
      const token = getAccessToken();
      const response = await fetch(`/api/v1/indicators/${indicator.id}/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          symbol: symbol.code,
          period: currentPeriod,
          params: params || {},
          klineData: getBarsRef.current() || [],
        })
      });

      if (!response.ok) {
        if (response.status === 401) {
          message.error('登录已过期，请重新登录');
          return null;
        }
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      if ((result.code === 0 || result.success) && result.data) {
        return result.data as IndicatorExecuteResult;
      }
      message.error('指标执行失败' + ': ' + (result.message || '未知错误'));
      return null;
    } catch (err) {
      console.error('执行自定义指标失败:', err);
      message.error('自定义指标执行失败' + ': ' + (err instanceof Error ? err.message : String(err)));
      return null;
    }
  }, [indicatorScope, symbol.code, currentPeriod, message]);

  // 启动指标（不判断是否已激活）。params 缺省时优先使用该品种的记忆参数（后端 chart 组，含旧 localStorage 迁移值）
  const startIndicator = useCallback(async (indicator: Indicator, params?: Record<string, unknown>) => {
    const chart = chartInstanceRef.current;
    if (!chart) return;

    const indicatorId = String(indicator.id);
    // 指标参数快照依赖 loadChartPrefs 完成后建立的模块级缓存（幂等 Promise，已是重入调用）
    await loadChartPrefs();
    const storedParams = loadIndicatorParams(symbol.code, indicatorId);
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
    // 未命中再请求后端自定义指标执行接口（builtin-local 范围下 executeBackendIndicator 直接返回 null）
    const localResult = calcLocalBuiltIn(indicatorId, getBarsRef.current() || [], effectiveParams);
    const result = localResult ?? await executeBackendIndicator(indicator, effectiveParams);
    if (!result) return;

    const customIndicatorName = registerCustomIndicator(indicator, result);
    if (!customIndicatorName) {
      message.warning('指标注册失败，请检查代码格式');
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
  }, [symbol.code, executeBackendIndicator, message, registerCustomIndicator]);

  // startIndicator 的命令式调用桥（VOL 自动添加在 init effect 闭包里调用，取最新引用）
  const startIndicatorRef = useRef(startIndicator);
  startIndicatorRef.current = startIndicator;

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
    // 移除该指标挂过的信号标注，避免数据重算后残留旧点位
    const signalOverlays = chart.getOverlays({ name: 'signalTag' });
    signalOverlays.forEach((overlay) => {
      if (overlay.groupId === `custom_${indicatorId}`) {
        chart.removeOverlay({ id: overlay.id });
      }
    });
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

  // 参数更新入口（图例 ⚙ → 弹窗确认）：确认后回写后端参数记忆（fire-and-forget）。
  // 内置指标走 overrideIndicator 直接改 calcParams 重算；本地/后端自定义指标重算数据后
  // 更新缓存再触发一次重算（calc 闭包实时读 customIndicatorDataRef，无闪烁、不换 pane）
  const handleUpdateIndicatorParams = useCallback(async (active: ActiveIndicator, newParams: IndicatorParams) => {
    const chart = chartInstanceRef.current;
    const indicator = active.original;
    if (!chart || !indicator) return;

    const indicatorId = String(active.id);
    // 参数记忆写后端（即时动态键；同步更新快照，弹窗内再读立即可见）
    saveIndicatorParams(symbol.code, indicatorId, newParams);

    const builtInName = !active.isCustom ? builtInIndicatorMap[indicatorId] : undefined;
    if (builtInName) {
      chart.overrideIndicator({ name: builtInName, calcParams: toCalcParamArray(newParams) });
    } else {
      const localResult = calcLocalBuiltIn(indicatorId, getBarsRef.current() || [], newParams);
      const result = localResult ?? await executeBackendIndicator(indicator, newParams);
      if (!result) return;
      registerCustomIndicator(indicator, result);
      // 用 overrideIndicator 触发实例重算，此时 calc 闭包读到的已是新缓存数据
      chart.overrideIndicator({ name: `custom_${indicatorId}` });
    }

    setActiveIndicators(prev => prev.map(ind => String(ind.id) === indicatorId ? { ...ind, params: newParams } : ind));
  }, [symbol.code, executeBackendIndicator, registerCustomIndicator]);

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
  const handleModeChange = useCallback((_mode: string) => {
    // 绘图模式由 DrawingBar 内部维护，壳无需处理
  }, []);

  // 处理锁定变化
  const handleLockChange = useCallback((lock: boolean) => {
    if (!chartInstanceRef.current) return;
    const overlaysList = chartInstanceRef.current.getOverlays({ groupId: 'drawing_tools' });
    overlaysList.forEach((overlay) => {
      chartInstanceRef.current?.overrideOverlay({ id: overlay.id, lock });
    });
  }, []);

  // 处理可见性变化
  const handleVisibleChange = useCallback((visible: boolean) => {
    if (!chartInstanceRef.current) return;
    const overlaysList = chartInstanceRef.current.getOverlays({ groupId: 'drawing_tools' });
    overlaysList.forEach((overlay) => {
      chartInstanceRef.current?.overrideOverlay({ id: overlay.id, visible });
    });
  }, []);

  // 处理删除
  const handleRemoveClick = useCallback((groupId: string) => {
    if (!chartInstanceRef.current) return;
    chartInstanceRef.current.removeOverlay({ groupId });
  }, []);

  // 当前语义蜡烛类型（下拉值）；ref 供数据闭包读取，state 供设置弹窗回显
  const [semanticCandleType, setSemanticCandleType] = useState<string>('candle_solid');
  const semanticCandleTypeRef = useRef<string>('candle_solid');

  // 按当前蜡烛类型把原始 K 线变换为图表显示数据：
  // heikin_ashi/renko/range/hlc_area 输出派生 bar，其余类型透传原始数据。
  // 指标与图例都消费这条喂数链路，与主图联动保持一致
  const getDisplayBars = useCallback((bars: KLineData[]): KLineData[] => {
    switch (semanticCandleTypeRef.current) {
      case 'heikin_ashi': return buildHeikinAshiRows(bars);
      case 'hlc_area': return buildHlcAreaRows(bars);
      case 'renko': return buildRenkoBricks(bars);
      case 'range': return buildRangeBars(bars);
      default: return bars;
    }
  }, []);

  // 重新喂数（内部重新 setDataLoader + resize）；页面 ref 与蜡烛类型切换共用
  const refreshChartData = useCallback(() => {
    const chart = chartInstanceRef.current;
    if (!chart) return;
    chart.setDataLoader({
      getBars: ({ callback }: DataLoaderGetBarsParams) => {
        callback(getDisplayBars(getBarsRef.current()));
      }
    });
    chart.resize();
  }, [getDisplayBars]);

  // 设置项统一入口：样式路径走 setStyles；Y 轴反转在 v10 不属于 styles，需走 overrideYAxis。
  // persist=false 用于偏好回放与恢复默认（读到的值/默认值不回写，否则会把服务端值原样再写一遍）
  const applyChartSetting = useCallback((path: string, value: unknown, persist = true) => {
    const chart = chartInstanceRef.current;
    if (!chart) return;
    if (path === 'yAxis.reverse') {
      chart.overrideYAxis({ reverse: Boolean(value) });
      setYAxisReverse(Boolean(value));
      // 注意：此处不走 return 短路前的公共保存口，统一落在各分支末尾
      if (persist) savePriceStyleValue(path, value);
      return;
    }
    // 蜡烛图类型特判：派生类型不是合法的 v10 chartType，需映射为原生形状；
    // area 家族还要切换渐变背景（线形图透明面积）；随后重新喂数以刷新派生 bar
    if (path === 'candle.type') {
      const nextType = String(value);
      const nativeType = CANDLE_TYPE_TO_NATIVE[nextType] ?? (nextType as CandleStyle['type']);
      semanticCandleTypeRef.current = nextType;
      setSemanticCandleType(nextType);
      // 线形图 = area 渲染 + 透明面积背景；其余场景恢复默认渐变，避免从线形切回后残留透明
      const areaBg = nativeType === 'area' && nextType === 'line'
        ? AREA_TRANSPARENT_BG
        : AREA_DEFAULT_BG;
      chart.setStyles({ candle: { type: nativeType, area: { backgroundColor: areaBg } } });
      if (DERIVED_PRICE_TYPES.has(nextType)) {
        refreshChartData();
      }
      if (persist) savePriceStyleValue(path, value);
      return;
    }
    // klinecharts setStyles 是深合并，局部路径更新即可
    const styles: Record<string, unknown> = {};
    setStyleValue(styles, path, value);
    chart.setStyles(styles as Parameters<Chart['setStyles']>[0]);
    if (persist) savePriceStyleValue(path, value);
  }, [refreshChartData]);

  // 读取当前样式，并把轴上的 reverse 补进去（设置弹窗回显用）；
  // candle.type 回显语义类型而非映射后的原生 chartType
  const getChartSettings = useCallback(() => {
    const chart = chartInstanceRef.current;
    if (!chart) return {} as Record<string, unknown>;
    const styles = chart.getStyles() as unknown as Record<string, unknown>;
    return {
      ...styles,
      candle: { ...(styles.candle as object), type: semanticCandleType },
      yAxis: { ...(styles.yAxis as object), reverse: yAxisReverse },
    };
  }, [yAxisReverse, semanticCandleType]);

  // 恢复默认：取消 pending 防抖 + 删除后端 priceStyle，再按默认值重置图表（不回写）
  const handleRestoreDefaultSettings = useCallback(() => {
    cancelPendingSaves();
    restorePriceStyle();
    CHART_SETTING_DEFS.forEach(({ path, defaultValue }) => applyChartSetting(path, defaultValue, false));
  }, [applyChartSetting]);

  // 切换时区：图表生效并持久化到 uiPrefs
  const handleTimezoneSelect = useCallback((nextTimezone: string) => {
    chartInstanceRef.current?.setTimezone(nextTimezone);
    setTimezone(nextTimezone);
    saveUiPrefs({ timezone: nextTimezone });
  }, []);

  // 截图：导出含 overlay 的 jpeg，底色跟随当前主题
  const getScreenshotUrl = useCallback(() => {
    const chart = chartInstanceRef.current;
    if (!chart) return '';
    const backgroundColor = document.documentElement.classList.contains('dark') ? '#151517' : '#ffffff';
    return chart.getConvertPictureUrl(true, 'jpeg', backgroundColor);
  }, []);

  // ===== 初始化图表（挂载时一次性）=====
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
      const chart = init(chartId, {
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
      const period = findPeriodItem(currentPeriod);
      chart.setSymbol({ ticker: symbol.code, name: symbol.name });
      chart.setPeriod({
        span: period?.span || 1,
        type: period?.type || 'minute',
      });

      // 设置数据加载器（数据由页面通过 getBars 提供；派生蜡烛类型在喂数时统一变换）
      chart.setDataLoader({
        getBars: ({ callback }: DataLoaderGetBarsParams) => {
          callback(getDisplayBars(getBarsRef.current()));
        }
      });

      // 自动添加 VOL 指标（只执行一次）：复用 startIndicator 的内置指标链路，
      // 补齐 paneId/params/original —— 旧实现手写 state 只有 id/name 且 params 为空，
      // 导致 VOL 没有 hover 工具条（paneId 为空匹配不到 pane）、⚙ 参数弹窗也无法落盘
      if (!volInitializedRef.current) {
        volInitializedRef.current = true;
        // 延迟执行确保K线数据已加载
        setTimeout(() => {
          try {
            const chartNow = chartInstanceRef.current;
            if (!chartNow) return;
            // 图表上已存在 VOL 时跳过（避免重复 createIndicator，幂等防御）
            const hasVol = (chartNow.getIndicators() || []).some((ind) => ind.name === 'VOL');
            const volDef = builtInIndicators.find(b => b.id === 'vol');
            if (hasVol || !volDef) return;
            void startIndicatorRef.current(volDef as unknown as Indicator, volDef.defaultParams);
          } catch (err) {
            console.error('创建VOL指标失败:', err);
          }
        }, 800);
      }
    }

    return () => {
      if (chartInstanceRef.current) {
        dispose(chartId);
        chartInstanceRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性初始化
  }, [chartId]);

  // 偏好回放：图表先按默认创建，后端 chart 组加载完成后逐项应用保存值。
  // 只在挂载时回放一次，applyChartSetting 为稳定 useCallback，故意固定空依赖
  useEffect(() => {
    let cancelled = false;
    loadChartPrefs().then(({ priceStyle, uiPrefs }) => {
      if (cancelled || !chartInstanceRef.current) return;
      // persist=false：回放不触发保存，否则把刚读到的值原样写回服务端
      for (const [path, value] of Object.entries(priceStyle)) {
        applyChartSetting(path, value, false);
      }
      if (uiPrefs.timezone) {
        chartInstanceRef.current?.setTimezone(uiPrefs.timezone);
        setTimezone(uiPrefs.timezone);
      }
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性回放
  }, []);

  // symbol / period 变化（或壳晚于页面初始化完成）时同步到图表
  useEffect(() => {
    const chart = chartInstanceRef.current;
    if (!chart) return;
    const period = findPeriodItem(currentPeriod);
    chart.setSymbol({ ticker: symbol.code, name: symbol.name });
    chart.setPeriod({
      span: period?.span || 1,
      type: period?.type || 'minute',
    });
  }, [symbol.code, symbol.name, currentPeriod]);

  // 监听图表容器大小变化
  useEffect(() => {
    const chartElement = document.getElementById(chartId);
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
  }, [chartId]);

  // 后端自定义指标重算的节流状态：连续喂数合并为一次请求；执行在途时新调用只挂 pending，
  // 完成后补一发尾沿，慢指标自动降频
  const backendRecalcStateRef = useRef<{ timer?: number; pending?: boolean; inFlight?: boolean }>({});

  // 尾沿节流的重算调度（回放场景专用入口）。1s 节流 + 在途门闩：
  // 播放中每根 bar 的喂数最多合并为 1 次/秒的 /execute 请求，指标执行慢时由门闩自动降频。
  // 递归引用自身实现在途完成后补尾沿，deps 不含自身（运行时引用已赋值）
   
  const recalcBackendIndicators = useCallback(() => {
    if (indicatorScope !== 'all') return;
    const st = backendRecalcStateRef.current;
    if (st.inFlight) { st.pending = true; return; }
    if (st.timer != null) return;
    st.timer = window.setTimeout(async () => {
      st.timer = undefined;
      st.inFlight = true;
      try {
        const chart = chartInstanceRef.current;
        if (!chart) return;
        const bars = getBarsRef.current() || [];
        for (const active of activeIndicatorsRef.current) {
          const indicatorId = String(active.id);
          if (builtInIndicatorMap[indicatorId] && !active.isCustom) continue;
          if (!active.original) continue;
          // 本地计算的指标走 recalculateIndicators 通道，这里只处理需后端执行的
          if (calcLocalBuiltIn(indicatorId, bars, active.params)) continue;
          const result = await executeBackendIndicator(active.original, active.params);
          if (!result) continue;
          const cache = buildCustomIndicatorCache(result);
          if (!cache) continue;
          customIndicatorDataRef.current.set(`custom_${indicatorId}`, cache);
          chart.overrideIndicator({ name: `custom_${indicatorId}` });
        }
      } finally {
        st.inFlight = false;
        if (st.pending) {
          st.pending = false;
          recalcBackendIndicators();
        }
      }
    }, 1000);
  }, [indicatorScope, executeBackendIndicator, buildCustomIndicatorCache]);

  // 命令式接口：页面通过 ref 触发喂数与指标重算
  useImperativeHandle(ref, () => ({
    getChart: () => chartInstanceRef.current,
    // 喂数统一走蜡烛类型变换 helper，确保派生类型（平均K/砖形等）与主图类型一致
    refreshData: refreshChartData,
    recalculateIndicators: () => {
      const chart = chartInstanceRef.current;
      if (!chart) return;
      const bars = getBarsRef.current() || [];
      // 内置指标由 klinecharts 基于新数据自动重算；
      // 本地/自定义指标（MFI/AD/ADOSC/ATR + 后端指标）需要用最新数据重建缓存再触发重算
      activeIndicatorsRef.current.forEach((active) => {
        const indicatorId = String(active.id);
        if (builtInIndicatorMap[indicatorId] && !active.isCustom) return;
        if (!active.original) return;
        const localResult = calcLocalBuiltIn(indicatorId, bars, active.params);
        if (!localResult) {
          // 无本地计算的指标（后端自定义）在 builtin-local 范围下不存在；all 范围下重算数据需后端，
          // 这里保守跳过（缓存数据长度由 calc 的 idx clamp 兜底）
          return;
        }
        const cache = buildCustomIndicatorCache(localResult);
        if (!cache) return;
        customIndicatorDataRef.current.set(`custom_${indicatorId}`, cache);
        chart.overrideIndicator({ name: `custom_${indicatorId}` });
      });
    },
    recalcBackendIndicators,
  }), [buildCustomIndicatorCache, indicatorScope, executeBackendIndicator, recalcBackendIndicators, refreshChartData]);

  // 当前悬停 pane 内的指标（决定 hover 工具条是否显示与显示内容）
  const paneIndicators = hoveredPaneId
    ? activeIndicators.filter(ind => ind.paneId === hoveredPaneId)
    : [];

  return (
    <div className="chart-page-fullscreen page-fullscreen">
      <div className="chart-page" ref={fullscreenTargetRef}>
        {/* 上方工具栏：复刻 klinecharts-pro 的 period-bar，最右接页面自定义插槽 */}
        <ChartPeriodBar
          spread={spread}
          // 锁定时不传回调：周期栏隐藏收起按钮，绘图栏常驻
          onToggleSpread={drawingBarLocked ? undefined : () => setSpread(prev => !prev)}
          symbol={symbol}
          periods={periods}
          currentPeriod={currentPeriod}
          onChangePeriod={onChangePeriod}
          activeIndicators={activeIndicators}
          onToggleIndicator={handleToggleIndicator}
          realtimeSlot={realtimeSlot}
          onOpenSymbolSearch={() => onOpenSymbolSearch?.()}
          currentTimezone={timezone}
          onTimezoneSelect={handleTimezoneSelect}
          getSettings={getChartSettings}
          onSettingChange={applyChartSetting}
          onRestoreDefaultSettings={handleRestoreDefaultSettings}
          getScreenshotUrl={getScreenshotUrl}
          fullscreenTarget={fullscreenTargetRef}
          indicatorScope={indicatorScope}
        />

        {/* 主图表区域 - 包含常驻的左侧绘图工具栏 */}
        <div className="chart-main-with-toolbar">
          {/* 左侧常驻绘图工具栏（锁定时恒显；否则菜单收起时隐藏） */}
          {(drawingBarLocked || spread) && (
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
                id={chartId}
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
});

ChartShell.displayName = 'ChartShell';

export default ChartShell;
