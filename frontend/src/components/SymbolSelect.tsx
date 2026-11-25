/**
 * SymbolSelect — 全站「标的 / 交易对」下拉唯一入口。
 *
 * 覆盖：回测配置（多选 + 自选组）、Worker 创建/编辑、数据采集表单、
 * 模型中心训练与回测、集成组合回测、智能体部署、指标提醒。
 *
 * 统一三件事（以前各页自己拼，选项目径互不一致）：
 *  1. 数据源：GET /data-pools/collection/symbols（自选组 + 裸标的），按 query 在模块级缓存；
 *  2. 选项形制：utils/symbolOptions 构造（组色圆点 + 组名 + 「N 标的 · 自选组」）；
 *  3. 取值：多选选自选组当场展开成组内标的（不再需要各页在提交时各写一遍 pool_ 解析）。
 *
 * 标的增删只需改数据池/交易所标的表，所有引用点自动跟随。
 */
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Select, Spin } from 'antd';
import type { SelectProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { dataApi } from '@/api/dataApi';
import type { DataPoolRecord } from '@/api/dataApi';
import { QUANT_COLORS } from '@/utils/colors';
import { buildSymbolOptions, expandPoolSelection } from '@/utils/symbolOptions';

export interface SymbolSource {
  dataPools?: DataPoolRecord[];
  directSymbols?: string[];
}

export interface SymbolSelectProps extends Omit<SelectProps, 'options'> {
  /** 多选；不传为单选 */
  mode?: 'multiple';
  /** 外部数据源（页面已取到标的列表时传，省一次请求） */
  source?: SymbolSource;
  /** getCollectionSymbols 查询参数；缺省 = 全部有效交易所标的 */
  query?: Record<string, string>;
  /** 单选场景默认不列自选组（选一个组没有意义）；多选默认列 */
  allowPools?: boolean;
  /** 值形态：slash = BTC/USDT（默认）；compact = BTCUSDT（模型中心既有口径） */
  valueFormat?: 'slash' | 'compact';
}

const sourceCache = new Map<string, Promise<SymbolSource>>();

const loadSource = (key: string, query: Record<string, string>): Promise<SymbolSource> => {
  const cached = sourceCache.get(key);
  if (cached) return cached;
  const task = dataApi
    .getCollectionSymbols(query)
    .then((res) => ({ dataPools: res?.data_pools ?? [], directSymbols: res?.direct_symbols ?? [] }))
    .catch((error) => {
      // 失败不缓存：网络恢复后下一次挂载重试
      console.error('[SymbolSelect] load symbols failed:', error);
      sourceCache.delete(key);
      return { dataPools: [], directSymbols: [] };
    });
  sourceCache.set(key, task);
  return task;
};

const toCompact = (symbol: string): string =>
  symbol.replace(/[/_-]/g, '').toUpperCase();

export default function SymbolSelect({
  source,
  query = {},
  mode,
  allowPools,
  valueFormat = 'slash',
  onChange,
  showSearch = true,
  allowClear = true,
  placeholder,
  ...rest
}: SymbolSelectProps) {
  const { t } = useTranslation();
  const queryKey = JSON.stringify(query);
  // 外部给了 source 就直接用（调用方常在 render 里现造对象，不进 state 就不存在自激）
  const [remote, setRemote] = useState<SymbolSource | undefined>(undefined);
  const loaded = source ?? remote;
  // 还没拿到任何数据才算 loading（请求失败会落成空 source，不会永久转圈）
  const loading = !loaded;
  const withPools = allowPools ?? mode === 'multiple';

  useEffect(() => {
    if (source) return undefined;
    let alive = true;
    void loadSource(queryKey, JSON.parse(queryKey) as Record<string, string>).then((next) => {
      if (!alive) return;
      setRemote(next);
    });
    return () => {
      alive = false;
    };
  }, [source, queryKey]);

  const options = useMemo(() => {
    const directSymbols = (loaded?.directSymbols ?? []).map((symbol) =>
      valueFormat === 'compact' ? toCompact(symbol) : symbol,
    );
    const picked = buildSymbolOptions({
      dataPools: withPools ? loaded?.dataPools : [],
      directSymbols,
      poolMeta: (count) => t('symbol_pool_meta', { count }),
    });
    if (withPools) return picked;

    // 单选不出「自选组」本身（一组标的没法折成一个 symbol），但把组内标的按组名分组
    // 列出来：用户仍能顺着自选组找标的，值仍是裸 symbol（不会提交 pool_x）。
    const pools = loaded?.dataPools ?? [];
    const seen = new Set<string>();
    const groups: { label: ReactNode; name: string; options: { value: string; label: string; name: string }[] }[] = [];
    for (const pool of pools) {
      const leaves: { value: string; label: string; name: string }[] = [];
      for (const symbol of pool.symbols ?? []) {
        const value = valueFormat === 'compact' ? toCompact(symbol) : symbol;
        if (!value || seen.has(value)) continue;
        seen.add(value);
        leaves.push({ value, label: value, name: value });
      }
      if (!leaves.length) continue;
      groups.push({
        name: pool.name,
        label: (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
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
            <span style={{ color: 'var(--qc-text-tertiary)', fontSize: 12 }}>
              {t('symbol_pool_meta', { count: leaves.length })}
            </span>
          </span>
        ),
        options: leaves,
      });
    }
    if (!groups.length) return picked;
    // 组内已列的标的从平铺段去掉（同一 symbol 在组里和平铺里出现两次会让用户以为有两个）
    return [...groups, ...picked.filter((option) => !seen.has(option.value))];
  }, [loaded, withPools, valueFormat, t]);

  // 多选：pool_<id> 当场展开成组内标的，去重保序；各页不必再写一遍解析
  const handleChange: SelectProps['onChange'] = (value, option) => {
    if (mode === 'multiple' && Array.isArray(value)) {
      const expanded = expandPoolSelection(
        value as string[],
        loaded?.dataPools,
        valueFormat === 'compact' ? toCompact : undefined,
      );
      onChange?.(expanded as never, option);
      return;
    }
    onChange?.(value, option);
  };

  return (
    <Select
      {...rest}
      mode={mode}
      showSearch={showSearch}
      allowClear={allowClear}
      placeholder={placeholder ?? t('select_symbol_or_group_placeholder')}
      loading={loading}
      options={options}
      onChange={handleChange}
      notFoundContent={loading ? <Spin size="small" /> : rest.notFoundContent}
      filterOption={(input, option) => {
        if (!input) return true;
        // label 已是 JSX（组色圆点 + 元信息），搜索走纯文本 name（组名 / symbol）
        const name: string = (option as { name?: string } | undefined)?.name ?? '';
        return name.toLowerCase().includes(input.toLowerCase());
      }}
    />
  );
}