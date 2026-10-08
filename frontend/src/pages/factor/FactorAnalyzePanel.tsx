/**
 * 右栏「分析」页签：锁定左栏选中因子，参数表单 + 异步分析 + 结果展示。
 * - 后端对每次成功分析强制自动留痕（无开关、无感知）；
 * - 分析/手动存快照成功后回调 onAnalyzed，由容器刷新左栏 last_metrics / 快照数。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  App as AntApp,
  Button,
  Card,
  DatePicker,
  Empty,
  Flex,
  Form,
  Input,
  InputNumber,
  Progress,
  Select,
  Space,
} from 'antd';
import { LineChartOutlined, StarOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import {
  factorApi,
  type FactorAnalyzeParams,
  type FactorAnalyzeResult,
  type FactorCatalogItem,
  type InstrumentInfo,
} from '@/api/factor';
import { useFactorJob } from '@/hooks/useFactorJob';
import FactorResultView from './FactorResultView';

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
 * 解析 horizons 文本：trim 后按中英文逗号分隔。空字符串 → null（后端默认 [1,2,3,5,10]）；
 * 每项必须是 1-120 整数、最多 20 个，否则返回错误信息（与后端校验一致）。
 */
const parseHorizons = (text: string | undefined): number[] | null | string => {
  const tx = (text ?? '').trim();
  if (!tx) return null;
  const parts = tx
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

interface Props {
  factor: FactorCatalogItem;
  onAnalyzed?: () => void;
}

const FactorAnalyzePanel: React.FC<Props> = ({ factor, onAnalyzed }) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [form] = Form.useForm<FormValues>();
  const [instruments, setInstruments] = useState<InstrumentInfo[]>([]);
  const [result, setResult] = useState<FactorAnalyzeResult | null>(null);
  const [lastParams, setLastParams] = useState<FactorAnalyzeParams | null>(null);
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const { run: runJob, status: jobStatus, loading: jobLoading } =
    useFactorJob<FactorAnalyzeResult>();
  const selected: string[] = Form.useWatch('instruments', form) ?? [];

  // 因子由左栏锁定：挂载即写入表单（组件在容器内按 factor.name 加 key，切因子整体重挂载）
  useEffect(() => {
    form.setFieldsValue({ factor_name: factor.name });
  }, [factor.name, form]);

  useEffect(() => {
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
          setLastParams(params);
          // 静默：不弹"已留痕"，仅刷新目录让快照数/最近指标自然变化
          onAnalyzed?.();
        },
        (msg) => {
          message.error(msg);
        },
      );
    } catch (err) {
      message.error(errMsg(err));
    }
  }, [form, runJob, onAnalyzed]);

  const saveNow = async () => {
    if (!lastParams) return;
    setSavingSnapshot(true);
    try {
      const r = await factorApi.saveSnapshot(lastParams);
      message.success(t('factor_wb_toast_saved', { id: r.id }) || `快照已保存（#${r.id}）`);
      onAnalyzed?.();
    } catch (e) {
      message.error((e as Error)?.message || t('factor_wb_toast_save_failed') || '保存失败');
    } finally {
      setSavingSnapshot(false);
    }
  };

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card title={t('factor_wb_card_params') || '分析参数'}>
        {/* inline 表单项换行后默认无垂直间距，用 rowGap 补到 middle 档 16px */}
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
          <Form.Item name="factor_name" label={t('factor_wb_form_factor') || '因子'}>
            <Select
              disabled
              style={{ width: 220 }}
              options={[{ value: factor.name, label: `${factor.label} (${factor.name})` }]}
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
            extra={t('factor_wb_form_cost_hint') || '单边费率基点，10bp=0.1%；用于分位组合费后净值'}
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
            <Progress type="circle" size={48} percent={Math.round(jobStatus.progress)} status="active" />
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
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          <Flex justify="flex-end">
            <Button
              type="primary"
              ghost
              icon={<StarOutlined />}
              loading={savingSnapshot}
              disabled={!lastParams}
              onClick={saveNow}
            >
              {t('factor_wb_btn_save') || '保存快照'}
            </Button>
          </Flex>
          <FactorResultView result={result} />
        </Space>
      )}
    </Space>
  );
};

export default FactorAnalyzePanel;
