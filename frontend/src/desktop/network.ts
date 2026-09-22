import { getDesktopRuntime } from './env';

// 后端 API/WS 的相对路径前缀；WS 流地址实际也挂在 /api/v1 下（如回测进度流）
const API_PREFIXES = ['/api', '/ws'];

export interface RewriteInput {
  url: string;
  /** 后端 base（http/https），null 表示未就绪，一律透传 */
  baseUrl: string | null;
  /** 页面自身 location.host，用于识别误指向壳自身的绝对 URL */
  pageHost: string;
}

function startsWithBackendPath(pathname: string): boolean {
  // startsWith 已同时覆盖 '/api'、'/api/...'；命中面仅限这两个保留前缀
  return API_PREFIXES.some((p) => pathname.startsWith(p));
}

/** HTTP/HTTPS：相对 /api|/ws 前置 base；host=页面自身的绝对后端 URL 换 origin */
export function rewriteHttpUrl({ url, baseUrl, pageHost }: RewriteInput): string {
  if (!baseUrl) return url;
  if (startsWithBackendPath(url)) return `${baseUrl}${url}`;
  try {
    const u = new URL(url);
    if ((u.protocol === 'http:' || u.protocol === 'https:') && u.host === pageHost
        && startsWithBackendPath(u.pathname)) {
      return `${baseUrl}${u.pathname}${u.search}${u.hash}`;
    }
  } catch {
    // 非绝对 URL（如 data:、blob: 或畸形 URL），不在重写范围，透传
  }
  return url;
}

function toWsBase(baseUrl: string): string {
  return baseUrl.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
}

/** WebSocket：规则同 HTTP，协议按后端 base 同步取 ws/wss */
export function rewriteWsUrl({ url, baseUrl, pageHost }: RewriteInput): string {
  if (!baseUrl) return url;
  const wsBase = toWsBase(baseUrl);
  if (startsWithBackendPath(url)) return `${wsBase}${url}`;
  try {
    const u = new URL(url);
    if ((u.protocol === 'ws:' || u.protocol === 'wss:') && u.host === pageHost
        && startsWithBackendPath(u.pathname)) {
      return `${wsBase}${u.pathname}${u.search}`;
    }
  } catch {
    // 透传非绝对 URL
  }
  return url;
}

const PATCH_FLAG = '__QC_NET_PATCHED__';

/**
 * 在 Tauri 环境安装全局网络重写（幂等）。
 * ponytail: 猴子补丁是有意为之——16 处相对 fetch + 3 处手工拼 WS 分散在各页面，
 * 单点改写比逐个调用点修改侵入小且不会漏新代码；上限：升级 Vite/Tauri 大版本
 * 或后端 API 前缀调整时需回归 network.test.ts。
 */
export function installNetworkBridge(): void {
  const g = globalThis as unknown as Record<string, unknown>;
  if (g[PATCH_FLAG]) return;

  const origFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const raw =
      typeof input === 'string' ? input
      : input instanceof URL ? input.href
      : input.url; // Request
    const { baseUrl } = getDesktopRuntime();
    const rewritten = rewriteHttpUrl({ url: raw, baseUrl, pageHost: window.location.host });
    if (rewritten === raw) return origFetch(input, init);
    if (typeof input === 'string' || input instanceof URL) {
      return origFetch(rewritten, init);
    }
    // Request：以原 Request 为模板复制（继承 method/headers/body），仅换 URL
    return origFetch(new Request(rewritten, input), init);
  };

  const OrigWebSocket = window.WebSocket;
  class PatchedWebSocket extends OrigWebSocket {
    constructor(url: string | URL, protocols?: string | string[]) {
      const raw = url instanceof URL ? url.href : url;
      const { baseUrl } = getDesktopRuntime();
      const rewritten = rewriteWsUrl({ url: raw, baseUrl, pageHost: window.location.host });
      super(rewritten, protocols);
    }
  }
  window.WebSocket = PatchedWebSocket as typeof WebSocket;

  g[PATCH_FLAG] = true;
}
