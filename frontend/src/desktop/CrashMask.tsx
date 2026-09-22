import { useEffect, useState } from 'react';
import { onBackendEvent, restartBackend, type BackendEvent } from './bridge';
import { getDesktopRuntime } from './env';
import { updateSplash, showSplash } from './splash';

/**
 * 全局崩溃守护：local 模式下 sidecar 非正常退出时显示遮罩并允许重启。
 * 重启成功后整页 reload——业务页面持有多条 WS/SSE 连接，整页重载比逐个
 * 重连更简单可靠，且会重新走一遍 bootstrap 拿到新端口。
 */
export default function CrashMask() {
  const [crashed, setCrashed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    void onBackendEvent((event: BackendEvent) => {
      if (event.status === 'crashed' && getDesktopRuntime().mode === 'local') {
        setCrashed(true);
      }
    }).then((fn) => {
      unlisten = fn;
    });
    return () => unlisten?.();
  }, []);

  if (!crashed) return null;

  const handleRestart = async () => {
    setBusy(true);
    showSplash('正在重启本机后端…');
    try {
      const cfg = await restartBackend();
      const base = cfg.baseUrl;
      if (base) {
        // 等新实例健康（冷启约 1 分钟）
        for (let i = 0; i < 90; i++) {
          try {
            const res = await fetch(`${base}/health`);
            if (res.ok) {
              window.location.reload();
              return;
            }
          } catch {
            // 尚未就绪
          }
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
      throw new Error('重启超时');
    } catch (e) {
      updateSplash(`后端重启失败：${e instanceof Error ? e.message : String(e)}`, false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99998,
        background: 'rgba(11,18,32,.92)',
        color: '#fee2e2',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 16,
        fontFamily: '-apple-system, "PingFang SC", sans-serif',
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 600 }}>本机后端已退出（非正常停止）</div>
      <button
        type="button"
        disabled={busy}
        onClick={handleRestart}
        style={{
          padding: '8px 22px',
          borderRadius: 8,
          border: 'none',
          background: busy ? '#64748b' : '#dc2626',
          color: '#fff',
          fontSize: 14,
          cursor: busy ? 'default' : 'pointer',
        }}
      >
        {busy ? '重启中…' : '重启后端'}
      </button>
    </div>
  );
}
