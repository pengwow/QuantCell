/**
 * Worker 详情「价格计划」tab：启动时固化的计划 + 运行态触发进度。
 *
 * state=fixed：ref_price 锚定、复现稳定；pending：尚未固化（引导下次启动时在
 * 确认弹窗填写参考价）。triggered_count / next_trigger 来自
 * GET /workers/{id}/plan（后端 _plan_runtime_progress 纯函数推导，Task 5）。
 *
 * 多标的：顶部 chips 列出 worker 全部标的（含 pending 占位），切换只换数据源
 * （按 symbol 读对应固化快照），不重算。
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Card, Empty, Segmented, Space, Spin, Tag, Typography } from 'antd';
import { getWorkerPlan } from '../../api/pricePlanApi';
import type { WorkerPlanResponse } from '../../types/pricePlan';
import PricePlanSection from '../../components/pricePlan/PricePlanSection';
import PricePlanKlineChart from '../../components/pricePlan/PricePlanKlineChart';

export default function WorkerPricePlanTab({ workerId }: { workerId: number }) {
  const { t } = useTranslation();
  const [resp, setResp] = useState<WorkerPlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  // 生效标的：用户选中项仍在列表则沿用，否则收敛回列表首标的
  const currentSymbol = useMemo(() => {
    const list = resp?.symbols ?? [];
    if (selected && list.some((s) => s.symbol === selected)) return selected;
    return list[0]?.symbol ?? resp?.symbol ?? null;
  }, [resp, selected]);

  useEffect(() => {
    let alive = true;
    getWorkerPlan(workerId, currentSymbol ?? undefined)
      .then((r) => {
        if (!alive) return;
        setResp(r);
        setError(null);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [workerId, currentSymbol]);

  if (error) return <Alert type="error" message={error} />;
  if (!resp) return <Spin />;

  const symbolStates = resp.symbols ?? [];
  const isFixed = resp.state === 'fixed' && !!resp.plan;

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      {symbolStates.length > 0 && (
        <Segmented
          size="small"
          value={currentSymbol ?? undefined}
          onChange={(v) => setSelected(String(v))}
          options={symbolStates.map((s) => ({
            label: s.symbol + (s.state === 'pending' ? t('pricePlan.pending_symbol') : ''),
            value: s.symbol,
          }))}
        />
      )}
      {!isFixed && <Empty description={t('pricePlan.detail_empty_pending')} />}
      {isFixed && (
        <Card size="small" title={t('pricePlan.detail_progress_title')}>
          <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
            <Space size="small" wrap>
              <Tag color="green">{t('pricePlan.detail_state_fixed')}</Tag>
              <Typography.Text>
                {t('pricePlan.detail_ref_price', { price: resp.ref_price?.toFixed(4) ?? '—' })}
              </Typography.Text>
              <Typography.Text>
                {t('pricePlan.detail_triggered_count', {
                  n: resp.triggered_count ?? 0,
                  total: resp.plan?.levels.length ?? 0,
                })}
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
      )}
      {isFixed && (
        <PricePlanKlineChart
          symbol={currentSymbol}
          plan={resp.plan ?? null}
          refPrice={resp.ref_price ?? null}
          triggeredIndexes={resp.triggered_indexes}
        />
      )}
      {isFixed && (
        <PricePlanSection plan={resp.plan ?? null} triggeredIndexes={resp.triggered_indexes} />
      )}
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
