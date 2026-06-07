import { useEffect, useMemo, useState } from 'react';
import { useRoutes, Navigate } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';

import AuthGuard from '@/components/AuthGuard';
import ConsoleLayout from '@/layouts/ConsoleLayout';
import LoginPage from '@/pages/login/LoginPage';
import ChartPage from '@/pages/chart/ChartPage';
import Worker from '@/pages/worker/Worker';
import WorkerDetail from '@/pages/worker/WorkerDetail';
import StrategyManagement from '@/pages/strategy/StrategyManagement';
import StrategyEditor from '@/pages/strategy/StrategyEditor';
import FactorAnalysis from '@/pages/factor/FactorAnalysis';
import ModelManagement from '@/pages/model/ModelManagement';
import DataManagementPage from '@/pages/data/DataManagementPage';
import KlineReplayPage from '@/pages/data/KlineReplayPage';
import Setting from '@/pages/setting/Setting';
import Agent from '@/pages/agent/Agent';

import BacktestLayout from '@/pages/backtest/BacktestLayout';
import BacktestList from '@/pages/backtest/BacktestList';
import BacktestDetail from '@/pages/backtest/BacktestDetail';
import BacktestConfig from '@/pages/backtest/BacktestConfig';
import BacktestReplay from '@/pages/backtest/BacktestReplay';

import GeneralSettingsPage from '@/pages/setting/GeneralSettingsPage';
import ExchangeSettingsPage from '@/pages/setting/ExchangeSettingsPage';
import NotificationsPage from '@/pages/setting/NotificationsPage';
import ModelSettingsPage from '@/pages/setting/ModelSettingsPage';
import SystemInfoPage from '@/pages/setting/SystemInfoPage';
import EnvironmentVariablesPage from '@/pages/setting/EnvironmentVariablesPage';
import PluginManagement from '@/pages/setting/PluginManagement';

import { pluginRegistry } from '@/plugins/PluginRegistry';
import PluginPage from '@/pages/plugin/PluginPage';

// 公开分享页（无需登录，使用 URL 中的 token 访问）
import SharePage from '@/pages/share/SharePage';

function createBaseRoutes(): RouteObject[] {
  return [
    {
      path: '/login',
      element: <LoginPage />,
    },
    // 公开分享页（无需登录，使用 URL 中的 token 访问）
    {
      path: '/share/:token',
      element: <SharePage />,
    },
    {
      path: '/',
      element: (
        <AuthGuard>
          <ConsoleLayout />
        </AuthGuard>
      ),
      children: [
        { path: '/chart', element: <ChartPage /> },
        { path: '/strategy-worker', element: <Worker /> },
        { path: '/strategy-worker/:workerId', element: <WorkerDetail /> },
        { path: '/strategy-management', element: <StrategyManagement /> },
        { path: '/strategy-editor', element: <StrategyEditor /> },
        { path: '/strategy-editor/:strategyName', element: <StrategyEditor /> },
        {
          path: '/backtest',
          element: <BacktestLayout />,
          children: [
            { index: true, element: <BacktestList /> },
            { path: 'detail/:backtestId', element: <BacktestDetail /> },
            { path: 'config', element: <BacktestConfig /> },
            { path: 'replay/:backtestId', element: <BacktestReplay /> },
          ],
        },
        { path: '/agent', element: <Agent /> },
        { path: '/factor-analysis', element: <FactorAnalysis /> },
        { path: '/model-management', element: <ModelManagement /> },
        { path: '/data-management', element: <DataManagementPage /> },
        { path: '/data-management/replay', element: <KlineReplayPage /> },
        {
          path: '/setting',
          element: <Setting />,
          children: [
            { index: true, element: <Navigate to="/setting/general" replace /> },
            { path: 'general', element: <GeneralSettingsPage /> },
            { path: 'env', element: <EnvironmentVariablesPage /> },
            { path: 'exchange', element: <ExchangeSettingsPage /> },
            { path: 'notifications', element: <NotificationsPage /> },
            { path: 'model', element: <ModelSettingsPage /> },
            { path: 'info', element: <SystemInfoPage /> },
            { path: 'plugins', element: <PluginManagement /> },
          ],
        },
        { index: true, element: <Navigate to="/chart" replace /> },
      ],
    },
  ];
}

export function DynamicRouter() {
  const [pluginVersion, setPluginVersion] = useState(0);

  useEffect(() => {
    const unsubscribe = pluginRegistry.subscribe(() => {
      setPluginVersion((v) => v + 1);
    });
    return unsubscribe;
  }, []);

  const routes = useMemo(() => {
    const base = createBaseRoutes();
    const rootRoute = base.find((r) => r.path === '/');
    if (!rootRoute || !rootRoute.children) return base;

    const pluginRoutes = pluginRegistry.getRoutes();
    for (const pr of pluginRoutes) {
      rootRoute.children.push({
        path: pr.path,
        element: <PluginPage pluginName={pr.pluginName} />,
      });
    }

    return base;
  }, [pluginVersion]);

  return useRoutes(routes);
}

import { setPageTitle } from '@/utils/pageTitle';
