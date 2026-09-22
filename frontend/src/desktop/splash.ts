// 冷启动遮罩：sidecar onefile 自解压约 1 分钟，需在 React 业务 bundle
// 渲染前给用户反馈。直接操作 DOM，避免被懒加载/异常波及。

const SPLASH_ID = '__qc_desktop_splash__';

const STYLE = `
#${SPLASH_ID} {
  position: fixed; inset: 0; z-index: 99999;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 18px; background: #0b1220; color: #e5e7eb;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}
#${SPLASH_ID} .qc-spin {
  width: 36px; height: 36px; border: 3px solid rgba(255,255,255,.18);
  border-top-color: #3b82f6; border-radius: 50%; animation: qc-rot .9s linear infinite;
}
#${SPLASH_ID} .qc-title { font-size: 20px; font-weight: 600; letter-spacing: .04em; }
#${SPLASH_ID} .qc-msg { font-size: 13px; color: #94a3b8; max-width: 420px; text-align: center; line-height: 1.6; }
#${SPLASH_ID} button {
  margin-top: 8px; padding: 6px 18px; border-radius: 8px; border: none;
  background: #2563eb; color: #fff; font-size: 13px; cursor: pointer;
}
@keyframes qc-rot { to { transform: rotate(360deg); } }
`;

export function showSplash(message: string): void {
  if (!document.getElementById(SPLASH_ID)) {
    const style = document.createElement('style');
    style.textContent = STYLE;
    document.head.appendChild(style);
    const el = document.createElement('div');
    el.id = SPLASH_ID;
    document.body.appendChild(el);
  }
  updateSplash(message);
}

export function updateSplash(message: string, withSpinner = true): void {
  const el = document.getElementById(SPLASH_ID);
  if (!el) return;
  el.innerHTML =
    (withSpinner ? '<div class="qc-spin"></div>' : '') +
    '<div class="qc-title">QuantCell</div>' +
    `<div class="qc-msg">${message}</div>`;
}

export function showSplashError(message: string, actionLabel: string, onAction: () => void): void {
  const el = document.getElementById(SPLASH_ID);
  if (!el) return;
  el.innerHTML =
    '<div class="qc-title">QuantCell</div>' +
    `<div class="qc-msg">${message}</div>`;
  const btn = document.createElement('button');
  btn.textContent = actionLabel;
  btn.onclick = onAction;
  el.appendChild(btn);
}

export function hideSplash(): void {
  document.getElementById(SPLASH_ID)?.remove();
}
