import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Divider, Flex, Modal, Select, Space, Switch } from 'antd';
import { getStyleValue } from './chartStyles';
import ChartTypeIcon from './ChartTypeIcon';
import type { OrderbookPrefs } from '../../services/chartPreferences';

export interface ChartSettingDef {
  /** 样式路径；yAxis.reverse 是虚拟路径（v10 中不属于 styles，需走 overrideYAxis） */
  path: string;
  i18nKey: string;
  /** klinecharts 默认值，供「恢复默认」使用 */
  defaultValue: unknown;
  control: 'switch' | 'select';
  /** select 选项值列表；文案统一走词条 chart.setting.{control}.{value} */
  options?: string[];
  /** select 选项左侧渲染类型迷你预览图标（蜡烛图类型下拉使用） */
  withIcon?: boolean;
}

/**
 * 设置项定义（ChartPage 的「恢复默认」也复用这份默认值，避免两处漂移）
 *
 * ponytail: pro 的 setting-modal 还有 yAxis.type（normal/percentage/log），
 * 但 klinecharts v10 的 styles.yAxis 已不含 type，v10 也没有百分比/对数坐标实现，
 * 保留该下拉只会静默失效，故不提供。
 */
export const CHART_SETTING_DEFS: ChartSettingDef[] = [
  {
    path: 'candle.type',
    i18nKey: 'chart.setting.candleType',
    defaultValue: 'candle_solid',
    control: 'select',
    withIcon: true,
    options: [
      // 除前六种为 v10 原生形状外，其余为派生类型（由 ChartShell 做数据变换或复用 area 渲染）
      'candle_solid',
      'candle_stroke',
      'candle_up_stroke',
      'candle_down_stroke',
      'ohlc',
      'area',
      'line',
      'hlc_area',
      'heikin_ashi',
      'renko',
      'range',
    ],
  },
  { path: 'candle.priceMark.last.show', i18nKey: 'chart.setting.priceMarkLast', defaultValue: true, control: 'switch' },
  { path: 'candle.priceMark.high.show', i18nKey: 'chart.setting.priceMarkHigh', defaultValue: true, control: 'switch' },
  { path: 'candle.priceMark.low.show', i18nKey: 'chart.setting.priceMarkLow', defaultValue: true, control: 'switch' },
  { path: 'indicator.lastValueMark.show', i18nKey: 'chart.setting.indicatorLastValue', defaultValue: false, control: 'switch' },
  { path: 'yAxis.reverse', i18nKey: 'chart.setting.yAxisReverse', defaultValue: false, control: 'switch' },
  { path: 'grid.show', i18nKey: 'chart.setting.grid', defaultValue: true, control: 'switch' },
];

interface ChartSettingModalProps {
  open: boolean;
  onClose: () => void;
  /** 读取图表当前样式（ChartPage 传入，含从轴状态补回的 yAxis.reverse） */
  getSettings: () => Record<string, unknown>;
  /** 单项变更后立即回写图表 */
  onChange: (path: string, value: unknown) => void;
  onRestoreDefault: () => void;
  /** null/undefined = 调用方未接订单簿（如回放页），隐藏整个分组 */
  orderbook?: OrderbookPrefs | null;
  /** 订单簿分组的 patch 回写（直接对应 saveOrderbookPrefs） */
  onOrderbookChange?: (patch: Partial<OrderbookPrefs>) => void;
  /** 回测成交标记备选项 */
  backtestOptions?: { label: string; value: string }[];
}

/** 图表样式设置弹窗：对应 pro 的 setting-modal（含恢复默认） */
const ChartSettingModal: React.FC<ChartSettingModalProps> = ({
  open,
  onClose,
  getSettings,
  onChange,
  onRestoreDefault,
  orderbook,
  onOrderbookChange,
  backtestOptions,
}) => {
  const { t } = useTranslation();
  const [values, setValues] = useState<Record<string, unknown>>({});

  const items = useMemo(
    () =>
      CHART_SETTING_DEFS.map((def) => ({
        ...def,
        label: t(def.i18nKey),
        options: def.options?.map((value) => ({
          value,
          // withIcon 的下拉选项带迷你预览图标（选中回显同样渲染，无需额外节点）
          label: def.withIcon ? (
            <span className="candle-type-option">
              <ChartTypeIcon type={value} />
              <span>{t(`chart.setting.${def.control}.${value}`)}</span>
            </span>
          ) : (
            t(`chart.setting.${def.control}.${value}`)
          ),
        })),
      })),
    [t],
  );

  // 每次打开时从图表读取当前样式，保证弹窗展示与图表实际状态一致
  useEffect(() => {
    if (!open) return;
    const styles = getSettings();
    setValues(Object.fromEntries(CHART_SETTING_DEFS.map((def) => [def.path, getStyleValue(styles, def.path)])));
  }, [open, getSettings]);

  const handleChange = (path: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [path]: value }));
    onChange(path, value);
  };

  return (
    <Modal
      title={t('chart.setting.title')}
      open={open}
      onCancel={onClose}
      footer={<Button onClick={onRestoreDefault}>{t('chart.setting.restore')}</Button>}
      width={420}
    >
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
        {items.map((item) => (
          <Flex key={item.path} justify="space-between" align="center" gap={16}>
            <span>{item.label}</span>
            {item.control === 'switch' ? (
              <Switch
                size="small"
                checked={Boolean(values[item.path])}
                onChange={(checked) => handleChange(item.path, checked)}
              />
            ) : (
              <Select
                size="small"
                style={{ width: 160 }}
                value={values[item.path] as string | undefined}
                options={item.options}
                // 下拉项内容较宽（图标 + 文案），关闭宽度回显限制避免被压缩
                popupMatchSelectWidth={false}
                onChange={(value) => handleChange(item.path, value)}
              />
            )}
          </Flex>
        ))}
        {/* 订单簿分组：orderbook 与 onOrderbookChange 均存在才渲染（回放页不传即隐藏，向后兼容）。
            返回数组而非 Fragment：Space 会把 Fragment 当单个 child 包进同一 item 容器，
            组内行间 middle 间距会塌陷；数组被逐项展平，每个元素独立参与 Space 间距 */}
        {orderbook && onOrderbookChange ? [
          <Divider key="ob-group" titlePlacement="left" plain>{t('chart.setting.orderbookGroup')}</Divider>,
          <Flex key="ob-panel" justify="space-between" align="center" gap={16}>
            <span>{t('chart.setting.orderbookPanel')}</span>
            <Switch size="small" checked={orderbook.panel}
              onChange={(v) => onOrderbookChange({ panel: v })} />
          </Flex>,
          <Flex key="ob-depthLevels" justify="space-between" align="center" gap={16}>
            <span>{t('chart.setting.depthLevels')}</span>
            <Select<OrderbookPrefs['depthLevels']>
              size="small"
              style={{ width: 80 }}
              value={orderbook.depthLevels}
              options={[{ value: 10, label: '10' }, { value: 20, label: '20' }]}
              onChange={(v) => onOrderbookChange({ depthLevels: v })}
            />
          </Flex>,
          <Flex key="ob-depthProfile" justify="space-between" align="center" gap={16}>
            <span>{t('chart.setting.depthProfile')}</span>
            <Switch size="small" checked={orderbook.depthProfile}
              onChange={(v) => onOrderbookChange({ depthProfile: v })} />
          </Flex>,
          <Flex key="ob-tradeTape" justify="space-between" align="center" gap={16}>
            <span>{t('chart.setting.tradeTape')}</span>
            <Switch size="small" checked={orderbook.tradeTape}
              onChange={(v) => onOrderbookChange({ tradeTape: v })} />
          </Flex>,
          // 副图指标组：独立分组标题，不复用业务开关文案
          <Divider key="ob-sub-ind" titlePlacement="left" plain>{t('chart.setting.subIndicators')}</Divider>,
          ...(['oi', 'funding', 'cvd'] as const).map((key) => (
            <Flex key={`ob-ind-${key}`} justify="space-between" align="center" gap={16}>
              <span>{t(`chart.setting.${key}Indicator`)}</span>
              <Switch size="small" checked={orderbook.indicators[key]}
                onChange={(v) => onOrderbookChange({ indicators: { ...orderbook.indicators, [key]: v } })} />
            </Flex>
          )),
          // 成交标记组：独立分组标题
          <Divider key="ob-marker-group" titlePlacement="left" plain>{t('chart.setting.tradeMarkerGroup')}</Divider>,
          <Flex key="ob-live-markers" justify="space-between" align="center" gap={16}>
            <span>{t('chart.setting.liveTradeMarkers')}</span>
            <Switch size="small" checked={orderbook.tradeMarkers.live}
              onChange={(v) => onOrderbookChange({ tradeMarkers: { ...orderbook.tradeMarkers, live: v } })} />
          </Flex>,
          <Flex key="ob-bt-markers" justify="space-between" align="center" gap={16}>
            <span>{t('chart.setting.backtestMarkers')}</span>
            <Select
              size="small"
              style={{ width: 160 }}
              allowClear
              value={orderbook.tradeMarkers.backtestId}
              placeholder={t('chart.setting.backtestMarkersPlaceholder')}
              options={backtestOptions ?? []}
              // allowClear 清空时 v 为 undefined，归一化为 null（无回测任务）
              onChange={(v) => onOrderbookChange({ tradeMarkers: { ...orderbook.tradeMarkers, backtestId: v ?? null } })}
            />
          </Flex>,
        ] : null}
      </Space>
    </Modal>
  );
};

export default ChartSettingModal;
