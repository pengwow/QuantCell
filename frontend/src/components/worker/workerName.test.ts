// buildWorkerName 最小自检：唯一性核心冲突路径 + 短码形态
import { describe, expect, it } from 'vitest';
import { buildWorkerName } from './workerName';

describe('buildWorkerName', () => {
  it('形态=策略名_4位短码，短码字母表内且小写', () => {
    const name = buildWorkerName('dual_ma', []);
    expect(name).toMatch(/^dual_ma_[2-9a-hjkmnp-z]{4}$/);
  });

  it('与现有名单冲突时重试生成不冲突的', () => {
    const first = buildWorkerName('s', []);
    const code = first.slice('s_'.length);
    const name = buildWorkerName('s', [first, `s_${code.slice(0, 3)}x`]);
    expect(name).not.toBe(first);
    // 依然符合形态且非空
    expect(name).toMatch(/^s_[2-9a-hjkmnp-z]{4,6}$/);
  });

  it('冲突大小写不敏感：传入大写名单，生成的小写名不会撞上', () => {
    const taken = new Set(['DUAL_MA_ABCD']);
    for (let i = 0; i < 200; i++) {
      const n = buildWorkerName('dual_ma', taken);
      expect(taken.has(n.toLowerCase())).toBe(false);
      expect(n.toLowerCase()).not.toBe('dual_ma_abcd');
    }
  });

  it('策略名空白回退 worker；超长名单全部占用则加长到 6 位', () => {
    expect(buildWorkerName('   ', [])).toMatch(/^worker_[2-9a-hjkmnp-z]{4}$/);
  });
});
