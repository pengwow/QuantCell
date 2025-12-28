import { useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useResponsive } from './hooks/useResponsive';
import { BarChartOutlined } from '@ant-design/icons';
import './App.css';

/**
 * 侧边栏导航组件
 * 功能：实现左侧图标菜单布局，支持鼠标悬停显示文字描述，设置按钮位于底部，支持收放功能
 */
const App = () => {
  const { isMobile, isTablet } = useResponsive();
  const [isCollapsed, setIsCollapsed] = useState(true);
  const location = useLocation();

  const handleMenuClick = (): void => {
    if (isMobile) {
      setIsCollapsed(true);
    }
  };

  const isVerticalLayout = isMobile || isTablet;

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
          <NavLink 
              to="/chart" 
              className={`nav-item ${location.pathname === '/chart' ? 'active' : ''}`}
              onClick={handleMenuClick}
            >
              <div className="nav-icon">
                <BarChartOutlined />
              </div>
              <span className="nav-text">图表</span>
            </NavLink>
          {/* 策略管理分组 */}
          <div className="menu-group">
            <div className="menu-group-title">策略管理</div>
            <NavLink 
              to="/agent/StrategyAgent" 
              className={`nav-item ${location.pathname === '/agent/StrategyAgent' ? 'active' : ''}`}
              onClick={handleMenuClick}
            >
              <div className="nav-icon">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm-2 14l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z" />
                </svg>
              </div>
              <span className="nav-text">策略代理</span>
            </NavLink>
            <NavLink 
              to="/backtest-results" 
              className={`nav-item ${location.pathname === '/backtest-results' ? 'active' : ''}`}
              onClick={handleMenuClick}
            >
              <div className="nav-icon">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
                </svg>
              </div>
              <span className="nav-text">回测结果</span>
            </NavLink>
          </div>

          {/* 因子分析分组 */}
          <div className="menu-group">
            <div className="menu-group-title">因子分析</div>
            <NavLink 
              to="/factor-analysis" 
              className={`nav-item ${location.pathname === '/factor-analysis' ? 'active' : ''}`}
              onClick={handleMenuClick}
            >
              <div className="nav-icon">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M10.5 1C5.81 1 2 4.81 2 9.5S5.81 18 10.5 18 19 14.19 19 9.5 15.19 1 10.5 1zm0 15c-2.49 0-4.5-2.01-4.5-4.5S8.01 6 10.5 6 15 8.01 15 10.5 12.99 16 10.5 16zm0-11C9.12 5 8 6.12 8 7.5S9.12 10 10.5 10 13 8.88 13 7.5 11.88 5 10.5 5zm0 9C12.99 14 15 11.99 15 9.5S12.99 5 10.5 5 6 7.01 6 9.5 8.01 14 10.5 14z" />
                </svg>
              </div>
              <span className="nav-text">因子分析</span>
            </NavLink>
          </div>

          {/* 模型管理分组 */}
          <div className="menu-group">
            <div className="menu-group-title">模型管理</div>
            <NavLink 
              to="/model-management" 
              className={`nav-item ${location.pathname === '/model-management' ? 'active' : ''}`}
              onClick={handleMenuClick}
            >
              <div className="nav-icon">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" />
                </svg>
              </div>
              <span className="nav-text">模型管理</span>
            </NavLink>
          </div>

          {/* 数据管理分组 */}
          <div className="menu-group">
            <div className="menu-group-title">数据管理</div>
            <NavLink 
              to="/data-management" 
              className={`nav-item ${location.pathname === '/data-management' ? 'active' : ''}`}
              onClick={handleMenuClick}
            >
              <div className="nav-icon">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
                </svg>
              </div>
              <span className="nav-text">数据管理</span>
            </NavLink>
          </div>
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
