import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

// ESM 兼容的 __dirname
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// 读取package.json获取版本号
const getAppVersion = () => {
  try {
    const packageJson = JSON.parse(fs.readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8'))
    return packageJson.version || '0.0.0'
  } catch {
    return '0.0.0'
  }
}

// 获取后端端口配置
const getBackendPort = () => {
  // 优先从环境变量读取
  const envPort = process.env.QUANTCELL_BACKEND_PORT
  if (envPort) {
    return parseInt(envPort, 10)
  }

  // 尝试从端口信息文件读取
  try {
    const portsFile = path.resolve(__dirname, '..', '.quantcell', 'ports.json')
    if (fs.existsSync(portsFile)) {
      const portsData = JSON.parse(fs.readFileSync(portsFile, 'utf-8'))
      if (portsData.backend && portsData.backend.port) {
        return portsData.backend.port
      }
    }
  } catch {
    // 读取失败时使用默认端口
  }

  return 8000
}

const backendPort = getBackendPort()

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(getAppVersion()),
    __BACKEND_PORT__: backendPort,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: `http://localhost:${backendPort}`,
        changeOrigin: true,
      },
      '/ws': {
        target: `ws://localhost:${backendPort}`,
        ws: true,
      },
    },
  },
})