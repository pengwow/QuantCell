import React, { useState, useEffect } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useResponsive } from './hooks/useResponsive';

import {
  BarChartOutlined, CodeOutlined, FundProjectionScreenOutlined,
  RobotOutlined, SettingOutlined, ProductOutlined,
  DownloadOutlined, InboxOutlined
} from '@ant-design/icons';

import { useConfigStore } from './store';
import { pluginManager } from './plugins';
import type { MenuGroup } from './plugins/PluginBase';
import { useTranslation } from 'react-i18next';
import { initTheme } from './utils/themeManager';
import './App.css';

/**
 * 侧边栏导航组件
 * 功能：实现左侧图标菜单布局，支持鼠标悬停显示文字描述，设置按钮位于底部，支持收放功能
 */
const App = () => {
  const { isMobile, isTablet } = useResponsive();
  const [isCollapsed, setIsCollapsed] = useState(true);
  const [menus, setMenus] = useState<MenuGroup[]>([]);
  const location = useLocation();
  const { t } = useTranslation();

  // 从全局配置store获取加载配置的方法
  const { loadConfigs } = useConfigStore();

  // 组件挂载时加载系统配置和菜单
  useEffect(() => {
    loadConfigs();
    loadMenus();
    initTheme();
  }, [loadConfigs]);

  const handleMenuClick = (): void => {
    if (isMobile) {
      setIsCollapsed(true);
    }
  };

  const isVerticalLayout = isMobile || isTablet;

  // 加载菜单，包括核心菜单和插件菜单
  const loadMenus = (): void => {
    // 核心菜单配置
    const coreMenus: MenuGroup[] = [
      {
        group: '', // 无分组的菜单项
        items: [
          {
            path: '/chart',
            name: t('chart'),
            icon: <BarChartOutlined />
          }
        ]
      },
      {
        group: t('strategy_management'),
        items: [
          {
            path: '/strategy-management',
            name: t('strategy_management'),
            icon: <CodeOutlined />
          },
          {
            path: '/agent/StrategyAgent',
            name: t('strategy_agent'),
            icon: <RobotOutlined />
          },
          {
            path: '/backtest',
            name: t('strategy_backtest'),
            icon: <FundProjectionScreenOutlined />
          }
        ]
      },
      // {
      //   group: t('factor_analysis'),
      //   items: [
      //     {
      //       path: '/factor-analysis',
      //       name: t('factor_analysis')
      //     }
      //   ]
      // },
      // {
      //   group: t('model_management'),
      //   items: [
      //     {
      //       path: '/model-management',
      //       name: t('model_management')
      //     }
      //   ]
      // },
      {
        group: t('data_management'),
        items: [
          {
            path: '/data-management/data-pools',
            name: t('data_pool_management'),
            icon: <InboxOutlined />
          },
          {
            path: '/data-management/collection',
            name: t('data_collection'),
            icon: <DownloadOutlined />
          },
          // {
          //   path: '/data-management/quality',
          //   name: t('data_quality'),
          //   icon: <InfoCircleOutlined />
          // },
          // {
          //   path: '/data-management/visualization',
          //   name: t('data_visualization'),
          //   icon: <BarChartOutlined />
          // }
        ]
      }
    ];

    // 获取插件菜单
    const pluginMenus = pluginManager.getAllMenus();

    // 合并核心菜单和插件菜单
    const allMenus = [...coreMenus, ...pluginMenus];

    setMenus(allMenus);
  };

  return (
    <div className={`app-container ${isVerticalLayout ? 'vertical-layout' : 'horizontal-layout'}`}>
      {/* 侧边栏导航 */}
      <aside
        className={`side-nav ${isCollapsed ? 'collapsed' : ''} ${isVerticalLayout ? 'top-nav' : ''}`}
        onMouseEnter={() => !isVerticalLayout && setIsCollapsed(false)}
        onMouseLeave={() => !isVerticalLayout && setIsCollapsed(true)}
      >
        {/* 侧边栏顶部品牌 */}
        <div className="nav-brand">
          <div className="brand-icon">
            <img src="/qbot.svg" alt="QBot Logo" className="brand-image" />
          </div>
          <div className="brand-text">QBot</div>
        </div>

        {/* 侧边栏菜单 */}
        <div className="nav-menu">
          {menus.map((menuGroup, groupIndex) => (
            <React.Fragment key={groupIndex}>
              {/* 渲染菜单分组标题 */}
              {menuGroup.group && (
                <div className="menu-group">
                  <div className="menu-group-title">{menuGroup.group}</div>

                  {/* 渲染分组内的菜单项 */}
                  {menuGroup.items.map((menuItem, itemIndex) => (
                    <NavLink
                      key={itemIndex}
                      to={menuItem.path}
                      className={`nav-item ${location.pathname === menuItem.path ? 'active' : ''}`}
                      onClick={handleMenuClick}
                    >
                      <div className="nav-icon">
                        {menuItem.icon || (
                          <ProductOutlined />
                        )}
                      </div>
                      <span className="nav-text">{menuItem.name}</span>
                    </NavLink>
                  ))}
                </div>
              )}

              {/* 渲染无分组的菜单项 */}
              {!menuGroup.group && menuGroup.items.map((menuItem, itemIndex) => (
                <NavLink
                  key={itemIndex}
                  to={menuItem.path}
                  className={`nav-item ${location.pathname === menuItem.path ? 'active' : ''}`}
                  onClick={handleMenuClick}
                >
                  <div className="nav-icon">
                    {menuItem.icon || (
                      <ProductOutlined />
                    )}
                  </div>
                  <span className="nav-text">{menuItem.name}</span>
                </NavLink>
              ))}
            </React.Fragment>
          ))}
        </div>

        {/* 设置按钮放在底部 */}
        <div className="nav-bottom">
          <NavLink
            to="/setting"
            className={`nav-item ${location.pathname === '/setting' ? 'active' : ''}`}
            onClick={handleMenuClick}
          >
            <SettingOutlined />
            <span className="nav-text">{t('setting')}</span>
          </NavLink>
        </div>
      </aside>

      {/* 主内容区域 */}
      <main className="main-container">
        <div className="content-wrapper">
          <Outlet />
        </div>
      </main>
    </div>
  );
};

export default App;
