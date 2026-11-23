/**
 * 标的下拉共享选项 — 各页「标的 / 交易标的」多选的统一构造入口
 * （回测配置 / Worker 创建弹窗 / Worker 编辑弹窗，三处共用）
 *
 * 自选组组项形制与数据管理页自选组一致：组色圆点（8px 圆，颜色取 pool.color || QUANT_COLORS.info）
 * + 组名 + 可选弱化后缀；裸标的保持纯文本。顺序恒为组在前、裸标的后。
 *
 * 注意：label 是 JSX，下拉的 filterOption 请走纯文本 name 字段，不要读 label。
 */
import type { ReactNode } from 'react';
import type { DataPoolRecord } from '@/api/dataApi';
import { QUANT_COLORS } from '@/utils/colors';

export interface QcSymbolOption {
  /** 'pool_<id>' 或裸 symbol（pool_ 前缀为全站约定，提交时展开为组内标的） */
  value: string;
  /** 组项：组色圆点 + 组名(+弱化后缀)；裸标的：纯文本 */
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
  /** 组项后面的弱化标记文案，如 t('favorite_group') */
  poolSuffix?: string;
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
        {args.poolSuffix && (
          <span style={{ color: 'var(--qc-text-tertiary)', fontSize: 12 }}>({args.poolSuffix})</span>
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
