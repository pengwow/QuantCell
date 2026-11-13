import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

// api 模块整体 mock：chartPreferences 只用 configApi
const configApiMock = {
  getConfig: vi.fn(),
  getConfigValues: vi.fn(),
  updateConfigValues: vi.fn().mockResolvedValue(undefined),
  setConfigKey: vi.fn().mockResolvedValue(undefined),
  deleteConfigKey: vi.fn().mockResolvedValue(undefined),
};
vi.mock('../api', () => ({ configApi: configApiMock }));

type ChartPrefsModule = typeof import('./chartPreferences');
// vi.resetModules() 后动态重导，拿到全新模块级状态（快照/防抖 buffer 不跨用例泄漏）
const importFresh = async (): Promise<ChartPrefsModule> => import('./chartPreferences');

// 内存版 localStorage：测试环境可能是 node，不依赖 jsdom
const createMemoryStorage = () => {
  const map = new Map<string, string>();
  return {
    getItem: (k: string) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k: string, v: string) => { map.set(k, v); },
    removeItem: (k: string) => { map.delete(k); },
    clear: () => map.clear(),
  };
};
let store: ReturnType<typeof createMemoryStorage>;

beforeEach(() => {
  vi.useFakeTimers();
  vi.resetModules();
  store = createMemoryStorage();
  vi.stubGlobal('localStorage', store);
  configApiMock.getConfig.mockReset();
  configApiMock.getConfig.mockResolvedValue({});
  configApiMock.updateConfigValues.mockClear();
  configApiMock.setConfigKey.mockClear();
  configApiMock.deleteConfigKey.mockClear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('loadChartPrefs', () => {
  it('解析 chart 组到快照：priceStyle/uiPrefs/指标参数', async () => {
    configApiMock.getConfig.mockResolvedValue({
      chart: {
        priceStyle: JSON.stringify({ 'candle.type': 'renko' }),
        uiPrefs: JSON.stringify({ period: '4h' }),
        'indicatorParams.BTCUSDT.macd': JSON.stringify({ fast: 12 }),
      },
    });
    const mod = await importFresh();
    const snap = await mod.loadChartPrefs();
    expect(snap.priceStyle['candle.type']).toBe('renko');
    expect(snap.uiPrefs.period).toBe('4h');
    expect(snap.indicatorParams['BTCUSDT.macd']).toEqual({ fast: 12 });
  });

  it('后端不可达时返回空快照，并迁移旧 localStorage 偏好', async () => {
    configApiMock.getConfig.mockRejectedValue(new Error('down'));
    store.setItem('chart_user_preferences', JSON.stringify({ period: '4h', symbol: 'ETHUSDT' }));
    const mod = await importFresh();
    const snap = await mod.loadChartPrefs();
    expect(snap.priceStyle).toEqual({});
    expect(snap.uiPrefs).toEqual({ period: '4h', symbol: 'ETHUSDT' });
    expect(store.getItem('chart_user_preferences')).toBeNull();
    expect(configApiMock.setConfigKey).toHaveBeenCalledWith(
      expect.objectContaining({ key: 'uiPrefs', name: 'chart' }),
    );
  });
});

describe('savePriceStyleValue', () => {
  it('800ms 防抖合并，且与服务端现值合并为整对象写回', async () => {
    configApiMock.getConfig.mockResolvedValue({
      chart: { priceStyle: JSON.stringify({ 'candle.type': 'area' }) },
    });
    const mod = await importFresh();
    await mod.loadChartPrefs();

    mod.savePriceStyleValue('yAxis.reverse', true);
    mod.savePriceStyleValue('grid.show', false);
    expect(configApiMock.updateConfigValues).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(800);
    expect(configApiMock.updateConfigValues).toHaveBeenCalledTimes(1);
    const payload = configApiMock.updateConfigValues.mock.calls[0][0];
    expect(JSON.parse(payload.priceStyle)).toEqual({
      'candle.type': 'area',
      'yAxis.reverse': true,
      'grid.show': false,
    });
  });

  it('首次 load 未完成前不写服务端（防 mount 默认值覆盖），load 完成后 flush 保留 buffer', async () => {
    let resolveGet!: (v: unknown) => void;
    configApiMock.getConfig.mockReturnValue(new Promise((res) => { resolveGet = res; }));
    const mod = await importFresh();
    const loadP = mod.loadChartPrefs();
    mod.savePriceStyleValue('yAxis.reverse', true);

    await vi.advanceTimersByTimeAsync(800);
    expect(configApiMock.updateConfigValues).not.toHaveBeenCalled();

    resolveGet({ chart: {} });
    await loadP;
    // !loaded 时 flush 会重新排队一个 DEBOUNCE_MS 定时器，再推进一拍触发
    await vi.advanceTimersByTimeAsync(800);
    expect(configApiMock.updateConfigValues).toHaveBeenCalledTimes(1);
    expect(JSON.parse(configApiMock.updateConfigValues.mock.calls[0][0].priceStyle))
      .toEqual({ 'yAxis.reverse': true });
  });
});

describe('saveUiPrefs', () => {
  it('uiPrefs 防抖合并写回', async () => {
    configApiMock.getConfig.mockResolvedValue({
      chart: { uiPrefs: JSON.stringify({ period: '1h' }) },
    });
    const mod = await importFresh();
    await mod.loadChartPrefs();

    mod.saveUiPrefs({ symbol: 'ETHUSDT' });
    mod.saveUiPrefs({ period: '4h' });
    await vi.advanceTimersByTimeAsync(800);
    expect(configApiMock.updateConfigValues).toHaveBeenCalledTimes(1);
    expect(JSON.parse(configApiMock.updateConfigValues.mock.calls[0][0].uiPrefs))
      .toEqual({ period: '4h', symbol: 'ETHUSDT' });
  });
});

describe('loadIndicatorParams / saveIndicatorParams', () => {
  it('后端未命中时迁移旧 localStorage 键并清理', async () => {
    store.setItem('qc:indicator-params:BTCUSDT:macd', JSON.stringify({ fast: 9 }));
    const mod = await importFresh();
    await mod.loadChartPrefs();
    expect(mod.loadIndicatorParams('BTCUSDT', 'macd')).toEqual({ fast: 9 });
    expect(store.getItem('qc:indicator-params:BTCUSDT:macd')).toBeNull();
  });

  it('保存即时写动态键，且会话内立即可读', async () => {
    const mod = await importFresh();
    await mod.loadChartPrefs();
    await mod.saveIndicatorParams('BTCUSDT', 'macd', { fast: 6 });
    expect(configApiMock.setConfigKey).toHaveBeenCalledWith({
      key: 'indicatorParams.BTCUSDT.macd',
      value: '{"fast":6}',
      name: 'chart',
    });
    expect(mod.loadIndicatorParams('BTCUSDT', 'macd')).toEqual({ fast: 6 });
  });
});

describe('restorePriceStyle', () => {
  it('删除后端键并取消 pending 防抖（防止晚到合并写复活已删配置）', async () => {
    configApiMock.getConfig.mockResolvedValue({
      chart: { priceStyle: '{"grid.show":false}' },
    });
    const mod = await importFresh();
    await mod.loadChartPrefs();
    mod.savePriceStyleValue('yAxis.reverse', true); // 产生 pending
    await mod.restorePriceStyle();
    expect(configApiMock.deleteConfigKey).toHaveBeenCalledWith('priceStyle');
    await vi.advanceTimersByTimeAsync(2000);
    expect(configApiMock.updateConfigValues).not.toHaveBeenCalled();
  });
});
