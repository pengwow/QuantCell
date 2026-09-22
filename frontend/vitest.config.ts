import { defineConfig } from 'vitest/config';
import path from 'path';

// 桌面适配层纯函数测试用 node 环境（不引 jsdom）；
// 需要 DOM 的判定一律抽成可注入参数的纯函数
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
