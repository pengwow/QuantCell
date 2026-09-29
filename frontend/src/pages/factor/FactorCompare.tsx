import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Form,
  InputNumber,
  message,
  Select,
  Space,
  Table,
} from 'antd';
import { SwapOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import type { EChartsOption } from 'echarts';
import type { TableProps } from 'antd';
import EChart from '@/components/EChart';
import {
  factorApi,
  type FactorCompareParams,
  type FactorCompareResult,
  type FactorCompareRow,
  type FactorDetail,
  type InstrumentInfo,
} from '@/api/factor';
import { useQuantColors } from '@/utils/colors';

const { RangePicker } = DatePicker;

interface FormValues {
  factor_names: string[];
  instruments: string[];
  interval: string;
  range?: [Dayjs, Dayjs] | null;
  method: 'spearman' | 'pearson';
  n_groups: number;
  window: number;
  forward: number;
}

const errMsg = (e: unknown) => (e as Error)?.message || '对比失败';

const fmt = (v: number | null | undefined, digits: number) =>
  v == null ? '—' : v.toFixed(digits);

const FactorCompare: React.FC = () => {
  const qc = useQuantColors();
  const [form] = Form.useForm<FormValues>();
  const [factors, setFactors] = useState<FactorDetail[]>([]);
  const [instruments, setInstruments] = useState<InstrumentInfo[]>([]);
  const [result, setResult] = useState<FactorCompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const selected: string[] = Form.useWatch('instruments', form) ?? [];

  useEffect(() => {
    factorApi
      .listDetail()
      .then((r) => setFactors(r.factors.filter((f) => f.supported)))
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

  const run = async () => {
    const v = await form.validateFields();
    const [s, e] = v.range ?? [];
    const params: FactorCompareParams = {
      factor_names: v.factor_names,
      instruments: v.instruments,
      interval: v.interval,
      candle_type: 'spot',
      start_time: s ? dayjs(s).format('YYYY-MM-DD HH:mm:ss') : null,
      end_time: e ? dayjs(e).format('YYYY-MM-DD HH:mm:ss') : null,
      method: v.method,
      n_groups: v.n_groups,
      window: v.window,
      forward: v.forward,
    };
    setLoading(true);
    try {
      setResult(await factorApi.compare(params));
    } catch (err) {
      setResult(null);
      message.error(errMsg(err));
    } finally {
      setLoading(false);
    }
  };

  const columns: TableProps<FactorCompareRow>['columns'] = [
    {
      title: '因子',
      dataIndex: 'factor_name',
      key: 'factor_name',
      fixed: 'left',
      render: (_, row) => (
        <div>
          <div>{row.label}</div>
          <div style={{ color: qc.chartMark, fontSize: 12 }}>{row.factor_name}</div>
        </div>
      ),
    },
    {
      title: '覆盖率%',
      dataIndex: 'coverage',
      key: 'coverage',
      align: 'right',
      render: (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`),
    },
    {
      title: '换手率',
      dataIndex: 'turnover',
      key: 'turnover',
      align: 'right',
      render: (v: number | null) => fmt(v, 4),
    },
    {
      title: 'IC均值',
      dataIndex: 'ic_mean',
      key: 'ic_mean',
      align: 'right',
      render: (v: number | null) => fmt(v, 3),
    },
    {
      title: 'ICIR',
      dataIndex: 'ic_ir',
      key: 'ic_ir',
      align: 'right',
      render: (v: number | null) => fmt(v, 3),
    },
    {
      title: '年化IR',
      dataIndex: 'annualized_ir',
      key: 'annualized_ir',
      align: 'right',
      render: (v: number | null) =>
        v == null ? (
          '—'
        ) : (
          <span style={{ color: v >= 0 ? qc.positive : qc.negative }}>{v.toFixed(2)}</span>
        ),
    },
    {
      title: 't-stat',
      dataIndex: 't_stat',
      key: 't_stat',
      align: 'right',
      render: (v: number | null) => fmt(v, 2),
    },
    {
      title: 'IC胜率',
      dataIndex: 'ic_positive_rate',
      key: 'ic_positive_rate',
      align: 'right',
      render: (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`),
    },
    {
      title: '多空收益',
      dataIndex: 'long_short_return',
      key: 'long_short_return',
      align: 'right',
      render: (v: number | null) => fmt(v, 4),
    },
    {
      title: '单调性',
      dataIndex: 'monotonicity_spearman',
      key: 'monotonicity_spearman',
      align: 'right',
      render: (v: number | null) => fmt(v, 3),
    },
    {
      title: '稳定性',
      dataIndex: 'stability_autocorr',
      key: 'stability_autocorr',
      align: 'right',
      render: (v: number | null) => fmt(v, 3),
    },
    {
      title: '组数',
      dataIndex: 'n_groups',
      key: 'n_groups',
      align: 'right',
    },
    {
      title: '样本数',
      dataIndex: 'bar_count',
      key: 'bar_count',
      align: 'right',
    },
  ];

  // 最多 5 条线，用语义色循环着色
  const linePalette = [qc.chartLine, qc.info, qc.positive, qc.warning, qc.negative];

  const icOption = useMemo<EChartsOption>(() => {
    if (!result) return {};
    const rows = result.factors;
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: rows.map((r) => r.label || r.factor_name) },
      grid: { left: '3%', right: '4%', containLabel: true },
      xAxis: {
        type: 'category',
        data: result.ic_series.dates,
        axisLabel: { color: qc.chartMark },
      },
      yAxis: { type: 'value', axisLabel: { color: qc.chartMark } },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 4 }],
      series: rows.map((r, i) => ({
        name: r.label || r.factor_name,
        type: 'line',
        showSymbol: false,
        // null 自动断线
        data: result.ic_series.series[r.factor_name] ?? [],
        itemStyle: { color: linePalette[i % linePalette.length] },
      })),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, qc]);

  return (
    <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
      <Card title="对比参数">
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
          <Form.Item
            name="factor_names"
            label="因子"
            rules={[
              {
                validator: (_, value: string[] | undefined) =>
                  value && value.length >= 2 && value.length <= 5
                    ? Promise.resolve()
                    : Promise.reject(new Error('请选择 2-5 个因子')),
              },
            ]}
          >
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              style={{ minWidth: 280 }}
              placeholder="选择 2-5 个因子"
              options={factors.map((f) => ({
                value: f.name,
                label: `${f.label} (${f.name})`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="instruments"
            label="品种"
            rules={[{ required: true, message: '选择品种' }]}
          >
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
            <RangePicker showTime format="YYYY-MM-DD HH:mm:ss" />
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
            <Button type="primary" icon={<SwapOutlined />} loading={loading} onClick={run}>
              开始对比
            </Button>
          </Form.Item>
        </Form>
        <p style={{ color: '#999', fontSize: 12, marginTop: 8, marginBottom: 0 }}>
          2-5 个可计算因子共用一组参数横向对比；滚动窗 / 前瞻单位均为 K 线根数。
        </p>
      </Card>

      {loading && <Card loading />}
      {!loading && !result && (
        <Card>
          <Empty description="选择 2-5 个因子后点击「开始对比」" />
        </Card>
      )}

      {!loading && result && (
        <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
          <Card title="指标对比">
            <Table<FactorCompareRow>
              rowKey="factor_name"
              columns={columns}
              dataSource={result.factors}
              pagination={false}
              scroll={{ x: 'max-content' }}
            />
          </Card>
          <Card title="IC 时序叠加">
            <EChart option={icOption} style={{ height: 360 }} opts={{ renderer: 'svg' }} />
          </Card>
        </Space>
      )}
    </Space>
  );
};

export default FactorCompare;
