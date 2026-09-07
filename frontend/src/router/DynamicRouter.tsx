import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { useRoutes, Navigate } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';
import { Spin } from 'antd';

import AuthGuard from '@/components/AuthGuard';
import ConsoleLayout from '@/layouts/ConsoleLayout';
// 首屏关键页面保持同步加载，避免登录后白屏等待
import LoginPage from '@/pages/login/LoginPage';
import ChartPage from '@/pages/chart/ChartPage';

// 非首屏页面按需加载：把 echarts 等大依赖拆成独立 chunk，访问对应路由时才请求，
// 避免全部打包进主 bundle 拖慢首屏
const Worker = lazy(() => import('@/pages/worker/Worker'));
const WorkerDetail = lazy(() => import('@/pages/worker/WorkerDetail'));
const StrategyManagement = lazy(() => import('@/pages/strategy/StrategyManagement'));
const StrategyEditor = lazy(() => import('@/pages/strategy/StrategyEditor'));
const FactorAnalysis = lazy(() => import('@/pages/factor/FactorAnalysis'));
const ModelManagement = lazy(() => import('@/pages/model/ModelManagement'));
const DataManagementPage = lazy(() => import('@/pages/data/DataManagementPage'));
const KlineReplayPage = lazy(() => import('@/pages/data/KlineReplayPage'));
const Setting = lazy(() => import('@/pages/setting/Setting'));
const Agent = lazy(() => import('@/pages/agent/Agent'));
const ModelRegistry = lazy(() => import('@/pages/model/ModelRegistry'));
const EnsemblePage = lazy(() => import('@/pages/ensemble/EnsemblePage'));
const RiskMonitorPage = lazy(() => import('@/pages/risk/RiskMonitorPage'));
const RLTrainingPage = lazy(() => import('@/pages/rl/RLTrainingPage'));

const BacktestLayout = lazy(() => import('@/pages/backtest/BacktestLayout'));
const BacktestList = lazy(() => import('@/pages/backtest/BacktestList'));
const BacktestDetail = lazy(() => import('@/pages/backtest/BacktestDetail'));
const BacktestConfig = lazy(() => import('@/pages/backtest/BacktestConfig'));
const BacktestReplay = lazy(() => import('@/pages/backtest/BacktestReplay'));

const GeneralSettingsPage = lazy(() => import('@/pages/setting/GeneralSettingsPage'));
const ExchangeSettingsPage = lazy(() => import('@/pages/setting/ExchangeSettingsPage'));
const NotificationsPage = lazy(() => import('@/pages/setting/NotificationsPage'));
const ModelSettingsPage = lazy(() => import('@/pages/setting/ModelSettingsPage'));
const SystemInfoPage = lazy(() => import('@/pages/setting/SystemInfoPage'));
const EnvironmentVariablesPage = lazy(() => import('@/pages/setting/EnvironmentVariablesPage'));
const PluginManagement = lazy(() => import('@/pages/setting/PluginManagement'));

import { pluginRegistry } from '@/plugins/PluginRegistry';
import PluginPage from '@/pages/plugin/PluginPage';

// 路由懒加载期间的占位 loading
const RouteLoading = () => (
  <div className="flex min-h-[50vh] items-center justify-center">
    <Spin size="large" />
  </div>
);

function createBaseRoutes(): RouteObject[] {
  return [
    {
      path: '/login',
      element: <LoginPage />,
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
        { path: '/rl-training', element: <RLTrainingPage /> },
        { path: '/model-registry', element: <ModelRegistry /> },
        { path: '/ensemble', element: <EnsemblePage /> },
        { path: '/risk-monitor', element: <RiskMonitorPage /> },
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
    // 插件注册/注销通过订阅递增 pluginVersion，触发路由表重建
    void pluginVersion;
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

  return <Suspense fallback={<RouteLoading />}>{useRoutes(routes)}</Suspense>;
}