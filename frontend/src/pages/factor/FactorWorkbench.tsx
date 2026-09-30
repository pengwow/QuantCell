import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
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
  Tooltip,
} from 'antd';
import { LineChartOutlined, StarOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
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

const FactorWorkbench: React.FC = () => {
  const qc = useQuantColors();
  const [form] = Form.useForm<FormValues>();
  const [factors, setFactors] = useState<FactorDetail[]>([]);
  const [instruments, setInstruments] = useState<InstrumentInfo[]>([]);
  const [result, setResult] = useState<FactorAnalyzeResult | null>(null);
  const [lastParams, setLastParams] = useState<FactorAnalyzeParams | null>(null);
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const { run: runJob, status: jobStatus, loading: jobLoading } =
    useFactorJob<FactorAnalyzeResult>();
  const selected: string[] = Form.useWatch('instruments', form) ?? [];

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
          setResult(r);
          // 复用同一次请求对象，保证收藏快照口径与本次分析完全一致
          setLastParams(params);
        },
        (msg) => {
          message.error(msg);
          setResult(null);
        },
      );
    } catch (err) {
      // 提交阶段同步 rejection（如 422/网络失败）
      setResult(null);
      message.error(errMsg(err));
    }
  }, [form, runJob]);

  const priceFactorOption = useMemo<EChartsOption>(() => {
    if (!result) return {};
    const fv = result.series.dates.map((d) => result.series.factor[d] ?? null);
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['价格', '因子值'] },
      grid: { left: '3%', right: '4%', containLabel: true },
      xAxis: { type: 'category', data: result.series.dates, axisLabel: { color: qc.chartMark } },
      yAxis: [
        { type: 'value', name: '价格', axisLabel: { color: qc.chartMark } },
        { type: 'value', name: '因子', axisLabel: { color: qc.chartMark } },
      ],
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 4 }],
      series: [
        {
          name: '价格',
          type: 'line',
          data: result.series.close,
          showSymbol: false,
          lineStyle: { color: qc.chartLine },
        },
        {
          name: '因子值',
          type: 'line',
          data: fv,
          showSymbol: false,
          yAxisIndex: 1,
          lineStyle: { color: qc.info },
        },
      ],
    };
  }, [result, qc]);

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
          name: 'IC',
          data: s.map((p) => ({
            value: p.ic,
            itemStyle: { color: p.ic >= 0 ? qc.positive : qc.negative },
          })),
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
        name: '分组',
        data: result.groups.map((g) => `G${g.group}`),
      },
      yAxis: { type: 'value', name: '平均前瞻收益' },
      series: [
        {
          type: 'bar',
          data: result.groups.map((g) => g.mean_forward_return),
          itemStyle: { color: qc.chartLine },
        },
      ],
    };
  }, [result, qc]);

  const decayOption = useMemo<EChartsOption>(() => {
    const decay = result?.inspection?.decay ?? [];
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['Spearman', 'Pearson'] },
      grid: { left: '3%', right: '4%', containLabel: true },
      xAxis: { type: 'category', name: 'lag(K线根数)', data: decay.map((d) => d.lag) },
      yAxis: { type: 'value', name: 'IC' },
      dataZoom: [],
      series: [
        {
          name: 'Spearman',
          type: 'line',
          smooth: false,
          data: decay.map((d) => d.spearman),
          itemStyle: { color: qc.chartLine },
        },
        {
          name: 'Pearson',
          type: 'line',
          smooth: false,
          data: decay.map((d) => d.pearson),
          itemStyle: { color: qc.info },
        },
      ],
    };
  }, [result, qc]);

  // 分位组用 qc 语义色循环取色（Q1 冷/弱 → Qn 暖/强），最多 5 色循环。
  // 毛净值实线、费后净值同色虚线（仅 fee_rate>0）；多空毛=加粗虚线、多空费后=加粗实线醒目区分。
  const quantileNavOption = useMemo<EChartsOption>(() => {
    const qn = result?.inspection?.quantile_nav;
    if (!qn) return {};
    const palette = [qc.negative, qc.warning, qc.neutral, qc.info, qc.positive];
    const withFee = qn.fee_rate > 0;
    const groupNames: string[] = [];
    qn.groups.forEach((g) => {
      groupNames.push(`Q${g.group}·换手${g.turnover.toFixed(2)}`);
      if (withFee) groupNames.push(`Q${g.group}费后`);
    });
    const hasLS = qn.long_short_nav != null;
    const lsGrossName = `多空毛·换手${
      qn.long_short_turnover == null ? '—' : qn.long_short_turnover.toFixed(2)
    }`;
    const hasLSNet = withFee && qn.long_short_nav_net != null;
    const lsNetName = '多空费后';
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
              name: `Q${g.group}·换手${g.turnover.toFixed(2)}`,
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
                    name: `Q${g.group}费后`,
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

  const stats: { key: string; title: ReactNode; value: number | string; precision?: number }[] =
    result
      ? [
          { key: 'ic_mean', title: 'IC 均值', value: result.ic.mean ?? 0, precision: 4 },
          { key: 'ic_ir', title: 'ICIR', value: result.ic.ir ?? 0, precision: 4 },
          { key: 'ic_positive_rate', title: 'IC 胜率', value: pct(result.ic.positive_rate) },
          {
            key: 'long_short_return',
            title: '多空收益',
            value: result.long_short_return ?? 0,
            precision: 4,
          },
          {
            key: 'monotonicity',
            title: '单调性 Spearman',
            value: result.monotonicity.spearman,
            precision: 4,
          },
          {
            key: 'stability',
            title: '稳定性(自相关)',
            value: result.stability.mean_autocorr ?? 0,
            precision: 4,
          },
          {
            key: 'coverage',
            title: '覆盖率',
            value:
              result.inspection?.coverage != null
                ? `${(result.inspection.coverage * 100).toFixed(1)}%`
                : '—',
          },
          {
            key: 'turnover',
            title: '换手率',
            value: result.inspection?.turnover != null ? result.inspection.turnover.toFixed(4) : '—',
          },
          {
            key: 'annualized_ir',
            title: (
              <Tooltip title="按 K 线周期年化（加密 7×24）；高频 IC 自相关会使年化 IR 偏大，t-stat 不受年化假设影响">
                <span>年化 IR</span>
              </Tooltip>
            ),
            value:
              result.inspection?.ic_stats.annualized_ir != null
                ? result.inspection.ic_stats.annualized_ir.toFixed(2)
                : '—',
          },
          {
            key: 't_stat',
            title: 't-stat',
            value:
              result.inspection?.ic_stats.t_stat != null
                ? result.inspection.ic_stats.t_stat.toFixed(2)
                : '—',
          },
          {
            key: 'nw_t_stat',
            title: (
              <Tooltip
                title={`Newey-West HAC 调整 t 统计量（Bartlett kernel，自动滞后 ${
                  result.inspection?.ic_stats.nw_lag ?? 0
                } 阶），扣除 IC 自相关导致的显著性虚高`}
              >
                <span>NW t-stat</span>
              </Tooltip>
            ),
            value:
              result.inspection?.ic_stats.nw_t_stat != null
                ? result.inspection.ic_stats.nw_t_stat.toFixed(2)
                : '—',
          },
        ]
      : [];

  return (
    <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
      <Card title="分析参数">
        <Form<FormValues>
          form={form}
          layout="inline"
          initialValues={{
            method: 'spearman',
            n_groups: 5,
            window: 20,
            forward: 1,
            interval: '1h',
            costBps: 0,
          }}
        >
          <Form.Item name="factor_name" label="因子" rules={[{ required: true, message: '选择因子' }]}>
            <Select
              showSearch
              optionFilterProp="label"
              style={{ width: 200 }}
              placeholder="选择因子"
              options={factors
                .filter((f) => f.supported)
                .map((f) => ({ value: f.name, label: `${f.label} (${f.name})` }))}
            />
          </Form.Item>
          <Form.Item name="instruments" label="品种" rules={[{ required: true, message: '选择品种' }]}>
            <Select
              mode="multiple"
              style={{ minWidth: 220 }}
              placeholder="选择品种"
              options={instruments.map((i) => ({ value: i.symbol, label: i.symbol }))}
            />
          </Form.Item>
          <Form.Item name="interval" label="周期">
            <Select style={{ width: 90 }} options={intervalOptions} />
          </Form.Item>
          <Form.Item name="range" label="时间范围">
            <RangePicker />
          </Form.Item>
          <Form.Item name="method" label="IC方法">
            <Select
              style={{ width: 110 }}
              options={[
                { value: 'spearman', label: 'Spearman' },
                { value: 'pearson', label: 'Pearson' },
              ]}
            />
          </Form.Item>
          <Form.Item name="n_groups" label="分组数">
            <InputNumber min={2} max={10} />
          </Form.Item>
          <Form.Item name="window" label="滚动窗">
            <InputNumber min={5} max={252} />
          </Form.Item>
          <Form.Item name="forward" label="前瞻(根)">
            <InputNumber min={1} max={120} />
          </Form.Item>
          <Form.Item name="horizonsText" label="衰减滞后">
            <Input placeholder="1,2,3,5,10（留空用默认）" allowClear style={{ width: 210 }} />
          </Form.Item>
          <Form.Item
            name="costBps"
            label="单边成本(bp)"
            extra="单边费率基点，10bp=0.1%；用于分位组合费后净值"
          >
            <InputNumber min={0} max={1000} step={1} precision={0} style={{ width: 110 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" icon={<LineChartOutlined />} loading={jobLoading} onClick={run}>
              开始分析
            </Button>
          </Form.Item>
        </Form>
        <p style={{ color: '#999', fontSize: 12, marginTop: 8, marginBottom: 0 }}>
          滚动窗 / 前瞻 / 衰减滞后单位均为 K 线根数；财务因子无数据来源，不在可选列表。
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
            <span>{jobStatus.message || '排队中…'}</span>
          </Flex>
        </Card>
      )}
      {!jobLoading && !result && (
        <Card>
          <Empty description="选择参数后点击「开始分析」" />
        </Card>
      )}

      {!jobLoading && result && (
        <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
          <Flex align="center" justify="space-between">
            <span style={{ fontSize: 16, fontWeight: 600 }}>分析结果</span>
            <Button
              icon={<StarOutlined />}
              loading={savingSnapshot}
              disabled={!lastParams}
              onClick={async () => {
                if (!lastParams) return;
                setSavingSnapshot(true);
                try {
                  const r = await factorApi.saveSnapshot(lastParams);
                  message.success(`已保存到档案（快照 #${r.id}）`);
                } catch (e) {
                  message.error((e as Error)?.message || '保存失败');
                } finally {
                  setSavingSnapshot(false);
                }
              }}
            >
              保存到档案
            </Button>
          </Flex>
          <Row gutter={[16, 16]}>
            {stats.map((s) => (
              <Col xs={12} md={8} key={s.key}>
                <Card>
                  <Statistic title={s.title} value={s.value} precision={s.precision} />
                </Card>
              </Col>
            ))}
          </Row>
          <Card title={`因子值 vs 价格（样本 ${result.bar_count} 根）`}>
            <EChart option={priceFactorOption} style={{ height: 360 }} opts={{ renderer: 'svg' }} />
          </Card>
          <Card title="IC 时序">
            <EChart option={icOption} style={{ height: 320 }} opts={{ renderer: 'svg' }} />
          </Card>
          <Card title="分组平均前瞻收益">
            <EChart option={groupOption} style={{ height: 300 }} opts={{ renderer: 'svg' }} />
          </Card>
          <Card
            title={`IC 衰减（lag ${
              (result.inspection?.decay ?? []).map((d) => d.lag).join('、') || '1–10'
            }）`}
          >
            <EChart option={decayOption} style={{ height: 300 }} opts={{ renderer: 'svg' }} />
          </Card>
          {result.inspection?.quantile_nav && (
            <Card title="分位组合净值">
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
