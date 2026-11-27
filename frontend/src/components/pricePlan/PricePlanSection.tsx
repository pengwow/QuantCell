/**
 * 价格计划展示区：warnings 黄牌 + 价位 chips + 可折叠明细表。
 *
 * 三处复用：编辑器预览 tab（Task 8）、创建弹窗自检区 compact 模式（Task 9）、
 * Worker 详情 plan tab（Task 10）。纯展示组件，数据由调用方传入，内部不发请求。
 *
 * 行↔线联动：明细表行 hover 时回调 onActivePriceChange，由父组件把 activePrice
 * 传给 PricePlanMiniChart / K 线 overlay 高亮对应价位线。
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Space, Table, Tag, Typography } from 'antd';
import type { PricePlan, PricePlanLevel } from '../../types/pricePlan';

/** 档位动作 → 展示颜色与词条 key（chips 与明细表共用；文案走 i18n，key 见 i18n/zh-CN.json pricePlan.*） */
export const ACTION_META: Record<PricePlanLevel['action'], { color: string; text: string }> = {
  buy: { color: 'volcano', text: 'pricePlan.action_buy' },
  sell: { color: 'geekblue', text: 'pricePlan.action_sell' },
  tp: { color: 'gold', text: 'pricePlan.action_tp' },
  mid: { color: 'default', text: 'pricePlan.action_mid' },
};

interface Props {
  plan: PricePlan | null;
  /** 紧凑模式（创建弹窗自检区）：默认只渲染 chips + warnings，明细收起 */
  compact?: boolean;
  /** 明细表滚动高度，缺省 260 */
  maxHeight?: number;
  /** 当前高亮价位（由父组件从图表联动回路传回） */
  activePrice?: number | null;
  /** 已触发层 index 集合（worker 详情传运行态：打勾/淡化，spec §4.A；预览场景不传） */
  triggeredIndexes?: number[];
  /** 明细行 hover / 离开时回调（null = 离开） */
  onActivePriceChange?: (price: number | null) => void;
}

export default function PricePlanSection({
  plan,
  compact = false,
  maxHeight = 260,
  activePrice = null,
  triggeredIndexes,
  onActivePriceChange,
}: Props) {
  const { t } = useTranslation();
  const [showTable, setShowTable] = useState(!compact);
  const triggered = new Set(triggeredIndexes); // 已触发层：打勾 + 淡化（spec §4.A）

  if (!plan) return null;

  const columns = [
    { title: '#', dataIndex: 'index', width: 48 },
    {
      title: t('pricePlan.col_action'),
      dataIndex: 'action',
      width: 80,
      render: (a: PricePlanLevel['action']) => {
        const meta = ACTION_META[a];
        return <Tag color={meta.color}>{t(meta.text)}</Tag>;
      },
    },
    { title: t('pricePlan.col_price'), dataIndex: 'price', width: 110, render: (p: number) => p.toFixed(4) },
    { title: t('pricePlan.col_target'), dataIndex: 'target_position', width: 100 },
    { title: t('pricePlan.col_label'), dataIndex: 'label', ellipsis: true },
  ];

  return (
    <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
      {plan.warnings.map((w, i) => (
        <Alert key={i} type="warning" showIcon message={w} />
      ))}

      {/* 价位 chips：一档一个 Tag，hover 等效明细行 hover 联动 */}
      <Space size={[4, 4]} wrap>
        {plan.levels.map((lv) => {
          const meta = ACTION_META[lv.action];
          const active = activePrice != null && Math.abs(lv.price - activePrice) < 1e-9;
          const done = triggered.has(lv.index);
          return (
            <Tag
              key={lv.index}
              color={meta.color}
              style={{ cursor: onActivePriceChange ? 'pointer' : undefined, opacity: active ? 1 : done ? 0.55 : 0.85 }}
              onMouseEnter={() => onActivePriceChange?.(lv.price)}
              onMouseLeave={() => onActivePriceChange?.(null)}
            >
              {done && '✓ '}
              {t(meta.text)} {lv.price.toFixed(4)}
              {lv.label ? ` · ${lv.label}` : ''}
            </Tag>
          );
        })}
      </Space>

      {/* 区间摘要（spec §4.B：可视化订单价格范围效果） */}
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {t('pricePlan.summary_range', {
          min: plan.summary.price_min.toFixed(4),
          max: plan.summary.price_max.toFixed(4),
        })}
        {plan.summary.entry_price != null &&
          t('pricePlan.summary_entry', { entry: plan.summary.entry_price.toFixed(4) })}
      </Typography.Text>

      {/* 明细表：非 compact 默认展开；compact 下点击展开 */}
      <Typography.Link style={{ fontSize: 12 }} onClick={() => setShowTable((v) => !v)}>
        {showTable ? t('pricePlan.collapse_detail') : t('pricePlan.expand_detail', { count: plan.levels.length })}
      </Typography.Link>
      {showTable && (
        <Table<PricePlanLevel>
          size="small"
          rowKey="index"
          columns={columns}
          dataSource={plan.levels}
          pagination={false}
          scroll={{ y: maxHeight }}
          onRow={(record) => ({
            onMouseEnter: () => onActivePriceChange?.(record.price),
            onMouseLeave: () => onActivePriceChange?.(null),
            style: {
              cursor: onActivePriceChange ? 'pointer' : undefined,
              background: activePrice != null && Math.abs(record.price - activePrice) < 1e-9 ? 'rgba(22,119,255,0.08)' : undefined,
              opacity: triggered.has(record.index) ? 0.45 : undefined, // 已触发层淡化
            },
          })}
        />
      )}
    </Space>
  );
}
