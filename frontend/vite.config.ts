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
    // 代码分割配置 - 减少内存使用
    rollupOptions: {
      output: {
        // 简化代码分割策略，减少并行处理和内存使用
        manualChunks: (id) => {
          // 只将大型依赖分割到单独的 chunk
          if (id.includes('node_modules')) {
            // React 相关
            if (id.includes('react') || id.includes('react-dom') || id.includes('react-router')) {
              return 'react-vendor'
            }
            // Ant Design 相关
            if (id.includes('antd') || id.includes('@ant-design')) {
              return 'ui-vendor'
            }
            // 图表库
            if (id.includes('echarts') || id.includes('klinecharts')) {
              return 'chart-vendor'
            }
            // 其他依赖不单独分割，避免循环依赖
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
    // 代码分割大小限制
    chunkSizeWarningLimit: 1000,
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
