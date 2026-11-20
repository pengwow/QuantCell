/**
 * 右栏 ⑦ 自迭代：把 Agent 的四类自循环如实展示（已关闭的就写已关闭，不美化）。
 *
 * A 迭代足迹      GET /agent/audit（最近 N 天工具调用按天聚合 + 失败次数）
 * B 记忆自迭代    GET /agent/memory（总闸 / MEMORY.md 只读 / cursor 进度 / 上次运行）
 * C 每日闭环时钟线 GET /agent/loop-status → jobs（点行展开最近一次运行详情）
 * D 重训台账      GET /agent/loop-status → retrain.gates + families
 *
 * 仅激活 Tab 时拉取；三个端点各发一次，Promise.allSettled 让单点失败不拖垮整页。
 * 失败只提示 + 重试按钮，不伪造数据（后端未就绪时卡片显示空态）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Spin, Table, Tooltip } from 'antd';
import type { TableColumnsType } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import dayjs from 'dayjs';
import {
  getAgentLoopStatus,
  getAgentMemory,
  queryToolAudit,
} from '@/api/agentApi';
import type {
  AgentLoopStatusResponse,
  AgentMemoryResponse,
  AgentRetrainFamily,
  ToolAuditResponse,
} from '@/api/agentApi';
import { formatTimestamp } from '@/utils/format';
import { useWorkbenchStore } from '../../store/workbenchStore';
import {
  auditDayBuckets,
  dreamProgress,
  formatRunDetail,
  loopJobState,
  memoryRunChars,
  memoryRunState,
  retrainGates,
} from './workbenchFormat';

/** 足迹窗口：审计表按天看，7 天足够看出频率，不再加时间窗切换控件 */
const DAYS = 7;
/** 与 AuditTab 同口径的固定窗口（后端上限 500） */
const AUDIT_LIMIT = 500;

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err));

const SelfLoopTab = () => {
  const { t } = useTranslation();
  const isActive = useWorkbenchStore((s) => s.activeTab) === 'selfloop';

  const [audit, setAudit] = useState<ToolAuditResponse | null>(null);
  const [memory, setMemory] = useState<AgentMemoryResponse | null>(null);
  const [loop, setLoop] = useState<AgentLoopStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    // 起点取 N 天前的本地零点：桶按本地自然日切，跨时区不会切出半天空桶
    const since = new Date();
    since.setHours(0, 0, 0, 0);
    since.setDate(since.getDate() - (DAYS - 1));

    const [auditRes, memoryRes, loopRes] = await Promise.allSettled([
      queryToolAudit({ start: since.toISOString(), limit: AUDIT_LIMIT }),
      getAgentMemory(),
      getAgentLoopStatus(),
    ]);

    const nextErrors: string[] = [];
    if (auditRes.status === 'fulfilled') setAudit(auditRes.value);
    else nextErrors.push(`audit: ${errText(auditRes.reason)}`);
    if (memoryRes.status === 'fulfilled') setMemory(memoryRes.value);
    else nextErrors.push(`memory: ${errText(memoryRes.reason)}`);
    if (loopRes.status === 'fulfilled') setLoop(loopRes.value);
    else nextErrors.push(`loop: ${errText(loopRes.reason)}`);

    setErrors(nextErrors);
    setLoading(false);
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (!isActive) return;
    // 延后一拍拉取：effect 体内同步 setState 会触发级联渲染告警（与 useWorkbenchData 建连同款处理）
    const timer = window.setTimeout(load, 0);
    return () => window.clearTimeout(timer);
  }, [isActive, load]);

  const rows = useMemo(() => audit?.audits ?? [], [audit]);
  const buckets = useMemo(() => auditDayBuckets(rows, DAYS), [rows]);
  const maxTotal = useMemo(
    () => buckets.reduce((m, b) => Math.max(m, b.total), 0),
    [buckets],
  );
  const failedTotal = useMemo(
    () => buckets.reduce((sum, b) => sum + b.failed, 0),
    [buckets],
  );

  const memState = memoryRunState(memory?.last_run ?? null);
  const memChars = memoryRunChars(memory?.last_run ?? null);
  const progress = dreamProgress(memory?.dream_cursor ?? 0, memory?.history_entries ?? 0);
  const gates = retrainGates(loop?.retrain?.gates);
  const families = loop?.retrain?.families ?? [];
  const jobs = loop?.jobs ?? [];

  const familyColumns: TableColumnsType<AgentRetrainFamily> = [
    {
      title: t('selfloop_family'),
      dataIndex: 'family',
      ellipsis: true,
      render: (v: string) => <span className="wb-nowrap-mono">{v}</span>,
    },
    {
      title: t('status'),
      dataIndex: 'status',
      width: 96,
      render: (v: string) => <span className="wb-nowrap-mono">{v}</span>,
    },
    {
      title: t('selfloop_shadow_days'),
      dataIndex: 'shadow_days',
      width: 92,
      align: 'right',
      render: (v?: number | null) => (
        <span className="wb-nowrap-mono">{v == null ? '-' : v}</span>
      ),
    },
    {
      title: t('selfloop_note'),
      dataIndex: 'note',
      ellipsis: true,
      render: (v?: string | null) => v || '-',
    },
  ];

  if (!loaded) {
    return (
      <div className="wb-center-spin">
        <Spin size="small" />
      </div>
    );
  }

  return (
    <div className="sl-root">
      <div className="sl-toolbar">
        <span className="sl-toolbar-note">{t('selfloop_toolbar_note')}</span>
        <Tooltip title={t('refresh')}>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={load}
          />
        </Tooltip>
      </div>

      {errors.length > 0 && (
        <Alert
          type="warning"
          showIcon
          title={t('selfloop_load_failed')}
          description={errors.join(' / ')}
          action={
            <Button size="small" onClick={load} loading={loading}>
              {t('retry')}
            </Button>
          }
        />
      )}

      {/* ---------- A 迭代足迹 ---------- */}
      <section className="sl-card">
        <header className="sl-card-head">
          <span className="sl-card-idx">A</span>
          <span className="sl-card-title">{t('selfloop_a_title')}</span>
          <span className="sl-card-note">{t('selfloop_a_note', { days: DAYS })}</span>
        </header>

        {rows.length === 0 ? (
          <div className="sl-empty">{t('selfloop_no_audit')}</div>
        ) : (
          <>
            <div className="sl-bars">
              {buckets.map((b) => {
                const pct = maxTotal === 0 ? 0 : (b.total / maxTotal) * 100;
                return (
                  <div
                    className="sl-bar"
                    key={b.date}
                    title={`${b.date} · ${t('selfloop_a_calls', { total: b.total })} · ${t('selfloop_a_failures', { failed: b.failed })}`}
                  >
                    <span className="sl-bar-val">{b.total}</span>
                    <span className="sl-bar-track">
                      <i
                        style={{ height: `${Math.max(pct, b.total > 0 ? 4 : 0)}%` }}
                        className={b.failed > 0 ? 'has-fail' : ''}
                      />
                    </span>
                    <span className="sl-bar-x">{dayjs(b.date).format('MM-DD')}</span>
                  </div>
                );
              })}
            </div>
            <div className="sl-chips">
              <span className="sl-chip">
                {t('selfloop_a_calls', { total: rows.length })}
              </span>
              <span className={failedTotal > 0 ? 'sl-chip alert' : 'sl-chip'}>
                {t('selfloop_a_failures', { failed: failedTotal })}
              </span>
            </div>
          </>
        )}
      </section>

      {/* ---------- B 记忆自迭代（Dream） ---------- */}
      <section className="sl-card">
        <header className="sl-card-head">
          <span className="sl-card-idx">B</span>
          <span className="sl-card-title">{t('selfloop_b_title')}</span>
          <span className="sl-card-head-right">
            <span className={memory?.enabled ? 'sl-chip on' : 'sl-chip off'}>
              {memory?.enabled ? t('selfloop_enabled') : t('selfloop_disabled')}
            </span>
          </span>
        </header>

        {!memory ? (
          <div className="sl-empty">{t('no_data')}</div>
        ) : (
          <>
            <div className="sl-mem-viewer">
              <div className="sl-mem-head">
                <span className="sl-mono">MEMORY.md</span>
                <span className="sl-ro-badge">{t('selfloop_readonly')}</span>
              </div>
              <div className="sl-mem-body">
                {memory.memory_markdown?.trim() ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {memory.memory_markdown}
                  </ReactMarkdown>
                ) : (
                  <span className="sl-muted">{t('selfloop_memory_empty')}</span>
                )}
              </div>
            </div>

            <div className="sl-meta">
              <div className="sl-meta-row">
                <span>{t('selfloop_cursor')}</span>
                <span className="sl-mono">
                  {progress.processed}/{progress.total}
                </span>
              </div>
              <span className="sl-progress">
                <i style={{ width: `${progress.pct}%` }} />
              </span>
              {progress.pending > 0 && (
                <div className="sl-meta-row sl-muted">
                  <span>{t('selfloop_cursor_pending')}</span>
                  <span className="sl-mono">{progress.pending}</span>
                </div>
              )}

              <div className="sl-meta-row">
                <span>{t('selfloop_last_run')}</span>
                <span className="sl-run-state">
                  {memState === 'updated' && (
                    <span className="qc-chip warn sl-tag-tight">
                      {`updated${memChars != null ? ` · ${memChars}` : ''}`}
                    </span>
                  )}
                  {memState === 'noop' && (
                    <span className="sl-muted">{t('selfloop_run_noop')}</span>
                  )}
                  {memState === 'failed' && (
                    <span className="qc-chip down sl-tag-tight">
                      {t('selfloop_run_failed')}
                    </span>
                  )}
                  {memState === 'never' && (
                    <span className="sl-muted">{t('selfloop_run_never')}</span>
                  )}
                  {memory.last_run && (
                    <span className="sl-mono sl-muted">
                      {formatTimestamp(memory.last_run.ts_iso)}
                    </span>
                  )}
                </span>
              </div>

              {memState === 'failed' && memory.last_run && (
                <pre className="sl-pre">
                  {memory.last_run.error ||
                    formatRunDetail(memory.last_run.detail) ||
                    t('detail')}
                </pre>
              )}

              <div className="sl-muted sl-small">{t('selfloop_next_run')}</div>
            </div>

            <div className="sl-foot">{t('selfloop_memory_note')}</div>
          </>
        )}
      </section>

      {/* ---------- C 每日闭环时钟线 ---------- */}
      <section className="sl-card">
        <header className="sl-card-head">
          <span className="sl-card-idx">C</span>
          <span className="sl-card-title">{t('selfloop_c_title')}</span>
          <span className="sl-card-note">{t('selfloop_c_note')}</span>
        </header>

        {jobs.length === 0 ? (
          <div className="sl-empty">{t('selfloop_jobs_empty')}</div>
        ) : (
          <div className="sl-jobs">
            {jobs.map((job) => {
              const state = loopJobState(job);
              const open = expandedJob === job.id;
              const detail = formatRunDetail(job.last_run?.detail);
              return (
                <div className="sl-job" key={job.id}>
                  <button
                    type="button"
                    className="sl-job-row"
                    aria-expanded={open}
                    onClick={() => setExpandedJob(open ? null : job.id)}
                  >
                    <span className={`sl-dot ${state}`} />
                    <span className="sl-job-name">{job.name}</span>
                    <span className="sl-job-cron sl-mono">{job.cron}</span>
                    <span className={`sl-job-state ${state}`}>
                      {state === 'ok' && t('selfloop_job_ok')}
                      {state === 'failed' && t('selfloop_job_failed')}
                      {state === 'idle' && t('selfloop_job_idle')}
                      {state === 'off' && t('selfloop_job_off')}
                    </span>
                  </button>
                  {open && (
                    <div className="sl-job-detail">
                      {job.last_run ? (
                        <>
                          <div className="sl-meta-row sl-muted">
                            <span>{t('selfloop_run_at')}</span>
                            <span className="sl-mono">
                              {formatTimestamp(job.last_run.ts_iso)}
                            </span>
                          </div>
                          {job.last_run.error && (
                            <pre className="sl-pre">{job.last_run.error}</pre>
                          )}
                          {detail && <pre className="sl-pre">{detail}</pre>}
                          {!job.last_run.error && !detail && (
                            <div className="sl-muted">{t('selfloop_no_detail')}</div>
                          )}
                        </>
                      ) : (
                        <div className="sl-muted">{t('selfloop_run_never')}</div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ---------- D 重训台账 ---------- */}
      <section className="sl-card">
        <header className="sl-card-head">
          <span className="sl-card-idx">D</span>
          <span className="sl-card-title">{t('selfloop_d_title')}</span>
          <span className="sl-card-note">{t('selfloop_d_note')}</span>
        </header>

        {!loop ? (
          // 端点未通/失败：不渲染双闸（否则会被读成"闸门都关着"，是假信息）
          <div className="sl-empty">{t('no_data')}</div>
        ) : (
          <>
            <div className="sl-gates">
              <span className={gates.autoRetrain ? 'sl-chip on' : 'sl-chip off'}>
                AUTO_RETRAIN · {gates.autoRetrain ? t('selfloop_gate_on') : t('selfloop_gate_off')}
              </span>
              <span className={gates.autoPromote ? 'sl-chip on' : 'sl-chip off'}>
                AUTO_PROMOTE · {gates.autoPromote ? t('selfloop_gate_on') : t('selfloop_gate_off')}
              </span>
            </div>

            {gates.anyOff && (
              <div className="sl-notice">{t('selfloop_retrain_warning')}</div>
            )}

            {families.length === 0 ? (
              <div className="sl-empty">{t('selfloop_families_empty')}</div>
            ) : (
              <Table<AgentRetrainFamily>
                size="small"
                rowKey={(r) => r.family}
                dataSource={families}
                columns={familyColumns}
                pagination={false}
                locale={{ emptyText: t('selfloop_families_empty') }}
              />
            )}
          </>
        )}

        <div className="sl-foot">{t('selfloop_d_footnote')}</div>
      </section>
    </div>
  );
};

export default SelfLoopTab;
