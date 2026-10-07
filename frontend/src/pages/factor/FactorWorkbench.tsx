import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Flex,
  Form,
  Input,
  InputNumber,
  message,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Tabs,
  Tooltip,
} from 'antd';
import { LineChartOutlined, StarOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { useSearchParams } from 'react-router-dom';
import type { EChartsOption } from 'echarts';
import EChart from '@/components/EChart';
import {
  factorApi,
  type FactorAnalyzeParams,
  type FactorAnalyzeResult,
  type FactorDetail,
  type InstrumentInfo,
} from '@/api/factor';
import { useFactorJob } from '@/hooks/useFactorJob';
import { useQuantColors } from '@/utils/colors';
import type { AnalyzeHistoryItem } from './FactorAnalysis';

const { RangePicker } = DatePicker;

interface FormValues {
  factor_name: string;
  instruments: string[];
  interval: string;
  range?: [Dayjs, Dayjs] | null;
  method: 'spearman' | 'pearson';
  n_groups: number;
  window: number;
  forward: number;
  /** 仅表单文本态，不进入 factor 参数对象；提交时解析为 horizons */
  horizonsText?: string;
  costBps: number;
}

const errMsg = (e: unknown) => (e as Error)?.message || '分析失败';

/**
 * 解析 horizons 文本：trim 后按中英文逗号分隔，逐项过滤空白。
 * 空字符串 → null（不传，后端用默认 [1,2,3,5,10]）；
 * 每项必须是 1-120 的整数、最多 20 个，否则返回错误信息（与后端校验一致）。
 */
const parseHorizons = (text: string | undefined): number[] | null | string => {
  const t = (text ?? '').trim();
  if (!t) return null;
  const parts = t
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (!parts.length) return null;
  if (parts.length > 20) return '衰减滞后最多 20 个';
  const hs: number[] = [];
  for (const p of parts) {
    if (!/^\d+$/.test(p)) return `衰减滞后必须是整数：${p}`;
    const n = Number(p);
    if (n < 1 || n > 120) return `衰减滞后必须是 1-120 的整数：${p}`;
    hs.push(n);
  }
  return hs;
};

/** 指标语气：good=绿（好）、mid=蓝（中等/可用）、bad=橙（偏弱/注意）、flat=默认色 */
type MetricTone = 'good' | 'mid' | 'bad' | 'flat';

/**
 * 统计指标的语义评级（研究经验口径，仅着色提示，不改变数值）：
 * - IC 强度按绝对值分档（负 IC 可反向使用，符号本身不分好坏）；
 * - 胜率按「与 IC 方向的一致性」着色（ic<0 时低胜率反而是一致的）；
 * - 覆盖率/换手率/显著性按常用阈值，阈值写在各分支里便于调整。
 */
const rateAbs = (x: number, strong: number, usable: number): MetricTone => {
  const a = Math.abs(x);
  if (a >= strong) return 'good';
  if (a >= usable) return 'mid';
  return 'bad';
};

const toneOf = (key: string, value: number): MetricTone => {
  switch (key) {
    case 'ic_mean':
      return rateAbs(value, 0.05, 0.03);
    case 'ic_ir':
    case 'annualized_ir':
      return rateAbs(value, 2, 1);
    case 'ic_ir_loose':
      return rateAbs(value, 0.5, 0.3);
    case 't_stat':
    case 'nw_t_stat':
      return rateAbs(value, 2, 1);
    case 'monotonicity':
      return rateAbs(value, 0.8, 0.5);
    case 'stability':
      if (value >= 0.5) return 'good';
      if (value >= 0.2) return 'mid';
      return 'bad';
    case 'long_short_return':
      return value > 0 ? 'good' : value < 0 ? 'bad' : 'flat';
    case 'coverage':
      // 入参为 0-1
      if (value >= 0.8) return 'good';
      if (value >= 0.5) return 'mid';
      return 'bad';
    case 'turnover':
      if (value <= 0.1) return 'good';
      if (value <= 0.3) return 'mid';
      return 'bad';
    default:
      return 'flat';
  }
};

interface Props {
  history: AnalyzeHistoryItem[];
  activeHistoryId: string | null;
  onSelectHistory: (id: string) => void;
  onPushHistory: (item: AnalyzeHistoryItem) => void;
  onClearHistory: () => void;
}

const FactorWorkbench: React.FC<Props> = ({
  history,
  activeHistoryId,
  onSelectHistory,
  onPushHistory,
  onClearHistory,
}) => {
  const qc = useQuantColors();
  const { t } = useTranslation();
  const [form] = Form.useForm<FormValues>();
  const [factors, setFactors] = useState<FactorDetail[]>([]);
  const [instruments, setInstruments] = useState<InstrumentInfo[]>([]);
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const { run: runJob, status: jobStatus, loading: jobLoading } =
    useFactorJob<FactorAnalyzeResult>();
  const selected: string[] = Form.useWatch('instruments', form) ?? [];
  const [searchParams, setSearchParams] = useSearchParams();
  // 防止同一组联动参数被 effect 重复触发（StrictMode/切 Tab 回来）
  const autoKeyRef = useRef<string>('');
  // IC 时序卡片内部 Tab（逐期/累计），切换结果时复位
  const [icTab, setIcTab] = useState<'ic' | 'cum'>('ic');

  const activeItem = useMemo(
    () => history.find((h) => h.id === activeHistoryId) ?? null,
    [history, activeHistoryId],
  );
  const result: FactorAnalyzeResult | null = activeItem?.result ?? null;
  const lastParams: FactorAnalyzeParams | null = activeItem?.params ?? null;

  // 切换/新增分析结果时复位 IC 卡片内部 Tab
  useEffect(() => {
    setIcTab('ic');
  }, [activeHistoryId]);

  // 浏览历史结果时把该次参数回填表单，便于查看口径或微调后重跑
  useEffect(() => {
    if (!activeItem) return;
    const p = activeItem.params;
    form.setFieldsValue({
      factor_name: p.factor_name,
      instruments: p.instruments,
      interval: p.interval,
      method: p.method,
      n_groups: p.n_groups,
      window: p.window,
      forward: p.forward,
      horizonsText: p.horizons?.join(',') ?? undefined,
      costBps: p.cost_bps ?? 0,
      // antd setFieldsValue 的 DeepPartial 不接受 null，无时间范围时直接不传
      ...(p.start_time && p.end_time
        ? { range: [dayjs(p.start_time), dayjs(p.end_time)] as [Dayjs, Dayjs] }
        : {}),
    });
  }, [activeItem, form]);

  useEffect(() => {
    factorApi
      .listDetail()
      .then((r) => setFactors(r.factors))
      .catch(() => undefined);
    factorApi
      .instruments('spot')
      .then((r) => setInstruments(r.symbols))
      .catch(() => undefined);
  }, []);

  // 周期下拉取所选品种共有周期的交集；没有共同周期时退回 1h
  const intervalOptions = useMemo(() => {
    const picked = instruments.filter((i) => selected.includes(i.symbol));
    if (!picked.length) return ['1h'].map((v) => ({ value: v, label: v }));
    const sets = picked.map((i) => new Set(i.intervals));
    const common = [...sets[0]].filter((x) => sets.every((s) => s.has(x)));
    return (common.length ? common : ['1h']).map((v) => ({ value: v, label: v }));
  }, [instruments, selected]);

  const run = useCallback(async () => {
    const v = await form.validateFields();
    const horizons = parseHorizons(v.horizonsText);
    if (typeof horizons === 'string') {
      message.error(horizons);
      return;
    }
    const [s, e] = v.range ?? [];
    const params: FactorAnalyzeParams = {
      factor_name: v.factor_name,
      instruments: v.instruments,
      interval: v.interval,
      candle_type: 'spot',
      start_time: s ? dayjs(s).format('YYYY-MM-DD') : null,
      end_time: e ? dayjs(e).format('YYYY-MM-DD') : null,
      method: v.method,
      n_groups: v.n_groups,
      window: v.window,
      forward: v.forward,
      horizons,
      cost_bps: v.costBps ?? 0,
    };
    try {
      await runJob(
        'analyze',
        params,
        (r) => {
          // 复用同一次请求对象，保证保存快照口径与本次分析完全一致
          onPushHistory({
            id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            ts: Date.now(),
            params,
            result: r,
          });
        },
        (msg) => {
          message.error(msg);
        },
      );
    } catch (err) {
      // 提交阶段同步 rejection（如 422/网络失败）
      message.error(errMsg(err));
    }
  }, [form, runJob, onPushHistory]);

  // 挖掘页「保存并分析」联动：?factor=&syms=&interval=&run=1
  // 数据列表就绪后预填表单；run=1 时自动分析一次，随后消费掉一次性参数
  useEffect(() => {
    if (!factors.length || !instruments.length) return;
    const factor = searchParams.get('factor');
    if (!factor) return;
    const syms = (searchParams.get('syms') ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .filter((s) => instruments.some((i) => i.symbol === s));
    const interval = searchParams.get('interval') ?? '1h';
    form.setFieldsValue({
      factor_name: factor,
      instruments: syms,
      interval: intervalOptions.some((o) => o.value === interval) ? interval : '1h',
    });
    if (searchParams.get('run') === '1') {
      const key = `${factor}|${syms.join(',')}|${interval}`;
      if (autoKeyRef.current !== key) {
        autoKeyRef.current = key;
        void run();
      }
    }
    const next = new URLSearchParams(searchParams);
    ['factor', 'syms', 'interval', 'run'].forEach((k) => next.delete(k));
    next.set('tab', 'workbench');
    setSearchParams(next, { replace: true });
    // run/form 稳定；intervalOptions 变化不影响已消费参数的清理
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [factors, instruments]);

  const priceFactorOption = useMemo<EChartsOption>(() => {
    if (!result) return {};
    const fv = result.series.dates.map((d) => result.series.factor[d] ?? null);
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: [t('factor_legend_price') || 'Price', t('factor_legend_factor_value') || 'Factor'] },
      grid: { left: '3%', right: '4%', containLabel: true },
      xAxis: { type: 'category', data: result.series.dates, axisLabel: { color: qc.chartMark } },
      yAxis: [
        { type: 'value', name: t('factor_echarts_price_y') || 'Price', axisLabel: { color: qc.chartMark } },
        { type: 'value', name: t('factor_echarts_factor_y') || 'Factor', axisLabel: { color: qc.chartMark } },
      ],
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 4 }],
      series: [
        {
          name: t('factor_legend_price') || 'Price',
          type: 'line',
          data: result.series.close,
          showSymbol: false,
          // itemStyle 同步着色，否则 SVG 图例圆点回退 ECharts 默认调色板
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
    if (!result) return {};
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
    if (!result) return {};
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
  }, [result, qc]);

  const groupOption = useMemo<EChartsOption>(() => {
    if (!result) return {};
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
    const decay = result?.inspection?.decay ?? [];
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
  // 毛净值实线、费后净值同色虚线（仅 fee_rate>0）；多空毛=加粗虚线、多空费后=加粗实线醒目区分。
  const quantileNavOption = useMemo<EChartsOption>(() => {
    const qn = result?.inspection?.quantile_nav;
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
  }, [result, qc]);

  // 比例转百分比字符串
  const pct = (x: number | null) => `${((x ?? 0) * 100).toFixed(1)}%`;

  const toneColor = useCallback(
    (tone: MetricTone): string | undefined =>
      tone === 'good'
        ? qc.positive
        : tone === 'mid'
          ? qc.info
          : tone === 'bad'
            ? qc.warning
            : undefined,
    [qc],
  );

  const stats: { key: string; title: ReactNode; value: number | string; precision?: number }[] =
    result
      ? [
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
            value:
              result.inspection?.coverage != null
                ? `${(result.inspection.coverage * 100).toFixed(1)}%`
                : '—',
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
            value:
              result.inspection?.ic_stats.t_stat != null
                ? result.inspection.ic_stats.t_stat.toFixed(2)
                : '—',
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
              result.inspection?.ic_stats.nw_t_stat != null
                ? result.inspection.ic_stats.nw_t_stat.toFixed(2)
                : '—',
          },
        ]
      : [];

  // IC 胜率单独评级：与 IC 均值方向一致才算好（ic<0 时低胜率才与因子方向一致）
  const positiveRateTone = useCallback((): MetricTone => {
    if (!result?.ic.mean || result.ic.positive_rate == null) return 'flat';
    const aligned = Math.sign(result.ic.mean) * (result.ic.positive_rate - 0.5);
    if (aligned >= 0.05) return 'good';
    if (aligned <= -0.05) return 'bad';
    return 'mid';
  }, [result]);

  // 覆盖率/换手率卡片值是字符串（%/小数），评级时需要 0-1 数值
  const coverageNum = result?.inspection?.coverage ?? null;
  const turnoverNum = result?.inspection?.turnover ?? null;

  return (
    <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
      <Card title={t('factor_wb_card_params') || '分析参数'}>
        {/* inline 表单项换行后默认无垂直间距（紧贴），用 flex rowGap 补到 middle 档；
            水平间距沿用 antd inline item 默认的 16px，避免与 marginInlineEnd 叠加 */}
        <Form<FormValues>
          form={form}
          layout="inline"
          style={{ rowGap: 16 }}
          initialValues={{
            method: 'spearman',
            n_groups: 5,
            window: 20,
            forward: 1,
            interval: '1h',
            costBps: 0,
          }}
        >
          <Form.Item
            name="factor_name"
            label={t('factor_wb_form_factor') || '因子'}
            rules={[{ required: true, message: t('factor_wb_form_factor_req') || '请选择因子' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              style={{ width: 200 }}
              placeholder={t('factor_wb_form_factor_ph') || '选择因子'}
              options={factors
                .filter((f) => f.supported)
                .map((f) => ({ value: f.name, label: `${f.label} (${f.name})` }))}
            />
          </Form.Item>
          <Form.Item
            name="instruments"
            label={t('factor_wb_form_instruments') || '品种'}
            rules={[{ required: true, message: t('factor_wb_form_instruments_req') || '请选择品种' }]}
          >
            <Select
              mode="multiple"
              style={{ minWidth: 220 }}
              placeholder={t('factor_wb_form_instruments_ph') || '选择品种'}
              options={instruments.map((i) => ({ value: i.symbol, label: i.symbol }))}
            />
          </Form.Item>
          <Form.Item name="interval" label={t('factor_wb_form_interval') || '周期'}>
            <Select style={{ width: 90 }} options={intervalOptions} />
          </Form.Item>
          <Form.Item name="range" label={t('factor_wb_form_range') || '时间范围'}>
            <RangePicker />
          </Form.Item>
          <Form.Item name="method" label={t('factor_wb_form_method') || 'IC方法'}>
            <Select
              style={{ width: 130 }}
              options={[
                { value: 'spearman', label: t('factor_wb_method_spearman') || 'Spearman' },
                { value: 'pearson', label: t('factor_wb_method_pearson') || 'Pearson' },
              ]}
            />
          </Form.Item>
          <Form.Item name="n_groups" label={t('factor_wb_form_groups') || '分组数'}>
            <InputNumber min={2} max={10} />
          </Form.Item>
          <Form.Item name="window" label={t('factor_wb_form_window') || '滚动窗'}>
            <InputNumber min={5} max={252} />
          </Form.Item>
          <Form.Item name="forward" label={t('factor_wb_form_forward') || '前瞻(根)'}>
            <InputNumber min={1} max={120} />
          </Form.Item>
          <Form.Item name="horizonsText" label={t('factor_wb_form_decay') || '衰减滞后'}>
            <Input
              placeholder={t('factor_wb_form_decay_ph') || '1,2,3,5,10（留空用默认）'}
              allowClear
              style={{ width: 210 }}
            />
          </Form.Item>
          <Form.Item
            name="costBps"
            label={t('factor_wb_form_cost') || '单边成本(bp)'}
            extra={
              t('factor_wb_form_cost_hint') ||
              '单边费率基点，10bp=0.1%；用于分位组合费后净值'
            }
          >
            <InputNumber min={0} max={1000} step={1} precision={0} style={{ width: 110 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" icon={<LineChartOutlined />} loading={jobLoading} onClick={run}>
              {t('factor_wb_form_run') || '开始分析'}
            </Button>
          </Form.Item>
        </Form>
        <p style={{ color: '#999', fontSize: 12, marginTop: 8, marginBottom: 0 }}>
          {t('factor_wb_form_hint') ||
            '滚动窗 / 前瞻 / 衰减滞后单位均为 K 线根数；财务因子无数据来源，不在可选列表'}
        </p>
      </Card>

      {jobLoading && <Card loading />}
      {jobLoading && jobStatus && (
        <Card size="small">
          <Flex gap="middle" align="center">
            <Progress
              type="circle"
              size={48}
              percent={Math.round(jobStatus.progress)}
              status="active"
            />
            <span>{jobStatus.message || t('factor_wb_queueing') || 'Queueing…'}</span>
          </Flex>
        </Card>
      )}
      {!jobLoading && !result && (
        <Card>
          <Empty description={t('factor_wb_empty_hint') || '选择参数后点击「开始分析」'} />
        </Card>
      )}

      {!jobLoading && result && (
        <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
          <Flex align="center" justify="space-between" wrap="wrap" gap="small">
            <Flex gap="small" align="center">
              <span style={{ fontSize: 16, fontWeight: 600 }}>
                {t('factor_wb_result_title') || '分析结果'}
              </span>
              {history.length > 1 && (
                <Select
                  size="small"
                  style={{ minWidth: 300 }}
                  value={activeHistoryId ?? undefined}
                  onChange={onSelectHistory}
                  options={history.map((h) => ({
                    value: h.id,
                    label: `${h.result.factor_name} · ${h.params.instruments.length} 品种 · ${dayjs(
                      h.ts,
                    ).format('MM-DD HH:mm')}`,
                  }))}
                />
              )}
            </Flex>
            <Flex gap="small">
              {history.length > 0 && (
                <Tooltip
                  title={
                    t('factor_wb_btn_clear_tip') ||
                    '清空本次会话保留的分析结果（不影响已保存快照）'
                  }
                >
                  <Button onClick={onClearHistory}>{t('factor_wb_btn_clear') || '清空历史'}</Button>
                </Tooltip>
              )}
              <Button
                type="primary"
                ghost
                icon={<StarOutlined />}
                loading={savingSnapshot}
                disabled={!lastParams}
                onClick={async () => {
                  if (!lastParams) return;
                  setSavingSnapshot(true);
                  try {
                    const r = await factorApi.saveSnapshot(lastParams);
                    message.success(
                      t('factor_wb_toast_saved', { id: r.id }) || `快照已保存（#${r.id}）`,
                    );
                  } catch (e) {
                    message.error(
                      (e as Error)?.message ||
                        t('factor_wb_toast_save_failed') ||
                        '保存失败',
                    );
                  } finally {
                    setSavingSnapshot(false);
                  }
                }}
              >
                {t('factor_wb_btn_save') || '保存快照'}
              </Button>
            </Flex>
          </Flex>
          <Row gutter={[16, 16]}>
            {stats.map((s) => {
              // 覆盖率/换手率/显著性卡片值是格式化字符串，评级必须取原始数值；
              // 原始值为 null（显示 —）时保持中性色
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
                s.key === 'ic_positive_rate'
                  ? positiveRateTone()
                  : rawNum == null
                    ? 'flat'
                    : toneOf(s.key, rawNum);
              return (
                <Col xs={12} sm={8} lg={6} xl={4} key={s.key}>
                  <Card size="small">
                    <Statistic
                      title={s.title}
                      value={s.value}
                      precision={s.precision}
                      valueStyle={{ color: toneColor(tone), fontSize: 20 }}
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
                      '红绿柱为每期截面 IC；切到「累计 IC」可看预测力是否持续'
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
                  children: (
                    <EChart
                      option={icOption}
                      style={{ height: 320 }}
                      opts={{ renderer: 'svg' }}
                    />
                  ),
                },
                {
                  key: 'cum',
                  label: t('factor_wb_tab_cum') || '累计 IC',
                  children: (
                    <EChart
                      option={cumIcOption}
                      style={{ height: 320 }}
                      opts={{ renderer: 'svg' }}
                    />
                  ),
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
                lags:
                  (result.inspection?.decay ?? []).map((d) => d.lag).join(', ') || '1–10',
              }) ||
              `IC 衰减（lag ${
                (result.inspection?.decay ?? []).map((d) => d.lag).join('、') || '1–10'
              }）`
            }
          >
            <EChart option={decayOption} style={{ height: 300 }} opts={{ renderer: 'svg' }} />
          </Card>
          {result.inspection?.quantile_nav && (
            <Card title={t('factor_card_quantile_nav') || '分位组合净值'}>
              <EChart
                option={quantileNavOption}
                style={{ height: 340 }}
                opts={{ renderer: 'svg' }}
              />
            </Card>
          )}
        </Space>
      )}
    </Space>
  );
};

export default FactorWorkbench;
