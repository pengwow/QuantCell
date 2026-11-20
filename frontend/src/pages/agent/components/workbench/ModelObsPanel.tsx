/**
 * 工作台模型行展开面板：训练期元数据（obs/奖励/成本/OOS）摘要（P3 收尾）。
 *
 * 数据源双层：
 *  - 主：detail 端点（GET /models/{id}/detail，modelApi.getModelDetail）的 metadata ——
 *    注册表把 meta.json 除 walk_forward 外全量并入（services/model_registry.py::seed_models_safe）；
 *  - 兜底：unified 行可选字段（modelApi.UnifiedModelRow 扩展位）——unified 端点当前未透传
 *    这些字段（缺口已上报），透传落地后未注册行（工作台刚训练的产物）也能直读展示。
 * 空字段一律「—」，不造假。
 *
 * 观测模式语义（backend services/rl_service.py）：
 *  - features = 原生指标向量（默认，obs_window 训练期固定写 1，展示上视为「不适用」）；
 *  - ohlcv_window = 原始 OHLCV 归一化窗口，obs_features = 基座通道 + 派生微结构通道
 *    （spread/mid_price，来自 bookDepth/bookTicker 聚合，仅作特征不可撮合）。
 * oos 报告（rl/walk_forward_rl.py::_oos_report）：evaluable/n_valid_folds/sharpe_ratio/
 * total_return_pct/passed；注册侧存于 metadata.walk_forward_oos。
 */
import { useEffect, useState } from 'react';
import { Alert, Descriptions, Spin, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import { modelApi } from '@/api/modelApi';
import type { ModelDetail, UnifiedModelRow } from '@/api/modelApi';
import { rewardText } from './metaFormat';

type OosReport = NonNullable<UnifiedModelRow['oos']>;

/** 行字段与 detail.metadata 合并读取（行字段优先：unified 透传后即最新直读源） */
const pick = <T,>(rowVal: T | undefined, metaVal: unknown): T | undefined =>
  (rowVal ?? metaVal) as T | undefined;

export default function ModelObsPanel({ row }: { row: UnifiedModelRow }) {
  const { t } = useTranslation();
  // loading 初值由「是否发起拉取」推导（已注册行挂载即转圈），effect 内不再同步 setState
  // ponytail: 同一已展开面板 row.model_id 变化的极罕场景不回置 loading；antd 展开行卸载即重建，无实际影响
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [loading, setLoading] = useState(() => row.registered && row.model_id != null);
  const [failed, setFailed] = useState<string | null>(null);

  // 已注册行展开时懒拉模型卡（未注册行不发请求：detail 404，展示以行字段兜底）。
  // 面板随展开/收起卸载挂载，state 天然 fresh，无需在 effect 里手动清空
  useEffect(() => {
    if (!row.registered || !row.model_id) return;
    let alive = true;
    modelApi
      .getModelDetail(row.model_id)
      .then((d) => alive && setDetail(d))
      .catch((err) => alive && setFailed(err instanceof Error ? err.message : String(err)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [row.registered, row.model_id]);

  const meta: Record<string, unknown> = detail?.metadata ?? {};

  const obsMode = pick(row.obs_mode, meta.obs_mode);
  const obsWindow = pick(row.obs_window, meta.obs_window);
  const obsFeatures = pick(row.obs_features, meta.obs_features);
  const dataType = pick(row.data_type, meta.data_type);
  const rewardTerms = pick(row.reward_terms, meta.reward_terms);
  const txnCost = pick(row.transaction_cost, meta.transaction_cost);
  const oos = (row.oos ?? (meta.walk_forward_oos as OosReport | undefined)) ?? undefined;

  // 观测模式文案；ohlcv_window 才有意义化窗口（features 模式训练期写 1，为占位）
  const obsModeText = (() => {
    if (typeof obsMode !== 'string' || !obsMode) return null;
    if (obsMode === 'ohlcv_window') return t('wb_meta_obs_mode_ohlcv', { n: obsWindow ?? '?' });
    if (obsMode === 'features') return t('wb_meta_obs_mode_features');
    return obsMode;
  })();
  const obsWindowText =
    obsMode === 'ohlcv_window' && typeof obsWindow === 'number' ? String(obsWindow) : null;
  const featuresText = Array.isArray(obsFeatures) && obsFeatures.length > 0 ? obsFeatures.map(String) : null;
  const rewardTextVal = rewardText(rewardTerms);
  const costText = typeof txnCost === 'number' && Number.isFinite(txnCost) ? `${txnCost}（${(txnCost * 100).toFixed(3).replace(/\.?0+$/, '')}%）` : null;

  const dash = <span style={{ color: 'var(--qc-text-tertiary)' }}>—</span>;
  const oosItem = (() => {
    if (oos == null || typeof oos !== 'object') return dash;
    if (oos.evaluable !== true) return <span>{t('wb_meta_oos_evaluable_false')}</span>;
    const foldPart = typeof oos.n_valid_folds === 'number' ? t('wb_meta_oos_folds', { n: oos.n_valid_folds }) : null;
    const metricPart =
      oos.sharpe_ratio != null && oos.total_return_pct != null
        ? t('wb_meta_oos_sharpe_return', {
            sharpe: Number(oos.sharpe_ratio).toFixed(2),
            ret: Number(oos.total_return_pct).toFixed(2),
          })
        : null;
    const passPart =
      oos.passed == null ? null : oos.passed ? t('wb_meta_oos_passed') : t('wb_meta_oos_not_passed');
    return (
      <span>
        {[metricPart, foldPart, passPart].filter(Boolean).join(' · ') || '—'}
      </span>
    );
  })();

  return (
    <div className="wb-meta-panel">
      {!row.registered && (
        <Alert type="info" showIcon title={t('wb_meta_unregistered')} style={{ marginBottom: 8 }} />
      )}
      {failed && (
        <Alert
          type="warning"
          showIcon
          title={t('wb_meta_load_failed', { err: failed })}
          style={{ marginBottom: 8 }}
        />
      )}
      <Descriptions
        title={<span style={{ fontSize: 12 }}>{t('wb_meta_panel_title')}</span>}
        size="small"
        bordered
        column={2}
        items={[
          { key: 'obs_mode', label: t('wb_meta_label_obs_mode'), children: obsModeText ?? dash },
          { key: 'obs_window', label: t('wb_meta_label_obs_window'), children: obsWindowText ?? dash },
          {
            key: 'obs_features',
            label: t('wb_meta_label_obs_features'),
            span: 2,
            children: featuresText ? (
              <>
                {featuresText.map((f) => (
                  <Tag key={f} style={{ marginInlineEnd: 4 }}>
                    {f}
                  </Tag>
                ))}
                <span style={{ color: 'var(--qc-text-tertiary)', fontSize: 12 }}>
                  {t('wb_meta_label_features_count', { n: featuresText.length })}
                </span>
              </>
            ) : (
              dash
            ),
          },
          { key: 'data_type', label: t('wb_meta_label_data_type'), children: typeof dataType === 'string' && dataType ? dataType : dash },
          { key: 'reward', label: t('wb_meta_label_reward_terms'), children: rewardTextVal ?? dash },
          { key: 'cost', label: t('wb_meta_label_txn_cost'), children: costText ?? dash },
          { key: 'oos', label: t('wb_meta_label_oos'), children: oosItem },
        ]}
      />
      {loading && (
        <div className="wb-center-spin" style={{ marginTop: 8 }}>
          <Spin size="small" />
        </div>
      )}
    </div>
  );
}
