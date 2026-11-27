/**
 * 价格计划预览 hook（编辑器 tab / 创建弹窗共用，spec §4/§4.B）。
 * - 260ms 防抖（ahooks useDebounceFn，与 demo 口径一致）
 * - 竞态保护：seq 计数器丢弃过期响应（上一请求未返回时参数又变了）
 * - 结果按 (strategy|ref|params) 会话级缓存，同参不重复请求
 * ponytail: 缓存无淘汰，上限 32 条整体清空——编辑器会话参数组合有限，够用；
 * 升级路径是 LRU，但现在不值得。
 */
import { useEffect, useRef, useState } from 'react';
import { useDebounceFn } from 'ahooks';
import { previewPricePlan } from '../api/pricePlanApi';
import type { PricePlanPreviewResponse } from '../types/pricePlan';

export interface UsePricePlanInput {
  strategyName: string | null | undefined;
  params: Record<string, unknown>;
  refPrice: number | null | undefined;
  /** 当前标的（多标的预览指定；后端按它取 params_by_symbol 覆盖） */
  symbol?: string | null;
  /** 按标的参数覆盖（与后端 resolver 同口径；前端不实现合并规则） */
  paramsBySymbol?: Record<string, Record<string, unknown>>;
}

/** 从 axios 422 错误里剥出可读 message（后端 detail={code,message}，兼容字符串形态） */
function extractPreviewError(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: { message?: string; code?: string } | string } } })
    .response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return detail?.message ?? detail?.code ?? '价格计划预览失败';
}

export function usePricePlan({ strategyName, params, refPrice, symbol, paramsBySymbol }: UsePricePlanInput) {
  const [data, setData] = useState<PricePlanPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);
  const cacheRef = useRef<Map<string, PricePlanPreviewResponse>>(new Map());

  const key =
    strategyName && refPrice ? `${strategyName}|${symbol ?? ''}|${refPrice}|${JSON.stringify(params)}|${JSON.stringify(paramsBySymbol ?? {})}` : null;

  const fetchPlan = async (
    k: string, name: string, p: Record<string, unknown>, ref: number, sym: string | null | undefined,
    bySymbol: Record<string, Record<string, unknown>> | undefined,
  ) => {
    const cached = cacheRef.current.get(k);
    if (cached) {
      setData(cached);
      setError(null);
      return;
    }
    const seq = ++seqRef.current;
    setLoading(true);
    setError(null);
    try {
      const res = await previewPricePlan({
        strategy_name: name,
        params: p,
        ref_price: ref,
        symbol: sym ?? undefined,
        params_by_symbol: bySymbol ?? undefined,
      });
      if (seq !== seqRef.current) return; // 已被更新的请求取代，丢弃
      if (cacheRef.current.size >= 32) cacheRef.current.clear();
      cacheRef.current.set(k, res);
      setData(res);
    } catch (err) {
      if (seq !== seqRef.current) return;
      setData(null);
      setError(extractPreviewError(err));
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  };

  const { run } = useDebounceFn(
    (k: string, name: string, p: Record<string, unknown>, ref: number, sym: string | null | undefined,
      bySymbol: Record<string, Record<string, unknown>> | undefined) => {
      void fetchPlan(k, name, p, ref, sym, bySymbol);
    },
    { wait: 260 },
  );

  useEffect(() => {
    // 无策略或无参考价：清空并静默（调用方负责先把 refPrice 取到）
    if (!key || !strategyName || !refPrice || refPrice <= 0) {
      seqRef.current += 1; // 在途响应作废
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    run(key, strategyName, params, refPrice, symbol, paramsBySymbol);
    // key 已含 params/symbol/paramsBySymbol 快照；引用变化由调用方 useMemo 保证，不被这个 effect 重复触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, strategyName, refPrice]);

  return { data, loading, error };
}
