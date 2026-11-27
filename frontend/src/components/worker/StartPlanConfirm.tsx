/**
 * 启动确认弹窗内容（Worker 列表点「启动」时的价格计划确认区）。
 *
 * 参考价不再手填：打开弹窗即对 worker 首标的自动取实时价（useSymbolPrice），
 * 取到即写回 refPriceRef 供父组件 onOk 读取并随启动请求固化价格计划锚点；
 * 取价失败（交易所不可达）如实显示 Alert + 重试，不做本地降级——refPrice 为
 * null 时父组件 onOk 自带 warning 阻断，保持「必须有参考价才启动」的语义。
 */
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Space, Typography } from 'antd';
import { usePricePlan } from '../../hooks/usePricePlan';
import { useSymbolPrice } from '../../hooks/useSymbolPrice';
import PricePlanSection from '../pricePlan/PricePlanSection';
import PricePlanMiniChart from '../pricePlan/PricePlanMiniChart';

interface StartPlanConfirmProps {
  strategyName: string;
  /** worker 首标的 + 交易所 + 市场类型：实时取价用（Worker.tsx 从 trading_config 解析） */
  symbol: string | null;
  exchange: string | null;
  marketType: string | null;
  params: Record<string, unknown>;
  /** 父组件读取确认时刻参考价的穿透引用（启动场景一个可变 ref 足够，不引 forwardRef） */
  refPriceRef: { current: number | null };
}

const StartPlanConfirm: React.FC<StartPlanConfirmProps> = ({
  strategyName,
  symbol,
  exchange,
  marketType,
  params,
  refPriceRef,
}) => {
  const { t } = useTranslation();
  const { data: price, loading: priceLoading, error: priceError, refetch } = useSymbolPrice({
    symbol,
    marketType,
    exchange,
  });
  const refPrice = price?.price ?? null;

  useEffect(() => {
    refPriceRef.current = refPrice;
  }, [refPrice, refPriceRef]);

  const { data, error, loading } = usePricePlan({ strategyName, params, refPrice });

  return (
    <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
      <Space size="small">
        <Typography.Text type="secondary">{t('pricePlan.worker_ref_price')}</Typography.Text>
        <Typography.Text strong>
          {refPrice != null ? refPrice : priceLoading ? '...' : '-'}
        </Typography.Text>
        {symbol && <Typography.Text type="secondary">{symbol}</Typography.Text>}
      </Space>
      {priceError && (
        <Alert
          type="warning"
          showIcon
          message={t('pricePlan.auto_fetch_failed', { message: priceError })}
          action={
            <Button size="small" onClick={refetch}>
              {t('pricePlan.auto_retry')}
            </Button>
          }
        />
      )}
      {error && <Alert type="warning" showIcon message={error} />}
      <PricePlanMiniChart plan={data ?? null} refPrice={refPrice} loading={loading} />
      <PricePlanSection plan={data ?? null} compact maxHeight={140} />
    </Space>
  );
};

export default StartPlanConfirm;
