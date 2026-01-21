import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path
      }
    }
  },
  build: {
    // 调整 chunk 大小警告阈值
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        // 优化 chunk 命名
        chunkFileNames: 'assets/[name]-[hash].js',
        // 增强 manualChunks 配置
        manualChunks: (id) => {
          // 将大型依赖拆分为独立 chunk
          if (id.includes('node_modules')) {
            // 特别处理大型库
            if (id.includes('@web3icons')) {
              return 'web3icons';
            }
            if (id.includes('echarts')) {
              return 'echarts';
            }
            if (id.includes('klinecharts')) {
              return 'klinecharts';
            }
            if (id.includes('antd') || id.includes('@ant-design') || id.includes('@rc-component')) {
              return 'antd';
            }
            if (id.includes('monaco-editor')) {
              return 'monaco-editor';
            }
            // 合并小型 React 生态依赖
            if (id.includes('react') || id.includes('react-dom') || id.includes('react-router') || id.includes('zustand')) {
              return 'react-core';
            }
            // 其他依赖按包名拆分
            return id.toString().split('node_modules/')[1].split('/')[0];
          }
        }
      }
    }
  },
  // 配置别名
  resolve: {
    alias: {
      '@plugins': resolve(__dirname, 'src/plugins'),
      '@i18n': resolve(__dirname, '../i18n')
    }
  },
  // 开发服务器配置
  optimizeDeps: {
    // 确保插件被正确处理
    include: ['react', 'react-dom', 'react-router-dom']
  }
})
