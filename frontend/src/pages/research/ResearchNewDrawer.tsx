/**
 * 新建研究会话抽屉（PRD §6.4）：模式 Radio + 数据窗口 + 成本/硬门高级参数。
 * 表单默认值来自后端 consts 的同一套口径，前端仅做展示与轻量校验。
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  /** 种子因子（「基于已有因子研究」入口带入）：展示为可清除标签，提交时随 payload 下发 */
  seedFactor?: string | null;
  /** 复制配置的来源会话：按它的 config 预填表单 */
  copyFrom?: ResearchSession | null;
  onClose: () => void;
  onCreated: (sessionId: number) => void;
}

const DEFAULT_SYMBOLS = ['BTCUSDT', 'ETHUSDT'];
const INTERVALS = ['15m', '30m', '1h', '4h', '1d'];

/** 与后端 research/consts 同口径的预算估算（仅提示，不拦截提交）。 */
const DEEP_CALLS_PER_LOOP = 4;
const QUICK_EXTRA_CALLS = 1;
const EST_TOKENS_PER_CALL = 12000;  // 与后端 consts.EST_TOKENS_PER_CALL 同口径（仅用于提示）

const estimateCalls = (mode: ResearchMode, candidates: number, loops: number): number =>
  mode === 'quick' ? candidates + QUICK_EXTRA_CALLS : loops * DEEP_CALLS_PER_LOOP;

interface FormValues {
  mode: ResearchMode;
  scenario: 'factor' | 'strategy' | 'model';
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
  sharpe_floor?: number;
  min_trades?: number;
  initial_cash?: number;
}

const ResearchNewDrawer: React.FC<Props> = ({ open, initialMode, seedFactor, copyFrom, onClose, onCreated }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<FormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 种子因子可清除：用本地 state 而不是直接绑 prop，用户能移除后再提交
  const [seed, setSeed] = useState<string | null>(null);
  const mode = Form.useWatch('mode', form) ?? 'deep';
  const scenario = Form.useWatch('scenario', form) ?? 'factor';
  // 复制配置预填会触发模式变化；这一次不要用默认值把复制来的参数冲掉
  const skipModeResetFor = useRef<ResearchMode | null>(null);
  const watchedCandidates = Form.useWatch('n_candidates', form);
  const watchedLoops = Form.useWatch('loop_n', form);
  const watchedMaxCalls = Form.useWatch('max_llm_calls', form);
  const watchedMaxTokens = Form.useWatch('max_tokens', form);

  const estCalls = estimateCalls(mode, watchedCandidates ?? 4, watchedLoops ?? 3);
  const estTokens = estCalls * EST_TOKENS_PER_CALL;
  // 估算只作为提示：低于估算时不拦截提交，由后端运行期 Budget 预留/结算兜底
  const overBudget = Boolean(
    (watchedMaxCalls && estCalls > watchedMaxCalls) || (watchedMaxTokens && estTokens > watchedMaxTokens),
  );

  // 打开抽屉：有复制来源就按它的 config 预填，否则只预置入口模式；种子因子同步重置（复制来源优先）
  useEffect(() => {
    if (!open) return;
    setSeed(seedFactor ?? null);
    if (copyFrom) {
      const cfg = copyFrom.config;
      const start = cfg.start ? dayjs(String(cfg.start)) : dayjs().subtract(180, 'day');
      const end = cfg.end ? dayjs(String(cfg.end)) : dayjs();
      skipModeResetFor.current = copyFrom.mode;
      form.setFieldsValue({
        mode: copyFrom.mode,
        scenario: (cfg.scenario as 'factor' | 'strategy' | 'model' | undefined) ?? 'factor',
        name: t('research_copy_name_prefix', { name: copyFrom.name }).slice(0, 64),
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
        sharpe_floor: Number(cfg.sharpe_floor) || undefined,
        min_trades: Number(cfg.min_trades) || undefined,
        initial_cash: Number(cfg.initial_cash) || undefined,
      });
      return;
    }
    skipModeResetFor.current = initialMode ?? 'deep';
    form.setFieldsValue({ mode: initialMode ?? 'deep' });
  }, [open, copyFrom, initialMode, seedFactor, form, t]);

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

  // strategy / model 只有 deep 链路（quick 复用的是因子挖掘）：切场景时把 quick 修正为 deep
  useEffect(() => {
    if (scenario !== 'factor' && mode === 'quick') {
      form.setFieldsValue({ mode: 'deep' });
    }
  }, [scenario, mode, form]);

  const submit = async () => {
    setError(null);
    try {
      const values = await form.validateFields();
      // 预算估算仅提示（见上方 Alert），不再拦截提交：真实单次消耗常低于估算
      const [start, end] = values.window;
      const isStrategy = values.scenario === 'strategy';
      // 夏普/成交硬门是 strategy 与 model 共用的回测口径（wf 折均值）；单品种资金仅回测链路需要
      const needsBacktestGates = isStrategy || values.scenario === 'model';
      const payload: ResearchCreateParams = {
        mode: values.mode,
        scenario: values.scenario || 'factor',
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
        icir_floor: needsBacktestGates ? undefined : values.icir_floor,
        corr_threshold: needsBacktestGates ? undefined : values.corr_threshold,
        sharpe_floor: needsBacktestGates ? values.sharpe_floor : undefined,
        min_trades: needsBacktestGates ? values.min_trades : undefined,
        initial_cash: isStrategy ? values.initial_cash : undefined,
        seed_factor: seed || undefined,
      };
      setSubmitting(true);
      const res = await researchApi.create(payload);
      onCreated(res.session_id);
      form.resetFields();
      onClose();
    } catch (err) {
      // 表单校验错误已在字段下展示；接口错误单独提示
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      setError(err instanceof Error ? err.message : t('research_msg_create_failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      title={t('research_new_title')}
      open={open}
      onClose={onClose}
      // 表单字段多（场景/模式/硬门分组），用 large 抽屉宽度；窄屏收缩避免溢出
      width="min(736px, 92vw)"
      // antd v6：「destroyOnClose」已废弃，更名 destroyOnHidden
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          mode: 'deep',
          scenario: 'factor',
          symbols: DEFAULT_SYMBOLS,
          interval: '1h',
          candle_type: 'spot',
          window: [dayjs().subtract(180, 'day'), dayjs()],
        }}
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          {error && <Alert type="error" title={error} showIcon />}

          {seed && (
            <Alert
              type="info"
              showIcon
              closable
              onClose={() => setSeed(null)}
              title={t('research_seed_alert_title', { name: seed })}
              description={t('research_seed_alert_desc')}
            />
          )}

          <Form.Item name="scenario" label={t('research_field_scenario')}>
            <Radio.Group optionType="button" buttonStyle="solid">
              <Radio.Button value="factor">{t('research_scenario_factor_option')}</Radio.Button>
              <Radio.Button value="strategy">{t('research_scenario_strategy_option')}</Radio.Button>
              <Radio.Button value="model">{t('research_scenario_model_option')}</Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Form.Item name="mode" label={t('research_field_mode')}>
            <Radio.Group optionType="button" buttonStyle="solid">
              <Radio.Button value="deep">{t('research_mode_deep_option')}</Radio.Button>
              <Radio.Button value="quick" disabled={scenario !== 'factor'}>
                {t('research_mode_quick_option')}
              </Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Form.Item name="name" label={t('research_field_name')}>
            <Input placeholder={t('research_name_placeholder')} maxLength={64} />
          </Form.Item>

          <Form.Item
            name="symbols"
            label={t('research_field_symbols')}
            rules={[{ required: true, message: t('research_symbols_required') }]}
          >
            <Select mode="tags" tokenSeparators={[',', ' ']} options={DEFAULT_SYMBOLS.map((s) => ({ value: s, label: s }))} />
          </Form.Item>

          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item name="interval" label={t('research_field_interval')} style={{ flex: 1 }}>
              <Select options={INTERVALS.map((i) => ({ value: i, label: i }))} />
            </Form.Item>
            <Form.Item name="candle_type" label={t('research_field_market')} style={{ flex: 1 }}>
              <Select
                options={[
                  { value: 'spot', label: t('research_market_spot') },
                  { value: 'future', label: t('research_market_future') },
                ]}
              />
            </Form.Item>
          </Space>

          <Form.Item
            name="window"
            label={t('research_field_window')}
            rules={[
              { required: true, message: t('research_window_required') },
              {
                validator: (_, value: [Dayjs, Dayjs] | undefined) =>
                  !value || value[1].diff(value[0], 'day') >= 30
                    ? Promise.resolve()
                    : Promise.reject(new Error(t('research_window_min_days'))),
              },
            ]}
          >
            <DatePicker.RangePicker style={{ width: '100%' }} allowClear={false} />
          </Form.Item>

          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item name="n_candidates" label={t('research_field_candidates')} style={{ flex: 1 }}>
              <InputNumber min={1} max={10} style={{ width: '100%' }} />
            </Form.Item>
            {mode === 'deep' && (
              <Form.Item name="loop_n" label={t('research_field_loops')} style={{ flex: 1 }}>
                <InputNumber min={1} max={10} style={{ width: '100%' }} />
              </Form.Item>
            )}
          </Space>

          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item name="max_llm_calls" label={t('research_field_max_calls')} style={{ flex: 1 }}>
              <InputNumber min={1} max={500} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="max_tokens" label={t('research_field_max_tokens')} style={{ flex: 1 }}>
              <InputNumber min={12000} step={1000} style={{ width: '100%' }} />
            </Form.Item>
          </Space>

          {overBudget && (
            <Alert
              type="warning"
              showIcon
              title={t('research_budget_warning', { calls: estCalls, tokens: estTokens })}
            />
          )}

          {/* factor 才有 IC_IR/相关性硬门；strategy/model 场景是回测口径的夏普/成交，单品种资金仅回测需要 */}
          {scenario !== 'factor' ? (
            <Space size="middle" style={{ display: 'flex' }}>
              <Form.Item
                name="sharpe_floor"
                label={t('research_field_sharpe_floor')}
                style={{ flex: 1 }}
                tooltip={t('research_sharpe_floor_tooltip')}
              >
                <InputNumber min={-5} max={10} step={0.1} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="min_trades" label={t('research_field_min_trades')} style={{ flex: 1 }}>
                <InputNumber min={1} max={10000} style={{ width: '100%' }} />
              </Form.Item>
              {scenario === 'strategy' && (
                <Form.Item name="initial_cash" label={t('research_field_initial_cash')} style={{ flex: 1 }}>
                  <InputNumber min={1000} step={10000} style={{ width: '100%' }} />
                </Form.Item>
              )}
            </Space>
          ) : (
            mode === 'deep' && (
              <Space size="middle" style={{ display: 'flex' }}>
                <Form.Item name="icir_floor" label={t('research_field_icir_floor')} style={{ flex: 1 }}>
                  <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="corr_threshold" label={t('research_field_corr_threshold')} style={{ flex: 1 }}>
                  <InputNumber min={0.1} max={1} step={0.05} style={{ width: '100%' }} />
                </Form.Item>
              </Space>
            )
          )}

          <Space>
            <Button type="primary" loading={submitting} onClick={() => void submit()}>
              {t('research_start_btn')}
            </Button>
            <Button onClick={onClose}>{t('cancel')}</Button>
          </Space>
        </Space>
      </Form>
    </Drawer>
  );
};

export default ResearchNewDrawer;
