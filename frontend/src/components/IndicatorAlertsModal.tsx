/**
 * 图表工具栏「信号提醒」直达弹窗
 *
 * 信号规则原本藏在 指标弹窗 → 自定义指标 → 编辑器 → 提醒 Tab 三层深处，
 * 这里提供一层直达入口：指标下拉（系统内置 + 用户自定义）+ 原样复用 IndicatorAlertTab。
 * 下拉选项展示 名称 + 描述（无描述仅名称）；图表的 symbol/周期经
 * defaultSymbol/defaultPeriod 传入，供新建规则表单做默认值对齐。
 */

import React, { useEffect, useMemo, useState } from 'react';
import { BellOutlined } from '@ant-design/icons';
import { Empty, Flex, Modal, Select, Spin, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import IndicatorAlertTab from './IndicatorAlertTab';
import { useIndicators } from '../hooks/useIndicators';
import { indicatorApi } from '../api';

/** 后端下发的内置指标提醒定义（不含沙箱代码） */
interface AlertBuiltinDefinition {
  key: string;
  name: string;
  description: string;
  plots: string[];
  params: Record<string, unknown>;
}

export interface IndicatorAlertsModalProps {
  visible: boolean;
  onClose: () => void;
  /** 图表当前交易对（如 BTC/USDT），作为新建规则的默认 symbol */
  defaultSymbol?: string;
  /** 图表当前周期（如 1h），作为新建规则的默认 period */
  defaultPeriod?: string;
}

/** 当前选中的指标（统一传递给规则 Tab；builtin 与 custom 互斥） */
interface SelectedIndicator {
  indicatorId?: number;
  builtinId?: string;
  indicatorName: string;
  /** 内置指标的输出线（plot_name 选择用） */
  plots?: string[];
}

const IndicatorAlertsModal: React.FC<IndicatorAlertsModalProps> = ({
  visible,
  onClose,
  defaultSymbol,
  defaultPeriod,
}) => {
  const { t } = useTranslation();
  // 不自动拉取（false），在弹窗打开时刷新，保证刚新建的指标立即可选
  const { indicators, loading, fetchIndicators } = useIndicators(false);
  const [builtins, setBuiltins] = useState<AlertBuiltinDefinition[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    void fetchIndicators();
    // 内置指标定义随弹窗打开刷新一次（跟随后端版本，不做本地缓存）
    indicatorApi
      .getAlertBuiltins()
      .then((res) => setBuiltins(Array.isArray(res) ? res : []))
      .catch(() => setBuiltins([]));
  }, [visible, fetchIndicators]);

  // 下拉 value 统一为字符串：builtin:<key> / custom:<id>
  useEffect(() => {
    if (visible && selectedKey === null) {
      if (builtins.length > 0) {
        setSelectedKey(`builtin:${builtins[0].key}`);
      } else if (!loading && indicators.length > 0) {
        setSelectedKey(`custom:${indicators[0].id}`);
      }
    }
  }, [visible, selectedKey, builtins, loading, indicators]);

  const builtinName = (item: AlertBuiltinDefinition) =>
    t(`indicator.builtin.${item.key}`, { defaultValue: item.name });

  const builtinDesc = (item: AlertBuiltinDefinition) =>
    t(`indicator.builtinDesc.${item.key}`, { defaultValue: item.description });

  /** 选项的名称 + 描述两行渲染（无描述仅名称） */
  const optionRender = (name: string, description?: string) => (
    <div>
      <div>{name}</div>
      {description && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {description}
        </Typography.Text>
      )}
    </div>
  );

  const options = useMemo(() => {
    const groups = [
      {
        label: t('indicator.alertsBuiltinGroup'),
        title: t('indicator.alertsBuiltinGroup'),
        options: builtins.map((item) => ({
          value: `builtin:${item.key}`,
          label: builtinName(item),
          desc: item.description ? builtinDesc(item) : undefined,
        })),
      },
      {
        label: t('indicator.alertsCustomGroup'),
        title: t('indicator.alertsCustomGroup'),
        options: indicators.map((ind) => ({
          value: `custom:${ind.id}`,
          label: ind.name,
          desc: ind.description || undefined,
        })),
      },
    ].filter((g) => g.options.length > 0);
    return groups;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [builtins, indicators, t]);

  /** 当前选中项解析后传给规则 Tab（切换指标通过 key 重挂载重新加载） */
  const selected = useMemo<SelectedIndicator | null>(() => {
    if (!selectedKey) return null;
    if (selectedKey.startsWith('builtin:')) {
      const key = selectedKey.slice('builtin:'.length);
      const def = builtins.find((b) => b.key === key);
      return def
        ? { builtinId: key, indicatorName: builtinName(def), plots: def.plots }
        : null;
    }
    const id = Number(selectedKey.slice('custom:'.length));
    const ind = indicators.find((i) => i.id === id);
    return ind ? { indicatorId: id, indicatorName: ind.name } : null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey, builtins, indicators]);


  return (
    <Modal
      title={
        <div className="indicator-modal-title">
          <BellOutlined />
          <span>{t('chart.toolbar.alerts')}</span>
        </div>
      }
      open={visible}
      onCancel={onClose}
      footer={null}
      width={760}
      centered
      destroyOnHidden
    >
      {loading && options.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : options.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('indicator.alertsNoIndicator')}
        />
      ) : (
        // Flex vertical 保证下拉与规则列表间距走 antd 间距体系
        <Flex vertical gap="middle">
          <Select
            value={selectedKey ?? undefined}
            onChange={(value) => setSelectedKey(value)}
            options={options}
            optionRender={(opt) => optionRender(opt.label as string, (opt.data as { desc?: string }).desc)}
            placeholder={t('indicator.alertsSelectIndicator')}
            style={{ width: 320 }}
            showSearch
            // 名称与描述一起参与过滤，方便按"均线/超买"等关键词找指标
            filterOption={(input, opt) => {
              const item = opt as { label?: string; desc?: string } | undefined;
              const text = `${item?.label ?? ''} ${item?.desc ?? ''}`.toLowerCase();
              return text.includes(input.toLowerCase());
            }}
            optionFilterProp="label"
          />
          {/* key 触发重挂载：切换指标时重新加载对应规则 */}
          {selected && (
            <IndicatorAlertTab
              key={selectedKey}
              indicatorId={selected.indicatorId}
              builtinId={selected.builtinId}
              indicatorName={selected.indicatorName}
              builtinPlots={selected.plots}
              defaultSymbol={defaultSymbol}
              defaultPeriod={defaultPeriod}
            />
          )}
        </Flex>
      )}
    </Modal>
  );
};

export default IndicatorAlertsModal;
