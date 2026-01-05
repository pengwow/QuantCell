import { createBrowserRouter, Navigate } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';

// 导入页面组件
import App from '../App';
import StrategyAgent from '../views/StrategyAgent';
import Setting from '../views/Setting';
import DataManagement from '../views/DataManagement';
import FactorAnalysis from '../views/FactorAnalysis';
import ModelManagement from '../views/ModelManagement';
import BacktestResults from '../views/BacktestResults';
import BacktestReplay from '../views/BacktestReplay';
import ChartPage from '../views/ChartPage';
import ScheduledTasks from '../views/ScheduledTasks';
import ScheduledTaskForm from '../views/ScheduledTasks/ScheduledTaskForm';

// 导入插件管理器
import { pluginManager } from '../plugins';

// 插件页面样式包裹组件
const PluginPageWrapper = ({ children }: { children: React.ReactNode }) => {
  return (
    <div style={{ 
      background: 'white', 
      borderRadius: '8px', 
      boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)', 
      padding: '20px', 
      minWidth: 0 
    }}>
      {children}
    </div>
  );
};

/**
 * 创建路由配置
 * @returns 路由实例
 */
export const createRouter = () => {
  // 基础路由配置
  const baseRoutes: RouteObject[] = [
    {
      path: '/',
      element: <App />,
      children: [
        {
          path: '/agent/StrategyAgent',
          element: <StrategyAgent />
        },
        {
          path: '/setting',
          element: <Setting />
        },
        {
          path: '/data-management',
          element: <DataManagement />
        },
        {
          path: '/factor-analysis',
          element: <FactorAnalysis />
        },
        {
          path: '/model-management',
          element: <ModelManagement />
        },
        {
          path: '/backtest-results',
          element: <BacktestResults />
        },
        {
          path: '/chart',
          element: <ChartPage />
        },
        {
          path: '/scheduled-tasks',
          element: <ScheduledTasks />
        },
        {
          path: '/scheduled-tasks/create',
          element: <ScheduledTaskForm />
        },
        {
          path: '/scheduled-tasks/edit/:id',
          element: <ScheduledTaskForm />
        },
        {
          path: '/backtest/replay/:backtestId',
          element: <BacktestReplay />
        },
        // 默认重定向到策略代理页面
        {
          index: true,
          element: <Navigate to="/agent/StrategyAgent" replace />
        }
      ]
    }
  ];

  // 获取插件路由
  const pluginRoutes = pluginManager.getAllRoutes();
  
  // 将插件路由添加到基础路由的children中
  if (pluginRoutes.length > 0 && baseRoutes[0].children) {
    for (const route of pluginRoutes) {
      baseRoutes[0].children.push({
        path: route.path,
        element: <PluginPageWrapper>{route.element}</PluginPageWrapper>
      });
    }
  }

  return createBrowserRouter(baseRoutes);
};

// 创建初始路由
export let router = createRouter();

/**
 * 更新路由配置，用于插件加载后重新创建路由
 */
export const updateRouter = () => {
  router = createRouter();
};

/**
 * 设置页面标题
 * @param title 页面标题
 */
export const setPageTitle = (title?: string): void => {
  document.title = title || 'React App';
};
