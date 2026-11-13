import { Outlet } from 'react-router-dom';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { setPageTitle } from '@/utils/pageTitle';

/**
 * 回测模块布局组件
 * 功能：仅负责设置浏览器标签标题与渲染子路由。返回按钮、标题与页边距
 * 统一由子页面的 PageContainer（title/onBack）提供，与其他菜单页面保持
 * 同一套页头结构（此前本组件自绘「返回+标题」行，导致列表页多出返回按钮、
 * 双重标题和比其他页面更大的左右内边距）。
 */
const BacktestLayout = () => {
  const { t } = useTranslation();

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('strategy_backtest'));
  }, [t]);

  return <Outlet />;
};

export default BacktestLayout;
