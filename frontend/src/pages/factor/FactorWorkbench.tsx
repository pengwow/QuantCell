import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  InputNumber,
  message,
  Row,
  Select,
  Space,
  Statistic,
} from 'antd';
import { LineChartOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import type { EChartsOption } from 'echarts';
import EChart from '@/components/EChart';
import {
  factorApi,
  type FactorAnalyzeResult,
  type FactorDetail,
  type InstrumentInfo,
} from '@/api/factor';
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
}

const errMsg = (e: unknown) => (e as Error)?.message || '分析失败';

const FactorWorkbench: React.FC = () => {
  const qc = useQuantColors();
  const [form] = Form.useForm<FormValues>();
  const [factors, setFactors] = useState<FactorDetail[]>([]);
  const [instruments, setInstruments] = useState<InstrumentInfo[]>([]);
  const [result, setResult] = useState<FactorAnalyzeResult | null>(null);
  const [loading, setLoading] = useState(false);
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
    const [s, e] = v.range ?? [];
    setLoading(true);
    try {
      setResult(
        await factorApi.analyze({
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
        }),
      );
    } catch (err) {
      setResult(null);
      message.error(errMsg(err));
    } finally {
      setLoading(false);
    }
  }, [form]);

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

  // 比例转百分比字符串
  const pct = (x: number | null) => `${((x ?? 0) * 100).toFixed(1)}%`;

  const stats: { title: string; value: number | string; precision?: number }[] = result
    ? [
        { title: 'IC 均值', value: result.ic.mean ?? 0, precision: 4 },
        { title: 'ICIR', value: result.ic.ir ?? 0, precision: 4 },
        { title: 'IC 胜率', value: pct(result.ic.positive_rate) },
        { title: '多空收益', value: result.long_short_return ?? 0, precision: 4 },
        { title: '单调性 Spearman', value: result.monotonicity.spearman, precision: 4 },
        { title: '稳定性(自相关)', value: result.stability.mean_autocorr ?? 0, precision: 4 },
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
          <Form.Item>
            <Button type="primary" icon={<LineChartOutlined />} loading={loading} onClick={run}>
              开始分析
            </Button>
          </Form.Item>
        </Form>
        <p style={{ color: '#999', fontSize: 12, marginTop: 8, marginBottom: 0 }}>
          滚动窗 / 前瞻单位均为 K 线根数；财务因子无数据来源，不在可选列表。
        </p>
      </Card>

      {loading && <Card loading />}
      {!loading && !result && (
        <Card>
          <Empty description="选择参数后点击「开始分析」" />
        </Card>
      )}

      {!loading && result && (
        <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
          <Row gutter={[16, 16]}>
            {stats.map((s) => (
              <Col xs={12} md={8} key={s.title}>
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
        </Space>
      )}
    </Space>
  );
};

export default FactorWorkbench;
