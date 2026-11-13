import { useEffect, useRef, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Input, Modal, Spin, App } from 'antd';
import type { KLineData } from 'klinecharts';
import { dataApi } from '../../api/dataApi';
import * as realtimeApi from '../../api/realtimeApi';
import RealtimeToggleButton from '../../components/RealtimeToggleButton';
import TokenDisplay from '../../components/TokenDisplay';
import ChartShell, { type ChartShellHandle } from '../../components/chart/ChartShell';
import { PERIOD_BAR_ITEMS } from '../../components/chart/chartConstants';
import { loadChartPrefs, saveUiPrefs } from '../../services/chartPreferences';
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
  const [currentPeriod, setCurrentPeriod] = useState('1h');

  // 加载状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 搜索弹窗状态
  const [searchVisible, setSearchVisible] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchResults, setSearchResults] = useState<Symbol[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

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

  // 保存用户偏好：写后端 chart.uiPrefs（800ms 防抖合并，见 services/chartPreferences）
  const saveUserPreferences = (symbol: string, period: string) => {
    saveUiPrefs({ symbol, period });
  };

  // 加载K线数据：拿到数据后由壳统一喂数（内部重新 setDataLoader + resize）
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
        shellRef.current?.refreshData();
      }
    } catch (error) {
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
        if (hit) setCurrentSymbol(hit); // 找不到（品种名变更/下架）保持默认 BTCUSDT
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
    setCurrentSymbol(symbol);
    setSearchVisible(false);
    setSearchKeyword('');
    saveUserPreferences(symbol.code, currentPeriod);
  };

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
        onChangePeriod={setCurrentPeriod}
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
