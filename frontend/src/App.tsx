import React, { useState, useEffect } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useResponsive } from './hooks/useResponsive';

import { BarChartOutlined, CodeOutlined, FundProjectionScreenOutlined, RobotOutlined, SettingOutlined, ProductOutlined, DownloadOutlined, InboxOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useConfigStore } from './store';
import { pluginManager } from './plugins';
import type { MenuGroup } from './plugins/PluginBase';
import { useTranslation } from 'react-i18next';
import { initTheme } from './utils/themeManager';
import { wsService } from './services/websocketService';
import './App.css';

/**
 * 侧边栏导航组件
 * 功能：实现左侧图标菜单布局，支持鼠标悬停显示文字描述，设置按钮位于底部，支持收放功能
 */
const App = () => {
  const { isMobile, isTablet } = useResponsive();
  const [isCollapsed, setIsCollapsed] = useState(true);
  const [menus, setMenus] = useState<MenuGroup[]>([]);
  const [isTooltipVisible, setIsTooltipVisible] = useState(false);
  const [systemMetrics, setSystemMetrics] = useState({
    connectionStatus: 'disconnected',
    cpuUsage: '0%',
    cpuUsagePercent: '0%',
    memoryUsage: '0GB / 0GB',
    memoryUsagePercent: '0%',
    diskSpace: '0GB / 0GB',
    diskSpacePercent: '0%'
  });
  const location = useLocation();
  const { t } = useTranslation();

  // 从全局配置store获取加载配置的方法
  const { loadConfigs } = useConfigStore();

  // 组件挂载时加载系统配置和菜单
  useEffect(() => {
    loadConfigs();
    loadMenus();
    initTheme();
    
    // 订阅系统状态主题
    wsService.subscribe('system:status');
    
    // 处理系统状态消息
    const handleSystemStatus = (data: any) => {
      if (data) {
        setSystemMetrics(prev => ({
          ...prev,
          cpuUsage: `${data.cpu_usage}%`,
          cpuUsagePercent: `${data.cpu_usage_percent}%`,
          memoryUsage: data.memory_usage,
          memoryUsagePercent: `${data.memory_usage_percent}%`,
          diskSpace: data.disk_space,
          diskSpacePercent: `${data.disk_space_percent}%`
        }));
      }
    };
    
    // 处理WebSocket连接状态变化
    const handleConnectionChange = (connected: boolean) => {
      console.log('WebSocket连接状态:', connected);
      // 更新系统指标中的连接状态
      setSystemMetrics(prev => ({
        ...prev,
        connectionStatus: connected ? 'connected' : 'disconnected'
      }));
    };
    
    // 注册监听器
    wsService.on('system_status', handleSystemStatus);
    wsService.onConnectionChange(handleConnectionChange);
    
    // 连接WebSocket服务
    wsService.connect();
    
    // 初始化连接状态
    const initialConnected = wsService.getConnected();
    setSystemMetrics(prev => ({
      ...prev,
      connectionStatus: initialConnected ? 'connected' : 'disconnected'
    }));
    
    // 清理函数
    return () => {
      wsService.off('system_status', handleSystemStatus);
      wsService.offConnectionChange(handleConnectionChange);
    };
  }, [loadConfigs]);

  const handleMenuClick = (): void => {
    if (isMobile) {
      setIsCollapsed(true);
    }
  };



  const isVerticalLayout = isMobile || isTablet;

  // 获取资源使用状态类名
  const getUsageStatusClass = (usage: string): string => {
    const value = parseInt(usage);
    if (value >= 85) {
      return 'critical';
    } else if (value >= 70) {
      return 'warning';
    } else {
      return 'normal';
    }
  };

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
          {
            path: '/data-management/quality',
            name: t('data_quality'),
            icon: <InfoCircleOutlined />
          },
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
    <>
      {/* 系统指标提示框 - 直接放在根元素下，避免侧边栏限制 */}
      { isTooltipVisible && (
        <div className="system-tooltip">
          <div className="system-tooltip-header">{t('system_status')}</div>
          <div className="system-tooltip-content">
            {/* 连接状态指示器 */}
            <div className="system-metric-item">
              <span className="system-metric-label">{t('connection')}:</span>
              <div className="status-indicator-container">
                <span 
                  className={`status-indicator ${systemMetrics.connectionStatus}`}
                ></span>
                <span className="system-metric-value">
                  {t(systemMetrics.connectionStatus)}
                </span>
              </div>
            </div>
            
            {/* CPU使用率指示器 */}
            <div className="system-metric-item">
              <span className="system-metric-label">{t('cpu_usage')}:</span>
              <div className="status-indicator-container">
                <span 
                  className={`status-indicator ${getUsageStatusClass(systemMetrics.cpuUsage)}`}
                ></span>
                <span className={`system-metric-value ${getUsageStatusClass(systemMetrics.cpuUsage)}`}>
                  {systemMetrics.cpuUsagePercent}  
                </span>
              </div>
            </div>
            
            {/* 内存使用率指示器 */}
            <div className="system-metric-item">
              <span className="system-metric-label">{t('memory_usage')}:</span>
              <div className="status-indicator-container">
                <span 
                  className={`status-indicator ${getUsageStatusClass(systemMetrics.memoryUsagePercent)}`}
                ></span>
                <span className={`system-metric-value ${getUsageStatusClass(systemMetrics.memoryUsagePercent)}`}>
                  {systemMetrics.memoryUsagePercent}  
                </span>
              </div>
            </div>
            
            {/* 磁盘空间使用率指示器 */}
            <div className="system-metric-item">
              <span className="system-metric-label">{t('disk_space')}:</span>
              <div className="status-indicator-container">
                <span 
                  className={`status-indicator ${getUsageStatusClass(systemMetrics.diskSpacePercent)}`}
                ></span>
                <span className={`system-metric-value ${getUsageStatusClass(systemMetrics.diskSpacePercent)}`}>
                  {systemMetrics.diskSpacePercent}  
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
      
      <div className={`app-container ${isVerticalLayout ? 'vertical-layout' : 'horizontal-layout'}`}>
      {/* 侧边栏导航 */}
      <aside
        className={`side-nav ${isCollapsed ? 'collapsed' : ''} ${isVerticalLayout ? 'top-nav' : ''}`}
        onMouseEnter={() => !isVerticalLayout && setIsCollapsed(false)}
        onMouseLeave={() => !isVerticalLayout && setIsCollapsed(true)}
      >
        {/* 侧边栏顶部品牌 */}
        <div className="nav-brand">
          <div 
            className="brand-icon"
            onMouseEnter={() => setIsTooltipVisible(true)}
            onMouseLeave={() => setIsTooltipVisible(false)}
          >
            <img src="/quantcell.svg" alt="QuantCell Logo" className="brand-image" />
          </div>
          <div className="brand-text">pengwow</div>
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

      {/* 侧边栏控制按钮 - 位于菜单栏外部 */}
      {/* {!isVerticalLayout && (
        <div className="sidebar-toggle-btn" onClick={handleToggleSidebar}>
          {isCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </div>
      )} */}
    </div>
    </>
  );
};

export default App;
