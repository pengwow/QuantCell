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
    rollupOptions: {
      output: {
        // 移除 preserveModules 配置，避免构建失败
        // 动态导入由 Vite 自动处理
        manualChunks: (id) => {
          // 将大型依赖拆分为独立 chunk
          if (id.includes('node_modules')) {
            // 特别处理 web3icons，将其拆分为独立 chunk
            if (id.includes('@web3icons')) {
              return 'web3icons';
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
