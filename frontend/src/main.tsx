import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import './index.css'
import 'antd/dist/reset.css'
import { router, updateRouter } from './router'
import { loadConfig, updateConfig } from './utils/configLoader'
import { pluginManager } from './plugins'

/**
 * 渲染应用
 * 1. 先加载配置数据
 * 2. 将配置挂载到window对象
 * 3. 初始化插件系统
 * 4. 更新路由配置
 * 5. 渲染应用组件
 */
async function renderApp() {
  try {
    // 加载配置数据
    const configData = await loadConfig();
    
    // 将配置挂载到window对象
    updateConfig(configData);
    
    // 初始化插件系统
    await pluginManager.init();
    
    // 更新路由配置，包含插件路由
    updateRouter();
    
    // 渲染应用
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        <RouterProvider router={router} />
      </StrictMode>,
    );
  } catch (error) {
    console.error('应用初始化失败:', error);
    // 即使配置加载失败，也尝试渲染应用
    try {
      // 尝试初始化插件系统
      await pluginManager.init();
      // 更新路由配置
      updateRouter();
    } catch (pluginError) {
      console.error('插件初始化失败:', pluginError);
    }
    
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        <RouterProvider router={router} />
      </StrictMode>,
    );
  }
}

// 启动应用渲染
renderApp();
