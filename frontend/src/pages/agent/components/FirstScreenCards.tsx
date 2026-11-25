/**
 * 右栏首屏两卡（demo #view-agent 1528–1592 的现网落法，D 档差距清单 §2）：
 *
 * 卡一「迭代足迹」：当前会话每条带 ReAct 轮次的 AI 回复一根柱。数据只来自
 *   agentStore.messages（SSE iteration_start / complete 聚合，与「迭代 X/Y」徽标同源），
 *   不足不补、无数据即空态——会话历史接口不带 iteration，不做跨会话假历史。
 * 卡二「记忆自迭代 · Dream」：GET /agent/memory 只读快照（MEMORY.md / cursor / 待处理 /
 *   上次运行）+ GET /agent/loop-status 里 agent_dream 的 next_run_at（真实挂载的
 *   APScheduler job.next_run_time），后者为 null 时「下次运行」整行不渲染。
 *
 * 8 页签工作台（WorkbenchPanel）在两卡下方继续承载完整功能，本组件只是把分析卡搬回第一眼。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getAgentLoopStatus, getAgentMemory } from '@/api/agentApi';
import type { AgentMemoryResponse } from '@/api/agentApi';
import { formatTimestamp } from '@/utils/format';
import { useAgentStore } from '../store/agentStore';
import {
  dreamProgress,
  footprintBarPct,
  footprintCap,
  footprintPoints,
  memoryRunChars,
  memoryRunState,
  nextRunCountdown,
} from './workbench/workbenchFormat';

/** demo 口径：图上最多画最近 12 根柱（多出来的回复不进图，均值也只按画出的算） */
const FOOTPRINT_BARS = 12;
/** 距上限 ≥80% 的柱计为预警柱（demo 33/40 = 82.5% 预警同款） */
const NEAR_CAP_RATIO = 0.8;

const FootprintCard = () => {
  const { t } = useTranslation();
  const messages = useAgentStore((s) => s.messages);

  // 近 12 条带轮次的回复；不足就有几根画几根（不补齐、不循环、不造数）
  const points = useMemo(
    () => footprintPoints(messages).slice(-FOOTPRINT_BARS),
    [messages],
  );
  const cap = useMemo(() => footprintCap(points), [points]);
  const mean = useMemo(
    () => (points.length === 0 ? null : points.reduce((s, p) => s + p.value, 0) / points.length),
    [points],
  );

  return (
    <section className="sl-card">
      <header className="sl-card-head">
        <span className="sl-card-title">{t('selfloop_a_title')}</span>
        <span className="sl-card-note">{t('agent_footprint_note')}</span>
        {mean != null && (
          <span className="sl-card-head-right">
            <span className="sl-chip">
              {t('agent_footprint_mean', { mean: mean.toFixed(1) })}
            </span>
          </span>
        )}
      </header>

      {points.length === 0 ? (
        // 空态：一根柱都不画——没有真实迭代就不存在图形
        <div className="sl-empty">{t('agent_footprint_empty')}</div>
      ) : (
        <>
          <div className="fs-bars">
            {cap != null && (
              <div className="fs-capline">
                <span>{t('agent_footprint_capline', { max: cap })}</span>
              </div>
            )}
            {points.map((p, i) => {
              const near = cap != null && p.value / cap >= NEAR_CAP_RATIO;
              return (
                <div
                  className={`fs-col${near ? ' near' : ''}${i === points.length - 1 ? ' cur' : ''}`}
                  key={`${p.ts}-${i}`}
                  title={p.ts ? new Date(p.ts).toLocaleString() : undefined}
                >
                  <span className={`fs-val${near ? ' near' : ''}`}>{p.value}</span>
                  <span className="fs-track">
                    <i style={{ height: `${footprintBarPct(p.value, cap, points)}%` }} />
                  </span>
                </div>
              );
            })}
          </div>
          <div className="fs-x">
            {points.map((p, i) => (
              <span key={`${p.ts}-x-${i}`}>
                {p.ts
                  ? new Date(p.ts).toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
                  : '-'}
              </span>
            ))}
          </div>
        </>
      )}

      <div className="sl-foot">{t('agent_footprint_source')}</div>
    </section>
  );
};

const DreamCard = () => {
  const { t } = useTranslation();
  const [memory, setMemory] = useState<AgentMemoryResponse | null>(null);
  const [nextRunAt, setNextRunAt] = useState<string | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');

  const load = useCallback(async () => {
    setState('loading');
    // 并行取两个只读端点：loop-status 挂了不影响记忆卡主体（countdown 行自动不渲染）
    const [memoryRes, loopRes] = await Promise.allSettled([getAgentMemory(), getAgentLoopStatus()]);
    if (memoryRes.status === 'fulfilled') {
      setMemory(memoryRes.value);
      setState('ready');
    } else {
      // 失败不伪造数据：留空态 + 头部刷新钮重试（SelfLoopTab 里还有带详情的完整版）
      setMemory(null);
      setState('error');
    }
    const dreamJob =
      loopRes.status === 'fulfilled' ? loopRes.value.jobs?.find((job) => job.id === 'agent_dream') : undefined;
    setNextRunAt(dreamJob?.next_run_at ?? null);
  }, []);

  useEffect(() => {
    // 延后一拍拉取：effect 体内同步 setState 会触发级联渲染告警（与 SelfLoopTab 同款处理）
    const timer = window.setTimeout(load, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const progress = dreamProgress(memory?.dream_cursor ?? 0, memory?.history_entries ?? 0);
  const runState = memoryRunState(memory?.last_run ?? null);
  const runChars = memoryRunChars(memory?.last_run ?? null);
  // ponytail: 倒计时在每次拉取时算一次，不逐秒刷新（分钟级 job 秒抖动无信息量）；
  // 需要更实时时由头部刷新钮或加 1min interval 触发
  const countdown = nextRunCountdown(nextRunAt);
  const countdownText =
    countdown === null
      ? null
      : countdown.kind === 'soon'
        ? t('agent_next_run_soon')
        : countdown.kind === 'minutes'
          ? t('agent_next_run_in_minutes', { n: countdown.value })
          : countdown.kind === 'hours'
            ? t('agent_next_run_in_hours', { n: countdown.value })
            : t('agent_next_run_in_days', { n: countdown.value });

  return (
    <section className="sl-card">
      <header className="sl-card-head">
        <span className="sl-card-title">{t('selfloop_b_title')}</span>
        {memory && (
          <span className={`sl-chip sl-mono ${memory.enabled ? 'on' : 'off'}`}>
            {`QUANTCELL_AGENT_DREAM = ${memory.enabled ? 1 : 0}`}
          </span>
        )}
        <span className="sl-card-head-right">
          <Button size="small" type="text" icon={<ReloadOutlined />} onClick={load} loading={state === 'loading'} aria-label={t('refresh')} />
        </span>
      </header>

      {state === 'loading' && !memory ? (
        <div className="wb-center-spin">
          <Spin size="small" />
        </div>
      ) : state === 'error' || !memory ? (
        <div className="sl-empty">{t('agent_dream_load_failed')}</div>
      ) : (
        <>
          <div className="sl-mem-viewer">
            <div className="sl-mem-head">
              <span className="sl-mono">MEMORY.md</span>
              <span className="sl-ro-badge">{t('selfloop_readonly')}</span>
            </div>
            <div className="sl-mem-body">
              {memory.memory_markdown?.trim() ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{memory.memory_markdown}</ReactMarkdown>
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
                {runState === 'updated' && (
                  <span className="qc-chip warn sl-tag-tight">
                    {`updated${runChars != null ? ` · ${runChars}` : ''}`}
                  </span>
                )}
                {runState === 'noop' && <span className="sl-muted">{t('selfloop_run_noop')}</span>}
                {runState === 'failed' && (
                  <span className="qc-chip down sl-tag-tight">{t('selfloop_run_failed')}</span>
                )}
                {runState === 'never' && <span className="sl-muted">{t('selfloop_run_never')}</span>}
                {memory.last_run && (
                  <span className="sl-mono sl-muted">{formatTimestamp(memory.last_run.ts_iso)}</span>
                )}
              </span>
            </div>
            {/* 下次运行：只渲染真实调度器给的时间戳；取不到（未挂载）整行不画 */}
            {nextRunAt && countdownText && (
              <div className="sl-meta-row">
                <span>{t('agent_next_run')}</span>
                <span className="sl-mono sl-muted">
                  {dayjs(nextRunAt).format('MM-DD HH:mm')} · {countdownText}
                </span>
              </div>
            )}
          </div>

          <div className="sl-foot">{t('selfloop_memory_note')}</div>
        </>
      )}
    </section>
  );
};

export default function FirstScreenCards() {
  return (
    <div className="fs-cards">
      <FootprintCard />
      <DreamCard />
    </div>
  );
}
