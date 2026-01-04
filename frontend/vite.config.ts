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
        manualChunks: undefined
      }
    }
  },
  // 配置插件目录别名
  resolve: {
    alias: {
      '@plugins': resolve(__dirname, 'src/plugins')
    }
  },
  // 开发服务器配置
  optimizeDeps: {
    // 确保插件被正确处理
    include: ['react', 'react-dom', 'react-router-dom']
  }
})
