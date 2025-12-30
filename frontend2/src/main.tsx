import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import './index.css'
import 'antd/dist/reset.css'
import { router } from './router'
import { loadConfig, updateConfig } from './utils/configLoader'

/**
 * 渲染应用
 * 1. 先加载配置数据
 * 2. 将配置挂载到window对象
 * 3. 渲染应用组件
 */
async function renderApp() {
  try {
    // 加载配置数据
    const configData = await loadConfig();
    
    // 将配置挂载到window对象
    updateConfig(configData);
    
    // 渲染应用
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        <RouterProvider router={router} />
      </StrictMode>,
    );
  } catch (error) {
    console.error('应用初始化失败:', error);
    // 即使配置加载失败，也尝试渲染应用
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        <RouterProvider router={router} />
      </StrictMode>,
    );
  }
}

// 启动应用渲染
renderApp();
