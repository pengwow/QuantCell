/**
 * 因子异步任务 Hook
 *
 * 封装 analyze/compare/llm_mine 任务的提交与跟踪：
 * - WS topic `factor:job`：data.type=progress 推进度，data.type=event 追加过程事件；
 * - WS 一旦收到本任务任意消息即视为存活，停止轮询（事件驱动足够及时）；
 * - WS 从未证明存活时降级轮询，状态连续不变按 1s→2s→5s 退避，一变化恢复 1s；
 * - attach/开始时 GET jobs/{id}/events 拉齐历史事件（WS 漏推/重连补齐）；
 * - 终态取结果、404 判丢失、10 分钟超时、卸载清理，语义同前。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '@/api';
import {
  factorApi,
  type FactorAnalyzeParams,
  type FactorCompareParams,
  type FactorJobEventEnvelope,
  type FactorJobStatus,
  type FactorMineLLMParams,
  type MiningEvent,
} from '@/api/factor';
import { wsService } from '@/services/websocketService';

const TOPIC = 'factor:job';
const POLL_STEPS = [1000, 2000, 5000]; // 降级轮询退避档
const TIMEOUT_MS = 10 * 60 * 1000;

export type FactorJobKind = 'analyze' | 'compare' | 'llm_mine';

export interface UseFactorJob<T> {
  run: (
    kind: FactorJobKind,
    params: FactorAnalyzeParams | FactorCompareParams | FactorMineLLMParams,
    onResult: (r: T) => void,
    onError: (msg: string) => void,
    onLost?: () => void,
  ) => Promise<void>;
  attach: (
    jobId: string,
    onResult: (r: T) => void,
    onError: (msg: string) => void,
    onLost?: () => void,
  ) => void;
  status: FactorJobStatus | null;
  loading: boolean;
  events: MiningEvent[];
}

export function useFactorJob<T>(): UseFactorJob<T> {
  const [status, setStatus] = useState<FactorJobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [events, setEvents] = useState<MiningEvent[]>([]);

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentIdRef = useRef<string | null>(null);
  const settledRef = useRef(false);
  const wsAliveRef = useRef(false);
  const unchangedRef = useRef(0);
  const lastSigRef = useRef<string>('');
  const eventsIdxRef = useRef(-1);
  const onResultRef = useRef<((r: T) => void) | null>(null);
  const onErrorRef = useRef<((msg: string) => void) | null>(null);
  const onLostRef = useRef<(() => void) | undefined>(undefined);
  const handleTerminalRef = useRef<(st: FactorJobStatus) => void>(() => {});

  const mergeEvents = useCallback((incoming: MiningEvent[]) => {
    if (incoming.length === 0) return;
    const fresh = incoming.filter((e) => e.idx > eventsIdxRef.current);
    if (fresh.length === 0) return;
    eventsIdxRef.current = Math.max(eventsIdxRef.current, fresh[fresh.length - 1].idx);
    setEvents((prev) => {
      const merged = [...prev, ...fresh];
      // 以 idx 去重排序，兜底防止 WS 推送与补齐重叠
      const map = new Map<number, MiningEvent>();
      merged.forEach((e) => map.set(e.idx, e));
      return [...map.values()].sort((a, b) => a.idx - b.idx).slice(-500);
    });
  }, []);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  // WS 消息按 data.type 分发；收到任意本任务消息即标记 WS 存活并停轮询
  const onWs = useCallback(
    (data: unknown) => {
      const env = data as FactorJobEventEnvelope | (FactorJobStatus & { type?: string });
      if (!env || env.job_id !== currentIdRef.current) return;
      wsAliveRef.current = true;
      stopPolling();
      if (env.type === 'event') {
        mergeEvents([(env as FactorJobEventEnvelope).event]);
        return;
      }
      const st = env as FactorJobStatus;
      if (st.status === 'completed' || st.status === 'failed') {
        handleTerminalRef.current(st);
      } else {
        setStatus(st);
      }
    },
    [mergeEvents, stopPolling],
  );

  const cleanup = useCallback(() => {
    stopPolling();
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    wsService.off(TOPIC, onWs);
  }, [onWs, stopPolling]);

  const fetchResult = useCallback(
    async (jobId: string) => {
      const result = await factorApi.getFactorJobResult<T>(jobId);
      onResultRef.current?.(result);
      setLoading(false);
      cleanup();
    },
    [cleanup],
  );

  const handleTerminal = useCallback(
    (st: FactorJobStatus) => {
      if (settledRef.current) return;
      settledRef.current = true;
      setStatus(st);
      if (st.status === 'completed') {
        void fetchResult(st.job_id).catch(() => {
          onErrorRef.current?.('获取任务结果失败，请重试');
          setLoading(false);
          cleanup();
        });
      } else if (st.status === 'failed') {
        onErrorRef.current?.(st.error || '任务失败');
        setLoading(false);
        cleanup();
      }
    },
    [cleanup, fetchResult],
  );

  handleTerminalRef.current = handleTerminal;

  const pollOnceRef = useRef<() => Promise<void>>(async () => {});
  const schedulePoll = useCallback(() => {
    if (wsAliveRef.current || settledRef.current) return;
    const delay = POLL_STEPS[Math.min(unchangedRef.current, POLL_STEPS.length - 1)];
    pollTimerRef.current = setTimeout(() => void pollOnceRef.current(), delay);
  }, []);

  pollOnceRef.current = async () => {
    const id = currentIdRef.current;
    if (!id || settledRef.current) return;
    try {
      const st = await factorApi.getFactorJob(id);
      if (settledRef.current) return;
      if (st.status === 'completed' || st.status === 'failed') {
        handleTerminal(st);
        return;
      }
      const sig = `${st.status}|${st.progress}|${st.stage}|${st.message}`;
      unchangedRef.current = sig === lastSigRef.current ? unchangedRef.current + 1 : 0;
      lastSigRef.current = sig;
      setStatus(st);
    } catch (e) {
      if (e instanceof ApiError && e.code === 404) {
        if (!settledRef.current) {
          settledRef.current = true;
          setLoading(false);
          cleanup();
          onLostRef.current?.();
        }
        return;
      }
      /* 单次失败忽略，按退避继续 */
    }
    schedulePoll();
  };

  const hydrateEvents = useCallback(
    async (jobId: string) => {
      try {
        const page = await factorApi.getFactorJobEvents(jobId, 0);
        if (currentIdRef.current === jobId) mergeEvents(page.events);
      } catch {
        /* 事件补齐失败不影响主流程，后续靠 WS/轮询 */
      }
    },
    [mergeEvents],
  );

  const _track = useCallback(
    (
      jobId: string,
      onResult: (r: T) => void,
      onError: (msg: string) => void,
      onLost?: () => void,
    ) => {
      cleanup();
      settledRef.current = false;
      wsAliveRef.current = false;
      unchangedRef.current = 0;
      lastSigRef.current = '';
      eventsIdxRef.current = -1;
      onResultRef.current = onResult;
      onErrorRef.current = onError;
      onLostRef.current = onLost;
      currentIdRef.current = jobId;
      setEvents([]);
      setLoading(true);

      wsService.subscribe(TOPIC);
      wsService.on(TOPIC, onWs);
      void hydrateEvents(jobId); // 拉齐历史事件（新任务为空，attach 可补齐）
      schedulePoll(); // 首次 1s；WS 在这之前到达则被 onWs 停掉
      timeoutRef.current = setTimeout(() => {
        if (settledRef.current) return;
        settledRef.current = true;
        cleanup();
        setLoading(false);
        onError('任务超时（10 分钟无结果），请重试');
      }, TIMEOUT_MS);
    },
    [cleanup, hydrateEvents, onWs, schedulePoll],
  );

  const run = useCallback(
    async (
      kind: FactorJobKind,
      params: FactorAnalyzeParams | FactorCompareParams | FactorMineLLMParams,
      onResult: (r: T) => void,
      onError: (msg: string) => void,
      onLost?: () => void,
    ) => {
      onResultRef.current = onResult;
      onErrorRef.current = onError;
      currentIdRef.current = null;
      setLoading(true);
      setStatus(null);
      setEvents([]);

      let accepted: { job_id: string; status: string };
      try {
        if (kind === 'analyze') {
          accepted = await factorApi.analyzeAsync(params as FactorAnalyzeParams);
        } else if (kind === 'llm_mine') {
          accepted = await factorApi.mineLLM(params as FactorMineLLMParams);
        } else {
          accepted = await factorApi.compareAsync(params as FactorCompareParams);
        }
      } catch (err) {
        setLoading(false);
        throw err;
      }
      _track(accepted.job_id, onResult, onError, onLost);
    },
    [_track],
  );

  const attach = useCallback<UseFactorJob<T>['attach']>(
    (jobId, onResult, onError, onLost) => {
      setStatus(null);
      _track(jobId, onResult, onError, onLost);
    },
    [_track],
  );

  useEffect(() => cleanup, [cleanup]);

  return { run, attach, status, loading, events };
}
