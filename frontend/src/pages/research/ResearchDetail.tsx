/**
 * 研究会话详情/运行状态（PRD §6.4 降级版，v0.3 独立页面 /research/:id）。
 * 只读 trial 流 + 运行事件面板 + 暂停/继续/取消/继续研究 + 采纳为因子；
 */
import { useCallback, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Descriptions,
  Flex,
  Progress,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import PageContainer from '@/components/PageContainer';
import { usePolling } from '@/hooks/usePolling';
import {
  researchApi,
  type ResearchEvent,
  type ResearchGate,
  type ResearchReplayResult,
  type ResearchSession,
  type ResearchStatus,
  type ResearchTrial,
} from '@/api/research';

const STATUS_META: Record<ResearchStatus, { color: string; label: string }> = {
  pending: { color: 'default', label: '排队中' },
  running: { color: 'processing', label: '运行中' },
  paused: { color: 'warning', label: '已暂停' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
  cancelled: { color: 'default', label: '已取消' },
};

const TERMINAL: ResearchStatus[] = ['completed', 'failed', 'cancelled'];
const STEP_LABELS = ['', '提出假设', '规划实验', '生成代码', '评估', '结构化反馈', '记录决策'];

const fmt = (value: unknown, digits = 4): string =>
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';

const GateTag: React.FC<{ label: string; gate?: ResearchGate }> = ({ label, gate }) => {
  if (!gate) return null;
  // unknown = 缺少对比数据（如续跑时没有持久化 corr），按未通过提示，不能显示成通过
  const unknown = gate.status === 'unknown';
  const color = unknown ? 'warning' : gate.pass ? 'success' : 'error';
  const text = unknown ? '无法判定' : gate.pass ? '通过' : '未过';
  return (
    <Tag color={color}>
      {label} {text}
    </Tag>
  );
};

const ResearchDetail: React.FC = () => {
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
  const [events, setEvents] = useState<ResearchEvent[]>([]);
  // 事件按 seq 增量拉取；用 ref 避免把 seq 放进 useCallback 依赖导致轮询重挂载
  const nextSeqRef = useRef(0);

  const load = useCallback(async () => {
    try {
      const data = await researchApi.get(sessionId);
      setDetail(data);
      // 事件已持久化到 research_events：不再依赖 backend_job_id（多 worker/重启后依然可增量读）
      const page = await researchApi.events(sessionId, nextSeqRef.current);
      if (page.events.length > 0) {
        nextSeqRef.current = page.next_seq;
        setEvents((prev) => [...prev, ...page.events].slice(-200));
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '会话加载失败');
    } finally {
      setLoading(false);
    }
  }, [sessionId, message]);

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
      message.error(err instanceof Error ? err.message : '操作失败');
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
      message.error(err instanceof Error ? err.message : '试验详情加载失败');
    }
  };

  const promote = async (row: ResearchTrial) => {
    try {
      const res = await researchApi.promote(sessionId, row.id);
      message.success(`已采纳为因子 ${res.factor_name}`);
      setTrial((prev) =>
        prev && prev.id === row.id ? { ...prev, promoted_factor_name: res.factor_name } : prev,
      );
      void load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '采纳失败');
    }
  };

  const replay = async (row: ResearchTrial) => {
    setReplaying(true);
    try {
      const res = await researchApi.replay(sessionId, row.id);
      setReplayResult(res);
      message.success(res.replay_meta.partial ? '回放完成（部分复现）' : '回放完成');
      void load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '回放失败');
    } finally {
      setReplaying(false);
    }
  };

  const columns: ColumnsType<ResearchTrial> = [
    {
      title: '轮次/候选',
      width: 110,
      render: (_, row) =>
        // 回放行固定 loop_idx=0，不占用正常轮次编号，这里直接标“回放”
        row.replay_of_id
          ? `回放 #${row.id}`
          : detail?.mode === 'quick'
            ? `第 1 轮 #${row.candidate_idx}`
            : `第 ${row.loop_idx} 轮`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: string) => <Tag>{status}</Tag>,
    },
    {
      title: '假设',
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
      title: '决策',
      width: 100,
      render: (_, row) =>
        row.decision == null ? (
          <Tag>待人工</Tag>
        ) : row.decision ? (
          <Tag color="success">通过</Tag>
        ) : (
          <Tag color="error">未通过</Tag>
        ),
    },
    {
      title: '异常',
      dataIndex: 'exception',
      ellipsis: true,
      render: (text: string | null) => text || '—',
    },
    {
      title: '操作',
      width: 90,
      render: (_, row) => (
        <Button size="small" onClick={() => void openTrial(row)}>
          详情
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
        label: 'IC_IR',
        original: fmt(o.metrics?.ic_ir),
        replay: fmt(n.metrics?.ic_ir),
        diff: diffText(meta.diff.ic_ir),
      },
      {
        key: 'ic_mean',
        label: 'IC',
        original: fmt(o.metrics?.ic_mean),
        replay: fmt(n.metrics?.ic_mean),
        diff: '—',
      },
      {
        key: 'oos',
        label: '样本外',
        original: o.oos_flag || '—',
        replay: n.oos_flag || '—',
        diff: meta.diff.oos_changed ? '变化' : '一致',
      },
      {
        key: 'corr_library',
        label: 'corr(因子库)',
        original: fmt(o.corr_library),
        replay: fmt(n.corr_library),
        diff: diffText(meta.diff.corr_library),
      },
      {
        key: 'corr_sota',
        label: 'corr(SOTA)',
        original: fmt(o.corr_sota),
        replay: meta.unreproducible.includes('corr_sota') ? '不可重算' : fmt(n.corr_sota),
        diff: '—',
      },
      {
        key: 'cost',
        label: 'Token / 调用',
        original: `${o.token_used} / ${o.llm_calls}`,
        replay: `${n.token_used} / ${n.llm_calls}`,
        diff: '—',
      },
    ];
  })();

  return (
    <PageContainer title={detail?.name || `研究会话 #${sessionId}`}>
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
        <Flex align="center" justify="space-between" wrap gap={8}>
          <Space size="small" wrap>
            <Button onClick={() => navigate('/research')}>返回列表</Button>
            <Typography.Title level={5} style={{ margin: 0 }}>
              {detail?.name || `会话 #${sessionId}`}
            </Typography.Title>
            {detail && <Tag color={statusMeta?.color}>{statusMeta?.label}</Tag>}
            {detail && <Tag>{detail.mode === 'quick' ? '快速验证' : '深度研究'}</Tag>}
            {detail?.extended_at && (
              <Tag color="blue">已追加 {new Date(detail.extended_at).toLocaleString()}</Tag>
            )}
          </Space>
          <Space wrap>
            <Button loading={loading} onClick={refresh}>
              刷新
            </Button>
            {/* quick 是一次性批量调用，后端明确拒绝 pause（409），前端不展示入口 */}
            {isDeep && detail?.status === 'running' && (
              <Button onClick={() => void act(() => researchApi.pause(sessionId), '已请求暂停')}>
                暂停
              </Button>
            )}
            {detail?.status === 'paused' && (
              <Button
                type="primary"
                onClick={() => void act(() => researchApi.resume(sessionId), '已继续研究')}
              >
                继续
              </Button>
            )}
            {detail && ['pending', 'running', 'paused'].includes(detail.status) && (
              <Button
                danger
                onClick={() =>
                  modal.confirm({
                    title: '取消研究会话',
                    content: '取消后当前进度保留，但不会继续执行。',
                    okText: '确认取消',
                    cancelText: '再想想',
                    onOk: () => act(() => researchApi.cancel(sessionId), '已取消'),
                  })
                }
              >
                取消
              </Button>
            )}
            {detail?.status === 'completed' && (
              <Button
                onClick={() =>
                  modal.confirm({
                    title: '继续研究',
                    content:
                      detail.mode === 'quick'
                        ? 'quick 会话追加的轮次会按深度研究编排，并从当前最佳候选接续。追加 2 轮与 10 次调用预算。'
                        : '追加 2 轮研究与 10 次 LLM 调用预算。',
                    okText: '追加',
                    cancelText: '取消',
                    onOk: () =>
                      act(() => researchApi.extend(sessionId, { extra_loops: 2 }), '已追加轮次'),
                  })
                }
              >
                继续研究
              </Button>
            )}
          </Space>
        </Flex>

        {detail?.error && <Alert type="error" showIcon message={detail.error} />}

        <Card size="small" title="运行状态">
          <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
            <Space size="large" wrap>
              <span>
                进度：{detail?.loop_done ?? 0}/{detail?.loop_n ?? '—'} 轮
                {isDeep && detail?.step_idx ? `　当前步骤：${STEP_LABELS[detail.step_idx] || '—'}` : ''}
              </span>
              <span>
                LLM 调用（已用 / 上限）：{detail?.llm_calls ?? 0} / {detail?.max_llm_calls ?? '—'}
              </span>
              <span>最优 IC_IR：{fmt(detail?.best_ic_ir)}</span>
            </Space>
            <Progress
              percent={tokenPercent}
              status={detail?.status === 'running' ? 'active' : undefined}
              format={() => `Token 已用 / 上限：${detail?.token_used ?? 0} / ${detail?.max_tokens ?? '—'}`}
            />
            {detail && (
              <Descriptions size="small" column={3}>
                <Descriptions.Item label="品种">
                  {(detail.config.symbols as string[] | undefined)?.join(', ') || '—'}
                </Descriptions.Item>
                <Descriptions.Item label="周期">
                  {String(detail.config.interval ?? '—')}
                </Descriptions.Item>
                <Descriptions.Item label="市场">
                  {String(detail.config.candle_type ?? '—')}
                </Descriptions.Item>
                <Descriptions.Item label="窗口">
                  {String(detail.config.start ?? '')} ~ {String(detail.config.end ?? '')}
                </Descriptions.Item>
                <Descriptions.Item label="候选数">{detail.n_candidates}</Descriptions.Item>
                <Descriptions.Item label="硬门">
                  IC_IR ≥ {String(detail.config.icir_floor ?? '—')}，|corr| &lt;{' '}
                  {String(detail.config.corr_threshold ?? '—')}
                </Descriptions.Item>
              </Descriptions>
            )}
          </Space>
        </Card>

        <Table<ResearchTrial>
          rowKey="id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={[...(detail?.trials ?? [])].sort((a, b) => b.id - a.id)}
          pagination={{ pageSize: 20, hideOnSinglePage: true }}
          locale={{ emptyText: '暂无试验记录' }}
        />

        <Card
          size="small"
          title="运行事件"
          extra={
            <Typography.Text type="secondary">
              seq ≤ {nextSeqRef.current}　事件已持久化，多 worker/重启后仍可增量读取
            </Typography.Text>
          }
        >
          {events.length === 0 ? (
            <Typography.Text type="secondary">暂无事件（研究开始后会逐步写入）</Typography.Text>
          ) : (
            <div style={{ maxHeight: 220, overflow: 'auto', fontSize: 12, lineHeight: 1.8 }}>
              {events.map((evt) => (
                <div key={evt.seq}>
                  <Typography.Text type="secondary">
                    {new Date(evt.ts * 1000).toLocaleTimeString()}　#{evt.seq}
                  </Typography.Text>{' '}
                  <Tag>{evt.stage}</Tag>
                  {evt.msg}
                </div>
              ))}
            </div>
          )}
        </Card>

        {trial && (
          <Card
            size="small"
            title={`试验 #${trial.id} 详情`}
            extra={
              <Space>
                {trial.code && !trial.replay_of_id && (
                  <Button loading={replaying} onClick={() => void replay(trial)}>
                    回放
                  </Button>
                )}
                {trial.promoted_factor_name ? (
                  <Tag color="success">已采纳：{trial.promoted_factor_name}</Tag>
                ) : (
                  trial.code && (
                    <Button
                      type="primary"
                      onClick={() =>
                        modal.confirm({
                          title: '采纳为因子',
                          content: `把试验 #${trial.id} 的代码写入因子库（重复采纳幂等）。`,
                          okText: '采纳',
                          cancelText: '取消',
                          onOk: () => promote(trial),
                        })
                      }
                    >
                      采纳为因子
                    </Button>
                  )
                )}
                <Button onClick={() => setTrial(null)}>关闭</Button>
              </Space>
            }
          >
            <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
              <Typography.Paragraph style={{ margin: 0 }}>
                假设：{trial.hypothesis || '—'}
              </Typography.Paragraph>
              {trial.hypothesis_reason && (
                <Typography.Paragraph style={{ margin: 0 }}>
                  理由：{trial.hypothesis_reason}
                </Typography.Paragraph>
              )}
              {trial.hypothesis_prediction && (
                <Typography.Paragraph style={{ margin: 0 }}>
                  预测：{trial.hypothesis_prediction}
                </Typography.Paragraph>
              )}
              {trial.task && (
                <Typography.Paragraph style={{ margin: 0 }}>
                  任务：{trial.task.name || ''} {trial.task.description || ''}
                </Typography.Paragraph>
              )}
              {trial.judge && (
                <Space wrap>
                  {/* gates 按模式不同：deep 有三门，quick 只有冗余门，全部可选读取 */}
                  <GateTag label="IC_IR" gate={trial.judge.gates?.icir} />
                  <GateTag label="样本外" gate={trial.judge.gates?.oos} />
                  <GateTag label="相关性" gate={trial.judge.gates?.corr} />
                  <GateTag label="冗余" gate={trial.judge.gates?.redundant} />
                  <Typography.Text type="secondary">{trial.judge.reason}</Typography.Text>
                </Space>
              )}
              {trial.oos_note && <Alert type="info" showIcon message={trial.oos_note} />}
              {trial.exception && <Alert type="error" showIcon message={trial.exception} />}
              <Typography.Text type="secondary">
                指标
                {trial.model ? `　模型：${trial.model}` : ''}
                {trial.temperature != null ? `　温度：${trial.temperature}` : ''}
                {trial.duration_ms ? `　耗时：${trial.duration_ms} ms` : ''}
                {trial.prompt_hash ? `　prompt：${trial.prompt_hash}` : ''}
                {trial.corr_sota != null ? `　corr(SOTA)：${fmt(trial.corr_sota)}` : ''}
                {trial.corr_library != null ? `　corr(库)：${fmt(trial.corr_library)}` : ''}
              </Typography.Text>
              <pre style={{ margin: 0, maxHeight: 240, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(trial.metrics ?? {}, null, 2)}
              </pre>
              {trial.metrics_oos && Object.keys(trial.metrics_oos).length > 0 && (
                <>
                  <Typography.Text type="secondary">样本外指标</Typography.Text>
                  <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                    {JSON.stringify(trial.metrics_oos, null, 2)}
                  </pre>
                </>
              )}
              <Typography.Text type="secondary">代码</Typography.Text>
              <pre style={{ margin: 0, maxHeight: 320, overflow: 'auto', fontSize: 12 }}>
                {trial.code || '（无代码）'}
              </pre>
            </Space>
          </Card>
        )}

        {replayResult && (
          <Card
            size="small"
            title={`回放对比：试验 #${replayResult.original.id} ↔ 回放 #${replayResult.trial.id}`}
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
                  ? '部分复现'
                  : replayResult.replay_meta.consistent
                    ? '指标一致'
                    : '指标有差异'}
              </Tag>
            }
          >
            <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
              {replayResult.replay_meta.partial && (
                <Alert
                  type="warning"
                  showIcon
                  message={`部分复现：缺少 ${replayResult.replay_meta.missing.join(', ')}，回放按引擎默认值执行`}
                />
              )}
              <Table
                size="small"
                pagination={false}
                rowKey="key"
                dataSource={replayRows}
                columns={[
                  { title: '指标', dataIndex: 'label', width: 140 },
                  { title: `原 trial #${replayResult.original.id}`, dataIndex: 'original' },
                  { title: `回放 #${replayResult.trial.id}`, dataIndex: 'replay' },
                  { title: '差异', dataIndex: 'diff' },
                ]}
              />
              <Typography.Text type="secondary">
                判定口径：IC_IR 差异 ≤ {replayResult.replay_meta.tolerance.ic_ir} 且样本外未变化视为一致；
                {replayResult.replay_meta.unreproducible.includes('corr_sota')
                  ? ' corr(SOTA) 依赖当时的 SOTA 因子序列，无法重算，仅展示原值。'
                  : ''}
              </Typography.Text>
              {replayResult.original.judge && (
                <Typography.Text type="secondary">
                  原判定原因：{replayResult.original.judge.reason || '—'}
                </Typography.Text>
              )}
              {replayResult.replay_meta.notes.length > 0 && (
                <Typography.Text type="secondary">
                  回放说明：{replayResult.replay_meta.notes.join('；')}
                </Typography.Text>
              )}
            </Space>
          </Card>
        )}
      </Space>
    </PageContainer>
  );
};

export default ResearchDetail;
