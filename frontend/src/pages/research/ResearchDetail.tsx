/**
 * 研究会话详情/运行状态（PRD §6.4 降级版，v0.3 独立页面 /research/:id）。
 * 只读 trial 流 + 运行事件面板 + 暂停/继续/取消/继续研究 + 采纳为因子；
 */
import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Descriptions,
  Drawer,
  Flex,
  Modal,
  Progress,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import PageContainer from '@/components/PageContainer';
import { usePolling } from '@/hooks/usePolling';
import { formatTokens } from '@/utils/format';
import {
  researchApi,
  type ResearchEvent,
  type ResearchGate,
  type ResearchReplayResult,
  type ResearchSession,
  type ResearchStatus,
  type ResearchTrial,
} from '@/api/research';

// 状态样式与文案：常量只存 i18n key，渲染时用 t() 取当前语言文案
const STATUS_META: Record<ResearchStatus, { color: string; i18nKey: string }> = {
  pending: { color: 'default', i18nKey: 'research_status_pending' },
  running: { color: 'processing', i18nKey: 'research_status_running' },
  paused: { color: 'warning', i18nKey: 'research_status_paused' },
  completed: { color: 'success', i18nKey: 'research_status_completed' },
  failed: { color: 'error', i18nKey: 'research_status_failed' },
  cancelled: { color: 'default', i18nKey: 'research_status_cancelled' },
};

const TERMINAL: ResearchStatus[] = ['completed', 'failed', 'cancelled'];
// 编排步骤同样只存 key，避免模块级常量把某种语言固化下来
const STEP_LABEL_KEYS = [
  '',
  'research_detail_step_hypothesis',
  'research_detail_step_experiment',
  'research_detail_step_code',
  'research_detail_step_evaluate',
  'research_detail_step_feedback',
  'research_detail_step_decision',
];

const fmt = (value: unknown, digits = 4): string =>
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';

const GateTag: React.FC<{ label: string; gate?: ResearchGate }> = ({ label, gate }) => {
  const { t } = useTranslation();
  if (!gate) return null;
  // unknown = 缺少对比数据（如续跑时没有持久化 corr），按未通过提示，不能显示成通过
  const unknown = gate.status === 'unknown';
  const color = unknown ? 'warning' : gate.pass ? 'success' : 'error';
  const text = unknown
    ? t('research_detail_gate_unknown')
    : gate.pass
      ? t('research_detail_gate_pass')
      : t('research_detail_gate_fail');
  return (
    <Tag color={color}>
      {label} {text}
    </Tag>
  );
};

type DiffLine = { type: 'same' | 'add' | 'del'; text: string };

/** 行级 LCS diff：对比视图只展示差异片段；代码通常 <200 行，O(n*m) 足够 */
const diffLines = (left: string[], right: string[]): DiffLine[] => {
  const n = left.length;
  const m = right.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      dp[i][j] =
        left[i] === right[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (left[i] === right[j]) {
      out.push({ type: 'same', text: left[i] });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ type: 'del', text: left[i] });
      i += 1;
    } else {
      out.push({ type: 'add', text: right[j] });
      j += 1;
    }
  }
  while (i < n) {
    out.push({ type: 'del', text: left[i] });
    i += 1;
  }
  while (j < m) {
    out.push({ type: 'add', text: right[j] });
    j += 1;
  }
  return out;
};

/** 对比面板：指标 / 三道硬门 / 成本并排，代码只渲染差异片段（基准为第一条） */
const ComparePanel: React.FC<{ trials: ResearchTrial[] }> = ({ trials }) => {
  const { t } = useTranslation();
  const base = trials[0];
  // PRD §6.7：quick 与 deep 同表，行按场景自适应——factor 有换手/覆盖率/多空收益，
  // strategy/model 有 Sharpe/回撤/胜率；某行所有 trial 都无值时不渲染（缺省口径见 PRD「—」）
  // label 存 i18n key，渲染时翻译；decision 行同样返回 key，交给列渲染统一翻译
  const metricRows = [
    {
      key: 'decision',
      label: 'research_detail_metric_decision',
      get: (tr: ResearchTrial) =>
        tr.decision == null
          ? 'research_detail_decision_pending'
          : tr.decision
            ? 'research_detail_decision_pass'
            : 'research_detail_decision_fail',
      i18nValue: true,
    },
    { key: 'ic_mean', label: 'research_detail_metric_ic_rankic', get: (tr: ResearchTrial) => tr.metrics?.ic_mean },
    { key: 'ic_ir', label: 'research_detail_metric_ic_ir', get: (tr: ResearchTrial) => tr.metrics?.ic_ir },
    { key: 'oos', label: 'research_detail_metric_oos', get: (tr: ResearchTrial) => tr.oos_flag },
    { key: 'sharpe', label: 'research_detail_metric_sharpe', get: (tr: ResearchTrial) => tr.metrics?.sharpe_ratio },
    {
      key: 'mdd',
      label: 'research_detail_metric_max_drawdown',
      get: (tr: ResearchTrial) => (tr.metrics as Record<string, unknown> | undefined)?.max_drawdown_pct,
    },
    { key: 'win_rate', label: 'research_detail_metric_win_rate', get: (tr: ResearchTrial) => (tr.metrics as Record<string, unknown> | undefined)?.win_rate },
    { key: 'turnover', label: 'research_detail_metric_turnover', get: (tr: ResearchTrial) => (tr.metrics as Record<string, unknown> | undefined)?.turnover },
    { key: 'coverage', label: 'research_detail_metric_coverage', get: (tr: ResearchTrial) => (tr.metrics as Record<string, unknown> | undefined)?.coverage },
    { key: 'ls_return', label: 'research_detail_metric_long_short', get: (tr: ResearchTrial) => (tr.metrics as Record<string, unknown> | undefined)?.long_short_return },
    { key: 'corr_sota', label: 'research_detail_metric_corr_sota', get: (tr: ResearchTrial) => tr.corr_sota },
    { key: 'corr_library', label: 'research_detail_metric_corr_library', get: (tr: ResearchTrial) => tr.corr_library },
    // 成本三行统一 ?? 0 兜底：candidates/planned 等未产生消费时显示 0 而非字面 "null"
    { key: 'token', label: 'research_detail_metric_token', get: (tr: ResearchTrial) => String(tr.token_used ?? 0) },
    { key: 'llm_calls', label: 'research_detail_metric_llm_calls', get: (tr: ResearchTrial) => String(tr.llm_calls ?? 0) },
    { key: 'duration', label: 'research_detail_metric_duration', get: (tr: ResearchTrial) => String(tr.duration_ms ?? 0) },
    { key: 'model', label: 'research_detail_metric_model', get: (tr: ResearchTrial) => tr.model || '—' },
  ].filter((row) =>
    // 全行无数据的指标不占位（如纯 strategy 会话没有 IC/换手）；get 返回原始值，null 才代表缺省
    trials.some((tr) => row.get(tr) != null),
  );
  // tag 为硬门短名（表格列头带「门」，GateTag 内只显示指标名）
  const gateRows = [
    { key: 'icir', label: 'research_detail_gate_icir_label', tag: 'research_detail_gate_icir_short', get: (tr: ResearchTrial) => tr.judge?.gates?.icir },
    { key: 'oos', label: 'research_detail_gate_oos_label', tag: 'research_detail_gate_oos_short', get: (tr: ResearchTrial) => tr.judge?.gates?.oos },
    { key: 'corr', label: 'research_detail_gate_corr_label', tag: 'research_detail_gate_corr_short', get: (tr: ResearchTrial) => tr.judge?.gates?.corr },
  ];
  type Row = {
    label: string;
    tag?: string;
    get: (tr: ResearchTrial) => unknown;
    i18nValue?: boolean;
  };
  const trialColumns = trials.map((tr, idx) => ({
    title: `#${tr.id}${idx === 0 ? t('research_detail_compare_baseline') : ''}`,
    key: `trial-${tr.id}`,
    render: (_: unknown, row: Row) => {
      const value = row.get(tr);
      // 硬门行返回 gate 对象：unknown 状态由 GateTag 显示为“无法判定”
      if (value && typeof value === 'object' && 'pass' in value) {
        return <GateTag label={t(row.tag ?? row.label)} gate={value as ResearchGate} />;
      }
      // decision 行返回的是 i18n key，其余行返回原始值
      if (row.i18nValue && typeof value === 'string') {
        return <Tag>{t(value)}</Tag>;
      }
      if (typeof value === 'number' && Number.isFinite(value)) return fmt(value);
      return String(value ?? '—');
    },
  }));

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Table
        size="small"
        pagination={false}
        rowKey="key"
        dataSource={metricRows}
        columns={[
          { title: t('research_detail_col_metric'), dataIndex: 'label', width: 120, render: (key: string) => t(key) },
          ...trialColumns,
        ]}
      />
      <Table
        size="small"
        pagination={false}
        rowKey="key"
        dataSource={gateRows}
        columns={[
          { title: t('research_detail_col_gate'), dataIndex: 'label', width: 120, render: (key: string) => t(key) },
          ...trialColumns,
        ]}
      />
      {trials.slice(1).map((tr) => {
        const changes = diffLines(
          (base.code || '').split('\n'),
          (tr.code || '').split('\n'),
        ).filter((line) => line.type !== 'same');
        return (
          <Card
            size="small"
            key={tr.id}
            title={t('research_detail_code_diff_title', { from: base.id, to: tr.id })}
          >
            {changes.length === 0 ? (
              <Tag color="success">{t('research_detail_code_identical')}</Tag>
            ) : (
              <pre style={{ margin: 0, maxHeight: 220, overflow: 'auto', fontSize: 12, lineHeight: 1.6 }}>
                {changes.map((line, idx) => (
                  <div
                    key={idx}
                    style={{
                      color: line.type === 'add' ? 'var(--tw-color-success)' : 'var(--tw-color-error)',
                      background: line.type === 'add'
                        ? 'color-mix(in srgb, var(--tw-color-success) 8%, var(--tw-color-background))'
                        : 'color-mix(in srgb, var(--tw-color-error) 8%, var(--tw-color-background))',
                    }}
                  >
                    {line.type === 'add' ? '+ ' : '- '}
                    {line.text}
                  </div>
                ))}
              </pre>
            )}
          </Card>
        );
      })}
    </Space>
  );
};

const ResearchDetail: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);
  const navigate = useNavigate();
  const { message, modal } = AntApp.useApp();

  const [detail, setDetail] = useState<ResearchSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [trial, setTrial] = useState<ResearchTrial | null>(null);
  // 回放结果：与原 trial 并排展示差异，不覆盖原记录（后端落 replay_of_id 新行）
  const [replayResult, setReplayResult] = useState<ResearchReplayResult | null>(null);
  const [replaying, setReplaying] = useState(false);
  // 对比：勾选 2–5 条，批量拉含代码的 trial 后弹窗并排展示
  const [selectedKeys, setSelectedKeys] = useState<number[]>([]);
  const [compareTrials, setCompareTrials] = useState<ResearchTrial[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [events, setEvents] = useState<ResearchEvent[]>([]);
  // 事件按 seq 增量拉取；用 ref 避免把 seq 放进 useCallback 依赖导致轮询重挂载
  const nextSeqRef = useRef(0);
  // 防并发重入：StrictMode 双 mount / tab 切回立即轮询 / 手动刷新都可能让两个 load 并发，
  // 它们带着同一个旧 nextSeqRef 各拉一批事件，导致同一 seq 被 append 两次（React key 重复警告）
  const loadBusyRef = useRef(false);
  // PRD §6.7：默认勾选（SOTA + 最新一轮）只初始化一次，不覆盖用户后续手动勾选
  const defaultPickRef = useRef(false);

  const load = useCallback(async () => {
    if (loadBusyRef.current) return;
    loadBusyRef.current = true;
    try {
      const data = await researchApi.get(sessionId);
      setDetail(data);
      if (!defaultPickRef.current && data.trials?.length) {
        defaultPickRef.current = true;
        const ids = data.trials.map((t) => t.id);
        const latest = Math.max(...ids);
        const best = data.best_trial_id;
        setSelectedKeys(
          best != null && ids.includes(best) && best !== latest ? [best, latest] : [latest],
        );
      }
      // 事件已持久化到 research_events：不再依赖 backend_job_id（多 worker/重启后依然可增量读）
      const page = await researchApi.events(sessionId, nextSeqRef.current);
      if (page.events.length > 0) {
        // 预算耗尽的全站级提醒已由 App 级研究 WS 桥（App.tsx ResearchEventBridge）弹出，
        // 这里只负责事件流展示，避免双弹
        nextSeqRef.current = page.next_seq;
        setEvents((prev) => [...prev, ...page.events].slice(-200));
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('research_detail_msg_load_failed'));
    } finally {
      loadBusyRef.current = false;
      setLoading(false);
    }
  }, [sessionId, message, t]);

  usePolling(load, {
    interval: 3000,
    enabled: Number.isFinite(sessionId) && (!detail || !TERMINAL.includes(detail.status)),
  });

  const refresh = () => {
    setLoading(true);
    void load();
  };

  const act = async (action: () => Promise<unknown>, okText: string) => {
    try {
      await action();
      message.success(okText);
      refresh();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('research_detail_msg_action_failed'));
    }
  };

  const openTrial = async (row: ResearchTrial) => {
    if (row.code) {
      setTrial(row);
      return;
    }
    try {
      setTrial(await researchApi.getTrial(sessionId, row.id));
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('research_detail_msg_trial_load_failed'));
    }
  };

  const promote = async (row: ResearchTrial) => {
    try {
      const res = await researchApi.promote(sessionId, row.id);
      message.success(t('research_detail_msg_promoted', { name: res.factor_name }));
      setTrial((prev) =>
        prev && prev.id === row.id ? { ...prev, promoted_factor_name: res.factor_name } : prev,
      );
      void load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('research_detail_msg_promote_failed'));
    }
  };

  const replay = async (row: ResearchTrial) => {
    setReplaying(true);
    try {
      const res = await researchApi.replay(sessionId, row.id);
      setReplayResult(res);
      message.success(
        res.replay_meta.partial
          ? t('research_detail_msg_replay_partial')
          : t('research_detail_msg_replay_done'),
      );
      void load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('research_detail_msg_replay_failed'));
    } finally {
      setReplaying(false);
    }
  };

  const openCompare = async () => {
    setComparing(true);
    try {
      // 列表接口不保证带 code，对比需要 diff，统一从批量接口取
      const res = await researchApi.batchTrials(sessionId, selectedKeys);
      setCompareTrials(res.trials);
      setCompareOpen(true);
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('research_detail_msg_batch_failed'));
    } finally {
      setComparing(false);
    }
  };

  const columns: ColumnsType<ResearchTrial> = [
    {
      title: t('research_detail_col_round'),
      width: 110,
      render: (_, row) =>
        // 回放行固定 loop_idx=0，不占用正常轮次编号，这里直接标“回放”
        row.replay_of_id
          ? t('research_detail_row_replay', { id: row.id })
          : detail?.mode === 'quick'
            ? t('research_detail_row_quick_round', { idx: row.candidate_idx })
            : t('research_detail_row_loop_round', { idx: row.loop_idx }),
    },
    {
      title: t('status'),
      dataIndex: 'status',
      width: 100,
      render: (status: string) => <Tag>{status}</Tag>,
    },
    {
      title: t('research_detail_col_hypothesis'),
      dataIndex: 'hypothesis',
      ellipsis: true,
      render: (text: string | null) => text || '—',
    },
    { title: 'IC', width: 90, render: (_, row) => fmt(row.metrics?.ic_mean) },
    { title: 'IC_IR', width: 90, render: (_, row) => fmt(row.metrics?.ic_ir) },
    {
      title: 'OOS',
      dataIndex: 'oos_flag',
      width: 80,
      render: (flag: string | null) => flag || '—',
    },
    {
      title: t('research_detail_col_decision'),
      width: 100,
      render: (_, row) =>
        row.decision == null ? (
          <Tag>{t('research_detail_decision_pending')}</Tag>
        ) : row.decision ? (
          <Tag color="success">{t('research_detail_decision_pass')}</Tag>
        ) : (
          <Tag color="error">{t('research_detail_decision_fail')}</Tag>
        ),
    },
    {
      title: t('research_detail_col_exception'),
      dataIndex: 'exception',
      ellipsis: true,
      render: (text: string | null) => text || '—',
    },
    {
      title: t('action'),
      width: 90,
      render: (_, row) => (
        <Button size="small" onClick={() => void openTrial(row)}>
          {t('research_detail_btn_detail')}
        </Button>
      ),
    },
  ];

  const statusMeta = detail ? STATUS_META[detail.status] : null;
  const isDeep = detail?.mode === 'deep';
  const tokenPercent =
    detail?.max_tokens && detail.max_tokens > 0
      ? Math.min(100, Math.round((detail.token_used / detail.max_tokens) * 100))
      : 0;

  // 回放对比行：原 trial / 回放 trial / 差异并排，corr(SOTA) 标记为不可重算
  const replayRows = (() => {
    if (!replayResult) return [];
    const o = replayResult.original;
    const n = replayResult.trial;
    const meta = replayResult.replay_meta;
    const diffText = (value: number | null | undefined) =>
      value == null ? '—' : value.toExponential(2);
    return [
      {
        key: 'ic_ir',
        label: t('research_detail_metric_ic_ir'),
        original: fmt(o.metrics?.ic_ir),
        replay: fmt(n.metrics?.ic_ir),
        diff: diffText(meta.diff.ic_ir),
      },
      {
        key: 'ic_mean',
        label: t('research_detail_metric_ic'),
        original: fmt(o.metrics?.ic_mean),
        replay: fmt(n.metrics?.ic_mean),
        diff: '—',
      },
      {
        key: 'oos',
        label: t('research_detail_metric_oos'),
        original: o.oos_flag || '—',
        replay: n.oos_flag || '—',
        diff: meta.diff.oos_changed
          ? t('research_detail_diff_changed')
          : t('research_detail_diff_same'),
      },
      {
        key: 'corr_library',
        label: t('research_detail_metric_corr_library'),
        original: fmt(o.corr_library),
        replay: fmt(n.corr_library),
        diff: diffText(meta.diff.corr_library),
      },
      {
        key: 'corr_sota',
        label: t('research_detail_metric_corr_sota'),
        original: fmt(o.corr_sota),
        replay: meta.unreproducible.includes('corr_sota')
          ? t('research_detail_diff_unreproducible')
          : fmt(n.corr_sota),
        diff: '—',
      },
      {
        key: 'cost',
        label: t('research_detail_metric_token_calls'),
        original: `${o.token_used} / ${o.llm_calls}`,
        replay: `${n.token_used} / ${n.llm_calls}`,
        diff: '—',
      },
    ];
  })();

  return (
    <PageContainer
      title={detail?.name || t('research_detail_page_title', { id: sessionId })}
    >
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
        <Flex align="center" justify="space-between" wrap gap={8}>
          <Space size="small" wrap>
            <Button onClick={() => navigate('/research')}>
              {t('research_detail_back_to_list')}
            </Button>
            <Typography.Title level={5} style={{ margin: 0 }}>
              {detail?.name || t('research_detail_session_title', { id: sessionId })}
            </Typography.Title>
            {detail && (
              <Tag color={statusMeta?.color}>
                {[
                  statusMeta ? t(statusMeta.i18nKey) : null,
                  // 排队位次：仅 pending 且后端返回序号时展示
                  detail.status === 'pending' && detail.queue_position
                    ? t('research_queue_position', { pos: detail.queue_position })
                    : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </Tag>
            )}
            {detail && (
              <Tag color={detail.scenario === 'strategy' ? 'geekblue' : detail.scenario === 'model' ? 'purple' : 'cyan'}>
                {detail.scenario === 'strategy'
                  ? t('research_detail_scenario_strategy')
                  : detail.scenario === 'model'
                    ? t('research_detail_scenario_model')
                    : t('research_detail_scenario_factor')}
              </Tag>
            )}
            {detail && (
              <Tag>
                {detail.mode === 'quick'
                  ? t('research_mode_quick')
                  : t('research_mode_deep')}
              </Tag>
            )}
            {detail?.extended_at && (
              <Tag color="blue">
                {t('research_detail_tag_extended', {
                  time: new Date(detail.extended_at).toLocaleString(),
                })}
              </Tag>
            )}
          </Space>
          <Space wrap>
            <Button loading={loading} onClick={refresh}>
              {t('refresh')}
            </Button>
            {/* quick 是一次性批量调用，后端明确拒绝 pause（409），前端不展示入口 */}
            {isDeep && detail?.status === 'running' && (
              <Button
                onClick={() =>
                  void act(() => researchApi.pause(sessionId), t('research_msg_pause_requested'))
                }
              >
                {t('research_action_pause')}
              </Button>
            )}
            {detail?.status === 'paused' && (
              <Button
                type="primary"
                onClick={() =>
                  void act(() => researchApi.resume(sessionId), t('research_msg_resumed'))
                }
              >
                {t('research_action_resume')}
              </Button>
            )}
            {detail && ['pending', 'running', 'paused'].includes(detail.status) && (
              <Button
                danger
                onClick={() =>
                  modal.confirm({
                    title: t('research_detail_cancel_title'),
                    content: t('research_detail_cancel_content'),
                    okText: t('research_detail_cancel_ok'),
                    cancelText: t('research_detail_cancel_abort'),
                    onOk: () => act(() => researchApi.cancel(sessionId), t('research_msg_cancelled')),
                  })
                }
              >
                {t('cancel')}
              </Button>
            )}
            {detail?.status === 'completed' && (
              <Button
                onClick={() =>
                  modal.confirm({
                    title: t('research_action_extend'),
                    content:
                      detail.mode === 'quick'
                        ? t('research_detail_extend_content_quick')
                        : t('research_detail_extend_content_deep'),
                    okText: t('research_detail_extend_ok'),
                    cancelText: t('cancel'),
                    onOk: () =>
                      act(
                        () => researchApi.extend(sessionId, { extra_loops: 2 }),
                        t('research_msg_extended', { n: 2 }),
                      ),
                  })
                }
              >
                {t('research_action_extend')}
              </Button>
            )}
          </Space>
        </Flex>

        {detail?.error && <Alert type="error" showIcon title={detail.error} />}

        <Card size="small" title={t('research_detail_card_status')}>
          <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
            <Space size="large" wrap>
              <span>
                {t('research_detail_loop_progress', {
                  done: detail?.loop_done ?? 0,
                  total: detail?.loop_n ?? '—',
                })}
                {isDeep && detail?.step_idx
                  ? `${t('research_detail_current_step', {
                      step: STEP_LABEL_KEYS[detail.step_idx]
                        ? t(STEP_LABEL_KEYS[detail.step_idx])
                        : '—',
                    })}`
                  : ''}
              </span>
              <span>
                {t('research_detail_llm_usage', {
                  used: detail?.llm_calls ?? 0,
                  max: detail?.max_llm_calls ?? '—',
                })}
              </span>
              <span>{t('research_detail_best_icir', { value: fmt(detail?.best_ic_ir) })}</span>
              {/* token 进度圆圈与统计文字同行内嵌：数值不占版面，悬停圆圈看详细用量 */}
              <Flex gap="small" align="center">
                <span>{t('research_detail_token_label')}</span>
                <Tooltip
                  title={t('research_detail_token_tooltip', {
                    used: formatTokens(detail?.token_used, '0'),
                    max: formatTokens(detail?.max_tokens, '—'),
                    rawUsed: detail?.token_used ?? 0,
                    rawMax: detail?.max_tokens ?? '—',
                  })}
                >
                  <Progress
                    type="circle"
                    size={32}
                    percent={tokenPercent}
                    status={detail?.status === 'running' ? 'active' : undefined}
                    // 用量分档变色：<60% 默认蓝，60-84% 橙色预警，>=85% 红色告警
                    strokeColor={tokenPercent >= 85 ? 'var(--tw-color-error)' : tokenPercent >= 60 ? 'var(--tw-color-warning)' : undefined}
                    format={() => ''}
                  />
                </Tooltip>
              </Flex>
            </Space>
            {detail && (
              <Descriptions size="small" column={3}>
                <Descriptions.Item label={t('research_detail_field_symbol')}>
                  {(detail.config.symbols as string[] | undefined)?.join(', ') || '—'}
                </Descriptions.Item>
                <Descriptions.Item label={t('research_detail_field_interval')}>
                  {String(detail.config.interval ?? '—')}
                </Descriptions.Item>
                <Descriptions.Item label={t('research_detail_field_market')}>
                  {String(detail.config.candle_type ?? '—')}
                </Descriptions.Item>
                <Descriptions.Item label={t('research_detail_field_window')}>
                  {String(detail.config.start ?? '')} ~ {String(detail.config.end ?? '')}
                </Descriptions.Item>
                <Descriptions.Item label={t('research_detail_field_candidates')}>
                  {detail.n_candidates}
                </Descriptions.Item>
                <Descriptions.Item label={t('research_detail_field_gate')}>
                  {t('research_detail_gate_rule', {
                    icir: String(detail.config.icir_floor ?? '—'),
                    corr: String(detail.config.corr_threshold ?? '—'),
                  })}
                </Descriptions.Item>
              </Descriptions>
            )}
          </Space>
        </Card>

        <Flex justify="space-between" align="center" wrap gap={8}>
          <Typography.Text type="secondary">{t('research_detail_compare_hint')}</Typography.Text>
          <Button
            type="primary"
            ghost
            loading={comparing}
            disabled={selectedKeys.length < 2 || selectedKeys.length > 5}
            onClick={() => void openCompare()}
          >
            {t('research_detail_compare_btn', { n: selectedKeys.length })}
          </Button>
        </Flex>

        <Table<ResearchTrial>
          rowKey="id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={[...(detail?.trials ?? [])].sort((a, b) => b.id - a.id)}
          pagination={{ pageSize: 20, hideOnSinglePage: true }}
          locale={{ emptyText: t('research_detail_empty_trials') }}
          rowSelection={{
            selectedRowKeys: selectedKeys,
            onChange: (keys) => setSelectedKeys(keys as number[]),
            // 最多 5 条：达到上限后未选中的行禁用，避免提交后才被后端 422
            getCheckboxProps: (row) => ({
              disabled: selectedKeys.length >= 5 && !selectedKeys.includes(row.id),
            }),
          }}
        />

        <Card
          size="small"
          title={t('research_detail_card_events')}
          extra={
            <Typography.Text type="secondary">
              {t('research_detail_events_meta', { seq: nextSeqRef.current })}
            </Typography.Text>
          }
        >
          {events.length === 0 ? (
            <Typography.Text type="secondary">{t('research_detail_events_empty')}</Typography.Text>
          ) : (
            <div style={{ maxHeight: 220, overflow: 'auto', fontSize: 12, lineHeight: 1.8 }}>
              {events.map((evt) => (
                <div key={evt.seq}>
                  <Typography.Text type="secondary">
                    {new Date(evt.ts * 1000).toLocaleTimeString()}#{evt.seq}
                  </Typography.Text>{' '}
                  <Tag>{evt.stage}</Tag>
                  {evt.msg}
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* 试验详情从页面内嵌 Card 改为右侧抽屉，宽度与因子库详情抽屉一致（68%） */}
        <Drawer
          open={!!trial}
          size="68%"
          title={trial ? t('research_detail_trial_title', { id: trial.id }) : ''}
          onClose={() => setTrial(null)}
          destroyOnHidden // antd v6：「destroyOnClose」已废弃
          extra={
            trial && (
              <Space>
                {trial.code && !trial.replay_of_id && (
                  <Button loading={replaying} onClick={() => void replay(trial)}>
                    {t('research_detail_btn_replay')}
                  </Button>
                )}
                {trial.promoted_factor_name ? (
                  <Tag color="success">
                    {t('research_detail_tag_promoted', { name: trial.promoted_factor_name })}
                  </Tag>
                ) : (
                  trial.code && (
                    <Button
                      type="primary"
                      onClick={() =>
                        modal.confirm({
                          title: t('research_detail_promote'),
                          content: t('research_detail_promote_content', { id: trial.id }),
                          okText: t('research_detail_promote_ok'),
                          cancelText: t('cancel'),
                          onOk: () => promote(trial),
                        })
                      }
                    >
                      {t('research_detail_promote')}
                    </Button>
                  )
                )}
              </Space>
            )
          }
        >
          {trial && (
            <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
              <Typography.Paragraph style={{ margin: 0 }}>
                {t('research_detail_hypothesis_line', { text: trial.hypothesis || '—' })}
              </Typography.Paragraph>
              {trial.hypothesis_reason && (
                <Typography.Paragraph style={{ margin: 0 }}>
                  {t('research_detail_reason_line', { text: trial.hypothesis_reason })}
                </Typography.Paragraph>
              )}
              {trial.hypothesis_prediction && (
                <Typography.Paragraph style={{ margin: 0 }}>
                  {t('research_detail_prediction_line', { text: trial.hypothesis_prediction })}
                </Typography.Paragraph>
              )}
              {trial.task && (
                <Typography.Paragraph style={{ margin: 0 }}>
                  {t('research_detail_task_line', {
                    name: trial.task.name || '',
                    description: trial.task.description || '',
                  })}
                </Typography.Paragraph>
              )}
              {trial.judge && (
                <Space wrap>
                  {/* gates 按模式不同：deep 有三门，quick 只有冗余门，全部可选读取 */}
                  <GateTag
                    label={t('research_detail_gate_icir_short')}
                    gate={trial.judge.gates?.icir}
                  />
                  <GateTag
                    label={t('research_detail_gate_oos_short')}
                    gate={trial.judge.gates?.oos}
                  />
                  <GateTag
                    label={t('research_detail_gate_corr_short')}
                    gate={trial.judge.gates?.corr}
                  />
                  <GateTag
                    label={t('research_detail_gate_redundant')}
                    gate={trial.judge.gates?.redundant}
                  />
                  <Typography.Text type="secondary">{trial.judge.reason}</Typography.Text>
                </Space>
              )}
              {trial.oos_note && <Alert type="info" showIcon title={trial.oos_note} />}
              {trial.exception && <Alert type="error" showIcon title={trial.exception} />}
              <Typography.Text type="secondary">
                {t('research_detail_metrics_label')}
                {trial.model
                  ? `${t('research_detail_meta_model', { model: trial.model })}`
                  : ''}
                {trial.temperature != null
                  ? `${t('research_detail_meta_temperature', { value: trial.temperature })}`
                  : ''}
                {trial.duration_ms
                  ? `${t('research_detail_meta_duration', { ms: trial.duration_ms })}`
                  : ''}
                {trial.prompt_hash
                  ? `${t('research_detail_meta_prompt', { hash: trial.prompt_hash })}`
                  : ''}
                {trial.corr_sota != null
                  ? `${t('research_detail_meta_corr_sota', { value: fmt(trial.corr_sota) })}`
                  : ''}
                {trial.corr_library != null
                  ? `${t('research_detail_meta_corr_library', { value: fmt(trial.corr_library) })}`
                  : ''}
              </Typography.Text>
              <pre style={{ margin: 0, maxHeight: 240, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(trial.metrics ?? {}, null, 2)}
              </pre>
              {trial.metrics_oos && Object.keys(trial.metrics_oos).length > 0 && (
                <>
                  <Typography.Text type="secondary">
                    {t('research_detail_metrics_oos')}
                  </Typography.Text>
                  <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                    {JSON.stringify(trial.metrics_oos, null, 2)}
                  </pre>
                </>
              )}
              <Typography.Text type="secondary">{t('research_detail_code')}</Typography.Text>
              <pre style={{ margin: 0, maxHeight: 320, overflow: 'auto', fontSize: 12 }}>
                {trial.code || t('research_detail_code_empty')}
              </pre>
            </Space>
          )}
        </Drawer>

        {replayResult && (
          <Card
            size="small"
            title={t('research_detail_replay_title', {
              orig: replayResult.original.id,
              replay: replayResult.trial.id,
            })}
            extra={
              <Tag
                color={
                  replayResult.replay_meta.partial
                    ? 'warning'
                    : replayResult.replay_meta.consistent
                      ? 'success'
                      : 'error'
                }
              >
                {replayResult.replay_meta.partial
                  ? t('research_detail_replay_partial')
                  : replayResult.replay_meta.consistent
                    ? t('research_detail_replay_consistent')
                    : t('research_detail_replay_diff')}
              </Tag>
            }
          >
            <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
              {replayResult.replay_meta.partial && (
                <Alert
                  type="warning"
                  showIcon
                  title={t('research_detail_replay_missing', {
                    missing: replayResult.replay_meta.missing.join(', '),
                  })}
                />
              )}
              <Table
                size="small"
                pagination={false}
                rowKey="key"
                dataSource={replayRows}
                columns={[
                  { title: t('research_detail_col_metric'), dataIndex: 'label', width: 140 },
                  {
                    title: t('research_detail_col_original_trial', {
                      id: replayResult.original.id,
                    }),
                    dataIndex: 'original',
                  },
                  {
                    title: t('research_detail_row_replay', { id: replayResult.trial.id }),
                    dataIndex: 'replay',
                  },
                  { title: t('research_detail_col_diff'), dataIndex: 'diff' },
                ]}
              />
              <Typography.Text type="secondary">
                {t('research_detail_replay_criteria', {
                  tol: replayResult.replay_meta.tolerance.ic_ir,
                })}
                {replayResult.replay_meta.unreproducible.includes('corr_sota')
                  ? ` ${t('research_detail_replay_criteria_corr_note')}`
                  : ''}
              </Typography.Text>
              {replayResult.original.judge && (
                <Typography.Text type="secondary">
                  {t('research_detail_original_judge_reason', {
                    reason: replayResult.original.judge.reason || '—',
                  })}
                </Typography.Text>
              )}
              {replayResult.replay_meta.notes.length > 0 && (
                <Typography.Text type="secondary">
                  {t('research_detail_replay_notes', {
                    notes: replayResult.replay_meta.notes.join('；'),
                  })}
                </Typography.Text>
              )}
            </Space>
          </Card>
        )}

        <Modal
          open={compareOpen}
          title={t('research_detail_compare_title', { n: compareTrials.length })}
          footer={null}
          width={980}
          onCancel={() => setCompareOpen(false)}
        >
          {compareTrials.length > 0 && <ComparePanel trials={compareTrials} />}
        </Modal>
      </Space>
    </PageContainer>
  );
};

export default ResearchDetail;
