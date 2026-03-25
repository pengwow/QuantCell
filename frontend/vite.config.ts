import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import fs from 'fs'

// 读取package.json获取版本号
const getAppVersion = () => {
  try {
    const packageJson = JSON.parse(fs.readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8'))
    return packageJson.version || '0.0.0'
  } catch {
    return '0.0.0'
  }
}

// 从环境变量获取host和port，使用默认值
const getServerConfig = () => {
  const host = process.env.VITE_HOST || 'localhost'
  const port = parseInt(process.env.VITE_PORT || '5173', 10)
  return { host, port }
}

const { host, port } = getServerConfig()

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(getAppVersion()),
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host,
    port,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
        // 添加错误处理，避免 EPIPE 错误导致崩溃
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, _res) => {
            // 只在非 EPIPE 错误时输出日志，减少日志噪音
            if (!err.message.includes('EPIPE') && !err.message.includes('ECONNRESET')) {
              console.log('WebSocket 代理错误:', err.message);
            }
          });
        },
      },
    },
  },
  build: {
    // 代码分割配置
    rollupOptions: {
      output: {
        // 手动代码分割策略
        manualChunks: {
          // React 核心库
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          // UI 组件库
          'ui-vendor': ['antd', '@ant-design/icons'],
          // 图表库
          'chart-vendor': ['echarts', 'echarts-for-react', 'klinecharts'],
          // 工具库
          'utils-vendor': ['lodash', 'dayjs', 'axios'],
          // 状态管理
          'state-vendor': ['zustand', 'immer'],
          // 国际化
          'i18n-vendor': ['i18next', 'react-i18next', 'i18next-browser-languagedetector'],
        },
        // 入口文件命名
        entryFileNames: 'assets/[name]-[hash].js',
        // 代码块文件命名
        chunkFileNames: 'assets/[name]-[hash].js',
        // 资源文件命名
        assetFileNames: (assetInfo) => {
          const info = assetInfo.name || ''
          if (info.endsWith('.css')) {
            return 'assets/css/[name]-[hash][extname]'
          }
          if (info.match(/\.(png|jpe?g|gif|svg|webp|ico)$/)) {
            return 'assets/images/[name]-[hash][extname]'
          }
          if (info.match(/\.(woff2?|eot|ttf|otf)$/)) {
            return 'assets/fonts/[name]-[hash][extname]'
          }
          return 'assets/[name]-[hash][extname]'
        },
      },
    },
    // 代码分割大小限制
    chunkSizeWarningLimit: 500,
    // 压缩配置
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
    // CSS 代码分割
    cssCodeSplit: true,
    // 预加载配置
    modulePreload: {
      polyfill: true,
    },
    // 资源内联限制
    assetsInlineLimit: 4096,
    // 源码映射
    sourcemap: false,
  },
  // 优化依赖预构建
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-router-dom',
      'antd',
      '@ant-design/icons',
      'echarts',
      'echarts-for-react',
      'klinecharts',
      'zustand',
      'i18next',
      'react-i18next',
    ],
    exclude: [],
  },
})
