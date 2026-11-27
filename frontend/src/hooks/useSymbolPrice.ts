/**
 * 实时最新价 hook（价格计划参考价自动预览 + 启动确认共用）。
 *
 * 后端 GET /marketdata/price 已有 30s 微缓存；本 hook 再做一层会话级缓存（同
 * exchange|symbol|market_type 30s 内直接复用），refetch() 绕过缓存强制回源，
 * 作为取价失败后的重试入口。错误剥离兼容 detail 为字符串或 {code,message}
 * 对象两种后端形态（本端点 400/502 的 detail 是对象，其他老端点是字符串）。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useDebounceFn } from 'ahooks';
import { fetchLatestPrice, type LatestPriceResponse } from '../api/pricePlanApi';

// ponytail: 模块级 Map 无淘汰——key 是用户选的标的组合（chips 数量级），不会膨胀；
// 若将来变成无界增长再换 LRU。
const priceCache = new Map<string, { value: LatestPriceResponse; expiresAt: number }>();
const TTL_MS = 30_000;

function extractPriceError(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: string; code?: string };
    return d.message ?? d.code ?? '';
  }
  return '';
}

export interface UseSymbolPriceParams {
  /** 交易标的（原始值即可，后端统一归一化大写去分隔符） */
  symbol: string | null | undefined;
  marketType: string | null | undefined;
  exchange: string | null | undefined;
}

export function useSymbolPrice({ symbol, marketType, exchange }: UseSymbolPriceParams) {
  const [data, setData] = useState<LatestPriceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);

  const key =
    symbol && marketType && exchange
      ? `${exchange}|${symbol.toUpperCase()}|${marketType}`
      : null;

  const doFetch = useCallback(async (cacheKey: string, bypassCache: boolean) => {
    const cached = priceCache.get(cacheKey);
    if (!bypassCache && cached && cached.expiresAt > Date.now()) {
      setData(cached.value);
      setError(null);
      return;
    }
    const seq = ++seqRef.current;
    setLoading(true);
    setError(null);
    try {
      // cacheKey 三段依次是 exchange|symbol|market_type，与入参一一对应
      const [ex, sym, mt] = cacheKey.split('|');
      const res = await fetchLatestPrice({ symbol: sym, market_type: mt, exchange: ex });
      if (seq !== seqRef.current) return; // 已有更新的请求接管，丢弃过期结果
      priceCache.set(cacheKey, { value: res, expiresAt: Date.now() + TTL_MS });
      setData(res);
    } catch (err) {
      if (seq !== seqRef.current) return;
      setData(null);
      setError(extractPriceError(err) || '获取实时价格失败');
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  }, []);

  const refetch = useCallback(() => {
    if (key) void doFetch(key, true);
  }, [key, doFetch]);

  // 260ms 防抖与 usePricePlan 一致：chips 快速切换/表单连续变更时不打请求风暴
  const { run } = useDebounceFn(
    (cacheKey: string) => {
      void doFetch(cacheKey, false);
    },
    { wait: 260 },
  );

  useEffect(() => {
    if (!key) {
      seqRef.current += 1; // 在途请求作废
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    run(key);
    // 只依赖 key（防抖 run 引用稳定）；与 usePricePlan 同款 eslint 豁免理由
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { data, loading, error, refetch };
}
