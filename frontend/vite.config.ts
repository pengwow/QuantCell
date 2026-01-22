import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig(() => {
  // 检测环境变量，判断是否为Tauri打包环境
  // 可以通过命令行参数或.env文件设置 VITE_IS_TAURI=true
  // const isTauri = process.env.VITE_IS_TAURI === 'true';
  
  return {
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
            // // 特别处理 web3icons，将其拆分为独立 chunk
            // if (id.includes('@web3icons')) {
            //   return isTauri ? 'web3icons' : undefined;
            // }
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
  };
})
