/**
 * Schema 驱动设置渲染器（P2-05 设置 schema 化）
 * 分组与表单结构完全由后端 GET /api/v1/config/schema 声明驱动，值走
 * GET/PUT /api/v1/config/values：新增配置项只改 backend/settings/schema.py，
 * 本页自动出现并可读写，无需再改前端代码。
 *
 * schema 覆盖不了的部分走了两类约定（逃生口，M4.2 收编特殊控件时启用）：
 * - 特殊控件：当前版本不收编（主题图片选择器仍在 GeneralSettingsPage），需要时给
 *   SchemaField 加 widget 字段并在本页加注册表查找即可
 * - AFTER_SAVE：保存后的生效副作用（theme 应用主题、language 切换 i18n）——schema 只管存取
 *
 * 原有子页（如 GeneralSettingsPage）保留不动，M4.2 逐组收编后再替换入口。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  App,
  Button,
  Card,
  Collapse,
  Input,
  InputNumber,
  Select,
  Space,
  Spin,
  Switch,
} from 'antd';
import {
  configApi,
  type SchemaFieldDef,
  type SchemaGroupDef,
} from '@/api';
import { useGuestRestriction } from '../../hooks/useGuestRestriction';
import { useSettings } from './SettingsContext';

type ValuesMap = Record<string, string | number | boolean>;

const SchemaSettingsPage = () => {
  const { t, i18n } = useTranslation();
  const { message } = App.useApp();
  const { applyTheme } = useSettings();
  const { checkPermission, getButtonDisabled } = useGuestRestriction();

  const [groups, setGroups] = useState<SchemaGroupDef[]>([]);
  const [values, setValues] = useState<ValuesMap>({});
  const [initialValues, setInitialValues] = useState<ValuesMap>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // i18n 释义：label/description 存的是 i18n key，缺失时 t() 原样返回 key，不影响展示
  const labelOf = useCallback((key: string) => t(key), [t]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [schema, vals] = await Promise.all([
          configApi.getConfigSchema(),
          configApi.getConfigValues(),
        ]);
        if (cancelled) return;
        setGroups(schema.groups ?? []);
        setValues(vals ?? {});
        setInitialValues(vals ?? {});
      } catch {
        if (!cancelled) message.error(t('load_failed'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [message, t]);

  const setFieldValue = (key: string, value: string | number | boolean) => {
    setValues((prev) => ({ ...prev, [key]: value }));
  };

  // 仅提交与初始值不同的 key，避免整包覆盖
  const changedValues = useMemo(() => {
    const changed: ValuesMap = {};
    for (const [key, value] of Object.entries(values)) {
      if (JSON.stringify(value) !== JSON.stringify(initialValues[key])) {
        changed[key] = value;
      }
    }
    return changed;
  }, [values, initialValues]);

  const handleSave = async () => {
    if (!checkPermission('修改系统设置')) return;
    if (Object.keys(changedValues).length === 0) return;
    setSaving(true);
    try {
      await configApi.updateConfigValues(changedValues);
      setInitialValues(values);
      // 保存后的生效副作用：schema 只管存取，"改了立即生效"的 UI 行为在这挂
      if (changedValues.theme !== undefined) {
        applyTheme(changedValues.theme as 'light' | 'dark' | 'auto');
      }
      if (changedValues.language !== undefined) {
        i18n.changeLanguage(String(changedValues.language));
      }
      message.success(t('config_saved'));
    } catch {
      message.error(t('save_failed'));
    } finally {
      setSaving(false);
    }
  };

  // 按字段类型/档位渲染基础控件
  const renderControl = (field: SchemaFieldDef) => {
    const value = values[field.key];
    if (field.type === 'bool') {
      return (
        <Switch
          checked={Boolean(value)}
          disabled={getButtonDisabled()}
          onChange={(checked) => setFieldValue(field.key, checked)}
        />
      );
    }
    if (field.type === 'number') {
      if (field.options.length > 0) {
        return (
          <Select
            style={{ width: 160 }}
            value={value as number}
            disabled={getButtonDisabled()}
            options={field.options.map((opt) => ({
              value: opt.value,
              label: labelOf(opt.label),
            }))}
            onChange={(v) => setFieldValue(field.key, v)}
          />
        );
      }
      return (
        <InputNumber
          style={{ width: 160 }}
          value={value as number}
          disabled={getButtonDisabled()}
          onChange={(v) => v !== null && setFieldValue(field.key, v)}
        />
      );
    }
    if (field.type === 'select') {
      return (
        <Select
          style={{ width: 240 }}
          value={String(value ?? '')}
          disabled={getButtonDisabled()}
          options={field.options.map((opt) => ({
            value: opt.value,
            label: labelOf(opt.label),
          }))}
          onChange={(v) => setFieldValue(field.key, v)}
        />
      );
    }
    if (field.type === 'text') {
      return (
        <Input.TextArea
          rows={3}
          value={String(value ?? '')}
          disabled={getButtonDisabled()}
          onChange={(e) => setFieldValue(field.key, e.target.value)}
        />
      );
    }
    return (
      <Input
        style={{ width: 280 }}
        value={String(value ?? '')}
        disabled={getButtonDisabled()}
        onChange={(e) => setFieldValue(field.key, e.target.value)}
      />
    );
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Space orientation="vertical" size="large" style={{ display: 'flex' }}>
      {groups.map((group) => {
        const advancedFields = group.fields.filter((f) => f.advanced);
        const normalFields = group.fields.filter((f) => !f.advanced);
        return (
          <Card key={group.key} title={labelOf(group.title)}>
            <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
              {normalFields.map((field) => (
                <FieldRow
                  key={field.key}
                  field={field}
                  labelOf={labelOf}
                  control={renderControl(field)}
                />
              ))}
              {advancedFields.length > 0 && (
                <Collapse
                  ghost
                  items={[
                    {
                      key: 'advanced',
                      label: t('advanced_settings'),
                      children: (
                        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
                          {advancedFields.map((field) => (
                            <FieldRow
                              key={field.key}
                              field={field}
                              labelOf={labelOf}
                              control={renderControl(field)}
                            />
                          ))}
                        </Space>
                      ),
                    },
                  ]}
                />
              )}
            </Space>
          </Card>
        );
      })}
      <Button
        type="primary"
        loading={saving}
        disabled={getButtonDisabled() || Object.keys(changedValues).length === 0}
        onClick={handleSave}
      >
        {t('save')}
      </Button>
    </Space>
  );
};

// 单字段行：label + 控件 + 可选说明，纯展示拆分，避免主循环嵌套过深
const FieldRow = ({
  field,
  labelOf,
  control,
}: {
  field: SchemaFieldDef;
  labelOf: (key: string) => string;
  control: React.ReactNode;
}) => (
  <div className="flex items-center justify-between gap-4 max-sm:flex-col max-sm:items-start">
    <div className="min-w-0">
      <div>{labelOf(field.label)}</div>
      {field.description && (
        <div className="text-xs opacity-60">{labelOf(field.description)}</div>
      )}
    </div>
    <div className="shrink-0">{control}</div>
  </div>
);

export default SchemaSettingsPage;
