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
  plugins: [
    react(),
    tailwindcss(),
    // 不启用 @originjs/vite-plugin-federation：src 内无 loadRemote/registerRemotes
    // 调用。它会生成 __federation_shared_react* chunk，与下方 manualChunks 的
    // react-vendor 争抢 react 模块实例，在 WKWebView 的 tauri:// 协议下形成 chunk
    // 初始化环（Cannot access 'Kp' before initialization）导致入口白屏。
    // 注意：index.html 里的 importmap 与 public/@react-*-proxy.js 是【刻意保留】的，
    // 它们只服务于 PluginRegistry 运行时动态 import 的外部插件 bundle（裸 react
    // specifier 在浏览器侧解析到 window.React）；主应用的 react 在打包期已被正常
    // 收进 react-vendor，不经 importmap，故对主 bundle 无影响。
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
    // Tauri dev 固定连 5173（devUrl），端口被占时直接失败而非静默漂移
    strictPort: true,
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
          // Ant Design 及其图标库必须在同一 chunk：antd 与 @ant-design/icons
          // 存在循环引用，拆成 ui-vendor / icons-vendor 两个 chunk 后，
          // WKWebView（tauri:// 协议）的模块求值顺序会命中 ESM TDZ：
          // "Cannot access '_p' before initialization"，导致入口 import 阶段
          // 整个崩溃白屏。普通浏览器求值顺序恰好不触发，但这是脆弱的偶然，
          // 同 chunk 打包才是根治（普通 http 下同样更稳）。
          if (
            pkg === 'antd' ||
            pkg === '@ant-design/icons' ||
            pkg === '@tabler/icons-react' ||
            pkg === '@web3icons/react'
          ) {
            return 'ui-vendor'
          }
          // Ant Design X（AIChat 弹窗专属组件，单向依赖 antd，独立分块安全）
          if (pkg === '@ant-design/x') {
            return 'antd-x-vendor'
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
    // antd 与图标库合并后 ui-vendor 约 1.3MB 属正常体量
    chunkSizeWarningLimit: 1500,
    // ponytail: 生产构建移除所有 console.log/debugger
    esbuild: {
      drop: ['console', 'debugger'],
    },
    // 压缩配置 - 使用 esbuild 减少内存使用
    minify: 'esbuild',
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
