/**
 * 价格计划自动预览（创建 Worker 弹窗用）。
 *
 * 不再手填参考价：按激活标的回源实时价作为 refPrice 驱动 usePricePlan 预览；
 * 多标的时渲染 chips 切换，每个标的按各自实时价独立预览。取价失败（交易所
 * 不可达）如实显示 Alert + 重试——策略要在交易所真实使用，取不到实时价本身
 * 就是要暴露的问题，不做任何本地数据降级（spec 决策）。
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Card, Space, Tag } from 'antd';
import PricePlanSection from './PricePlanSection';
import PricePlanMiniChart from './PricePlanMiniChart';
import { usePricePlan } from '../../hooks/usePricePlan';
import { useSymbolPrice } from '../../hooks/useSymbolPrice';

interface PricePlanAutoPreviewProps {
  strategyName: string;
  /** 提交口径的标的列表（已大写去重）；空数组时只显示引导提示 */
  symbols: string[];
  exchange: string | null | undefined;
  marketType: string | null | undefined;
}

const PricePlanAutoPreview: React.FC<PricePlanAutoPreviewProps> = ({
  strategyName,
  symbols,
  exchange,
  marketType,
}) => {
  const { t } = useTranslation();
  // 激活 chip 所在标；用户增删标的后被删项自动收敛回首标的
  const [active, setActive] = useState<string | null>(null);
  const current = active != null && symbols.includes(active) ? active : (symbols[0] ?? null);

  const {
    data: price,
    loading: priceLoading,
    error: priceError,
    refetch,
  } = useSymbolPrice({ symbol: current, marketType, exchange });

  const refPrice = price?.price ?? null;
  // 预览参数恒传空对象：后端 resolve 时补策略文件默认值（spec 决策）
  const { data: plan, error: planError, loading: planLoading } = usePricePlan({
    strategyName,
    params: {},
    refPrice,
  });

  return (
    <Card size="small" title={t('pricePlan.create_self_check_title')} style={{ marginTop: 16 }}>
      <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
        {!current && <Alert type="info" showIcon message={t('pricePlan.auto_need_symbol')} />}
        {symbols.length > 1 && (
          <Space size={4} wrap>
            {symbols.map((s) => (
              <Tag.CheckableTag key={s} checked={s === current} onChange={() => setActive(s)}>
                {s}
              </Tag.CheckableTag>
            ))}
          </Space>
        )}
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
        <PricePlanMiniChart plan={plan ?? null} refPrice={refPrice} loading={priceLoading || planLoading} />
        <PricePlanSection plan={plan ?? null} compact maxHeight={120} />
        {!priceError && planError && <Alert type="warning" showIcon message={planError} />}
      </Space>
    </Card>
  );
};

export default PricePlanAutoPreview;
