/**
 * Worker 详情「价格计划」tab：启动时固化的计划 + 运行态触发进度。
 *
 * state=fixed：ref_price 锚定、复现稳定；pending：尚未固化（引导下次启动时在
 * 确认弹窗填写参考价）。triggered_count / next_trigger 来自
 * GET /workers/{id}/plan（后端 _plan_runtime_progress 纯函数推导，Task 5）。
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Card, Empty, Space, Spin, Tag, Typography } from 'antd';
import { getWorkerPlan } from '../../api/pricePlanApi';
import type { WorkerPlanResponse } from '../../types/pricePlan';
import PricePlanSection from '../../components/pricePlan/PricePlanSection';
import PricePlanMiniChart from '../../components/pricePlan/PricePlanMiniChart';

export default function WorkerPricePlanTab({ workerId }: { workerId: number }) {
  const { t } = useTranslation();
  const [resp, setResp] = useState<WorkerPlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activePrice, setActivePrice] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    getWorkerPlan(workerId)
      .then((r) => {
        if (alive) setResp(r);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [workerId]);

  if (error) return <Alert type="error" message={error} />;
  if (!resp) return <Spin />;

  if (resp.state !== 'fixed' || !resp.plan) {
    return <Empty description={t('pricePlan.detail_empty_pending')} />;
  }

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card size="small" title={t('pricePlan.detail_progress_title')}>
        <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
          <Space size="small" wrap>
            <Tag color={resp.state === 'fixed' ? 'green' : 'orange'}>
              {resp.state === 'fixed' ? t('pricePlan.detail_state_fixed') : t('pricePlan.detail_state_pending')}
            </Tag>
            <Typography.Text>
              {t('pricePlan.detail_ref_price', { price: resp.ref_price?.toFixed(4) ?? '—' })}
            </Typography.Text>
            <Typography.Text>
              {t('pricePlan.detail_triggered_count', { n: resp.triggered_count ?? 0, total: resp.plan.levels.length })}
            </Typography.Text>
          </Space>
          {resp.next_trigger && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('pricePlan.detail_next_trigger', {
                label: resp.next_trigger.label ?? resp.next_trigger.price.toFixed(4),
                dist: resp.next_trigger.distance_pct.toFixed(2),
              })}
            </Typography.Text>
          )}
        </Space>
      </Card>
      {/* K 线为样例走势（围绕固化参考价），用于展示计划档位在价格轴上的分布 */}
      <PricePlanMiniChart plan={resp.plan} refPrice={resp.ref_price ?? null} activePrice={activePrice} />
      <PricePlanSection
        plan={resp.plan}
        activePrice={activePrice}
        triggeredIndexes={resp.triggered_indexes}
        onActivePriceChange={setActivePrice}
      />
    </Space>
  );
}

/**
 * 列表展开行摘要 chips：固化状态 + 已触发比例一行式展示。
 * ponytail: 每个展开行独立 fetch 一次 plan，展开才请求；失败静默不渲染
 * （展开面板是轻摘要，完整计划在详情 tab，这里不值得做缓存层）。
 */
export function PlanSummaryChips({ workerId }: { workerId: number }) {
  const { t } = useTranslation();
  const [state, setState] = useState<WorkerPlanResponse | null>(null);

  useEffect(() => {
    let alive = true;
    getWorkerPlan(workerId)
      .then((r) => {
        if (alive) setState(r);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [workerId]);

  if (!state?.plan) return null;
  const total = state.plan.levels.length;
  const triggered = state.triggered_count ?? 0;
  const pct = total ? Math.round((triggered / total) * 100) : 0;
  return (
    <Space size={4} wrap>
      <Tag color={state.state === 'fixed' ? 'green' : 'orange'} style={{ fontSize: 11 }}>
        {state.state === 'fixed' ? t('pricePlan.chips_state_fixed') : t('pricePlan.chips_state_pending')}
      </Tag>
      <Tag style={{ fontSize: 11 }}>{t('pricePlan.chips_triggered', { n: triggered, total, p: pct })}</Tag>
    </Space>
  );
}
