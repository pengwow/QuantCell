/**
 * 启动确认弹窗内容：参考价输入 + 价格计划可视化（迷你图 + 紧凑区间 chips）。
 * 用在 Worker 页 handleStart 的 modal.confirm 里；参考价经 refPriceRef 回传父组件，
 * 确认启动时随 POST /workers/{id}/lifecycle/start 的 body 固化。
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, InputNumber, Space, Typography } from 'antd';
import { usePricePlan } from '../../hooks/usePricePlan';
import PricePlanSection from '../pricePlan/PricePlanSection';
import PricePlanMiniChart from '../pricePlan/PricePlanMiniChart';

interface Props {
  strategyName: string;
  params: Record<string, unknown>;
  /** 父组件读取确认时参考价的穿透引用（forwardRef 太重，启动场景一个 ref 够用） */
  refPriceRef: { current: number | null };
}

export default function StartPlanConfirm({ strategyName, params, refPriceRef }: Props) {
  const { t } = useTranslation();
  const [refPriceInput, setRefPriceInput] = useState<number | null>(null);
  const { data, error, loading } = usePricePlan({ strategyName, params, refPrice: refPriceInput });

  return (
    <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
      <Space size="small">
        <Typography.Text>{t('pricePlan.worker_ref_price')}</Typography.Text>
        <InputNumber
          autoFocus
          min={0}
          value={refPriceInput}
          onChange={(v) => {
            refPriceRef.current = v ?? null;
            setRefPriceInput(v ?? null);
          }}
        />
      </Space>
      {error && <Alert type="warning" message={error} />}
      <PricePlanMiniChart plan={data ?? null} refPrice={refPriceInput} loading={loading} />
      <PricePlanSection plan={data ?? null} compact maxHeight={140} />
    </Space>
  );
}
