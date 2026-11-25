/**
 * 主题体系守卫测试 —— 保证品牌色"单一真相源"不被悄悄破坏
 *
 * 守卫三条断言链：
 *   1. palettes.ts：每个注册主题亮/暗两套字段齐全、值合法（hex / rgba）。
 *   2. 渠道映射：CSS 变量（含 --tw-color-* 旧名别名）与 antd token 由同一 palette 派生。
 *   3. 消费端同步：index.html 首帧背景兜底、global.css 零颜色字面量 —— 编辑 palette 后必须同步。
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { paletteToTradingToken, getCssVars, getPalette, themeAlgorithm } from './index';
import { THEMES } from './palettes';
import { ACTIVE_THEME_ID, resolveTheme } from './config';
import { THEME_MODES, THEME_PALETTE_FIELDS, THEME_EFFECT_FIELDS, COLOR_RE } from './fields';
import type { ThemeMode } from './types';

const src = (p: string) => readFileSync(fileURLToPath(new URL(p, import.meta.url)), 'utf8');

const REQUIRED_FIELDS = THEME_PALETTE_FIELDS;
const MODES: ThemeMode[] = THEME_MODES;

describe('theme: antd 算法主色', () => {
  // 暗色下 darkAlgorithm 会把 seed 主色重生成暗色调色板（#f97316 → #d76516），
  // 导致 antd 按钮与 --qc-primary 出现两种橙。themeAlgorithm 必须把它钉回 palette。
  it('暗色算法把 primary 一族钉回 palette 主色', () => {
    const p = getPalette('dark');
    const algo = themeAlgorithm('dark');
    const out = algo({ colorPrimary: '#000000' } as never);
    expect(out.colorPrimary).toBe(p.primary);
    expect(String(out.colorPrimaryBg)).toContain('color-mix');
    expect(out.colorPrimaryHover).not.toBe('#000000');
  });

  it('亮色仍直接使用 antd defaultAlgorithm（不介入派生）', () => {
    const p = getPalette('light');
    const out = themeAlgorithm('light')({ colorPrimary: p.primary } as never);
    expect(out.colorPrimary).toBe(p.primary);
  });
});

describe('theme: palettes.ts', () => {
  it('至少注册一个主题，且 ACTIVE_THEME_ID 指向已注册主题', () => {
    expect(Object.keys(THEMES).length).toBeGreaterThan(0);
    expect(THEMES[ACTIVE_THEME_ID]).toBeDefined();
    expect(resolveTheme().light).toBeDefined();
  });

  it.each(MODES)('%s palette 字段齐全且取值合法', (mode) => {
    for (const [name, theme] of Object.entries(THEMES)) {
      const palette = theme[mode];
      for (const field of REQUIRED_FIELDS) {
        const v = palette[field];
        expect(v, `${name}.${mode}.${field}`).toBeDefined();
        if (field === 'chartSeries' || field === 'chartPlotExtra') {
          expect((v as string[]).length).toBeGreaterThanOrEqual(2);
          (v as string[]).forEach((c) => expect(c).toMatch(COLOR_RE));
        } else {
          expect(v as string, `${name}.${mode}.${field}`).toMatch(COLOR_RE);
        }
      }
    }
  });
});

describe('theme: 渠道映射由同一 palette 派生', () => {
  it.each(MODES)('CSS 变量与 antd token 与 %s palette 一致', (mode) => {
    const p = getPalette(mode);
    const vars = getCssVars(mode);
    const token = paletteToTradingToken(mode);

    // 规范名
    expect(vars['--qc-primary']).toBe(p.primary);
    expect(vars['--qc-bg']).toBe(p.background);
    expect(vars['--qc-text']).toBe(p.foreground);
    expect(vars['--qc-border']).toBe(p.border);
    expect(vars['--qc-success']).toBe(p.success);
    // design-spec §2.1 / §10.3 新增槽位
    expect(vars['--qc-canvas']).toBe(p.canvas);
    expect(vars['--qc-text-quaternary']).toBe(p.textQuaternary);
    expect(vars['--qc-border-strong']).toBe(p.borderStrong);
    expect(vars['--qc-on-primary']).toBe(p.onPrimary);
    expect(vars['--qc-shadow-card']).toBe(p.shadowCard);
    // 旧名别名与规范名取值一致（消费端逐步迁移，别名不能漂移）
    expect(vars['--tw-color-background']).toBe(p.background);
    expect(vars['--tw-color-foreground']).toBe(p.foreground);
    expect(vars['--tw-color-border-secondary']).toBe(p.borderSubtle);
    // antd token
    expect(token.colorPrimary).toBe(p.primary);
    expect(token.colorBgBase).toBe(p.background);
    expect(token.colorBgLayout).toBe(p.canvas);
    expect(token.colorTextSecondary).toBe(p.textSecondary);
    expect(token.colorChartLine).toBe(p.chartLine);
    expect(token.chartSeries).toEqual(p.chartSeries);
  });

  it.each(MODES)('%s palette 的 effect 槽位（阴影）是非空字符串', (mode) => {
    for (const [name, theme] of Object.entries(THEMES)) {
      const palette = theme[mode];
      for (const field of THEME_EFFECT_FIELDS) {
        const v = palette[field];
        expect(typeof v, `${name}.${mode}.${field}`).toBe('string');
        expect(v.trim(), `${name}.${mode}.${field}`).not.toBe('');
      }
    }
  });
});

describe('theme: 消费端同步', () => {
  it('index.html 首帧背景兜底与 palette 页面底色一致', () => {
    const html = src('../../index.html');
    expect(html).toMatch(/<style>[^<]*html\s*\{[^}]*background-color:\s*#ffffff/m);
    expect(html).toMatch(/html\.dark\s*\{[^}]*background-color:\s*#17191c/m);
  });

  it('global.css / index.css 不持有颜色字面量（真相源只在 palettes.ts）', () => {
    for (const file of ['../global.css', '../index.css']) {
      const hexes = src(file).match(/#[0-9a-fA-F]{3,8}\b/g) ?? [];
      expect(hexes, `${file} 残留颜色字面量: ${hexes.join(', ')}`).toEqual([]);
    }
  });
});
