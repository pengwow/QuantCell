import { describe, expect, it } from 'vitest';
import { groupSymbolsByMarket, probeMarkets } from './ArchiveWatermarkStrip';

describe('probeMarkets', () => {
  it('期货专属 kind 不白探 spot', () => {
    expect(probeMarkets('markPriceKlines')).toEqual(['um', 'cm']);
  });

  it('通用 kind 三个 market 全探', () => {
    expect(probeMarkets('aggTrades')).toEqual(['spot', 'um', 'cm']);
  });
});

describe('groupSymbolsByMarket（按 market 分组各发一个任务）', () => {
  it('同 kind 多 market 各自成组，不混发', () => {
    expect(
      groupSymbolsByMarket([
        { market: 'spot', symbols: ['BTCUSDT'] },
        { market: 'um', symbols: ['BTCUSDT', 'ETHUSDT'] },
      ]),
    ).toEqual([
      { market: 'spot', symbols: ['BTCUSDT'] },
      { market: 'um', symbols: ['BTCUSDT', 'ETHUSDT'] },
    ]);
  });

  it('空列表 / 探测失败(null) 的 market 丢弃：无可补之物就不发任务', () => {
    expect(
      groupSymbolsByMarket([
        { market: 'spot', symbols: [] },
        { market: 'um', symbols: null },
        { market: 'cm', symbols: ['BTCUSD_PERP'] },
      ]),
    ).toEqual([{ market: 'cm', symbols: ['BTCUSD_PERP'] }]);
  });

  it('全空时返回空数组（调用方据此隐藏补齐钮）', () => {
    expect(groupSymbolsByMarket([{ market: 'spot', symbols: [] }])).toEqual([]);
  });
});
