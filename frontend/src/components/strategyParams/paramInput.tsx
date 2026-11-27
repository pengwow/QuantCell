/**
 * 策略参数共享渲染器（spec 2026-11-28 D3）。
 * 受控用法：SymbolParamOverrides / WorkerCreateModal 共用；
 * BacktestConfig 的卡片 3 走 Form 双向绑定（name 字段机制不同），沿用其本地渲染器不迁移。
 */
import type { TFunction } from 'i18next';
import { Input, InputNumber, Select } from 'antd';
import type { StrategyParam } from '../../types/backtest';

export function inheritedHint(inherited: unknown): string | undefined {
  return inherited == null || inherited === '' ? undefined : String(inherited);
}

export function renderStrategyParamInput(
  param: StrategyParam,
  t: TFunction,
  value: unknown,
  onChange: (v: unknown) => void,
  inherited?: unknown,
) {
  const type = (param.type || 'string').toLowerCase();
  const placeholder = param.description || t('please_input_value');
  const inheritedPlaceholder = inheritedHint(inherited) ? `${placeholder}（${inheritedHint(inherited)}）` : placeholder;

  switch (type) {
    case 'int':
      return (
        <InputNumber value={value as number | undefined} onChange={(v) => onChange(v ?? undefined)} precision={0}
          style={{ width: '100%' }} placeholder={placeholder} />
      );
    case 'float':
      return (
        <InputNumber value={value as number | undefined} onChange={(v) => onChange(v ?? undefined)} step={0.01}
          style={{ width: '100%' }} placeholder={placeholder} />
      );
    case 'bool':
    case 'boolean':
      return (
        <Select
          value={value as boolean | undefined}
          onChange={onChange}
          allowClear
          placeholder={t('please_select')}
          options={[
            { value: true, label: t('yes') },
            { value: false, label: t('no') },
          ]}
        />
      );
    case 'select':
      return (
        <Select value={value as string | undefined} onChange={onChange} allowClear placeholder={placeholder}
          options={(param.options ?? []).map((opt) => ({ value: opt, label: opt }))} style={{ width: '100%' }} />
      );
    case 'json':
      return (
        <Input.TextArea value={value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value)}
          onChange={(e) => onChange(e.target.value)} rows={2} placeholder={inheritedPlaceholder} />
      );
    case 'string':
    default:
      return (
        <Input value={value == null ? '' : String(value)} onChange={(e) => onChange(e.target.value)}
          placeholder={inheritedPlaceholder} />
      );
  }
}
