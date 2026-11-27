import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from './index';
import { fetchKlines, getWorkerPlan, KLINE_INTERVALS } from './pricePlanApi';

vi.mock('./index', () => ({
  apiRequest: {
    get: vi.fn().mockResolvedValue([]),
    post: vi.fn().mockResolvedValue({}),
  },
}));

const mockedGet = vi.mocked(apiRequest.get);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('pricePlanApi', () => {
  it('fetchKlines 路径正确且第二参即查询本体（不包 params）', async () => {
    await fetchKlines({
      symbol: 'BTCUSDT',
      market_type: 'spot',
      exchange: 'binance',
      interval: '15m',
      limit: 120,
    });

    expect(mockedGet).toHaveBeenCalledTimes(1);
    const [url, query] = mockedGet.mock.calls[0];
    expect(url).toBe('/marketdata/klines');
    expect(query).toEqual({
      symbol: 'BTCUSDT',
      market_type: 'spot',
      exchange: 'binance',
      interval: '15m',
      limit: 120,
    });
    // 历史雷区：查询参数不能被包成 { params: ... }
    expect(query).not.toHaveProperty('params');
  });

  it('getWorkerPlan 无 symbol 时不带查询，有 symbol 时带 { symbol }', async () => {
    await getWorkerPlan(42);
    expect(mockedGet).toHaveBeenLastCalledWith('/workers/42/plan', undefined);

    await getWorkerPlan(42, 'ETHUSDT');
    expect(mockedGet).toHaveBeenLastCalledWith('/workers/42/plan', { symbol: 'ETHUSDT' });
  });

  it('KLINE_INTERVALS 白名单与后端一致', () => {
    expect([...KLINE_INTERVALS]).toEqual(['1m', '5m', '15m', '1h', '4h', '1d']);
  });
});
