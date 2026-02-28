import { memo, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  IconBrandGithub,
  IconChartBar,
  IconCode,
  IconDatabase,
  IconHelp,
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarRightCollapse,
  IconLogout,
  IconMenu2,
  IconSettings,
} from "@tabler/icons-react";
import { Button, Drawer, Layout, Menu, type MenuProps, theme } from "antd";

import AppLocale from "@/components/AppLocale";
import AppTheme from "@/components/AppTheme";
import useBrowserTheme from "@/hooks/useBrowserTheme";
import type { ThemeMode } from "@/components/AppTheme";

const ConsoleLayout = () => {
  const { t } = useTranslation();
  const { token: themeToken } = theme.useToken();
  const { themeMode, setThemeMode } = useBrowserTheme();

  const [siderCollapsed, setSiderCollapsed] = useState(false);

  const handleSetThemeMode = (mode: ThemeMode) => {
    setThemeMode(mode);
  };

  const handleLogoutClick = () => {
    localStorage.removeItem("token");
    window.location.href = "/login";
  };

  const handleDocumentClick = () => {
    window.open("https://github.com/QuantCell", "_blank");
  };

  const handleGitHubClick = () => {
    window.open("https://github.com/QuantCell", "_blank");
  };

  return (
    <Layout className="h-screen bg-background text-foreground" hasSider>
      <Layout.Sider
        className="group/sider z-20 h-full border-r bg-background max-md:static max-md:hidden"
        style={{ borderColor: themeToken.colorBorderSecondary }}
        theme="light"
        width={siderCollapsed ? 81 : 256}
      >
        <div className="flex size-full flex-col items-center justify-between overflow-hidden select-none">
          <div className="w-full px-2">
            <SiderMenu collapsed={siderCollapsed} />
          </div>
          <div className="w-full px-2 pb-2">
            <Menu
              style={{ background: "transparent", borderInlineEnd: "none" }}
              inlineCollapsed={siderCollapsed}
              items={[
                {
                  key: "document",
                  icon: (
                    <span className="anticon scale-125" role="img">
                      <IconHelp size="1em" />
                    </span>
                  ),
                  label: t('help') || "帮助",
                  onClick: handleDocumentClick,
                },
                {
                  key: "logout",
                  danger: true,
                  icon: (
                    <span className="anticon scale-125" role="img">
                      <IconLogout size="1em" />
                    </span>
                  ),
                  label: t('logout') || "退出登录",
                  onClick: handleLogoutClick,
                },
              ]}
              mode="vertical"
              selectable={false}
            />
          </div>
        </div>
        <div className="absolute top-1/2 right-0 translate-x-1/2 -translate-y-1/2 opacity-0 transition-opacity group-hover/sider:opacity-100">
          <Button
            className="bg-background shadow-sm"
            icon={
              siderCollapsed ? (
                <IconLayoutSidebarRightCollapse size="1.5em" stroke="1.25" color="#999" />
              ) : (
                <IconLayoutSidebarLeftCollapse size="1.5em" stroke="1.25" color="#999" />
              )
            }
            shape="circle"
            type="text"
            onClick={() => setSiderCollapsed(!siderCollapsed)}
          />
        </div>
      </Layout.Sider>

      <Layout className="flex flex-col overflow-hidden">
        <Layout.Header
          className="relative border-b shadow-sm md:hidden"
          style={{
            padding: 0,
            borderBottomColor: themeToken.colorBorderSecondary,
          }}
        >
          <div className="absolute inset-0 z-0">
            <div
              className="h-full w-full"
              style={{
                backgroundImage:
                  "linear-gradient(rgba(255, 255, 255, 0.063) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.063) 1px, transparent 1px)",
                backgroundSize: "20px 20px",
              }}
            >
              <div className="h-full w-full backdrop-blur-[1px]"></div>
            </div>
          </div>
          <div className="flex size-full items-center justify-between overflow-hidden px-4">
            <div className="flex items-center gap-4">
              <SiderMenuDrawer trigger={<Button icon={<IconMenu2 size="1.25em" stroke="1.25" />} />} />
            </div>
            <div className="flex size-full grow items-center justify-end gap-4 overflow-hidden">
              <AppTheme.LinkButton
                themeMode={themeMode as ThemeMode}
                setThemeMode={handleSetThemeMode}
              />
              <AppLocale.LinkButton />
              <Button icon={<IconBrandGithub size="1.25em" stroke="1.25" />} onClick={handleGitHubClick} />
              <Button danger icon={<IconLogout size="1.25em" stroke="1.25" />} onClick={handleLogoutClick} />
            </div>
          </div>
        </Layout.Header>

        <Layout.Content className="relative flex-1 overflow-x-hidden overflow-y-auto">
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  );
};

const SiderMenu = memo(({ collapsed, onSelect }: { collapsed?: boolean; onSelect?: (key: string) => void }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const MENU_KEY_CHART = "/chart";
  const MENU_KEY_STRATEGY = "/strategy-management";
  const MENU_KEY_AGENT = "/agent";
  const MENU_KEY_BACKTEST = "/backtest";
  const MENU_KEY_DATA = "/data-management";
  const MENU_KEY_SETTINGS = "/setting";

  const menuItems: Required<MenuProps>["items"] = (
    [
      [MENU_KEY_CHART, "chart", <IconChartBar size="1em" />],
      [MENU_KEY_STRATEGY, "strategy_management", <IconCode size="1em" />],
      [MENU_KEY_AGENT, "agent", <IconCode size="1em" />],
      [MENU_KEY_BACKTEST, "strategy_backtest", <IconChartBar size="1em" />],
      [MENU_KEY_DATA, "data_management", <IconDatabase size="1em" />],
      [MENU_KEY_SETTINGS, "setting", <IconSettings size="1em" />],
    ] satisfies Array<[string, string, React.ReactNode]>
  ).map(([key, label, icon]) => {
    return {
      key: key,
      icon: (
        <span className="anticon scale-125" role="img">
          {icon}
        </span>
      ),
      label: t(label),
      onClick: () => {
        navigate(key);
        onSelect?.(key);
      },
    };
  });

  const [menuSelectedKey, setMenuSelectedKey] = useState<string>();

  const getActiveMenuItem = () => {
    const item =
      menuItems.find((item) => item!.key === location.pathname) ??
      menuItems.find((item) => item!.key !== MENU_KEY_CHART && location.pathname.startsWith(item!.key as string));
    return item;
  };

  useEffect(() => {
    const item = getActiveMenuItem();
    if (item) {
      setMenuSelectedKey(item.key as string);
    } else {
      setMenuSelectedKey(void 0);
    }
  }, [location.pathname]);

  useEffect(() => {
    if (menuSelectedKey && menuSelectedKey !== getActiveMenuItem()?.key) {
      navigate(menuSelectedKey);
    }
  }, [menuSelectedKey]);

  return (
    <>
      <div className="h-[64px] w-full overflow-hidden px-4 py-2 max-md:py-0">
        <div className="flex size-full items-center justify-around gap-2">
          <img src="/logo.svg" className="size-[36px]" />
          {!collapsed && (
            <>
              <span className="w-[81px] truncate text-base leading-[64px] font-semibold">QuantCell</span>
            </>
          )}
        </div>
      </div>
      <div className="w-full grow overflow-x-hidden overflow-y-auto">
        <Menu
          style={{ background: "transparent", borderInlineEnd: "none" }}
          inlineCollapsed={collapsed}
          items={menuItems}
          mode="vertical"
          selectedKeys={menuSelectedKey ? [menuSelectedKey] : []}
          onSelect={({ key }) => {
            setMenuSelectedKey(key);
          }}
        />
      </div>
    </>
  );
});

const SiderMenuDrawer = memo(({ trigger }: { trigger: React.ReactNode }) => {
  const [siderOpen, setSiderOpen] = useState(false);

  const triggerEl = (
    <div onClick={() => setSiderOpen(true)}>
      {trigger}
    </div>
  );

  const handleMenuSelect = useCallback(() => {
    setSiderOpen(false);
  }, []);

  return (
    <>
      {triggerEl}
      <Drawer
        closable={false}
        destroyOnClose
        open={siderOpen}
        placement="left"
        styles={{
          body: { padding: 0 },
        }}
        onClose={() => setSiderOpen(false)}
      >
        <SiderMenu onSelect={handleMenuSelect} />
      </Drawer>
    </>
  );
});

export default ConsoleLayout;
