/**
 * 技术指标管理Hook
 * 提供指标的CRUD操作、代码验证和AI生成功能
 */

import { useState, useCallback, useEffect } from 'react';

// 指标数据类型
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
  created_at?: string;
  updated_at?: string;
}

// 指标参数类型
export interface IndicatorParam {
  name: string;
  type: 'int' | 'float' | 'bool' | 'string';
  default: any;
  description: string;
}

// 活跃指标类型（用于图表显示）
export interface ActiveIndicator extends Indicator {
  params?: Record<string, any>;
  userParams?: Record<string, any>;
}

// API响应类型
interface ApiResponse<T> {
  code: number;
  msg?: string;
  data?: T;
}

// 使用indicators Hook
export const useIndicators = () => {
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 获取指标列表
  const fetchIndicators = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/indicators');
      const data = await response.json();
      // 确保数据是数组
      if (Array.isArray(data)) {
        setIndicators(data);
      } else if (data && Array.isArray(data.data)) {
        setIndicators(data.data);
      } else {
        setIndicators([]);
        console.warn('API 返回的指标数据不是数组:', data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取指标列表失败');
      setIndicators([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // 创建指标
  const createIndicator = useCallback(async (indicator: Partial<Indicator>) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/indicators', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(indicator),
      });
      const data: Indicator = await response.json();
      setIndicators(prev => [data, ...prev]);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建指标失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // 更新指标
  const updateIndicator = useCallback(async (id: number, indicator: Partial<Indicator>) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/indicators/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(indicator),
      });
      const data: Indicator = await response.json();
      setIndicators(prev => prev.map(item => item.id === id ? data : item));
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新指标失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // 删除指标
  const deleteIndicator = useCallback(async (id: number) => {
    setLoading(true);
    setError(null);
    try {
      await fetch(`/api/indicators/${id}`, { method: 'DELETE' });
      setIndicators(prev => prev.filter(item => item.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除指标失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // 验证代码
  const verifyCode = useCallback(async (code: string) => {
    try {
      const response = await fetch('/api/indicators/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      return await response.json();
    } catch (err) {
      throw err instanceof Error ? err : new Error('验证代码失败');
    }
  }, []);

  // 获取指标参数
  const getIndicatorParams = useCallback(async (indicatorId: number) => {
    try {
      const response = await fetch(`/api/indicators/${indicatorId}/params`);
      const data: ApiResponse<IndicatorParam[]> = await response.json();
      return data.data || [];
    } catch (err) {
      throw err instanceof Error ? err : new Error('获取指标参数失败');
    }
  }, []);

  // 执行指标计算
  const executeIndicator = useCallback(async (
    indicatorId: number,
    symbol: string,
    period: string,
    params?: Record<string, any>
  ) => {
    try {
      const response = await fetch(`/api/indicators/${indicatorId}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, period, params }),
      });
      const data = await response.json();
      return data;
    } catch (err) {
      throw err instanceof Error ? err : new Error('执行指标计算失败');
    }
  }, []);

  // AI生成代码（SSE流式）
  const aiGenerateCode = useCallback(async (
    prompt: string,
    existingCode?: string,
    onChunk?: (chunk: string) => void
  ) => {
    try {
      const response = await fetch('/api/indicators/ai-generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, existing_code: existingCode }),
      });

      if (!response.body) {
        throw new Error('无法获取响应流');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullCode = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.substring(6);
            if (data === '[DONE]') continue;

            try {
              const parsed = JSON.parse(data);
              if (parsed.content) {
                fullCode += parsed.content;
                onChunk?.(parsed.content);
              }
              if (parsed.done) {
                return fullCode;
              }
            } catch {
              // 忽略解析错误
            }
          }
        }
      }

      return fullCode;
    } catch (err) {
      throw err instanceof Error ? err : new Error('AI生成代码失败');
    }
  }, []);

  // 初始加载
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
    getIndicatorParams,
    executeIndicator,
    aiGenerateCode,
  };
};

// 内置指标定义
export const builtInIndicators = [
  { id: 'vol', name: 'VOL (成交量)', shortName: 'VOL', type: 'volume', defaultParams: { ma1: 5, ma2: 10 } },
  { id: 'sma', name: 'SMA (简单移动平均)', shortName: 'SMA', type: 'line', defaultParams: { length: 20 } },
  { id: 'ema', name: 'EMA (指数移动平均)', shortName: 'EMA', type: 'line', defaultParams: { length: 20 } },
  { id: 'rsi', name: 'RSI (相对强弱)', shortName: 'RSI', type: 'line', defaultParams: { length: 14 } },
  { id: 'macd', name: 'MACD', shortName: 'MACD', type: 'macd', defaultParams: { fast: 12, slow: 26, signal: 9 } },
  { id: 'bb', name: '布林带 (Bollinger Bands)', shortName: 'BB', type: 'band', defaultParams: { length: 20, mult: 2 } },
  { id: 'atr', name: 'ATR (平均真实波幅)', shortName: 'ATR', type: 'line', defaultParams: { period: 14 } },
  { id: 'cci', name: 'CCI (商品通道指数)', shortName: 'CCI', type: 'line', defaultParams: { length: 20 } },
  { id: 'williams', name: 'Williams %R (威廉指标)', shortName: 'W%R', type: 'line', defaultParams: { length: 14 } },
  { id: 'mfi', name: 'MFI (资金流量指标)', shortName: 'MFI', type: 'line', defaultParams: { length: 14 } },
  { id: 'adx', name: 'ADX (平均趋向指数)', shortName: 'ADX', type: 'adx', defaultParams: { length: 14 } },
  { id: 'obv', name: 'OBV (能量潮)', shortName: 'OBV', type: 'line', defaultParams: {} },
  { id: 'adosc', name: 'ADOSC (积累/派发振荡器)', shortName: 'ADOSC', type: 'line', defaultParams: { fast: 3, slow: 10 } },
  { id: 'ad', name: 'AD (积累/派发线)', shortName: 'AD', type: 'line', defaultParams: {} },
  { id: 'kdj', name: 'KDJ (随机指标)', shortName: 'KDJ', type: 'line', defaultParams: { period: 9, k: 3, d: 3 } },
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

export default useIndicators;
