// extractBackendErrorMessage 最小自检：用 strategy/generate 400 的真实响应体形状
// （curl 实录）驱动，守护"气泡永不渲染 [object Object]"这一条。
import { describe, expect, it } from 'vitest';
import { extractBackendErrorMessage } from './StrategyChatProvider';

describe('extractBackendErrorMessage', () => {
  it('FastAPI HTTPException 嵌套 detail（实测 400 体）取 message', () => {
    const body = {
      detail: { message: '未配置默认AI模型', error: '请先配置AI模型并设置默认提供商' },
    };
    expect(extractBackendErrorMessage(body)).toBe('未配置默认AI模型');
  });

  it('ApiResponse 形状取顶层 message；裸字符串 detail 同样可读', () => {
    expect(extractBackendErrorMessage({ message: '上游超时' })).toBe('上游超时');
    expect(extractBackendErrorMessage('参数不合法')).toBe('参数不合法');
    expect(extractBackendErrorMessage({ detail: '参数不合法' })).toBe('参数不合法');
  });

  it('中间层无可读文案时由顶层兜底 stringify，绝不产出 [object Object]', () => {
    expect(extractBackendErrorMessage({ message: { code: 400 } })).toBe('{"message":{"code":400}}');
  });

  it('无法提取时 stringify 整体；原始类型返回 null 交给调用方兜底', () => {
    expect(extractBackendErrorMessage({ foo: 'bar' })).toBe('{"foo":"bar"}');
    expect(extractBackendErrorMessage(42)).toBeNull();
    expect(extractBackendErrorMessage(null)).toBeNull();
    expect(extractBackendErrorMessage('   ')).toBeNull();
  });

  it('深度超过 2 层不再下钻', () => {
    expect(extractBackendErrorMessage({ detail: { error: { message: '太深' } } })).toBe(
      '{"detail":{"error":{"message":"太深"}}}',
    );
  });
});
