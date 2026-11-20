/**
 * 右栏「概览」页签：因子元信息 + 最近一次分析的核心指标（catalog.last_metrics，0 额外请求）。
 */
import { useTranslation } from 'react-i18next';
import { Button, Card, Col, Descriptions, Flex, Row, Select, Space, Statistic } from 'antd';
import type { FactorCatalogItem } from '@/api/factor';
import { useQuantColors } from '@/utils/colors';
import {
  EDITABLE_CATEGORIES,
  categoryLabel,
  factorSource,
  isAiProduced,
  toneColor,
  toneOf,
} from './factorMeta';
import { QcEmpty } from '@/components/ui/DataTable';

const FactorOverviewPanel: React.FC<{
  factor: FactorCatalogItem;
  onGoAnalyze?: () => void;
  /** 「查看代码」跳转：切到详情的代码 Tab */
  onGoCode?: () => void;
  /** 传入则分类可就地修改；内置/代码/合成因子后端禁止修改，仍只读展示 */
  onCategoryChange?: (category: string) => Promise<void> | void;
  categorySaving?: boolean;
}> = ({ factor, onGoAnalyze, onGoCode, onCategoryChange, categorySaving }) => {
  const { t } = useTranslation();
  const qc = useQuantColors();
  const lm = factor.last_metrics;
  const source = factorSource(factor);

  const statusLabel = (s: FactorCatalogItem['lifecycle_status']) =>
    t(`factor_status_${s.toLowerCase()}`) || s;

  const sourceLabel = (src: ReturnType<typeof factorSource>) =>
    t(`factor_lib_source_${src}`) || src;

  // 概览可展示的核心指标（last_metrics 口径，与快照摘要一致）
  const metrics: { key: string; label: string; text: string; raw: number | null }[] = lm
    ? [
        { key: 'ic_mean', label: t('factor_stat_ic_mean') || 'IC 均值', text: (lm.ic_mean ?? 0).toFixed(4), raw: lm.ic_mean },
        { key: 'ic_ir_loose', label: t('factor_stat_icir') || 'ICIR', text: (lm.ic_ir ?? 0).toFixed(4), raw: lm.ic_ir },
        {
          key: 'ic_positive_rate',
          label: t('factor_stat_ic_pos_rate') || 'IC 胜率',
          text: lm.ic_positive_rate == null ? '—' : `${(lm.ic_positive_rate * 100).toFixed(1)}%`,
          raw: lm.ic_positive_rate,
        },
        {
          key: 'long_short_return',
          label: t('factor_stat_ls_return') || '多空收益',
          text: (lm.long_short_return ?? 0).toFixed(4),
          raw: lm.long_short_return,
        },
        {
          key: 'monotonicity',
          label: t('factor_stat_monotonicity') || '单调性 Spearman',
          text: (lm.monotonicity_spearman ?? 0).toFixed(4),
          raw: lm.monotonicity_spearman,
        },
        {
          key: 'stability',
          label: t('factor_stat_stability') || '稳定性(自相关)',
          text: (lm.stability_autocorr ?? 0).toFixed(4),
          raw: lm.stability_autocorr,
        },
        {
          key: 'coverage',
          label: t('factor_stat_coverage') || '覆盖率',
          text: lm.coverage == null ? '—' : `${(lm.coverage * 100).toFixed(1)}%`,
          raw: lm.coverage,
        },
        {
          key: 'turnover',
          label: t('factor_stat_turnover') || '换手率',
          text: lm.turnover == null ? '—' : lm.turnover.toFixed(4),
          raw: lm.turnover,
        },
        {
          key: 'annualized_ir',
          label: t('factor_stat_ann_ir') || '年化 IR',
          text: lm.annualized_ir == null ? '—' : lm.annualized_ir.toFixed(2),
          raw: lm.annualized_ir,
        },
        {
          key: 'nw_t_stat',
          label: t('factor_stat_nw_tstat') || 'NW t-stat',
          text: lm.nw_t_stat == null ? '—' : lm.nw_t_stat.toFixed(2),
          raw: lm.nw_t_stat,
        },
      ]
    : [];

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card size="small" className="qc-card">
        <Descriptions
          column={2}
          size="small"
          items={[
            {
              key: 'category',
              label: t('factor_detail_meta_category') || '分类',
              children:
                // 表达式与代码因子的分类均可由用户指定；内置/合成由系统维护，只读展示
                onCategoryChange && ['expression', 'code'].includes(factorSource(factor)) ? (
                  <Select
                    size="small"
                    value={factor.category}
                    loading={categorySaving}
                    // Descriptions 为 table 布局：固定紧凑宽度，避免被撑宽后压到相邻「来源」单元格
                    style={{ width: 112 }}
                    onChange={(v) => void onCategoryChange(v)}
                    options={EDITABLE_CATEGORIES.map((c) => ({
                      value: c,
                      label: categoryLabel(c, t),
                    }))}
                  />
                ) : (
                  <span className="qc-chip info">{categoryLabel(factor.category, t)}</span>
                ),
            },
            {
              key: 'source',
              label: t('factor_detail_meta_source') || '来源',
              children: (
                <span className="qc-row-chips">
                  <span className="qc-chip quiet">{sourceLabel(factorSource(factor))}</span>
                  {isAiProduced(factor) && <span className="qc-chip pri">AI</span>}
                </span>
              ),
            },
            {
              key: 'status',
              label: t('factor_detail_lifecycle') || '生命周期',
              children: (
                <span className={`qc-chip ${
                  factor.lifecycle_status === 'LIVE'
                    ? 'ok'
                    : factor.lifecycle_status === 'RETIRED'
                      ? 'down'
                      : 'warn'
                }`}>
                  {statusLabel(factor.lifecycle_status)}
                </span>
              ),
            },
            {
              key: 'count',
              label: t('factor_detail_meta_snapshots') || '快照数',
              children: factor.snapshot_count,
            },
            {
              key: 'last',
              label: t('factor_detail_meta_last_snapshot') || '最近快照',
              children: factor.last_snapshot_at?.replace('T', ' ').slice(0, 19) ?? '—',
            },
            { key: 'bars', label: t('factor_snap_col_samples') || '样本数', children: lm?.bar_count ?? '—' },
            {
              key: 'description',
              label: t('factor_detail_meta_description') || '描述',
              span: 2,
              children: factor.description ? (
                <span style={{ fontSize: 12 }}>{factor.description}</span>
              ) : (
                <span className="qc-cell-none">—</span>
              ),
            },
            {
              key: 'expression',
              label: t('factor_detail_meta_expression') || '表达式',
              span: 2,
              children:
                source === 'code' || source === 'composite' ? (
                  <Flex gap="small" align="center" wrap="wrap">
                    <span className={`qc-chip ${source === 'code' ? 'info' : 'pri'}`}>
                      {source === 'code'
                        ? t('factor_code_summary_code') || 'Python 代码因子'
                        : t('factor_code_summary_composite') || 'IC 加权合成因子'}
                    </span>
                    <Button type="link" size="small" style={{ paddingInline: 0 }} onClick={onGoCode}>
                      {t('factor_code_view') || '查看代码'} →
                    </Button>
                  </Flex>
                ) : (
                  <code className="qc-mono" style={{ fontSize: 12 }}>{factor.expression || '—'}</code>
                ),
            },
          ]}
        />
      </Card>

      {lm ? (
        <Card size="small" className="qc-card" title={t('factor_detail_metrics_title') || '最近分析核心指标'}>
          <Row gutter={[16, 16]}>
            {metrics.map((m) => (
              <Col xs={12} sm={8} lg={6} xl={4} key={m.key}>
                <Statistic
                  title={m.label}
                  value={m.text}
                  styles={{
                    content: {
                      color: toneColor(m.raw == null ? 'flat' : toneOf(m.key, m.raw), qc),
                      fontSize: 20,
                    },
                  }}
                />
              </Col>
            ))}
          </Row>
        </Card>
      ) : (
        <Card className="qc-card">
          <QcEmpty
            title={t('factor_detail_overview_empty_title')}
            description={t('factor_detail_overview_empty')}
            action={
              <button type="button" className="qc-mini-btn pri" onClick={onGoAnalyze}>
                {t('factor_detail_overview_go_analyze') || '去分析'}
              </button>
            }
          />
        </Card>
      )}
    </Space>
  );
};

export default FactorOverviewPanel;
