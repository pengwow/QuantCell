import { describe, it, expect } from 'vitest';
import { PAGE_SIZE_OPTIONS, PER_PAGE_OPTIONS, snapPageSize } from './pagination';

describe('pagination 档位常量', () => {
  it('档位均为 12 的倍数且数字版与字符串版一一对应', () => {
    expect(PAGE_SIZE_OPTIONS).toEqual(['12', '24', '36', '48', '96']);
    expect(PER_PAGE_OPTIONS).toEqual([12, 24, 36, 48, 96]);
  });
});

describe('snapPageSize 旧值就近吸附', () => {
  it.each([
    [10, 12],
    [15, 12],
    [20, 24],
    [30, 36],
    [50, 48],
    [100, 96],
    // 已在新档位上的值保持不变
    [24, 24],
    [48, 48],
    // 非法/边界值兜底为最小档 12
    [0, 12],
    [-10, 12],
  ])('%i → %i', (input, expected) => {
    expect(snapPageSize(input)).toBe(expected);
  });
});
