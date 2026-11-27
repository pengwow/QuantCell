/**
 * 启动确认弹窗内容（Worker 列表点「启动」时的价格计划确认区）。
 *
 * 参考价不再手填：打开弹窗即对 worker 全量标的静默取实时价，逐个写入父组件穿透的
 * refPricesRef（onOk 读取后按标的固化价格计划锚点）。首标的取价失败只提示、不阻塞
 * 弹窗——最终阻断在父组件 onOk（refPrice 为 null 时不提交），保持「必须有参考价才
 * 启动」的语义。预览区用 Segmented 切标的，每标的按各自实时价独立预览。
 */
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Segmented, Space, Typography } from 'antd';
import { fetchLatestPrice } from '../../api/pricePlanApi';
import { usePricePlan } from '../../hooks/usePricePlan';
import PricePlanKlineChart from '../pricePlan/PricePlanKlineChart';
import PricePlanSection from '../pricePlan/PricePlanSection';

interface StartPlanConfirmProps {
  strategyName: string;
  /** worker 全量标的（trading_config.symbols_config.symbols） */
  symbols: string[];
  exchange: string | null;
  marketType: string | null;
  params: Record<string, unknown>;
  /** 父组件读取各标的参考价的穿透引用（onOk 启动时随请求提交） */
  refPricesRef: { current: Record<string, number | null> };
}

// 错误剥离兼容 detail 为字符串或 {code,message} 两种后端形态（与 useSymbolPrice 同口径）
function extractPriceError(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: string; code?: string };
    return d.message ?? d.code ?? '';
  }
  return err instanceof Error ? err.message : String(err ?? '');
}

const StartPlanConfirm: React.FC<StartPlanConfirmProps> = ({
  strategyName,
  symbols,
  exchange,
  marketType,
  params,
  refPricesRef,
}) => {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string | null>(null);
  // 当前标的：用户选中项被删/失配时收敛回首标的
  const current =
    selected != null && symbols.includes(selected) ? selected : (symbols[0] ?? null);

  const [prices, setPrices] = useState<Record<string, number | null>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  // 标的数组每次渲染都是新引用，用 join 结果作为稳定依赖
  const symbolsKey = symbols.join('|');

  // 挂载/标的或交易所变化 → 全量静默取价；卸载后既不 setState 也不写父 ref
  useEffect(() => {
    if (!exchange || !marketType || !symbolsKey) return;
    let alive = true;
    const syms = symbolsKey.split('|');
    // 取价逻辑收在局部函数里：既避免 effect 体内同步 setState，又保持卸载守卫集中
    const loadPrices = async () => {
      setLoading(true);
      setErrors({});
      const results = await Promise.allSettled(
        syms.map((sym) => fetchLatestPrice({ symbol: sym, market_type: marketType, exchange })),
      );
      if (!alive) return;
      const nextPrices: Record<string, number | null> = {};
      const nextErrors: Record<string, string> = {};
      results.forEach((r, i) => {
        const sym = syms[i];
        if (r.status === 'fulfilled' && r.value.price > 0) {
          nextPrices[sym] = r.value.price;
        } else {
          nextPrices[sym] = null;
          nextErrors[sym] = r.status === 'rejected' ? extractPriceError(r.reason) : '';
        }
        refPricesRef.current[sym] = nextPrices[sym];
      });
      setPrices(nextPrices);
      setErrors(nextErrors);
    };
    void loadPrices().finally(() => {
      if (alive) setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [symbolsKey, exchange, marketType, refPricesRef]);

  const refPrice = current ? prices[current] ?? null : null;
  const { data: plan, error: planError } = usePricePlan({ strategyName, params, refPrice });

  const firstSymbol = symbols[0];
  const firstError = firstSymbol ? errors[firstSymbol] : undefined;
  const waitingPrice = refPrice == null && !loading && !firstError;

  return (
    <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
      {symbols.length > 1 && (
        <Segmented
          size="small"
          value={current ?? undefined}
          onChange={(v) => setSelected(String(v))}
          options={symbols.map((s) => ({ label: s, value: s }))}
        />
      )}
      <Space size="small" wrap>
        <Typography.Text type="secondary">{t('pricePlan.worker_ref_price')}</Typography.Text>
        <Typography.Text strong>
          {refPrice != null ? refPrice : loading ? '...' : '-'}
        </Typography.Text>
        {current && <Typography.Text type="secondary">{current}</Typography.Text>}
      </Space>
      {firstError && (
        <Alert
          type="warning"
          showIcon
          message={t('pricePlan.start_price_missing_hint', { symbol: firstSymbol })}
        />
      )}
      {planError && <Alert type="warning" showIcon message={planError} />}
      {waitingPrice && <Alert type="info" showIcon message={t('pricePlan.kline_waiting_price')} />}
      <PricePlanKlineChart
        symbol={current}
        exchange={exchange}
        marketType={marketType}
        plan={plan ?? null}
        refPrice={refPrice}
        height={300}
      />
      <PricePlanSection plan={plan ?? null} compact maxHeight={140} />
    </Space>
  );
};

export default StartPlanConfirm;
