import { useEffect, useMemo, useState } from 'react';
import {
  App as AntApp,
  Button,
  Card,
  DatePicker,
  Flex,
  Form,
  InputNumber,
  Progress,
  Radio,
  Select,
  Slider,
  Space,
  Switch,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import {
  factorApi,
  type FactorMineLLMParams,
  type FactorMineResult,
  type InstrumentInfo,
} from '@/api/factor';
import { useFactorJob } from '@/hooks/useFactorJob';
import MiningResultView from './MiningResultView';

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
  compose: boolean;
}

const errMsg = (e: unknown) => (e as Error)?.message || '挖掘失败';

const FactorMining: React.FC<{ onMined?: (name: string) => void }> = ({ onMined }) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [form] = Form.useForm<FormValues>();
  const [candleType, setCandleType] = useState<'spot' | 'future'>('spot');
  const [instruments, setInstruments] = useState<InstrumentInfo[]>([]);
  const [temperature, setTemperature] = useState(0.8);
  const [result, setResult] = useState<FactorMineResult | null>(null);
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
      compose: v.compose,
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

  return (
    <Space orientation="vertical" size="large" style={{ display: 'flex' }}>
      <Card title={t('factor_mining_card_main') || 'LLM 因子挖掘'}>
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
            compose: true,
          }}
        >
          <Form.Item
            name="instruments"
            label={t('factor_wb_form_instruments') || '品种'}
            rules={[
              {
                required: true,
                validator: (_, value: string[] | undefined) =>
                  value && value.length >= 1
                    ? Promise.resolve()
                    : Promise.reject(new Error(t('factor_wb_form_instruments_req') || '请至少选择一个品种')),
              },
            ]}
          >
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              allowClear
              placeholder={t('factor_wb_form_instruments_ph') || '选择品种（可多选）'}
              options={instruments.map((i) => ({ value: i.symbol, label: i.symbol }))}
            />
          </Form.Item>
          <Form.Item label={t('factor_mining_form_market') || '市场类型'}>
            <Radio.Group
              value={candleType}
              optionType="button"
              buttonStyle="solid"
              options={[
                { value: 'spot', label: t('factor_mining_spot') || '现货' },
                { value: 'future', label: t('factor_mining_future') || '合约' },
              ]}
              onChange={(ev) => {
                // 切换市场：重新拉取品种列表并清空已选品种
                setCandleType(ev.target.value as 'spot' | 'future');
                form.setFieldValue('instruments', []);
              }}
            />
          </Form.Item>
          <Form.Item name="interval" label={t('factor_wb_form_interval') || '周期'}>
            <Select style={{ width: 160 }} options={intervalOptions} />
          </Form.Item>
          <Form.Item name="range" label={t('factor_mining_form_range_opt') || '时间范围（可选）'}>
            <RangePicker showTime format="YYYY-MM-DD HH:mm:ss" />
          </Form.Item>
          <Flex gap="middle" wrap>
            <Form.Item name="n_candidates" label={t('factor_mining_form_candidates') || '每轮候选数'}>
              <InputNumber min={1} max={8} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="n_rounds" label={t('factor_mining_form_rounds') || '反思轮数'}>
              <InputNumber min={1} max={4} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="top_k" label={t('factor_mining_form_topk') || 'Top K'}>
              <InputNumber min={1} max={10} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item
              name="test_ratio"
              label={t('factor_mining_form_test_ratio') || '样本外比例'}
              extra={t('factor_mining_form_test_ratio_hint') || '0=不切分；取后段时间做样本外复核'}
            >
              <InputNumber min={0} max={0.5} step={0.05} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item
              name="wf_folds"
              label={t('factor_mining_form_wf_folds') || 'WF折数'}
              extra={t('factor_mining_form_wf_folds_hint') || '0=单次样本外切分；2-6=滚动 walk-forward 多窗口复核'}
              tooltip={t('factor_mining_form_wf_folds_tip') || '在多个连续样本外窗口上分别计算截面 IC，汇总均值/ICIR/符号一致性，比单次切分更能识别过拟合'}
            >
              <InputNumber min={0} max={6} step={1} precision={0} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item
              name="compose"
              label={t('factor_mining_form_compose') || '合成最佳因子'}
              extra={t('factor_mining_form_compose_hint') || '去重后对最佳候选做 IC 加权 zscore 自动合成'}
              tooltip={t('factor_mining_form_compose_tip') || '权重与标准化统计只在 train 段拟合冻结；合成因子可在结果区直接保存到因子库'}
              valuePropName="checked"
            >
              <Switch
                checkedChildren={t('factor_mining_switch_on') || '开'}
                unCheckedChildren={t('factor_mining_switch_off') || '关'}
              />
            </Form.Item>
            <Form.Item label={t('factor_mining_form_temperature') || '温度'}>
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
              {t('factor_mining_run') || '开始挖掘'}
            </Button>
          </Form.Item>
          {jobLoading && (
            <Form.Item label={t('factor_mining_progress') || '挖掘进度'}>
              <Flex gap="middle" align="center">
                <Progress
                  style={{ flex: 1, marginBottom: 0 }}
                  percent={Math.round(jobStatus?.progress ?? 0)}
                  status="active"
                />
                <span>{jobStatus?.message || t('factor_wb_queueing') || '排队中…'}</span>
              </Flex>
            </Form.Item>
          )}
        </Form>
      </Card>

      <Card title={t('factor_mining_card_result') || '挖掘结果'}>
        {result ? (
          <MiningResultView result={result} onMined={onMined} />
        ) : (
          <span style={{ color: '#8c8c8c' }}>
            {t('factor_mining_empty') || '暂无挖掘结果，请先在上方配置并开始挖掘'}
          </span>
        )}
      </Card>
    </Space>
  );
};

export default FactorMining;
