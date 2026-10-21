import { describe, expect, it } from 'vitest';
import { buildMarginSettingsPayload, pickDirectSymbols } from './marginSettings';

describe('pickDirectSymbols', () => {
  it('排除数据池占位符，保留直接选择的品种', () => {
    expect(pickDirectSymbols(['BTC/USDT', 'pool_12', 'ETH/USDT'])).toEqual(['BTC/USDT', 'ETH/USDT']);
  });

  it('未选择时返回空数组', () => {
    expect(pickDirectSymbols(undefined)).toEqual([]);
  });
});

describe('buildMarginSettingsPayload', () => {
  it('按当前品种顺序生成数组并补默认值', () => {
    expect(buildMarginSettingsPayload(undefined, ['BTC/USDT', 'ETH/USDT'])).toEqual([
      { symbol: 'BTC/USDT', leverage: 1, margin_mode: 'cross' },
      { symbol: 'ETH/USDT', leverage: 1, margin_mode: 'cross' },
    ]);
  });

  it('保留用户已填的杠杆与模式', () => {
    const payload = buildMarginSettingsPayload(
      { 'BTC/USDT': { leverage: 20, margin_mode: 'isolated' } },
      ['BTC/USDT'],
    );
    expect(payload).toEqual([{ symbol: 'BTC/USDT', leverage: 20, margin_mode: 'isolated' }]);
  });

  it('丢弃已不在本次回测列表里的残留键', () => {
    const payload = buildMarginSettingsPayload(
      { 'BTC/USDT': { leverage: 5, margin_mode: 'cross' }, SOLUSDT: { leverage: 10, margin_mode: 'cross' } },
      ['BTC/USDT'],
    );
    expect(payload).toHaveLength(1);
    expect(payload[0].symbol).toBe('BTC/USDT');
  });

  it('排除数据池占位符', () => {
    const payload = buildMarginSettingsPayload(undefined, ['pool_3', 'BTC/USDT']);
    expect(payload).toEqual([{ symbol: 'BTC/USDT', leverage: 1, margin_mode: 'cross' }]);
  });

  it('杠杆被清空时回退 1', () => {
    const payload = buildMarginSettingsPayload({ 'BTC/USDT': { margin_mode: 'isolated' } }, ['BTC/USDT']);
    expect(payload[0].leverage).toBe(1);
  });
});
