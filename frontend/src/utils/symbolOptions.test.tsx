import { describe, expect, it } from 'vitest';
import type { CSSProperties, ReactElement, ReactNode } from 'react';
import { buildSymbolOptions } from './symbolOptions';
import { QUANT_COLORS } from './colors';

// label 子节点形状断言用的轻量视图类型（React 19 下 ReactElement.props 是 unknown）
type SpanEl = ReactElement<{ style?: CSSProperties; children?: ReactNode | ReactNode[] }>;
// 按 React 语义取子节点：undefined/null/false 空位渲染为空，不计入
const childrenOf = (el: ReactNode): ReactNode[] => {
  const c = (el as SpanEl).props.children;
  return (Array.isArray(c) ? c : [c]).filter((x) => x !== undefined && x !== null && x !== false);
};

describe('buildSymbolOptions', () => {
  const pools = [
    { id: 1, name: '主流币', color: '#667eea', symbols: ['BTC/USDT', 'ETH/USDT'] },
    { id: 2, name: '国产币' },
  ];

  it('组项在前、裸标的后；value/name/symbols 各就各位', () => {
    const options = buildSymbolOptions({ dataPools: pools, directSymbols: ['BTC/USDT', 'SOL/USDT'] });
    expect(options.map((o) => o.value)).toEqual(['pool_1', 'pool_2', 'BTC/USDT', 'SOL/USDT']);
    expect(options[0].type).toBe('data_pool');
    expect(options[0].name).toBe('主流币');
    expect(options[0].symbols).toEqual(['BTC/USDT', 'ETH/USDT']);
    expect(options[2].type).toBe('direct_symbol');
    expect(options[2].name).toBe('BTC/USDT');
  });

  it('组色：自定义色原样进入 label，缺省回落 QUANT_COLORS.info（与数据管理页同源）', () => {
    const options = buildSymbolOptions({ dataPools: pools });
    const dotColor = (o: (typeof options)[number]) => {
      const dot = childrenOf(o.label)[0] as SpanEl;
      return dot.props.style?.backgroundColor;
    };
    expect(dotColor(options[0])).toBe('#667eea');
    expect(dotColor(options[1])).toBe(QUANT_COLORS.info);
  });

  it('poolSuffix 渲染为第三个弱化子节点，不传则只有圆点+组名', () => {
    const withSuffix = buildSymbolOptions({ dataPools: pools, poolSuffix: '自选组' });
    const children = childrenOf(withSuffix[0].label);
    expect(children).toHaveLength(3);
    // JSX 里 ({suffix}) 会编译成 ["(", suffix, ")"] 数组子节点
    expect((children[2] as SpanEl).props.children).toEqual(['(', '自选组', ')']);

    const plain = buildSymbolOptions({ dataPools: pools });
    expect(childrenOf(plain[0].label)).toHaveLength(2);
  });

  it('入参缺数组（null / 非法形状）安全返回空数组', () => {
    expect(buildSymbolOptions({ dataPools: undefined, directSymbols: undefined })).toEqual([]);
    expect(buildSymbolOptions({})).toEqual([]);
  });
});
