import { createBrowserRouter, Navigate } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';

// 导入布局
import ConsoleLayout from '@/layouts/ConsoleLayout';

// 导入页面组件
import LoginPage from '@/pages/login/LoginPage';
import ChartPage from '@/pages/chart/ChartPage';
import Worker from '@/pages/worker/Worker';
import StrategyManagement from '@/pages/strategy/StrategyManagement';
import StrategyEditor from '@/pages/strategy/StrategyEditor';
import FactorAnalysis from '@/pages/factor/FactorAnalysis';
import ModelManagement from '@/pages/model/ModelManagement';
import DataManagementPage from '@/pages/data/DataManagementPage';
import KlineReplayPage from '@/pages/data/KlineReplayPage';
import Setting from '@/pages/setting/Setting';
import Agent from '@/pages/agent/Agent';

// 导入回测模块
import BacktestLayout from '@/pages/backtest/BacktestLayout';
import BacktestList from '@/pages/backtest/BacktestList';
import BacktestDetail from '@/pages/backtest/BacktestDetail';
import BacktestConfig from '@/pages/backtest/BacktestConfig';
import BacktestReplay from '@/pages/backtest/BacktestReplay';

// 导入设置子页面
import GeneralSettingsPage from '@/pages/setting/GeneralSettingsPage';
import ExchangeSettingsPage from '@/pages/setting/ExchangeSettingsPage';
import NotificationsPage from '@/pages/setting/NotificationsPage';
import ModelSettingsPage from '@/pages/setting/ModelSettingsPage';
import SystemInfoPage from '@/pages/setting/SystemInfoPage';

// 基础路由配置
const baseRoutes: RouteObject[] = [
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: <ConsoleLayout />,
    children: [
      {
        path: '/chart',
        element: <ChartPage />,
      },
      {
        path: '/strategy-worker',
        element: <Worker />,
      },
      {
        path: '/strategy-management',
        element: <StrategyManagement />,
      },
      {
        path: '/strategy-editor',
        element: <StrategyEditor />,
      },
      {
        path: '/strategy-editor/:strategyName',
        element: <StrategyEditor />,
      },
      // 回测模块路由
      {
        path: '/backtest',
        element: <BacktestLayout />,
        children: [
          {
            index: true,
            element: <BacktestList />,
          },
          {
            path: 'detail/:backtestId',
            element: <BacktestDetail />,
          },
          {
            path: 'config',
            element: <BacktestConfig />,
          },
          {
            path: 'replay/:backtestId',
            element: <BacktestReplay />,
          },
        ],
      },
      {
        path: '/agent',
        element: <Agent />,
      },
      {
        path: '/factor-analysis',
        element: <FactorAnalysis />,
      },
      {
        path: '/model-management',
        element: <ModelManagement />,
      },
      {
        path: '/data-management',
        element: <DataManagementPage />,
      },
      {
        path: '/data-management/replay',
        element: <KlineReplayPage />,
      },
      // 设置页面及其子路由
      {
        path: '/setting',
        element: <Setting />,
        children: [
          {
            index: true,
            element: <Navigate to="/setting/general" replace />,
          },
          {
            path: 'general',
            element: <GeneralSettingsPage />,
          },
          {
            path: 'exchange',
            element: <ExchangeSettingsPage />,
          },
          {
            path: 'notifications',
            element: <NotificationsPage />,
          },
          {
            path: 'model',
            element: <ModelSettingsPage />,
          },
          {
            path: 'info',
            element: <SystemInfoPage />,
          },
        ],
      },
      // 默认重定向到图表页面
      {
        index: true,
        element: <Navigate to="/chart" replace />,
      },
    ],
  },
];

// 创建路由
export const router = createBrowserRouter(baseRoutes);

// 设置页面标题
export const setPageTitle = (title?: string): void => {
  document.title = title ? `${title} - QuantCell` : 'QuantCell - 量化交易平台';
};
