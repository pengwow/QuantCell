import { describe, expect, it } from 'vitest';
import { rewriteHttpUrl, rewriteWsUrl } from './network';

// local sidecar；pageHost 模拟 WKWebView 的 tauri://localhost（host=localhost，无端口）
const LOCAL = { baseUrl: 'http://127.0.0.1:58964', pageHost: 'localhost' };

describe('rewriteHttpUrl', () => {
  it('相对 /api 路径前置后端 base', () => {
    expect(rewriteHttpUrl({ url: '/api/v1/auth/logout', ...LOCAL })).toBe(
      'http://127.0.0.1:58964/api/v1/auth/logout',
    );
  });

  it('误指向页面 host 的绝对 /api URL 替换 origin 并保留 query', () => {
    const out = rewriteHttpUrl({
      url: 'http://localhost/api/v1/x?a=1#frag',
      ...LOCAL,
    });
    expect(out).toBe('http://127.0.0.1:58964/api/v1/x?a=1#frag');
  });

  it('第三方绝对 URL 原样透传', () => {
    const url = 'https://api.github.com/repos';
    expect(rewriteHttpUrl({ url, ...LOCAL })).toBe(url);
  });

  it('已指向后端的 URL 原样透传', () => {
    const url = 'http://127.0.0.1:58964/health';
    expect(rewriteHttpUrl({ url, ...LOCAL })).toBe(url);
  });

  it('baseUrl 为 null 时一律透传', () => {
    expect(rewriteHttpUrl({ url: '/api/x', baseUrl: null, pageHost: 'localhost' })).toBe(
      '/api/x',
    );
  });

  it('非 http(s) 且非相对 API 路径原样透传', () => {
    expect(rewriteHttpUrl({ url: 'data:text/plain,hi', ...LOCAL })).toBe('data:text/plain,hi');
  });
});

describe('rewriteWsUrl', () => {
  it('相对 /ws 路径转后端 ws 地址', () => {
    expect(rewriteWsUrl({ url: '/ws/worker', ...LOCAL })).toBe(
      'ws://127.0.0.1:58964/ws/worker',
    );
  });

  it('手工拼的 ws://localhost/api 流地址替换 origin 为带端口的后端', () => {
    expect(
      rewriteWsUrl({
        url: 'ws://localhost/api/v1/backtest/progress/123/stream',
        ...LOCAL,
      }),
    ).toBe('ws://127.0.0.1:58964/api/v1/backtest/progress/123/stream');
  });

  it('remote https 后端派生 wss', () => {
    expect(
      rewriteWsUrl({
        url: 'wss://tauri.localhost/ws/worker',
        baseUrl: 'https://api.example.com',
        pageHost: 'tauri.localhost',
      }),
    ).toBe('wss://api.example.com/ws/worker');
  });

  it('第三方 ws 透传', () => {
    const url = 'wss://stream.binance.com:9443/ws';
    expect(rewriteWsUrl({ url, ...LOCAL })).toBe(url);
  });
});
