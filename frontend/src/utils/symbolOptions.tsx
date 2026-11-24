/**
 * 标的下拉共享选项 — 全站「标的 / 交易对」下拉的唯一选项构造入口
 * （SymbolSelect 组件内部使用；数据采集页页面已有数据源时也直接走这里）
 *
 * 自选组组项形制：组色圆点（8px 圆，颜色取 pool.color || QUANT_COLORS.info）
 * + 组名 + 弱化元信息（「N 标的 · 自选组」，由调用方传入文案构造器），
 * 让用户在列表里一眼看出哪些是自选组、组内有多少个标的。裸标的保持纯文本。
 * 顺序恒为组在前、裸标的后。
 *
 * 注意：label 是 JSX，下拉的 filterOption 请走纯文本 name 字段，不要读 label。
 */
import type { ReactNode } from 'react';
import type { DataPoolRecord } from '@/api/dataApi';
import { QUANT_COLORS } from '@/utils/colors';

export interface QcSymbolOption {
  /** 'pool_<id>' 或裸 symbol（pool_ 前缀为全站约定，提交时由 SymbolSelect 展开） */
  value: string;
  /** 组项：组色圆点 + 组名 + 元信息；裸标的：纯文本 */
  label: ReactNode;
  /** 纯文本搜索串（组 = 组名；裸标的 = symbol） */
  name: string;
  type: 'data_pool' | 'direct_symbol';
  /** data_pool 项的组内标的，提交时展开 */
  symbols?: string[];
}

export function buildSymbolOptions(args: {
  dataPools?: DataPoolRecord[];
  directSymbols?: string[];
  /** 组项元信息文案（组内标的数 + 自选组标记），如 (n) => t('symbol_pool_meta', { n }) */
  poolMeta?: (count: number) => string;
}): QcSymbolOption[] {
  const dataPools = Array.isArray(args.dataPools) ? args.dataPools : [];
  const directSymbols = Array.isArray(args.directSymbols) ? args.directSymbols : [];

  const poolOptions: QcSymbolOption[] = dataPools.map((pool) => ({
    value: `pool_${pool.id}`,
    type: 'data_pool',
    name: pool.name,
    symbols: pool.symbols || [],
    label: (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        {/* 组色圆点：同数据管理页自选组的 8px 圆点，未设色回落 info（与数据管理页 pool.color 兜底一致） */}
        <span
          aria-hidden
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            backgroundColor: pool.color || QUANT_COLORS.info,
            flexShrink: 0,
          }}
        />
        <span>{pool.name}</span>
        {args.poolMeta && (
          <span style={{ color: 'var(--qc-text-tertiary)', fontSize: 12 }}>
            {args.poolMeta((pool.symbols || []).length)}
          </span>
        )}
      </span>
    ),
  }));

  const symbolOptions: QcSymbolOption[] = directSymbols.map((symbol) => ({
    value: symbol,
    type: 'direct_symbol',
    name: symbol,
    label: symbol,
  }));

  return [...poolOptions, ...symbolOptions];
}
/**
 * 多选值里的自选组展开：`pool_<id>` → 组内全部标的（去重保序）。
 * 组已删 / 空组不产出值；单标的原样保留。SymbolSelect 的 onChange 与
 * 各页提交前的兜底共用这一份实现。
 */
export function expandPoolSelection(
  values: string[],
  dataPools: DataPoolRecord[] | undefined,
  mapSymbol: (symbol: string) => string = (symbol) => symbol,
): string[] {
  const expanded: string[] = [];
  for (const item of values) {
    if (typeof item === 'string' && item.startsWith('pool_')) {
      const pool = (dataPools ?? []).find((p) => `pool_${p.id}` === item);
      for (const symbol of pool?.symbols ?? []) expanded.push(mapSymbol(symbol));
    } else {
      expanded.push(item);
    }
  }
  return [...new Set(expanded)];
}
