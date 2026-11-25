import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  IconBell,
  IconBrandGithub,
  IconChevronsLeft,
  IconMenu2,
  IconSettings,
} from "@tabler/icons-react";
import { Badge, Drawer, Popover } from "antd";

import AppLocale from "@/components/AppLocale";
import AppTheme from "@/components/AppTheme";
import SideNav, { pickRouteTitleKey } from "@/components/layout/SideNav";
import { NotificationPanel } from "@/components/NotificationInbox";
import useBrowserTheme from "@/hooks/useBrowserTheme";
import type { ThemeMode } from "@/components/AppTheme";
import { useUpdateStore } from "@/desktop/updateStore";
import { useUpdater } from "@/desktop/useUpdater";
import { useNotificationStore } from "@/store/notificationStore";

/**
 * 控制台布局骨架（design-spec §5）：
 * 顶部 Header 52px 通栏（logo + 面包屑 | 主题胶囊 + 图标钮）→
 * 下方 flex 行（Sider 216px 卡片 + main 4/4/18 内边距）。
 * <md 保留 Drawer 导航 + header 图标组；Sider 折叠态持久化 localStorage。
 */
const ConsoleLayout = () => {
  const { t } = useTranslation();
  const { themeMode, setThemeMode } = useBrowserTheme();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // ponytail: 默认展开，折叠状态持久化到 localStorage
  const [siderCollapsed, setSiderCollapsed] = useState(() => localStorage.getItem('sider_collapsed') === 'true');

  // 折叠状态变化时持久化
  useEffect(() => {
    localStorage.setItem('sider_collapsed', String(siderCollapsed));
  }, [siderCollapsed]);

  // 有可用更新时设置按钮显示红点；useUpdater 顺带触发启动后静默检查（全局只调度一次）
  const updateAvailable = useUpdateStore((s) => s.status) === 'available';
  useUpdater();

  // 站内通知未读数（ws 实时增量 + 收件箱页读取后的权威值）
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const syncUnreadCount = useNotificationStore((s) => s.syncUnreadCount);

  // 角标冷启动：刷新后 store 重开、未读数归 0，必须主动取一次权威值；
  // 之前只在悬浮面板/收件箱页挂载时才 loadList，所以角标要等鼠标悬浮才出现。
  useEffect(() => {
    void syncUnreadCount();
  }, [syncUnreadCount]);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  // 文档标题在 SideNav 内统一维护（与菜单选中态同源）
  const crumbTitleKey = pickRouteTitleKey(pathname);
  const crumb = crumbTitleKey ? t(crumbTitleKey) : undefined;

  const handleGitHubClick = () => {
    window.open("https://github.com/pengwow/QuantCell", "_blank");
  };

  return (
    <div className="qc-app">
      <header className="qc-header">
        <div className="qc-header-left">
          <button
            type="button"
            className="qc-icon-btn qc-hamburger"
            aria-label="打开导航菜单"
            onClick={() => setDrawerOpen(true)}
          >
            <IconMenu2 size={16} stroke={1.5} />
          </button>
          <img src="/logo.svg" alt="QuantCell" className="qc-logo" />
          <span className="qc-brand">QuantCell</span>
          {crumb && (
            <>
              <span className="qc-crumb-sep">/</span>
              <span className="qc-crumb">{crumb}</span>
            </>
          )}
        </div>
        <div className="qc-header-right">
          <AppTheme.LinkButton themeMode={themeMode as ThemeMode} setThemeMode={setThemeMode} />
          {/* 语言切换沿用原入口（原 mobile header 行为，桌面不展示） */}
          <AppLocale.LinkButton className="qc-header-locale" />
          <Badge
            className="qc-bell"
            count={unreadCount}
            size="small"
            overflowCount={99}
            offset={[-3, 3]}
          >
            <Popover
              content={<NotificationPanel />}
              placement="bottomRight"
              trigger="hover"
            >
              <button
                type="button"
                className="qc-icon-btn"
                aria-label={t('message_center') || "消息"}
                onClick={() => navigate("/notifications")}
              >
                <IconBell size={16} stroke={1.5} />
              </button>
            </Popover>
          </Badge>
          <button
            type="button"
            className="qc-icon-btn"
            aria-label="GitHub"
            onClick={handleGitHubClick}
          >
            <IconBrandGithub size={16} stroke={1.5} />
          </button>
          <Badge dot={updateAvailable} status="error" offset={[-2, 2]}>
            <button
              type="button"
              className="qc-icon-btn"
              aria-label={t('setting') || "设置"}
              onClick={() => navigate("/setting")}
            >
              <IconSettings size={16} stroke={1.5} />
            </button>
          </Badge>
        </div>
      </header>

      <div className="qc-app-body">
        <aside
          className="qc-sider"
          data-collapsed={siderCollapsed}
          aria-label="侧边导航"
        >
          <SideNav collapsed={siderCollapsed} />
          <div className="qc-sider-foot">
            {/* 布局层没有可靠的健康数据源，不展示「系统正常」类状态点 */}
            <span className="qc-ver">v{__APP_VERSION__}</span>
            <button
              type="button"
              className="qc-icon-btn qc-collapse-btn"
              aria-expanded={!siderCollapsed}
              aria-label="折叠 / 展开侧栏"
              title="折叠 / 展开侧栏"
              onClick={() => setSiderCollapsed(!siderCollapsed)}
            >
              <IconChevronsLeft size={15} stroke={1.4} />
            </button>
          </div>
        </aside>

        <main className="qc-main">
          <Outlet />
        </main>
      </div>

      <Drawer
        closable={false}
        destroyOnHidden
        open={drawerOpen}
        placement="left"
        size={272}
        styles={{
          body: { padding: 0, display: "flex", flexDirection: "column" },
        }}
        onClose={closeDrawer}
      >
        <SideNav onSelect={closeDrawer} />
      </Drawer>
    </div>
  );
};

export default ConsoleLayout;
