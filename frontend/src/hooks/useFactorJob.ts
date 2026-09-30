/**
 * 因子异步任务 Hook
 *
 * 封装 analyze/compare 异步任务的提交与跟踪：
 * - POST async 端点拿 job_id；
 * - WS topic `factor:job` 接收进度/终态推送（不含结果）；
 * - 1s 间隔轮询 GET /jobs/{id} 作为 WS 不可用时的降级；
 * - 终态 completed 后 GET /jobs/{id}/result 取结果，failed 回调错误；
 * - 10 分钟无终态按超时处理；组件卸载自动清理。
 *
 * 竞态处理：拿到 job_id 后先 subscribe + on 注册监听，再立即 pollOnce 查一次，
 * 避免任务比 WS 订阅更快完成而漏掉终态。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  factorApi,
  type FactorAnalyzeParams,
  type FactorCompareParams,
  type FactorJobStatus,
} from '@/api/factor';
import { wsService } from '@/services/websocketService';

const TOPIC = 'factor:job';
const POLL_MS = 1000;
const TIMEOUT_MS = 10 * 60 * 1000;

export type FactorJobKind = 'analyze' | 'compare';

export interface UseFactorJob<T> {
  run: (
    kind: FactorJobKind,
    params: FactorAnalyzeParams | FactorCompareParams,
    onResult: (r: T) => void,
    onError: (msg: string) => void,
  ) => Promise<void>;
  status: FactorJobStatus | null;
  loading: boolean;
}

export function useFactorJob<T>(): UseFactorJob<T> {
  const [status, setStatus] = useState<FactorJobStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentIdRef = useRef<string | null>(null);
  const settledRef = useRef(false);
  const onResultRef = useRef<((r: T) => void) | null>(null);
  const onErrorRef = useRef<((msg: string) => void) | null>(null);
  // handleTerminal 在 onWs 之后定义，用 ref 桥接以保持 onWs/cleanup 引用稳定
  const handleTerminalRef = useRef<(st: FactorJobStatus) => void>(() => {});

  // WS 消息只处理当前任务；非终态更新进度，终态交给统一处理（仅触发一次）
  const onWs = useCallback((data: unknown) => {
    const st = data as FactorJobStatus | null;
    if (!st || st.job_id !== currentIdRef.current) return;
    if (st.status === 'completed' || st.status === 'failed') {
      handleTerminalRef.current(st);
    } else {
      setStatus(st);
    }
  }, []);

  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    wsService.off(TOPIC, onWs);
  }, [onWs]);

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

  // 每次渲染同步最新 handleTerminal，onWs 本身保持稳定引用
  handleTerminalRef.current = handleTerminal;

  const pollOnce = useCallback(async () => {
    const id = currentIdRef.current;
    if (!id || settledRef.current) return;
    try {
      const st = await factorApi.getFactorJob(id);
      if (settledRef.current) return;
      if (st.status === 'completed' || st.status === 'failed') {
        handleTerminal(st);
      } else {
        setStatus(st);
      }
    } catch {
      /* 单次轮询失败忽略，下一次重试 */
    }
  }, [handleTerminal]);

  const run = useCallback(
    async (
      kind: FactorJobKind,
      params: FactorAnalyzeParams | FactorCompareParams,
      onResult: (r: T) => void,
      onError: (msg: string) => void,
    ) => {
      cleanup();
      settledRef.current = false;
      onResultRef.current = onResult;
      onErrorRef.current = onError;
      currentIdRef.current = null;
      setLoading(true);
      setStatus(null);

      // 联合参数按 kind 分支调用，各自断言为对应请求类型
      let accepted: { job_id: string; status: string };
      try {
        if (kind === 'analyze') {
          accepted = await factorApi.analyzeAsync(params as FactorAnalyzeParams);
        } else {
          accepted = await factorApi.compareAsync(params as FactorCompareParams);
        }
      } catch (err) {
        // 同步提交阶段失败：复位 loading 后交调用方 catch 提示
        setLoading(false);
        throw err;
      }
      currentIdRef.current = accepted.job_id;

      // 关键：先订阅 + 注册监听，再立即查一次状态，
      // 防止任务在订阅生效前就已完成而漏掉终态
      wsService.subscribe(TOPIC);
      wsService.on(TOPIC, onWs);
      void pollOnce();
      timerRef.current = setInterval(() => void pollOnce(), POLL_MS);
      timeoutRef.current = setTimeout(() => {
        if (settledRef.current) return;
        settledRef.current = true;
        cleanup();
        setLoading(false);
        onError('任务超时（10 分钟无结果），请重试');
      }, TIMEOUT_MS);
    },
    [cleanup, onWs, pollOnce],
  );

  // 组件卸载清理定时器与 WS 监听
  useEffect(() => cleanup, [cleanup]);

  return { run, status, loading };
}
