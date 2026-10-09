// 冷启动遮罩：sidecar onefile 自解压约 1 分钟，需在 React 业务 bundle
// 渲染前给用户反馈。直接操作 DOM，避免被懒加载/异常波及。

const SPLASH_ID = '__qc_desktop_splash__';

/**
 * 动画 logo SVG 标记（内联而非 <img src>，因为 WebKit 不支持通过 <img> 加载的
 * 外部 SVG 中的内部 CSS @keyframes 动画）。动画 CSS 在 STYLE 常量中定义。
 */
const LOGO_SVG = `<svg class="qc-logo" xmlns="http://www.w3.org/2000/svg" viewBox="-6 -6 44 44" width="44" height="44">
  <defs>
    <linearGradient id="qcGreenBlockGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#22c55e;stop-opacity:1" />
      <stop offset="50%" style="stop-color:#16a34a;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#15803d;stop-opacity:1" />
    </linearGradient>
    <filter id="qcDropShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="1" stdDeviation="1.5" flood-color="#000000" flood-opacity="0.3"/>
    </filter>
    <filter id="qcGreenGlow" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="0.5" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <g class="qc-rotate-wrap">
    <g filter="url(#qcDropShadow)">
      <path d="M 4 2 L 24 2 C 26 2, 26 4, 26 4 L 26 17 L 21 17 L 21 7 L 7 7 L 7 20.9 L 17 20.9 L 17 26 L 4 26 C 2 26, 2 24, 2 24 L 2 4 C 2 2, 4 2, 4 2 Z" fill="#0ea5e9"/>
    </g>
    <rect x="19" y="19" width="9" height="9" rx="2.5" ry="2.5" fill="url(#qcGreenBlockGrad)" filter="url(#qcGreenGlow)" stroke="rgba(255,255,255,0.3)" stroke-width="0.5"/>
    <rect x="20.5" y="20.5" width="3" height="3" rx="0.6" fill="white" opacity="0.4"/>
  </g>
  <g class="qc-breath">
    <rect x="11.2" y="11.2" width="5.6" height="5.6" rx="1.7" ry="1.7" fill="url(#qcGreenBlockGrad)" filter="url(#qcGreenGlow)" stroke="rgba(255,255,255,0.5)" stroke-width="0.5"/>
    <rect x="12.3" y="12.3" width="2.2" height="2.2" rx="0.6" fill="white" opacity="0.4"/>
  </g>
</svg>`;

const STYLE = `
#${SPLASH_ID} {
  position: fixed; inset: 0; z-index: 99999;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 18px; background: #0b1220; color: #e5e7eb;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}
#${SPLASH_ID} .qc-logo { display: block; }
/* logo 旋转 + 呼吸动画（定义在此而非内联 SVG style，确保 WebKit 下也能播放） */
#${SPLASH_ID} .qc-rotate-wrap {
  transform-origin: 14px 14px;
  animation: qc-rotate 2.5s ease-in-out infinite;
}
@keyframes qc-rotate {
  0% { transform: rotate(0deg); }
  20% { transform: rotate(360deg); }
  100% { transform: rotate(360deg); }
}
#${SPLASH_ID} .qc-breath {
  transform-origin: 14px 14px;
  animation: qc-breath 2.5s ease-in-out infinite;
}
@keyframes qc-breath {
  0% { transform: scale(0.75); }
  50% { transform: scale(1.3); }
  100% { transform: scale(0.75); }
}
#${SPLASH_ID} .qc-title { font-size: 20px; font-weight: 600; letter-spacing: .04em; }
#${SPLASH_ID} .qc-msg { font-size: 13px; color: #94a3b8; max-width: 420px; text-align: center; line-height: 1.6; }
#${SPLASH_ID} button {
  margin-top: 8px; padding: 6px 18px; border-radius: 8px; border: none;
  background: #2563eb; color: #fff; font-size: 13px; cursor: pointer;
}
`;

/** 生成遮罩内容 HTML（纯函数，便于在 node 环境单测） */
export function splashMarkup(message: string, withLogo = true): string {
  return (
    (withLogo ? LOGO_SVG : '') +
    '<div class="qc-title">QuantCell</div>' +
    `<div class="qc-msg">${message}</div>`
  );
}

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

export function updateSplash(message: string, withLogo = true): void {
  const el = document.getElementById(SPLASH_ID);
  if (!el) return;
  el.innerHTML = splashMarkup(message, withLogo);
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
