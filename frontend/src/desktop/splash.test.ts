import { describe, expect, it } from 'vitest';
import { splashMarkup } from './splash';

describe('splashMarkup', () => {
  it('默认渲染动画 logo（内联 SVG + 旋转/呼吸类名）、标题与文案', () => {
    const html = splashMarkup('正在启动本机后端…');
    expect(html).toContain('<svg class="qc-logo"');
    expect(html).toContain('qc-rotate-wrap');
    expect(html).toContain('qc-breath');
    expect(html).toContain('<div class="qc-title">QuantCell</div>');
    expect(html).toContain('<div class="qc-msg">正在启动本机后端…</div>');
  });

  it('withLogo=false 时不渲染 logo（错误态/重启失败态）', () => {
    const html = splashMarkup('后端重启失败', false);
    expect(html).not.toContain('qc-logo');
    expect(html).toContain('<div class="qc-title">QuantCell</div>');
    expect(html).toContain('后端重启失败');
  });

  it('不再包含旧的转圈 spinner', () => {
    expect(splashMarkup('x')).not.toContain('qc-spin');
  });
});
