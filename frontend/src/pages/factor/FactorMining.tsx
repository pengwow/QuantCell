import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  DatePicker,
  Drawer,
  Flex,
  Form,
  Input,
  InputNumber,
  message,
  Popconfirm,
  Progress,
  Radio,
  Select,
  Slider,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import type { TableProps } from 'antd';
import {
  factorApi,
  type FactorMineLLMParams,
  type FactorMineResult,
  type InstrumentInfo,
  type MinedCandidate,
} from '@/api/factor';
import { useFactorJob } from '@/hooks/useFactorJob';
import { useQuantColors } from '@/utils/colors';

const { RangePicker } = DatePicker;

interface FormValues {
  instruments: string[];
  interval: string;
  range?: [Dayjs, Dayjs] | null;
  n_candidates: number;
  n_rounds: number;
  top_k: number;
  test_ratio: number;
  wf_folds: number;
}

const errMsg = (e: unknown) => (e as Error)?.message || '挖掘失败';

const fmt = (v: number | null | undefined, digits: number) =>
  v == null ? '—' : v.toFixed(digits);

/** ISO 时间串 → 'YYYY-MM-DD HH:mm' 紧凑展示 */
const fmtTime = (iso: string) => iso.replace('T', ' ').slice(0, 16);

/** 样本外复核结论 → Tag 颜色与中文文案 */
const OOS_TAG: Record<NonNullable<MinedCandidate['oos_flag']>, { color: string; text: string }> = {
  ok: { color: 'green', text: '稳定' },
  weak: { color: 'orange', text: '衰减' },
  sign_flip: { color: 'red', text: '符号反转' },
};

/** 候选状态 → Tag 颜色与中文文案 */
const STATUS_TAG: Record<MinedCandidate['status'], { color: string; text: string }> = {
  success: { color: 'green', text: '有效' },
  security_error: { color: 'red', text: '安全拦截' },
  output_error: { color: 'orange', text: '输出不合规' },
  timeout: { color: 'red', text: '超时/资源限制' },
  resource_error: { color: 'red', text: '超时/资源限制' },
  runtime_error: { color: 'default', text: '运行失败' },
  empty: { color: 'default', text: '空响应' },
  llm_truncated: { color: 'orange', text: '思考超限' },
};

const FactorMining: React.FC = () => {
  const qc = useQuantColors();
  const [form] = Form.useForm<FormValues>();
  const [candleType, setCandleType] = useState<'spot' | 'future'>('spot');
  const [instruments, setInstruments] = useState<InstrumentInfo[]>([]);
  const [temperature, setTemperature] = useState(0.8);
  const [result, setResult] = useState<FactorMineResult | null>(null);
  const [drawerRow, setDrawerRow] = useState<MinedCandidate | null>(null);
  // Popconfirm 内嵌命名 Input 的局部状态：打开时写入当前行与默认名称，确认时取最新值
  const [saveRow, setSaveRow] = useState<MinedCandidate | null>(null);
  const [saveName, setSaveName] = useState('');
  const [saving, setSaving] = useState(false);
  const { run: runJob, status: jobStatus, loading: jobLoading } =
    useFactorJob<FactorMineResult>();
  const selected: string[] = Form.useWatch('instruments', form) ?? [];

  // 市场类型切换后重新拉取品种列表（初始挂载 spot 也由此 effect 完成）
  useEffect(() => {
    factorApi
      .instruments(candleType)
      .then((r) => setInstruments(r.symbols))
      .catch(() => undefined);
  }, [candleType]);

  // 周期下拉取所选品种共有周期的交集；没有共同周期时退回 1h
  const intervalOptions = useMemo(() => {
    const picked = instruments.filter((i) => selected.includes(i.symbol));
    if (!picked.length) return ['1h'].map((v) => ({ value: v, label: v }));
    const sets = picked.map((i) => new Set(i.intervals));
    const common = [...sets[0]].filter((x) => sets.every((s) => s.has(x)));
    return (common.length ? common : ['1h']).map((v) => ({ value: v, label: v }));
  }, [instruments, selected]);

  // 表格数据：按轮次升序；同轮成功候选按 fitness 降序，失败候选排在成功之后
  const dataSource = useMemo(() => {
    if (!result) return [];
    return [...result.candidates].sort((a, b) => {
      if (a.round !== b.round) return a.round - b.round;
      const rank = (r: MinedCandidate) => (r.status === 'success' ? 0 : 1);
      if (rank(a) !== rank(b)) return rank(a) - rank(b);
      const fa = a.metrics?.fitness ?? Number.NEGATIVE_INFINITY;
      const fb = b.metrics?.fitness ?? Number.NEGATIVE_INFINITY;
      return fb - fa;
    });
  }, [result]);

  const run = async () => {
    const v = await form.validateFields();
    const [s, e] = v.range ?? [];
    const params: FactorMineLLMParams = {
      instruments: v.instruments,
      interval: v.interval,
      candle_type: candleType,
      start_time: s ? dayjs(s).format('YYYY-MM-DD HH:mm:ss') : null,
      end_time: e ? dayjs(e).format('YYYY-MM-DD HH:mm:ss') : null,
      n_candidates: v.n_candidates,
      n_rounds: v.n_rounds,
      top_k: v.top_k,
      temperature,
      test_ratio: v.test_ratio,
      wf_folds: v.wf_folds,
    };
    setResult(null);
    try {
      await runJob('llm_mine', params, setResult, (msg) => {
        message.error(msg);
      });
    } catch (err) {
      // 提交阶段同步 rejection（如未配置 AI 模型的 400、422、网络失败）
      message.error(errMsg(err));
    }
  };

  // Popconfirm 确认：reject 时气泡保持打开，便于改名重试
  const handleSave = async () => {
    if (!saveRow) return;
    const name = saveName.trim();
    if (!name) {
      message.warning('请输入因子名称');
      throw new Error('empty name');
    }
    setSaving(true);
    try {
      await factorApi.addCodeFactor(name, saveRow.code);
      message.success(`已保存到因子库：${name}`);
    } catch (err) {
      message.error(errMsg(err));
      throw err;
    } finally {
      setSaving(false);
    }
  };

  const columns: TableProps<MinedCandidate>['columns'] = [
    {
      title: '轮次',
      dataIndex: 'round',
      key: 'round',
      width: 70,
      align: 'center',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (status: MinedCandidate['status'], row) => {
        const t = STATUS_TAG[status];
        return (
          <Flex gap="small" align="center">
            <Tag color={t.color} style={{ marginInlineEnd: 0 }}>
              {t.text}
            </Tag>
            {status === 'success' && row.redundant && (
              <Tooltip
                title={`与 ${(row.redundant_with || '').slice(0, 8)} 的因子相关系数 ${row.redundant_corr ?? '—'}`}
              >
                <Tag color="orange" style={{ marginInlineEnd: 0 }}>
                  重复
                </Tag>
              </Tooltip>
            )}
          </Flex>
        );
      },
    },
    {
      title: 'fitness',
      key: 'fitness',
      align: 'right',
      width: 90,
      render: (_, row) => {
        const v = row.metrics?.fitness;
        return v == null ? (
          '—'
        ) : (
          <span style={{ color: v >= 0 ? qc.positive : qc.negative }}>{v.toFixed(2)}</span>
        );
      },
    },
    {
      title: 'IC',
      key: 'ic_mean',
      align: 'right',
      width: 90,
      render: (_, row) => fmt(row.metrics?.ic_mean, 4),
    },
    {
      title: '样本外IC',
      key: 'oos_ic',
      align: 'right',
      width: 100,
      render: (_, row) => fmt(row.metrics_oos?.ic_mean, 4),
    },
    {
      title: 'OOS',
      key: 'oos_flag',
      align: 'center',
      width: 90,
      render: (_, row) => {
        const flag = row.oos_flag;
        return flag ? <Tag color={OOS_TAG[flag].color}>{OOS_TAG[flag].text}</Tag> : '—';
      },
    },
    {
      title: 'WF一致性',
      key: 'wf_consistency',
      align: 'right',
      width: 100,
      render: (_, row) => {
        const v = row.metrics_oos?.sign_consistency;
        return v == null ? '—' : `${Math.round(v * 100)}%`;
      },
    },
    {
      title: 'IR',
      key: 'ic_ir',
      align: 'right',
      width: 90,
      render: (_, row) => fmt(row.metrics?.ic_ir, 3),
    },
    {
      title: '覆盖率',
      key: 'coverage',
      align: 'right',
      width: 90,
      render: (_, row) => {
        const v = row.metrics?.coverage;
        return v == null ? '—' : `${(v * 100).toFixed(1)}%`;
      },
    },
    {
      title: '换手',
      key: 'turnover',
      align: 'right',
      width: 100,
      render: (_, row) => fmt(row.metrics?.turnover, 4),
    },
    {
      title: '多空收益',
      key: 'long_short_return',
      align: 'right',
      width: 110,
      render: (_, row) => fmt(row.metrics?.long_short_return, 5),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 170,
      render: (_, row) => (
        <Flex gap="small">
          <Button size="small" onClick={() => setDrawerRow(row)}>
            代码
          </Button>
          {row.status === 'success' && (
            <Popconfirm
              title="保存为因子"
              description={
                <Input
                  value={saveName}
                  onChange={(ev) => setSaveName(ev.target.value)}
                  placeholder="因子名称"
                />
              }
              okText="保存"
              cancelText="取消"
              okButtonProps={{ loading: saving }}
              onOpenChange={(open) => {
                if (open) {
                  // 打开瞬间写入当前行与默认名，保证 onConfirm 拿到与该行一致的最新名称
                  setSaveRow(row);
                  setSaveName(`llm_${(row.code_hash || '').slice(0, 8)}`);
                }
              }}
              onConfirm={handleSave}
            >
              <Button size="small" type="link">
                保存为因子
              </Button>
            </Popconfirm>
          )}
        </Flex>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ display: 'flex' }}>
      <Card title="LLM 因子挖掘">
        <Form<FormValues>
          form={form}
          layout="vertical"
          initialValues={{
            interval: '1h',
            n_candidates: 4,
            n_rounds: 2,
            top_k: 5,
            test_ratio: 0.3,
            wf_folds: 0,
          }}
        >
          <Form.Item
            name="instruments"
            label="品种"
            rules={[
              {
                required: true,
                validator: (_, value: string[] | undefined) =>
                  value && value.length >= 1
                    ? Promise.resolve()
                    : Promise.reject(new Error('请至少选择一个品种')),
              },
            ]}
          >
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              allowClear
              placeholder="选择品种（可多选）"
              options={instruments.map((i) => ({ value: i.symbol, label: i.symbol }))}
            />
          </Form.Item>
          <Form.Item label="市场类型">
            <Radio.Group
              value={candleType}
              optionType="button"
              buttonStyle="solid"
              options={[
                { value: 'spot', label: '现货' },
                { value: 'future', label: '合约' },
              ]}
              onChange={(ev) => {
                // 切换市场：重新拉取品种列表并清空已选品种
                setCandleType(ev.target.value as 'spot' | 'future');
                form.setFieldValue('instruments', []);
              }}
            />
          </Form.Item>
          <Form.Item name="interval" label="周期">
            <Select style={{ width: 160 }} options={intervalOptions} />
          </Form.Item>
          <Form.Item name="range" label="时间范围（可选）">
            <RangePicker showTime format="YYYY-MM-DD HH:mm:ss" />
          </Form.Item>
          <Flex gap="middle" wrap>
            <Form.Item name="n_candidates" label="每轮候选数">
              <InputNumber min={1} max={8} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="n_rounds" label="反思轮数">
              <InputNumber min={1} max={4} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="top_k" label="Top K">
              <InputNumber min={1} max={10} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item
              name="test_ratio"
              label="样本外比例"
              extra="0=不切分；取后段时间做样本外复核"
            >
              <InputNumber min={0} max={0.5} step={0.05} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item
              name="wf_folds"
              label="WF折数"
              extra="0=单次样本外切分；2-6=滚动 walk-forward 多窗口复核"
              tooltip="在多个连续样本外窗口上分别计算截面 IC，汇总均值/ICIR/符号一致性，比单次切分更能识别过拟合"
            >
              <InputNumber min={0} max={6} step={1} precision={0} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item label="温度">
              <Flex gap="middle" align="center" style={{ width: 280 }}>
                <Slider
                  style={{ flex: 1, margin: 0 }}
                  min={0}
                  max={2}
                  step={0.1}
                  value={temperature}
                  onChange={setTemperature}
                />
                <InputNumber
                  style={{ width: 72 }}
                  min={0}
                  max={2}
                  step={0.1}
                  value={temperature}
                  onChange={(v) => setTemperature(v ?? 0)}
                />
              </Flex>
            </Form.Item>
          </Flex>
          <Form.Item>
            <Button type="primary" loading={jobLoading} disabled={jobLoading} onClick={run}>
              开始挖掘
            </Button>
          </Form.Item>
          {jobLoading && (
            <Form.Item label="挖掘进度">
              <Flex gap="middle" align="center">
                <Progress
                  style={{ flex: 1, marginBottom: 0 }}
                  percent={Math.round(jobStatus?.progress ?? 0)}
                  status="active"
                />
                <span>{jobStatus?.message || '排队中…'}</span>
              </Flex>
            </Form.Item>
          )}
        </Form>
      </Card>

      <Card title="挖掘结果">
        <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
          {result && (
            <Flex gap="large" wrap>
              <Statistic title="生成" value={result.stats.generated} />
              <Statistic title="去重后" value={result.stats.unique} />
              <Statistic title="成功" value={result.stats.succeeded} valueStyle={{ color: qc.positive }} />
              <Statistic
                title="重复"
                value={result.stats.redundant ?? 0}
                valueStyle={{ color: '#d46b08' }}
              />
              <Statistic title="失败" value={result.stats.failed} valueStyle={{ color: qc.negative }} />
            </Flex>
          )}
          <Table<MinedCandidate>
            rowKey={(r) => `${r.round}-${r.candidate}-${r.code_hash || 'empty'}`}
            columns={columns}
            dataSource={dataSource}
            pagination={{ pageSize: 20 }}
            scroll={{ x: 'max-content' }}
            expandable={{
              rowExpandable: (r) =>
                !!r.error || !!r.oos_note || !!r.metrics_oos?.folds?.length,
              expandedRowRender: (r) => (
                <Flex vertical gap="small">
                  {r.error && (
                    <span style={{ color: '#cf1322', whiteSpace: 'pre-wrap' }}>{r.error}</span>
                  )}
                  {r.oos_note && (
                    <span style={{ color: '#d46b08', whiteSpace: 'pre-wrap' }}>{r.oos_note}</span>
                  )}
                  {r.metrics_oos?.folds?.map((f) => (
                    <Flex key={f.index} gap="middle" wrap align="center">
                      <Tag>窗口 {f.index + 1}</Tag>
                      <span style={{ color: '#8c8c8c' }}>
                        {fmtTime(f.start)} ~ {fmtTime(f.end)}
                      </span>
                      <span>IC: {fmt(f.ic_mean, 4)}</span>
                      <span>
                        覆盖率:{' '}
                        {f.coverage == null ? '—' : `${(f.coverage * 100).toFixed(1)}%`}
                      </span>
                      <span>bars: {f.bar_count}</span>
                    </Flex>
                  ))}
                </Flex>
              ),
            }}
            locale={{ emptyText: '暂无挖掘结果，请先在上方配置并开始挖掘' }}
          />
        </Space>
      </Card>

      <Drawer
        open={!!drawerRow}
        title={drawerRow ? `轮次${drawerRow.round} 候选${drawerRow.candidate}` : ''}
        width={640}
        onClose={() => setDrawerRow(null)}
      >
        {drawerRow?.code ? (
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 13 }}>{drawerRow.code}</pre>
        ) : (
          '无代码'
        )}
      </Drawer>
    </Space>
  );
};

export default FactorMining;
