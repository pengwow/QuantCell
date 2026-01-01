import React, { useState, useEffect } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useResponsive } from './hooks/useResponsive';
import { BarChartOutlined } from '@ant-design/icons';
import { useConfigStore } from './store';
import { pluginManager } from './plugins';
import type { MenuGroup } from './plugins/PluginBase';
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
  
  // 从全局配置store获取加载配置的方法
  const { loadConfigs } = useConfigStore();

  // 组件挂载时加载系统配置和菜单
  useEffect(() => {
    loadConfigs();
    loadMenus();
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
            name: '图表',
            icon: <BarChartOutlined />
          }
        ]
      },
      {
        group: '策略管理',
        items: [
          {
            path: '/agent/StrategyAgent',
            name: '策略代理'
          },
          {
            path: '/backtest-results',
            name: '回测结果'
          }
        ]
      },
      {
        group: '因子分析',
        items: [
          {
            path: '/factor-analysis',
            name: '因子分析'
          }
        ]
      },
      {
        group: '模型管理',
        items: [
          {
            path: '/model-management',
            name: '模型管理'
          }
        ]
      },
      {
        group: '数据管理',
        items: [
          {
            path: '/data-management',
            name: '数据管理'
          },
          {
            path: '/scheduled-tasks',
            name: '定时任务'
          }
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
            <img src="/src/assets/react.svg" alt="QBot Logo" className="brand-image" />
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
                          <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm-2 14l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z" />
                          </svg>
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
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm-2 14l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z" />
                      </svg>
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
            <div className="nav-icon">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" />
              </svg>
            </div>
            <span className="nav-text">系统设置</span>
          </NavLink>
        </div>
      </aside>

      {/* 主内容区域 */}
      <main className="main-container">
        <Outlet />
      </main>
    </div>
  );
};

export default App;
