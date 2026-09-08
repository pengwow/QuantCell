import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import federation from '@originjs/vite-plugin-federation'
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
  plugins: [
    react(),
    tailwindcss(),
    federation({
      name: 'quantcell-host',
      shared: ['react', 'react-dom'],
    }),
  ],
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
        ws: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
        // 添加错误处理，避免 EPIPE 错误导致崩溃
        configure: (proxy) => {
          proxy.on('error', (err) => {
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
    // 代码分割配置 - 减少内存使用
    rollupOptions: {
      // Circular chunk 由 vite-plugin-federation 的 shared react/react-dom 包装与手动分包叠加产生，
      // 属规范内的已知噪声（产物无真实循环依赖），仅告警非错误，故显式忽略该告警
      onwarn: (warning, warn) => {
        if (typeof warning === 'object' && warning.code === 'CIRCULAR_CHUNK') return
        warn(warning)
      },
      output: {
        // 简化代码分割策略，减少并行处理和内存使用
        manualChunks: (id) => {
          if (!id.includes('node_modules')) return
          // 提取 node_modules 下的主包名（含 @scope/name），按精确包名分组，避免子串误匹配导致循环依赖
          const match = id.match(/node_modules\/(@[^/]+\/[^/]+|[^/]+)/)
          const pkg = match ? match[1] : ''
          // React 生态
          if (
            pkg === 'react' ||
            pkg === 'react-dom' ||
            pkg === 'react-router' ||
            pkg === 'react-router-dom' ||
            pkg === 'react-i18next' ||
            pkg === 'zustand'
          ) {
            return 'react-vendor'
          }
          // Ant Design 生态
          if (pkg === 'antd') {
            return 'ui-vendor'
          }
          // Ant Design X（AIChat 弹窗专属组件，独立分块避免混入 antd 主包）
          if (pkg === '@ant-design/x') {
            return 'antd-x-vendor'
          }
          // 图标库独立分块（被多个页面按需具名引用，拆开避免撑大 ui-vendor）
          if (pkg === '@ant-design/icons' || pkg === '@tabler/icons-react' || pkg === '@web3icons/react') {
            return 'icons-vendor'
          }
          // 图表库：klinecharts 用于主行情图（首屏），echarts 仅模型管理页使用，拆开避免首屏携带 echarts
          if (pkg === 'klinecharts') {
            return 'kline-vendor'
          }
          if (pkg === 'echarts' || pkg === 'echarts-for-react') {
            return 'chart-vendor'
          }
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
    // 代码分割大小限制：antd 主包拆分后约 1.2MB 属正常体量，阈值上调到 1300 消除误报
    chunkSizeWarningLimit: 1300,
    // 压缩配置 - 使用 esbuild 减少内存使用
    minify: 'esbuild',
    // esbuild 的 drop 选项在 Vite 中通过 rollup 插件配置
    // CSS 代码分割
    cssCodeSplit: true,
    // 禁用预加载减少内存使用
    modulePreload: false,
    // 资源内联限制
    assetsInlineLimit: 4096,
    // 源码映射
    sourcemap: false,
    // 限制并发数，减少内存使用
    reportCompressedSize: false,
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
