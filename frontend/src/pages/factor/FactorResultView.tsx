/**
 * 因子分析结果纯展示：核心指标卡 + 价格/IC/分组/衰减/分位净值图表。
 * 被「分析」面板与「快照详情」Drawer 共用，不持有请求或表单状态。
 */
import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Col, Row, Space, Statistic, Tabs, Tooltip } from 'antd';
import type { EChartsOption } from 'echarts';
import EChart from '@/components/EChart';
import type { FactorAnalyzeResult } from '@/api/factor';
import { useQuantColors } from '@/utils/colors';
import { toneColor, toneOf, type MetricTone } from './factorMeta';

const FactorResultView: React.FC<{ result: FactorAnalyzeResult }> = ({ result }) => {
  const qc = useQuantColors();
  const { t } = useTranslation();
  // IC 时序卡片内部 Tab（逐期/累计）
  const [icTab, setIcTab] = useState<'ic' | 'cum'>('ic');

  const priceFactorOption = useMemo<EChartsOption>(() => {
    const fv = result.series.dates.map((d) => result.series.factor[d] ?? null);
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: [t('factor_legend_price') || 'Price', t('factor_legend_factor_value') || 'Factor'] },
      grid: { left: '3%', right: '4%', containLabel: true },
      xAxis: { type: 'category', data: result.series.dates, axisLabel: { color: qc.chartMark } },
      yAxis: [
        { type: 'value', name: t('factor_echarts_price_y') || 'Price', axisLabel: { color: qc.chartMark } },
        { type: 'value', name: t('factor_legend_factor_value') || 'Factor', axisLabel: { color: qc.chartMark } },
      ],
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 4 }],
      series: [
        {
          name: t('factor_legend_price') || 'Price',
          type: 'line',
          data: result.series.close,
          showSymbol: false,
          itemStyle: { color: qc.chartLine },
          lineStyle: { color: qc.chartLine },
        },
        {
          name: t('factor_legend_factor_value') || 'Factor',
          type: 'line',
          data: fv,
          showSymbol: false,
          yAxisIndex: 1,
          // chartLine 与 info 同源（都是蓝），因子线用 warning 金色与价格线区分
          itemStyle: { color: qc.warning },
          lineStyle: { color: qc.warning },
        },
      ],
    };
  }, [result, qc, t]);

  const icOption = useMemo<EChartsOption>(() => {
    const s = result.ic.series.filter((p) => p.ic !== null) as { t: string; ic: number }[];
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', containLabel: true },
      xAxis: { type: 'category', data: s.map((p) => p.t), axisLabel: { color: qc.chartMark } },
      yAxis: { type: 'value', min: -1, max: 1, axisLabel: { color: qc.chartMark } },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 4 }],
      series: [
        {
          type: 'bar',
          name: t('factor_echarts_ic_name') || 'IC',
          data: s.map((p) => ({
            value: p.ic,
            itemStyle: { color: p.ic >= 0 ? qc.positive : qc.negative },
          })),
        },
      ],
    };
  }, [result, qc, t]);

  // 累计 IC：逐期 IC 的累积和，用于观察因子预测力是否稳定持续（而非靠少数时段）
  const cumIcOption = useMemo<EChartsOption>(() => {
    const s = result.ic.series.filter((p) => p.ic !== null) as { t: string; ic: number }[];
    let acc = 0;
    const cum = s.map((p) => {
      acc += p.ic;
      return Number(acc.toFixed(6));
    });
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v) => Number(v).toFixed(4) },
      grid: { left: '3%', right: '4%', containLabel: true },
      xAxis: { type: 'category', data: s.map((p) => p.t), axisLabel: { color: qc.chartMark } },
      yAxis: { type: 'value', axisLabel: { color: qc.chartMark } },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 4 }],
      series: [
        {
          type: 'line',
          name: t('factor_echarts_cum_ic') || 'Cumulative IC',
          data: cum,
          showSymbol: false,
          lineStyle: { color: qc.chartLine, width: 2 },
          areaStyle: { opacity: 0.06 },
          markLine: {
            symbol: 'none',
            silent: true,
            lineStyle: { color: qc.chartMark, type: 'dashed', opacity: 0.5 },
            data: [{ yAxis: 0 }],
          },
        },
      ],
    };
  }, [result, qc, t]);

  const groupOption = useMemo<EChartsOption>(() => {
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', containLabel: true },
      xAxis: {
        type: 'category',
        name: t('factor_echarts_group_x') || 'Group',
        data: result.groups.map((g) => `G${g.group}`),
      },
      yAxis: { type: 'value', name: t('factor_echarts_group_y') || 'Avg Forward Return' },
      series: [
        {
          type: 'bar',
          data: result.groups.map((g) => ({
            value: g.mean_forward_return,
            itemStyle: {
              color: g.mean_forward_return >= 0 ? qc.positive : qc.negative,
            },
          })),
        },
      ],
    };
  }, [result, qc, t]);

  const decayOption = useMemo<EChartsOption>(() => {
    const decay = result.inspection?.decay ?? [];
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: [t('factor_wb_method_spearman') || 'Spearman', t('factor_wb_method_pearson') || 'Pearson'] },
      grid: { left: '3%', right: '4%', containLabel: true },
      xAxis: { type: 'category', name: 'lag (bars)', data: decay.map((d) => d.lag) },
      yAxis: { type: 'value', name: t('factor_echarts_decay_y') || 'IC' },
      dataZoom: [],
      series: [
        {
          name: t('factor_wb_method_spearman') || 'Spearman',
          type: 'line',
          smooth: false,
          data: decay.map((d) => d.spearman),
          itemStyle: { color: qc.chartLine },
        },
        {
          name: t('factor_wb_method_pearson') || 'Pearson',
          type: 'line',
          smooth: false,
          data: decay.map((d) => d.pearson),
          itemStyle: { color: qc.warning },
        },
      ],
    };
  }, [result, qc, t]);

  // 分位组用 qc 语义色循环取色（Q1 冷/弱 → Qn 暖/强），最多 5 色循环。
  // 毛净值实线、费后净值同色虚线（仅 fee_rate>0）；多空毛=加粗虚线、多空费后=加粗实线。
  const quantileNavOption = useMemo<EChartsOption>(() => {
    const qn = result.inspection?.quantile_nav;
    if (!qn) return {};
    const palette = [qc.negative, qc.warning, qc.neutral, qc.info, qc.positive];
    const withFee = qn.fee_rate > 0;
    const groupNames: string[] = [];
    qn.groups.forEach((g) => {
      groupNames.push(t('factor_wb_group_nav_gross', { group: g.group, turnover: g.turnover.toFixed(2) }) || `Q${g.group}·换手${g.turnover.toFixed(2)}`);
      if (withFee) groupNames.push(t('factor_wb_group_nav_fee', { group: g.group }) || `Q${g.group}费后`);
    });
    const hasLS = qn.long_short_nav != null;
    const lsGrossName =
      t('factor_wb_ls_nav_gross', { turnover: qn.long_short_turnover == null ? '—' : qn.long_short_turnover.toFixed(2) }) ||
      `多空毛·换手${qn.long_short_turnover == null ? '—' : qn.long_short_turnover.toFixed(2)}`;
    const hasLSNet = withFee && qn.long_short_nav_net != null;
    const lsNetName = t('factor_wb_ls_nav_fee') || '多空费后';
    return {
      tooltip: { trigger: 'axis' },
      legend: {
        data: [
          ...groupNames,
          ...(hasLS ? [lsGrossName] : []),
          ...(hasLSNet ? [lsNetName] : []),
        ],
      },
      grid: { left: '3%', right: '4%', containLabel: true },
      xAxis: { type: 'category', data: qn.dates, axisLabel: { color: qc.chartMark } },
      yAxis: { type: 'value', axisLabel: { color: qc.chartMark } },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 4 }],
      series: [
        ...qn.groups.flatMap((g, i) => {
          const color = palette[i % palette.length];
          return [
            {
              name: t('factor_wb_group_nav_gross', { group: g.group, turnover: g.turnover.toFixed(2) }) || `Q${g.group}·换手${g.turnover.toFixed(2)}`,
              type: 'line' as const,
              showSymbol: false,
              connectNulls: true,
              data: g.nav,
              itemStyle: { color },
              lineStyle: { color, width: 1.2 },
            },
            ...(withFee
              ? [
                  {
                    name: t('factor_wb_group_nav_fee', { group: g.group }) || `Q${g.group}费后`,
                    type: 'line' as const,
                    showSymbol: false,
                    connectNulls: true,
                    data: g.nav_net,
                    itemStyle: { color },
                    lineStyle: { color, width: 1, type: 'dashed' as const },
                  },
                ]
              : []),
          ];
        }),
        ...(hasLS
          ? [
              {
                name: lsGrossName,
                type: 'line' as const,
                showSymbol: false,
                connectNulls: true,
                data: qn.long_short_nav as (number | null)[],
                itemStyle: { color: qc.positive },
                lineStyle: { color: qc.positive, width: 2.5, type: 'dashed' as const },
              },
            ]
          : []),
        ...(hasLSNet
          ? [
              {
                name: lsNetName,
                type: 'line' as const,
                showSymbol: false,
                connectNulls: true,
                data: qn.long_short_nav_net as (number | null)[],
                itemStyle: { color: qc.positive },
                lineStyle: { color: qc.positive, width: 2.5 },
              },
            ]
          : []),
      ],
    };
  }, [result, qc, t]);

  // 比例转百分比字符串
  const pct = (x: number | null) => `${((x ?? 0) * 100).toFixed(1)}%`;

  // IC 胜率单独评级：与 IC 均值方向一致才算好（ic<0 时低胜率才与因子方向一致）
  const positiveRateTone = useCallback((): MetricTone => {
    if (!result.ic.mean || result.ic.positive_rate == null) return 'flat';
    const aligned = Math.sign(result.ic.mean) * (result.ic.positive_rate - 0.5);
    if (aligned >= 0.05) return 'good';
    if (aligned <= -0.05) return 'bad';
    return 'mid';
  }, [result]);

  // 覆盖率/换手率卡片值是字符串（%/小数），评级时需要 0-1 数值
  const coverageNum = result.inspection?.coverage ?? null;
  const turnoverNum = result.inspection?.turnover ?? null;

  const stats: { key: string; title: ReactNode; value: number | string; precision?: number }[] = [
    { key: 'ic_mean', title: t('factor_stat_ic_mean') || 'IC 均值', value: result.ic.mean ?? 0, precision: 4 },
    { key: 'ic_ir_loose', title: t('factor_stat_icir') || 'ICIR', value: result.ic.ir ?? 0, precision: 4 },
    { key: 'ic_positive_rate', title: t('factor_stat_ic_pos_rate') || 'IC 胜率', value: pct(result.ic.positive_rate) },
    {
      key: 'long_short_return',
      title: t('factor_stat_ls_return') || '多空收益',
      value: result.long_short_return ?? 0,
      precision: 4,
    },
    {
      key: 'monotonicity',
      title: t('factor_stat_monotonicity') || '单调性 Spearman',
      value: result.monotonicity.spearman,
      precision: 4,
    },
    {
      key: 'stability',
      title: t('factor_stat_stability') || '稳定性(自相关)',
      value: result.stability.mean_autocorr ?? 0,
      precision: 4,
    },
    {
      key: 'coverage',
      title: t('factor_stat_coverage') || '覆盖率',
      value: result.inspection?.coverage != null ? `${(result.inspection.coverage * 100).toFixed(1)}%` : '—',
    },
    {
      key: 'turnover',
      title: t('factor_stat_turnover') || '换手率',
      value: result.inspection?.turnover != null ? result.inspection.turnover.toFixed(4) : '—',
    },
    {
      key: 'annualized_ir',
      title: (
        <Tooltip
          title={
            t('factor_stat_ann_ir_tip') ||
            '按 K 线周期年化（加密 7×24）；高频 IC 自相关会使年化 IR 偏大，t-stat 不受年化假设影响'
          }
        >
          <span>{t('factor_stat_ann_ir') || '年化 IR'}</span>
        </Tooltip>
      ),
      value:
        result.inspection?.ic_stats.annualized_ir != null
          ? result.inspection.ic_stats.annualized_ir.toFixed(2)
          : '—',
    },
    {
      key: 't_stat',
      title: t('factor_stat_tstat') || 't-stat',
      value: result.inspection?.ic_stats.t_stat != null ? result.inspection.ic_stats.t_stat.toFixed(2) : '—',
    },
    {
      key: 'nw_t_stat',
      title: (
        <Tooltip
          title={
            t('factor_stat_nw_tstat_tip', { lag: result.inspection?.ic_stats.nw_lag ?? 0 }) ||
            'Newey-West HAC 调整 t 统计量（Bartlett kernel，自动滞后 0 阶），扣除 IC 自相关导致的显著性虚高'
          }
        >
          <span>{t('factor_stat_nw_tstat') || 'NW t-stat'}</span>
        </Tooltip>
      ),
      value:
        result.inspection?.ic_stats.nw_t_stat != null ? result.inspection.ic_stats.nw_t_stat.toFixed(2) : '—',
    },
  ];

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Row gutter={[16, 16]}>
        {stats.map((s) => {
          // 覆盖率/换手率/显著性卡片值是格式化字符串，评级必须取原始数值；原始值 null（显示 —）时保持中性色
          const icStats = result.inspection?.ic_stats;
          const rawNum =
            s.key === 'coverage'
              ? coverageNum
              : s.key === 'turnover'
                ? turnoverNum
                : s.key === 'annualized_ir'
                  ? (icStats?.annualized_ir ?? null)
                  : s.key === 't_stat'
                    ? (icStats?.t_stat ?? null)
                    : s.key === 'nw_t_stat'
                      ? (icStats?.nw_t_stat ?? null)
                      : typeof s.value === 'number'
                        ? s.value
                        : null;
          const tone =
            s.key === 'ic_positive_rate' ? positiveRateTone() : rawNum == null ? 'flat' : toneOf(s.key, rawNum);
          return (
            <Col xs={12} sm={8} lg={6} xl={4} key={s.key}>
              <Card size="small">
                <Statistic
                  title={s.title}
                  value={s.value}
                  precision={s.precision}
                  styles={{ content: { color: toneColor(tone, qc), fontSize: 20 } }}
                />
              </Card>
            </Col>
          );
        })}
      </Row>
      <Card
        title={
          t('factor_card_price_factor', { count: result.bar_count }) ||
          `因子值 vs 价格（样本 ${result.bar_count} 根）`
        }
      >
        <EChart option={priceFactorOption} style={{ height: 360 }} opts={{ renderer: 'svg' }} />
      </Card>
      <Card
        title={t('factor_card_ic_ts') || 'IC 时序'}
        extra={
          <Tooltip
            title={
              icTab === 'cum'
                ? t('factor_card_ic_ts_tip_cum') ||
                  '累计 IC 持续沿一个方向走，说明预测力稳定；反复穿越零线说明因子仅在少数时段有效'
                : t('factor_card_ic_ts_tip_period') ||
                  '柱状=逐期 IC；切到「累计 IC」可看预测力是否持续'
            }
          >
            <span style={{ color: qc.chartMark, fontSize: 12 }}>
              {icTab === 'cum'
                ? t('factor_card_ic_ts_label_cum') || '累计 IC 持续单向=预测力稳定'
                : t('factor_card_ic_ts_label_period') || '柱状=逐期 IC'}
            </span>
          </Tooltip>
        }
      >
        <Tabs
          size="small"
          activeKey={icTab}
          onChange={(k) => setIcTab(k as 'ic' | 'cum')}
          items={[
            {
              key: 'ic',
              label: t('factor_wb_tab_ic') || '逐期 IC',
              children: <EChart option={icOption} style={{ height: 320 }} opts={{ renderer: 'svg' }} />,
            },
            {
              key: 'cum',
              label: t('factor_wb_tab_cum') || '累计 IC',
              children: <EChart option={cumIcOption} style={{ height: 320 }} opts={{ renderer: 'svg' }} />,
            },
          ]}
        />
      </Card>
      <Card title={t('factor_card_group_return') || '分组平均前瞻收益'}>
        <EChart option={groupOption} style={{ height: 300 }} opts={{ renderer: 'svg' }} />
      </Card>
      <Card
        title={
          t('factor_card_ic_decay', {
            lags: (result.inspection?.decay ?? []).map((d) => d.lag).join(', ') || '1–10',
          }) ||
          `IC 衰减（lag ${(result.inspection?.decay ?? []).map((d) => d.lag).join('、') || '1–10'}）`
        }
      >
        <EChart option={decayOption} style={{ height: 300 }} opts={{ renderer: 'svg' }} />
      </Card>
      {result.inspection?.quantile_nav && (
        <Card title={t('factor_card_quantile_nav') || '分位组合净值'}>
          <EChart option={quantileNavOption} style={{ height: 340 }} opts={{ renderer: 'svg' }} />
        </Card>
      )}
    </Space>
  );
};

export default FactorResultView;
