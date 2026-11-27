/**
 * 按标的参数覆盖（spec 2026-11-28 D1/D3）：每个标的一个「覆盖参数」入口 → Popover 表单。
 * 留空 = 删除该键 = 继承公共值（与提交过滤口径一致）；受控组件，value 不含空值键。
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge, Button, Flex, Popover, Space, Typography } from 'antd';
import type { StrategyParam } from '../../types/backtest';
import { renderStrategyParamInput } from './paramInput';

export interface SymbolParamOverridesProps {
  schema: StrategyParam[];
  symbols: string[];
  value: Record<string, Record<string, unknown>>;
  onChange: (v: Record<string, Record<string, unknown>>) => void;
  baseValues: Record<string, unknown>;
  disabled?: boolean;
}

const cleanOverrides = (raw: Record<string, unknown>): Record<string, unknown> =>
  Object.fromEntries(
    Object.entries(raw).filter(([, v]) => v !== '' && v !== null && v !== undefined),
  );

export default function SymbolParamOverrides({
  schema, symbols, value, onChange, baseValues, disabled,
}: SymbolParamOverridesProps) {
  const { t } = useTranslation();
  const [openSymbol, setOpenSymbol] = useState<string | null>(null);

  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const sym of symbols) out[sym] = Object.keys(value[sym] ?? {}).length;
    return out;
  }, [symbols, value]);

  const updateSymbol = (sym: string, patch: Record<string, unknown>) => {
    onChange({ ...value, [sym]: cleanOverrides({ ...(value[sym] ?? {}), ...patch }) });
  };

  if (!schema.length || !symbols.length) return null;

  const form = (sym: string) => (
    <Space orientation="vertical" size="small" style={{ display: 'flex', width: 340 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {t('strategyParams.inherit_hint')}
      </Typography.Text>
      {schema.map((p) => (
        <Flex key={p.name} align="center" gap={8} justify="space-between">
          <Typography.Text style={{ minWidth: 110, fontSize: 12 }}>{p.name}</Typography.Text>
          <div style={{ flex: 1 }}>
            {renderStrategyParamInput(p, t, value[sym]?.[p.name], (v) => updateSymbol(sym, { [p.name]: v }), baseValues[p.name])}
          </div>
        </Flex>
      ))}
    </Space>
  );

  return (
    <Flex gap="small" wrap>
      {symbols.map((sym) => (
        <Popover
          key={sym}
          trigger="click"
          open={openSymbol === sym}
          onOpenChange={(open) => setOpenSymbol(open ? sym : null)}
          title={t('strategyParams.override_title', { symbol: sym })}
          content={form(sym)}
        >
          <Badge count={counts[sym]} size="small" offset={[2, -2]}>
            <Button size="small" disabled={disabled}>
              {sym} · {t('strategyParams.override_button')}
            </Button>
          </Badge>
        </Popover>
      ))}
    </Flex>
  );
}
