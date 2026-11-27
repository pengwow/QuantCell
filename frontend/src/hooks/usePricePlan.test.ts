// @vitest-environment jsdom
// 全局 vitest.config.ts 是 node 环境（项目约定不引 jsdom）；本 hook 测试需要真实
// React 渲染（renderHook → createRoot），仅此文件启用 jsdom，全局配置不动
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usePricePlan } from './usePricePlan';
import * as api from '../api/pricePlanApi';

vi.mock('../api/pricePlanApi', () => ({
  previewPricePlan: vi.fn(),
}));

const mockedPreview = vi.mocked(api.previewPricePlan);
const PLAN = {
  levels: [{ index: 0, price: 100, action: 'buy' as const, target_position: 0.1, label: '入场' }],
  summary: { price_min: 100, price_max: 100, entry_price: 100, extra: {} },
  warnings: [],
  params_resolved: {},
};

beforeEach(() => {
  vi.useFakeTimers();
  mockedPreview.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('usePricePlan', () => {
  it('260ms 防抖后请求一次并回填', async () => {
    mockedPreview.mockResolvedValue(PLAN);
    const { result } = renderHook(() =>
      usePricePlan({ strategyName: 'grid', params: { levels: 4 }, refPrice: 100 }),
    );
    // fake timers 下 RTLwaitFor 的 interval 不推进会卡死，一律用 vi.waitFor（fake-timer-aware）
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    await vi.waitFor(() => expect(result.current.data).toEqual(PLAN));
    expect(mockedPreview).toHaveBeenCalledTimes(1);
  });

  it('连续变更只触发最后一次（防抖）', async () => {
    mockedPreview.mockResolvedValue(PLAN);
    const initial = { strategyName: 'grid', params: { levels: 4 }, refPrice: 100 };
    const { rerender } = renderHook(
      (p: typeof initial) => usePricePlan(p),
      { initialProps: initial },
    );
    // 只断言请求次数：防抖保证 preview 仅发出 1 次，且用最后一组参数
    rerender({ ...initial, params: { levels: 5 } });
    rerender({ ...initial, params: { levels: 6 } });
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(mockedPreview).toHaveBeenCalledTimes(1);
    expect(mockedPreview).toHaveBeenLastCalledWith(
      expect.objectContaining({ params: { levels: 6 } }),
    );
  });

  it('无参考价时静默不请求', () => {
    renderHook(() => usePricePlan({ strategyName: 'grid', params: {}, refPrice: null }));
    act(() => vi.advanceTimersByTime(500));
    expect(mockedPreview).not.toHaveBeenCalled();
  });

  it('422 错误读出可读 message', async () => {
    mockedPreview.mockRejectedValue({
      response: { data: { detail: { code: 'PLAN_UNSUPPORTED', message: '策略未声明 price_plan' } } },
    });
    const { result } = renderHook(() =>
      usePricePlan({ strategyName: 'grid', params: {}, refPrice: 100 }),
    );
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    await vi.waitFor(() => expect(result.current.error).toContain('price_plan'));
    expect(result.current.data).toBeNull();
  });
});
