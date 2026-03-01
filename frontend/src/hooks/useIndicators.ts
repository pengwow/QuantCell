import { useState, useEffect, useCallback } from 'react';
import { indicatorApi } from '../api';

export interface Indicator {
  id: number;
  name: string;
  description: string;
  code: string;
  user_id: number;
  is_buy: number;
  end_time: number;
  publish_to_community: number;
  pricing_type: string;
  price: number;
  is_encrypted: number;
}

export interface IndicatorParams {
  [key: string]: any;
}

export interface ActiveIndicator {
  id: string | number;
  name: string;
  params?: IndicatorParams;
  isCustom?: boolean;
}

// 内置指标定义
export const builtInIndicators = [
  { id: 'vol', name: 'VOL (成交量)', shortName: 'VOL', type: 'volume', defaultParams: { ma1: 5, ma2: 10 } },
  { id: 'sma', name: 'SMA (简单移动平均)', shortName: 'SMA', type: 'line', defaultParams: { length: 20 } },
  { id: 'ema', name: 'EMA (指数移动平均)', shortName: 'EMA', type: 'line', defaultParams: { length: 20 } },
  { id: 'rsi', name: 'RSI (相对强弱指数)', shortName: 'RSI', type: 'line', defaultParams: { length: 14 } },
  { id: 'macd', name: 'MACD (指数平滑异同平均线)', shortName: 'MACD', type: 'line', defaultParams: { fast: 12, slow: 26, signal: 9 } },
  { id: 'bb', name: 'BB (布林带)', shortName: 'BB', type: 'line', defaultParams: { length: 20, stdDev: 2 } },
  { id: 'atr', name: 'ATR (平均真实波幅)', shortName: 'ATR', type: 'line', defaultParams: { length: 14 } },
  { id: 'cci', name: 'CCI (商品通道指数)', shortName: 'CCI', type: 'line', defaultParams: { length: 20 } },
  { id: 'wr', name: 'Williams %R (威廉指标)', shortName: 'WR', type: 'line', defaultParams: { length: 14 } },
  { id: 'mfi', name: 'MFI (资金流量指标)', shortName: 'MFI', type: 'line', defaultParams: { length: 14 } },
  { id: 'adx', name: 'ADX (平均趋向指数)', shortName: 'ADX', type: 'line', defaultParams: { length: 14 } },
  { id: 'obv', name: 'OBV (能量潮)', shortName: 'OBV', type: 'line', defaultParams: {} },
  { id: 'adosc', name: 'ADOSC (震荡指标)', shortName: 'ADOSC', type: 'line', defaultParams: { fast: 3, slow: 10 } },
  { id: 'ad', name: 'AD (累积/派发线)', shortName: 'AD', type: 'line', defaultParams: {} },
  { id: 'kdj', name: 'KDJ (随机指标)', shortName: 'KDJ', type: 'line', defaultParams: { k: 9, d: 3, j: 3 } }
];

// 默认指标代码模板
export const defaultIndicatorCode = `# 指标代码示例
import pandas as pd
import numpy as np

my_indicator_name = "双均线交叉"
my_indicator_description = "基于5日和20日均线交叉产生买卖信号"

# 计算均线
sma_short = df["close"].rolling(5).mean()
sma_long = df["close"].rolling(20).mean()

# 生成信号
buy = (sma_short > sma_long) & (sma_short.shift(1) <= sma_long.shift(1))
sell = (sma_short < sma_long) & (sma_short.shift(1) >= sma_long.shift(1))

# 输出格式
output = {
    "name": my_indicator_name,
    "plots": [
        {"name": "SMA5", "data": sma_short.tolist(), "color": "#1890ff", "overlay": True},
        {"name": "SMA20", "data": sma_long.tolist(), "color": "#ff7a45", "overlay": True}
    ],
    "signals": [
        {"type": "buy", "text": "B", "data": buy.tolist(), "color": "#00E676"},
        {"type": "sell", "text": "S", "data": sell.tolist(), "color": "#FF5252"}
    ]
}
`;

export const useIndicators = () => {
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 获取指标列表
  const fetchIndicators = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await indicatorApi.getIndicators();
      setIndicators(data);
    } catch (err: any) {
      setError(err.message || '获取指标列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // 创建指标
  const createIndicator = useCallback(async (data: Partial<Indicator>) => {
    setLoading(true);
    setError(null);
    try {
      const result = await indicatorApi.createIndicator(data);
      await fetchIndicators();
      return result;
    } catch (err: any) {
      setError(err.message || '创建指标失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [fetchIndicators]);

  // 更新指标
  const updateIndicator = useCallback(async (id: number, data: Partial<Indicator>) => {
    setLoading(true);
    setError(null);
    try {
      const result = await indicatorApi.updateIndicator(id, data);
      await fetchIndicators();
      return result;
    } catch (err: any) {
      setError(err.message || '更新指标失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [fetchIndicators]);

  // 删除指标
  const deleteIndicator = useCallback(async (id: number) => {
    setLoading(true);
    setError(null);
    try {
      await indicatorApi.deleteIndicator(id);
      await fetchIndicators();
    } catch (err: any) {
      setError(err.message || '删除指标失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [fetchIndicators]);

  // 验证指标代码
  const verifyCode = useCallback(async (code: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await indicatorApi.verifyCode(code);
      return result;
    } catch (err: any) {
      setError(err.message || '代码验证失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // 执行指标计算
  const executeIndicator = useCallback(async (id: number, _params?: IndicatorParams) => {
    setLoading(true);
    setError(null);
    try {
      const result = await indicatorApi.getIndicatorParams(id);
      return result;
    } catch (err: any) {
      setError(err.message || '执行指标失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // AI生成代码（SSE流式）
  const aiGenerateCode = useCallback((
    prompt: string,
    existingCode: string = '',
    onChunk: (chunk: string) => void,
    onComplete: () => void,
    onError: (error: string) => void
  ) => {
    const url = '/api/indicators/ai-generate';
    const eventSource = new EventSource(`${url}?prompt=${encodeURIComponent(prompt)}&existing_code=${encodeURIComponent(existingCode)}`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.chunk) {
          onChunk(data.chunk);
        }
        if (data.complete) {
          eventSource.close();
          onComplete();
        }
        if (data.error) {
          eventSource.close();
          onError(data.error);
        }
      } catch (err) {
        onChunk(event.data);
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      onError('SSE连接错误');
    };

    return () => {
      eventSource.close();
    };
  }, []);

  // 获取单个指标
  const getIndicator = useCallback(async (id: number) => {
    setLoading(true);
    setError(null);
    try {
      const result = await indicatorApi.getIndicator(id);
      return result;
    } catch (err: any) {
      setError(err.message || '获取指标失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIndicators();
  }, [fetchIndicators]);

  return {
    indicators,
    loading,
    error,
    fetchIndicators,
    createIndicator,
    updateIndicator,
    deleteIndicator,
    verifyCode,
    executeIndicator,
    aiGenerateCode,
    getIndicator,
    builtInIndicators
  };
};

export default useIndicators;
