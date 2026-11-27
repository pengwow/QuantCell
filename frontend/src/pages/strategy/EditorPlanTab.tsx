/**
 * 策略编辑器「价格计划」tab：声明 price_plan 的策略在此可视化预览计划结构。
 *
 * 参数值来源：参数定义的 default 值 + 可选 JSON 覆盖。编辑器态没有运行时参数实例
 * （参数值在 worker 创建/回测表单里才填），预览语义是「结构可视化」——运行态锚定
 * 见 worker 启动固化链路（Task 9 / Task 10）。
 */
import { useState } from 'react';
import { Alert, Card, Input, InputNumber, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { usePricePlan } from '../../hooks/usePricePlan';
import PricePlanSection from '../../components/pricePlan/PricePlanSection';
import PricePlanMiniChart from '../../components/pricePlan/PricePlanMiniChart';

interface Props {
  /** 当前编辑中的策略名（selectedStrategy.name） */
  strategyName: string;
}

export default function EditorPlanTab({ strategyName }: Props) {
  const { t } = useTranslation();
  const [refPrice, setRefPrice] = useState<number | null>(null);
  const [overrideText, setOverrideText] = useState('');
  const [activePrice, setActivePrice] = useState<number | null>(null);

  // JSON 覆盖解析：非法 JSON 按无覆盖处理并提示，不让预览白屏
  // 合法的 {}（无字段覆盖）不算非法，只有 parse 抛错才算
  let overrideInvalid = false;
  let overrides: Record<string, unknown> = {};
  try {
    overrides = overrideText.trim() ? (JSON.parse(overrideText) as Record<string, unknown>) : {};
  } catch {
    overrideInvalid = true;
    overrides = {};
  }

  const { data, error, loading } = usePricePlan({
    strategyName,
    params: overrides, // 默认参数由后端 preview resolved merge 补齐，前端只送覆盖
    refPrice,
  });

  if (!strategyName) {
    return <Alert type="info" message={t('pricePlan.editor_save_first')} />;
  }

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card size="small" title={t('pricePlan.editor_preview_settings')}>
        <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
          <Space size="small" wrap>
            <Typography.Text>{t('pricePlan.editor_ref_price')}</Typography.Text>
            <InputNumber
              value={refPrice}
              onChange={(v) => setRefPrice(v == null ? null : Number(v))}
              min={0}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('pricePlan.editor_ref_price_hint')}
            </Typography.Text>
          </Space>
          <Input.TextArea
            rows={2}
            placeholder={t('pricePlan.editor_override_placeholder')}
            value={overrideText}
            onChange={(e) => setOverrideText(e.target.value)}
          />
          {overrideInvalid && <Alert type="warning" message={t('pricePlan.editor_override_invalid')} />}
        </Space>
      </Card>

      {error && <Alert type="error" message={error} />}

      <Card size="small" title={t('pricePlan.editor_plan_preview')}>
        {/* data 即 PricePlanPreviewResponse（顶层 levels/summary/warnings），直接当 PricePlan 用 */}
        <PricePlanMiniChart plan={data ?? null} refPrice={refPrice} activePrice={activePrice} loading={loading} />
        <div style={{ marginTop: 16 }}>
          <PricePlanSection plan={data ?? null} activePrice={activePrice} onActivePriceChange={setActivePrice} />
        </div>
      </Card>
    </Space>
  );
}
