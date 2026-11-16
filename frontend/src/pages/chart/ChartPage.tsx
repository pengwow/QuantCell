import { useEffect, useRef, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Input, Modal, Spin, App } from 'antd';
import type { KLineData } from 'klinecharts';
import { dataApi } from '../../api/dataApi';
import { backtestApi } from '../../api';
import * as realtimeApi from '../../api/realtimeApi';
import RealtimeToggleButton from '../../components/RealtimeToggleButton';
import TokenDisplay from '../../components/TokenDisplay';
import ChartShell, { type ChartShellHandle } from '../../components/chart/ChartShell';
import { PERIOD_BAR_ITEMS } from '../../components/chart/chartConstants';
import { OrderBookPanel } from '../../components/chart/orderbook/OrderBookPanel';
import { TradeTape } from '../../components/chart/orderbook/TradeTape';
import type { FillPoint } from '../../components/chart/orderbook/fillMarkers';
import type { DepthProfileSnapshot } from '../../components/chart/orderbook/depthOverlay';
import wsService from '../../services/websocketService';
import {
  loadChartPrefs,
  saveUiPrefs,
  saveOrderbookPrefs,
  getOrderbookPrefsSnapshot,
  type OrderbookPrefs,
} from '../../services/chartPreferences';
import { setPageTitle } from '@/utils/pageTitle';
// 搜索弹窗的样式类（symbol-search-results 等）定义在此文件中
import './ChartPage.css';

interface Symbol {
  code: string;
  name: string;
  exchange?: string;
  base?: string;
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

// 实时数据更新配置
const REALTIME_UPDATE_CONFIG = {
  throttleInterval: 100,
  maxVisibleBars: 200,
  batchThreshold: 5,
  batchInterval: 200,
};

// 后端 ProductItem -> 前端 Symbol 最小映射（历史口径：缺省 name 用 symbol 兜底）
const toSymbols = (list: ProductItem[]): Symbol[] =>
  list.map((item: ProductItem) => ({
    code: item.symbol,
    name: item.name || item.symbol,
    exchange: item.exchange,
    base: item.base,
  }));

/**
 * 实时图表页：只负责数据加载、实时订阅队列、品种搜索与系统配置自动连接。
 * 图表实例、指标、画图、周期栏、设置等通用能力全部由共享壳 ChartShell 承载
 * （与行情回放页共用同一壳）。
 */
const ChartPage = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();

  // 共享壳句柄：数据更新后通过它重新喂数
  const shellRef = useRef<ChartShellHandle>(null);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('chart'));
  }, [t]);

  // 品种和周期状态
  const [currentSymbol, setCurrentSymbol] = useState<Symbol>({
    code: 'BTCUSDT',
    name: 'BTC/USDT',
    base: 'BTC'
  });
  // WS 内部品种口径无斜杠（如 ETHUSDT）；currentSymbol.code 来自品种列表，可能带斜杠（ETH/USDT）。
  // 引擎频道订阅与 depth/trades 过滤必须用无斜杠口径，否则永远匹配不上（TradeTape 曾因此恒空态）
  const wsSymbol = currentSymbol.code.replace('/', '');
  // 供 processBatchUpdate 等稳定回调读取当前品种（避免 useCallback 依赖抖动引起下游订阅重建）
  const wsSymbolRef = useRef(wsSymbol);
  wsSymbolRef.current = wsSymbol;
  const [currentPeriod, setCurrentPeriod] = useState('1h');

  // 加载状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 搜索弹窗状态
  const [searchVisible, setSearchVisible] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchResults, setSearchResults] = useState<Symbol[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // 实时数据状态：realtimeActive 是「引擎就绪」信号（RealtimeToggleButton 完成启动/连接后才回调 true），
  // 引擎频道的订阅必须等它就位，否则页面加载早期必报「订阅失败」
  const [realtimeActive, setIsRealtimeActive] = useState(false);
  const [systemConfig, setSystemConfig] = useState({
    realtime_enabled: false,
    data_mode: 'cache' as 'realtime' | 'cache',
  });

  // 实时数据引用
  const realtimeDataQueueRef = useRef<unknown[]>([]);
  const lastUpdateTimeRef = useRef<number>(0);
  const batchUpdateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const klineDataRef = useRef<KLineData[]>([]);
  // K线请求序号：品种/周期切换并发拉取时，只有最后一次请求允许写回 klineDataRef（防旧响应盖新图）
  const klineReqSeqRef = useRef(0);

  // 保存用户偏好：写后端 chart.uiPrefs（800ms 防抖合并，见 services/chartPreferences）
  const saveUserPreferences = (symbol: string, period: string) => {
    saveUiPrefs({ symbol, period });
  };

  // 加载K线数据：拿到数据后由壳统一喂数（内部重新 setDataLoader + resize）
  const loadKlineData = useCallback(async () => {
    const seq = ++klineReqSeqRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await dataApi.getKlines({
        symbol: currentSymbol.code,
        interval: currentPeriod,
        limit: 500,
      });

      // 竞态守卫：慢的旧请求返回时直接丢弃，否则旧品种数据会覆盖新品种图表
      if (seq !== klineReqSeqRef.current) return;

      // API 返回的数据已经是正确的格式，直接使用
      if (data && Array.isArray(data)) {
        // types/data 的 KlineData 与 klinecharts KLineData 字段一致（后者多 volume?/turnover? 可选字段与索引签名），此处做受控断言
        klineDataRef.current = data as unknown as KLineData[];
        shellRef.current?.refreshData();
      }
    } catch (error) {
      // 过时请求的失败同样静默丢弃，避免已被取代的旧请求误报错误
      if (seq !== klineReqSeqRef.current) return;
      setError('加载K线数据失败');
      message.error('加载K线数据失败');
      console.error('加载K线数据失败:', error);
    } finally {
      setLoading(false);
    }
  }, [currentSymbol, currentPeriod, message]);

  // 当品种或周期变化时重新加载数据（setSymbol/setPeriod 由壳内部响应 props 变化完成）
  const preferSavingRef = useRef(false);
  useEffect(() => {
    loadKlineData();
    // 首渲染不保存：防止 load 完成前以默认 BTCUSDT/1h 覆盖服务端偏好
    if (preferSavingRef.current) {
      saveUserPreferences(currentSymbol.code, currentPeriod);
    }
    preferSavingRef.current = true;
  }, [currentSymbol, currentPeriod, loadKlineData]);

  // 组件挂载时读取图表偏好：恢复周期；品种需与商品列表对账取完整 Symbol 对象
  useEffect(() => {
    let cancelled = false;
    loadChartPrefs().then(async ({ uiPrefs }) => {
      if (cancelled) return;
      if (uiPrefs.period) setCurrentPeriod(uiPrefs.period);
      const preferredCode = uiPrefs.symbol;
      if (!preferredCode) return;
      try {
        const response = await dataApi.getProducts({ filter: preferredCode, limit: 20 });
        const productsList = (response?.products || []) as unknown as ProductItem[];
        if (cancelled) return;
        const hit = toSymbols(productsList).find((p: Symbol) => p.code === preferredCode);
        if (hit) {
          // 与切品种同理：清空默认品种数据，防 setSymbol 快照成「偏好 ticker + 默认品种图」
          klineDataRef.current = [];
          setCurrentSymbol(hit);
        }
      } catch {
        // 商品列表拉取失败保持默认品种，不打扰
      }
    });
    return () => { cancelled = true; };
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

  // ========== 订单簿 / 深度轮廓 / 成交流水接线（设置开关 + WS 订阅 + 回测成交标记） ==========

  // 订单簿面板/深度轮廓/成交流水偏好：挂载后从后端一次性回放
  const [orderbookPrefs, setOrderbookPrefs] = useState<OrderbookPrefs | null>(null);
  const [depthData, setDepthData] = useState<DepthProfileSnapshot | null>(null);
  const [backtestFills, setBacktestFills] = useState<FillPoint[]>([]);
  const [backtestOptions, setBacktestOptions] = useState<{ label: string; value: string }[]>([]);
  // WS 连接标记：动态 topic 订阅在断线重连后不会自动恢复，用它作为订阅 effect 的依赖触发重订阅
  const [wsConnected, setWsConnected] = useState(wsService.getConnected());

  useEffect(() => {
    let cancelled = false;
    loadChartPrefs().then(() => {
      if (!cancelled) setOrderbookPrefs(getOrderbookPrefsSnapshot());
    });
    return () => { cancelled = true; };
  }, []);

  // 设置弹窗的偏好更新：patch 为「顶层键完整值」粒度（见 ChartSettingModal 各 onChange），
  // 浅合并单步 setState 即可，落库复用 saveOrderbookPrefs 的 800ms 防抖（弹窗仅在偏好非空时打开，
  // prev 兜底取当前快照防载入竞态）
  const updateOrderbookPrefs = useCallback((patch: Partial<OrderbookPrefs>) => {
    setOrderbookPrefs((prev) => ({ ...(prev ?? getOrderbookPrefsSnapshot()), ...patch }));
    saveOrderbookPrefs(patch);
  }, []);

  useEffect(() => {
    const onConnectionChange = (connected: boolean) => setWsConnected(connected);
    wsService.onConnectionChange(onConnectionChange);
    return () => wsService.offConnectionChange(onConnectionChange);
  }, []);

  // 盘口深度/成交流水的喂流需求：面板或深度轮廓开 → 交易所 depth20 引擎频道 + 'depth' 广播 topic；
  // 成交流水开 → aggTrade 引擎频道 + 'trades' 广播 topic。条件变化/断线重连时对称增删
  const needsDepthFeed = (orderbookPrefs?.panel ?? false) || (orderbookPrefs?.depthProfile ?? false);
  const needsTradeFeed = orderbookPrefs?.tradeTape ?? false;

  // 引擎频道的交易所侧订阅（depth20/aggTrade）：必须等实时引擎就绪（realtimeActive），
  // 提前发起会被 engine.subscribe 拒绝并返回「订阅失败」；与下方 WS 广播 topic 订阅解耦
  useEffect(() => {
    if (!realtimeActive || (!needsDepthFeed && !needsTradeFeed)) return;
    const channels: string[] = [];
    if (needsDepthFeed) {
      // 引擎频道固定 depth20 档快照流，与显示档数（depthLevels）解耦：渲染在前端截取。
      // 必须显式 @100ms：币安部分订单簿流默认 1s 推一条，不带后缀订单簿只有 1Hz
      channels.push(`${wsSymbol}@depth20@100ms`);
    }
    if (needsTradeFeed) {
      channels.push(`${wsSymbol}@aggTrade`);
    }
    realtimeApi.subscribeKlineChannels(channels).catch((e) => {
      console.error('[ChartPage] Failed to subscribe depth/trade engine channels:', e);
    });
    return () => {
      realtimeApi.unsubscribeKlineChannels(channels).catch(() => {});
    };
  }, [realtimeActive, needsDepthFeed, needsTradeFeed, wsSymbol]);

  // WS 广播 topic（depth/trades）由常驻 ws_push 消费者产出，与引擎启动时序无关，仅随 WS 连接触发
  useEffect(() => {
    if (!wsConnected || (!needsDepthFeed && !needsTradeFeed)) return;
    const topics: string[] = [];
    if (needsDepthFeed) {
      topics.push('depth');
    }
    if (needsTradeFeed) {
      topics.push('trades');
    }
    wsService.subscribe(topics);
    return () => {
      wsService.unsubscribe(topics);
    };
  }, [needsDepthFeed, needsTradeFeed, currentSymbol.code, wsConnected]);

  // 深度轮廓数据 listener：仅开关开启时收集；topic 收发由上面的订阅 effect 统一持有
  const depthProfileOn = orderbookPrefs?.depthProfile ?? false;
  useEffect(() => {
    if (!depthProfileOn) {
      setDepthData(null); // 关闭时清残快照，避免重开瞬间闪旧数据
      return;
    }
    const handleDepth = (data: unknown) => {
      const snapshot = data as { symbol?: string; bids?: [number, number][]; asks?: [number, number][] } | null;
      if (!snapshot?.bids?.length || !snapshot?.asks?.length) return;
      setDepthData({
        // overlay 按 WS 口径（大写）比对品种，这里统一大写化
        symbol: (snapshot.symbol ?? currentSymbol.code).toUpperCase(),
        bids: snapshot.bids,
        asks: snapshot.asks,
        timestamp: Date.now(),
      });
    };
    wsService.on('depth', handleDepth);
    return () => wsService.off('depth', handleDepth);
  }, [depthProfileOn, currentSymbol.code]);

  // 回测成交点：设置里选定回测任务后按 T9 契约拉 fills_detail（秒级时间戳），
  // 换算毫秒 FillPoint 传给壳画 replay 标记；清空选择 / 品种切换时同步清理
  const backtestFillTaskId = orderbookPrefs?.tradeMarkers?.backtestId ?? null;
  useEffect(() => {
    if (!backtestFillTaskId) {
      setBacktestFills([]);
      return;
    }
    let cancelled = false;
    backtestApi.getBacktestDetail(backtestFillTaskId)
      .then((detail) => {
        if (cancelled) return;
        setBacktestFills((detail.fills_detail ?? []).map((fill) => ({
          timestamp: fill.timestamp * 1000, // fills_detail 秒级 → FillPoint 毫秒
          side: fill.side === 'sell' ? 'sell' : 'buy',
          price: fill.price,
          quantity: fill.quantity,
          source: 'backtest' as const,
        })));
      })
      .catch((e) => {
        console.warn('[ChartPage] Failed to fetch backtest fills:', backtestFillTaskId, e);
        if (!cancelled) setBacktestFills([]);
      });
    return () => { cancelled = true; };
  }, [backtestFillTaskId, currentSymbol.code]);

  // 回测任务下拉（设置弹窗选用）：ponytail 挂载时一次性拉取，新任务需刷新页面 —— 升级路径为打开弹窗时重拉
  useEffect(() => {
    let cancelled = false;
    backtestApi.getBacktestList({ page: 1, page_size: 50 })
      .then((resp) => {
        if (cancelled) return;
        setBacktestOptions((resp.backtests ?? []).map((task) => ({
          label: `${task.strategy_name} ${task.created_at.slice(0, 16).replace('T', ' ')}`,
          value: task.id,
        })));
      })
      .catch((e) => console.warn('[ChartPage] Failed to fetch backtest task list:', e));
    return () => { cancelled = true; };
  }, []);

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
        setSearchResults(toSymbols(productsList));
      } else {
        setSearchResults([]);
      }
    } catch (error) {
      message.error('搜索失败');
      console.error('搜索品种失败:', error);
    } finally {
      setSearchLoading(false);
    }
  }, [searchKeyword, message]);

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
    // 切品种必须先清空旧 K 线：ChartShell（子组件）的 setSymbol effect 先于本页加载 effect 执行，
    // klinecharts 的 setSymbol 会同步回调 getBars，把 ref 里的旧品种数据快照成新品种的图
    klineDataRef.current = [];
    setCurrentSymbol(symbol);
    setSearchVisible(false);
    setSearchKeyword('');
    saveUserPreferences(symbol.code, currentPeriod);
  };

  // 切周期与切品种同理：setPeriod 触发的同步 getBars 会把旧周期数据快照成新周期图，先清空
  const handleChangePeriod = useCallback((period: string) => {
    klineDataRef.current = [];
    setCurrentPeriod(period);
  }, []);

  // 批量处理实时数据更新
  const processBatchUpdate = useCallback(() => {
    if (realtimeDataQueueRef.current.length === 0) return;

    const queue = realtimeDataQueueRef.current;

    try {
      const currentData = klineDataRef.current || [];

      queue.forEach((data) => {
        // 从实时消息（可能嵌套多层）中解析K线
        const kline = extractRealtimeKline(data);
        if (!kline) {
          return;
        }

        // 品种过滤：切品种瞬间旧订阅的残留推送不得混入新图（消息缺 s 字段时无法判定，放行）
        if (kline.s != null && String(kline.s).toUpperCase() !== wsSymbolRef.current.toUpperCase()) {
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
        // 数据已在 klineDataRef 更新完毕，通知壳重新喂数（setDataLoader + resize）
        shellRef.current?.refreshData();
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

  return (
    <>
      <ChartShell
        ref={shellRef}
        chartId="language-k-line"
        symbol={currentSymbol}
        periods={PERIOD_BAR_ITEMS}
        currentPeriod={currentPeriod}
        onChangePeriod={handleChangePeriod}
        getBars={() => klineDataRef.current}
        onOpenSymbolSearch={() => setSearchVisible(true)}
        realtimeSlot={
          <RealtimeToggleButton
            symbol={currentSymbol.code}
            period={currentPeriod.toLowerCase()}
            defaultRealtimeEnabled={systemConfig.realtime_enabled}
            onRealtimeData={handleRealtimeData}
            onStatusChange={handleRealtimeStatusChange}
          />
        }
        indicatorScope="all"
        loading={loading}
        error={error}
        rightPanelSlot={
          // 「订单簿面板」是右栏总开关：关闭即整体卸载右栏（含成交流水），
          // K线图 flex 自动铺满释放的横向空间；重新开启时右栏恢复，图表自动缩回。
          // 布局偏好由 saveOrderbookPrefs 持久化到后端，下次进入自动套用
          orderbookPrefs?.panel ? (
            // 右栏子块为原生元素，间距用 gap；成交流水从属于面板开关
            <>
              <OrderBookPanel symbol={wsSymbol} depthLevels={orderbookPrefs.depthLevels} />
              {orderbookPrefs.tradeTape && <TradeTape symbol={wsSymbol} />}
            </>
          ) : null
        }
        depthData={depthData}
        orderbookModalProps={
          orderbookPrefs
            ? {
                orderbook: orderbookPrefs,
                onOrderbookChange: updateOrderbookPrefs,
                backtestOptions,
              }
            : undefined
        }
        backtestFills={backtestFills}
      />

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
    </>
  );
};

export default ChartPage;
