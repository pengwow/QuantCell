import { createBrowserRouter, Navigate } from 'react-router-dom';

// 导入页面组件
import App from '../App';
import StrategyAgent from '../views/StrategyAgent';
import Setting from '../views/Setting';
import DataManagement from '../views/DataManagement';
import FactorAnalysis from '../views/FactorAnalysis';
import ModelManagement from '../views/ModelManagement';
import BacktestResults from '../views/BacktestResults';
import ChartPage from '../views/ChartPage';

/**
 * 创建路由配置
 * @returns 路由实例
 */
export const router = createBrowserRouter([
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
      // 默认重定向到策略代理页面
      {
        index: true,
        element: <Navigate to="/agent/StrategyAgent" replace />
      }
    ]
  }
]);

/**
 * 设置页面标题
 * @param title 页面标题
 */
export const setPageTitle = (title?: string): void => {
  document.title = title || 'React App';
};
