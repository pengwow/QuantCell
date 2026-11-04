/**
 * 新建研究会话抽屉（PRD §6.4）：模式 Radio + 数据窗口 + 成本/硬门高级参数。
 * 表单默认值来自后端 consts 的同一套口径，前端仅做展示与轻量校验。
 */
import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  DatePicker,
  Drawer,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { researchApi, type ResearchCreateParams, type ResearchMode, type ResearchSession } from '@/api/research';

interface Props {
  open: boolean;
  initialMode?: ResearchMode;
  /** 复制配置的来源会话：按它的 config 预填表单 */
  copyFrom?: ResearchSession | null;
  onClose: () => void;
  onCreated: (sessionId: number) => void;
}

const DEFAULT_SYMBOLS = ['BTCUSDT', 'ETHUSDT'];
const INTERVALS = ['15m', '30m', '1h', '4h', '1d'];

/** 与后端 research/consts 同一口径的创建前预算估算（下限，仅拦明显不够的上限）。 */
const DEEP_CALLS_PER_LOOP = 4;
const QUICK_EXTRA_CALLS = 1;
const EST_TOKENS_PER_CALL = 3000;

const estimateCalls = (mode: ResearchMode, candidates: number, loops: number): number =>
  mode === 'quick' ? candidates + QUICK_EXTRA_CALLS : loops * DEEP_CALLS_PER_LOOP;

interface FormValues {
  mode: ResearchMode;
  name?: string;
  symbols: string[];
  interval: string;
  candle_type: 'spot' | 'future';
  window: [Dayjs, Dayjs];
  n_candidates?: number;
  loop_n?: number;
  max_llm_calls?: number;
  max_tokens?: number;
  icir_floor?: number;
  corr_threshold?: number;
}

const ResearchNewDrawer: React.FC<Props> = ({ open, initialMode, copyFrom, onClose, onCreated }) => {
  const [form] = Form.useForm<FormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mode = Form.useWatch('mode', form) ?? 'deep';
  // 复制配置预填会触发模式变化；这一次不要用默认值把复制来的参数冲掉
  const skipModeResetFor = useRef<ResearchMode | null>(null);
  const watchedCandidates = Form.useWatch('n_candidates', form);
  const watchedLoops = Form.useWatch('loop_n', form);
  const watchedMaxCalls = Form.useWatch('max_llm_calls', form);

  const estCalls = estimateCalls(mode, watchedCandidates ?? 4, watchedLoops ?? 3);
  const estTokens = estCalls * EST_TOKENS_PER_CALL;
  const overBudget = Boolean(watchedMaxCalls && estCalls > watchedMaxCalls);

  // 打开抽屉：有复制来源就按它的 config 预填，否则只预置入口模式
  useEffect(() => {
    if (!open) return;
    if (copyFrom) {
      const cfg = copyFrom.config;
      const start = cfg.start ? dayjs(String(cfg.start)) : dayjs().subtract(180, 'day');
      const end = cfg.end ? dayjs(String(cfg.end)) : dayjs();
      skipModeResetFor.current = copyFrom.mode;
      form.setFieldsValue({
        mode: copyFrom.mode,
        name: `复制-${copyFrom.name}`.slice(0, 64),
        symbols: (cfg.symbols as string[] | undefined) ?? DEFAULT_SYMBOLS,
        interval: String(cfg.interval ?? '1h'),
        candle_type: (cfg.candle_type as 'spot' | 'future' | undefined) ?? 'spot',
        window: [start, end],
        n_candidates: copyFrom.n_candidates,
        loop_n: copyFrom.loop_n,
        max_llm_calls: Number(cfg.max_llm_calls) || undefined,
        max_tokens: Number(cfg.max_tokens) || undefined,
        icir_floor: Number(cfg.icir_floor) || undefined,
        corr_threshold: Number(cfg.corr_threshold) || undefined,
      });
      return;
    }
    skipModeResetFor.current = initialMode ?? 'deep';
    form.setFieldsValue({ mode: initialMode ?? 'deep' });
  }, [open, copyFrom, initialMode, form]);

  // 切换模式时把候选数与预算重置为对应默认值，避免 quick 带上 deep 的 30 次预算
  useEffect(() => {
    const skip = skipModeResetFor.current === mode;
    skipModeResetFor.current = null;
    if (skip) return;
    const isQuick = mode === 'quick';
    form.setFieldsValue({
      n_candidates: isQuick ? 4 : 2,
      loop_n: isQuick ? 1 : 3,
      max_llm_calls: isQuick ? 6 : 30,
      max_tokens: isQuick ? 40_000 : 200_000,
      icir_floor: 0.15,
      corr_threshold: 0.7,
    });
  }, [mode, form]);

  const submit = async () => {
    setError(null);
    try {
      const values = await form.validateFields();
      // 与后端同一口径的前置校验：明显不够的预算不提交，避免建完才在后台爆掉
      const needCalls = estimateCalls(
        values.mode,
        values.n_candidates ?? 4,
        values.mode === 'deep' ? (values.loop_n ?? 3) : 1,
      );
      const needTokens = needCalls * EST_TOKENS_PER_CALL;
      if (values.max_llm_calls && needCalls > values.max_llm_calls) {
        setError(`按候选数/轮次估算至少需要 ${needCalls} 次 LLM 调用，超过上限 ${values.max_llm_calls}，请提高上限或减少轮次`);
        return;
      }
      if (values.max_tokens && needTokens > values.max_tokens) {
        setError(`按估算至少需要约 ${needTokens} tokens，超过上限 ${values.max_tokens}`);
        return;
      }
      const [start, end] = values.window;
      const payload: ResearchCreateParams = {
        mode: values.mode,
        name: values.name?.trim() || undefined,
        symbols: values.symbols,
        interval: values.interval,
        candle_type: values.candle_type,
        start: start.format('YYYY-MM-DD'),
        end: end.format('YYYY-MM-DD'),
        n_candidates: values.n_candidates,
        loop_n: values.mode === 'deep' ? values.loop_n : 1,
        max_llm_calls: values.max_llm_calls,
        max_tokens: values.max_tokens,
        icir_floor: values.icir_floor,
        corr_threshold: values.corr_threshold,
      };
      setSubmitting(true);
      const res = await researchApi.create(payload);
      onCreated(res.session_id);
      form.resetFields();
      onClose();
    } catch (err) {
      // 表单校验错误已在字段下展示；接口错误单独提示
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      setError(err instanceof Error ? err.message : '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      title="新建 AI 研究"
      open={open}
      onClose={onClose}
      size="40%"
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          mode: 'deep',
          symbols: DEFAULT_SYMBOLS,
          interval: '1h',
          candle_type: 'spot',
          window: [dayjs().subtract(180, 'day'), dayjs()],
        }}
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          {error && <Alert type="error" message={error} showIcon />}

          <Form.Item name="mode" label="研究模式">
            <Radio.Group optionType="button" buttonStyle="solid">
              <Radio.Button value="deep">深度研究（假设→编码→评估→反馈）</Radio.Button>
              <Radio.Button value="quick">快速验证（复用现有挖掘）</Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Form.Item name="name" label="会话名称（可选）">
            <Input placeholder="留空自动生成" maxLength={64} />
          </Form.Item>

          <Form.Item
            name="symbols"
            label="品种"
            rules={[{ required: true, message: '请至少选择一个品种' }]}
          >
            <Select mode="tags" tokenSeparators={[',', ' ']} options={DEFAULT_SYMBOLS.map((s) => ({ value: s, label: s }))} />
          </Form.Item>

          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item name="interval" label="周期" style={{ flex: 1 }}>
              <Select options={INTERVALS.map((i) => ({ value: i, label: i }))} />
            </Form.Item>
            <Form.Item name="candle_type" label="市场" style={{ flex: 1 }}>
              <Select
                options={[
                  { value: 'spot', label: '现货' },
                  { value: 'future', label: '合约' },
                ]}
              />
            </Form.Item>
          </Space>

          <Form.Item
            name="window"
            label="数据窗口"
            rules={[
              { required: true, message: '请选择数据窗口' },
              {
                validator: (_, value: [Dayjs, Dayjs] | undefined) =>
                  !value || value[1].diff(value[0], 'day') >= 30
                    ? Promise.resolve()
                    : Promise.reject(new Error('数据窗口至少 30 天')),
              },
            ]}
          >
            <DatePicker.RangePicker style={{ width: '100%' }} allowClear={false} />
          </Form.Item>

          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item name="n_candidates" label="候选数" style={{ flex: 1 }}>
              <InputNumber min={1} max={10} style={{ width: '100%' }} />
            </Form.Item>
            {mode === 'deep' && (
              <Form.Item name="loop_n" label="研究轮次" style={{ flex: 1 }}>
                <InputNumber min={1} max={10} style={{ width: '100%' }} />
              </Form.Item>
            )}
          </Space>

          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item name="max_llm_calls" label="LLM 调用上限" style={{ flex: 1 }}>
              <InputNumber min={1} max={500} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="max_tokens" label="Token 上限" style={{ flex: 1 }}>
              <InputNumber min={1000} step={1000} style={{ width: '100%' }} />
            </Form.Item>
          </Space>

          {overBudget && (
            <Alert
              type="warning"
              showIcon
              message={`按候选数/轮次估算至少需要 ${estCalls} 次调用（约 ${estTokens} tokens），当前上限不够，请提高上限或减少轮次`}
            />
          )}

          {/* quick 只走冗余门，IC_IR/相关性属于 deep 专属硬门，不展示 */}
          {mode === 'deep' && (
            <Space size="middle" style={{ display: 'flex' }}>
              <Form.Item name="icir_floor" label="IC_IR 硬门" style={{ flex: 1 }}>
                <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="corr_threshold" label="相关性上限" style={{ flex: 1 }}>
                <InputNumber min={0.1} max={1} step={0.05} style={{ width: '100%' }} />
              </Form.Item>
            </Space>
          )}

          <Space>
            <Button type="primary" loading={submitting} onClick={() => void submit()}>
              开始研究
            </Button>
            <Button onClick={onClose}>取消</Button>
          </Space>
        </Space>
      </Form>
    </Drawer>
  );
};

export default ResearchNewDrawer;
