import { memo, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  IconBell,
  IconBrandGithub,
  IconChartBar,
  IconChartHistogram,
  IconCode,
  IconDatabase,
  IconFlask,
  IconHelp,
  IconHome,
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarRightCollapse,
  IconMenu2,
  IconSettings,
  IconBotId,
  IconRobot,
  IconPlug,
  IconShield,
  IconStack,
  IconMicroscope,
} from "@tabler/icons-react";
import { Badge, Button, Drawer, Layout, Menu, type MenuProps, Popover, theme } from "antd";
import { setPageTitle } from "@/utils/pageTitle";

import AppLocale from "@/components/AppLocale";
import AppTheme from "@/components/AppTheme";
import { NotificationPanel } from "@/components/NotificationInbox";
import useBrowserTheme from "@/hooks/useBrowserTheme";
import type { ThemeMode } from "@/components/AppTheme";
import { pluginRegistry } from "@/plugins/PluginRegistry";
import { useUpdateStore } from "@/desktop/updateStore";
import { useUpdater } from "@/desktop/useUpdater";
// P2-02 能力开关：菜单按部署能力过滤（agent_gateway 关闭时隐藏代理菜单）
import { isCapabilityEnabled, useCapabilityStore } from "@/store/capabilityStore";
import { useNotificationStore } from "@/store/notificationStore";

const ConsoleLayout = () => {
  const { t } = useTranslation();
  const { token: themeToken } = theme.useToken();
  const { themeMode, setThemeMode } = useBrowserTheme();

  // ponytail: 默认展开，折叠状态持久化到 localStorage
  const [siderCollapsed, setSiderCollapsed] = useState(() => localStorage.getItem('sider_collapsed') === 'true');

  // 折叠状态变化时持久化
  useEffect(() => {
    localStorage.setItem('sider_collapsed', String(siderCollapsed));
  }, [siderCollapsed]);
  const handleSetThemeMode = (mode: ThemeMode) => {
    setThemeMode(mode);
  };

  const navigate = useNavigate();

  // 有可用更新时设置菜单显示红点；useUpdater 顺带触发启动后静默检查（全局只调度一次）
  const updateAvailable = useUpdateStore((s) => s.status) === 'available';
  useUpdater();

  // 站内通知未读数（ws 实时增量 + 收件箱页读取后的权威值）
  const unreadCount = useNotificationStore((s) => s.unreadCount);

  const handleDocumentClick = () => {
    window.open("https://github.com/pengwow/QuantCell", "_blank");
  };

  const handleGitHubClick = () => {
    window.open("https://github.com/pengwow/QuantCell", "_blank");
  };

  return (
    <Layout className="h-screen bg-background text-foreground" hasSider>
      <Layout.Sider
        className="group/sider z-20 h-full border-r bg-background max-md:static max-md:hidden"
        style={{ borderColor: themeToken.colorBorderSecondary }}
        theme="light"
        width={siderCollapsed ? 80 : 192}
      >
        <div className="flex size-full flex-col items-center justify-between overflow-hidden select-none">
          {/* 折叠时去掉横向内边距：antd inline-collapsed 菜单固定宽 80px，需与 Sider 等宽才能居中 */}
          <div className={`w-full ${siderCollapsed ? "px-0" : "px-2"}`}>
            <SiderMenu collapsed={siderCollapsed} />
          </div>
          <div className={`w-full pb-2 ${siderCollapsed ? "px-0" : "px-2"}`}>
            <Menu
              style={{ background: "transparent", borderInlineEnd: "none" }}
              items={[
                {
                  key: "/notifications",
                  // 未读角标挂在铃铛图标本体上：折叠模式只渲染 icon，挂在 label 文本上折叠后完全不可见。
                  // 折叠态 antd 会给 .anticon 强制写入 line-height:40px（menu/style/vertical.js 折叠规则），
                  // 把 Badge 的定位容器撑高、角标跑到铃铛正上方并被菜单项顶部裁掉一半。
                  // 内联锁死 line-height/font-size（内联样式特异性高于 antd 规则），展开/折叠两态几何完全一致。
                  icon: (
                    <Badge count={unreadCount} size="small" offset={[-2, 2]}>
                      <span className="anticon" role="img" style={{ lineHeight: 1, fontSize: 14 }}>
                        <IconBell size="1em" />
                      </span>
                    </Badge>
                  ),
                  label: (
                    // 悬停出最近通知预览面板（辅助入口）；点击直接进收件箱页
                    <Popover
                      content={<NotificationPanel />}
                      placement="rightBottom"
                      trigger="hover"
                    >
                      <span className="flex items-center">{t('message_center') || "消息"}</span>
                    </Popover>
                  ),
                  onClick: () => navigate("/notifications"),
                },
                {
                  key: "document",
                  icon: (
                    <span className="anticon" role="img">
                      <IconHelp size="1em" />
                    </span>
                  ),
                  label: t('help') || "帮助",
                  onClick: handleDocumentClick,
                },
                {
                  key: "/setting",
                  icon: (
                    <span className="anticon" role="img">
                      <IconSettings size="1em" />
                    </span>
                  ),
                  label: (
                    <span className="flex items-center gap-2">
                      {t('setting') || "设置"}
                      {updateAvailable && <Badge status="error" />}
                    </span>
                  ),
                  onClick: () => navigate("/setting"),
                },
              ]}
              mode="inline"
              inlineCollapsed={siderCollapsed}
              selectable={false}
            />
          </div>
        </div>
        <div className="absolute top-1/2 right-0 z-[10000] translate-x-1/2 -translate-y-1/2 opacity-0 transition-opacity group-hover/sider:opacity-100">
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
              // ponytail: 移动端 header 网格用主色低透明度，替代硬编码的白色网格（暗色模式下会刺眼）
              style={{
                backgroundImage:
                  `linear-gradient(${themeToken.colorPrimary}10 1px, transparent 1px), linear-gradient(90deg, ${themeToken.colorPrimary}10 1px, transparent 1px)`,
                backgroundSize: '20px 20px',
              }}
            >
              <div className="h-full w-full backdrop-blur-[1px]"></div>
            </div>
          </div>
          <div className="relative z-10 flex size-full items-center justify-between overflow-hidden px-4">
            <div className="flex items-center gap-4">
              <SiderMenuDrawer trigger={<Button icon={<IconMenu2 size="1.25em" stroke="1.25" />} />} />
            </div>
            <div className="flex size-full grow items-center justify-end gap-4 overflow-hidden">
              <AppTheme.LinkButton
                themeMode={themeMode as ThemeMode}
                setThemeMode={handleSetThemeMode}
              />
              <AppLocale.LinkButton />
              {/* 小屏铃铛：语言切换右侧、GitHub 左侧，最右保留设置入口。
                  offset 向内收（+y 下压、-x 左移），否则角标伸出按钮顶部被 Header 裁掉一半 */}
              <Badge count={unreadCount} size="small" offset={[-4, 6]}>
                <Button
                  aria-label={t('message_center') || "消息"}
                  icon={<IconBell size="1.25em" stroke="1.25" />}
                  onClick={() => navigate("/notifications")}
                />
              </Badge>
              <Button icon={<IconBrandGithub size="1.25em" stroke="1.25" />} onClick={handleGitHubClick} />
              <Button icon={<IconSettings size="1.25em" stroke="1.25" />} onClick={() => navigate("/setting")} />
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

  // P2-02：能力集启动时加载一次；未就绪时按兼容默认渲染（不阻塞首屏）
  const capabilities = useCapabilityStore((s) => s.capabilities);
  useEffect(() => {
    void useCapabilityStore.getState().loadCapabilities();
  }, []);

  const MENU_KEY_HOME = "/home";
  const MENU_KEY_CHART = "/chart";
  const MENU_KEY_AGENT = "/agent";
  const MENU_KEY_STRATEGY = "/strategy-management";
  const MENU_KEY_STRATEGY_TASK = "/strategy-worker";
  const MENU_KEY_DATA = "/data-management";
  const MENU_KEY_FACTOR = "/factor-analysis";
  const MENU_KEY_MODEL_HUB = "/model-hub";
  const MENU_KEY_RISK = "/risk-monitor";
  const MENU_KEY_RESEARCH = "/research";

  // ponytail: 路由路径 → 翻译键的映射表，用于自动设置浏览器 tab 标题。
  // 匹配策略：先精确匹配路径前缀，再 fallback 到通用的路径段
  const ROUTE_TITLE_KEYS: Array<[string, string]> = [
    [MENU_KEY_HOME, "home"],
    [MENU_KEY_CHART, "chart"],
    [MENU_KEY_AGENT, "strategy_agent"],
    [MENU_KEY_STRATEGY, "strategy_management"],
    [MENU_KEY_STRATEGY_TASK, "strategy_task"],
    [MENU_KEY_DATA, "data_management"],
    [MENU_KEY_MODEL_HUB, "model_hub"],
    [MENU_KEY_RISK, "risk_monitor"],
    // 子路由补全 — menu 里没有但需要正确标题的页面
    ["/backtest", "backtest"],
    ["/notifications", "message_center"],
    ["/setting/general", "general"],
    ["/setting/env", "env"],
    ["/setting/exchange", "exchange"],
    ["/setting/notifications", "notifications"],
    ["/setting/model", "model"],
    ["/setting/info", "info"],
    ["/setting/plugins", "plugins"],
    ["/setting", "setting"],
    ["/strategy-editor", "strategy_editor"],
    ["/factor-analysis", "factor_analysis"],
    ["/research", "research"],
    ["/model-management", "model_management"],
  ];

  const [pluginMenus, setPluginMenus] = useState(pluginRegistry.getMenuItems());

  useEffect(() => {
    const unsubscribe = pluginRegistry.subscribe(() => {
      setPluginMenus(pluginRegistry.getMenuItems());
    });
    return unsubscribe;
  }, []);

  const baseMenuItems: Required<MenuProps>["items"] = (
    [
      [MENU_KEY_HOME, "home", <IconHome size="1em" />, false],
      [MENU_KEY_CHART, "chart", <IconChartBar size="1em" />, false],
      [MENU_KEY_AGENT, "strategy_agent", <IconRobot size="1em" />, false],
      [MENU_KEY_STRATEGY, "strategy_management", <IconCode size="1em" />, false],
      [MENU_KEY_STRATEGY_TASK, "strategy_task", <IconBotId size="1em" />, false],
      [MENU_KEY_DATA, "data_management", <IconDatabase size="1em" />, false],
      [MENU_KEY_FACTOR, "factor_analysis", <IconChartHistogram size="1em" />, false],
      [MENU_KEY_RESEARCH, "research", <IconMicroscope size="1em" />, false],
      [MENU_KEY_MODEL_HUB, "model_hub", <IconStack size="1em" />, false],
      // 回测中心：RL/普通回测任务列表的固定入口；side nav 分组后落入「交易」组
      ["/backtest", "backtest_center", <IconFlask size="1em" />, false],
      [MENU_KEY_RISK, "risk_monitor", <IconShield size="1em" />, false],
    ] satisfies Array<[string, string, React.ReactNode, boolean]>
  ).map(([key, label, icon, disabled]) => {
    return {
      key: key,
      icon: (
        <span className="anticon" role="img">
          {icon}
        </span>
      ),
      // 折叠时也保留 label：inlineCollapsed 模式下 antd 自动隐藏文字、只显图标，
      // 并在 hover 时浮出包含该 label 的 tooltip
      label: t(label),
      disabled: disabled,
      onClick: () => {
        if (!disabled) {
          navigate(key);
          onSelect?.(key);
        }
      },
    };
  });

  const pluginMenuItems: Required<MenuProps>["items"] = pluginMenus.map((pm) => ({
    key: pm.key,
    icon: (
      <span className="anticon" role="img">
        {pm.icon || <IconPlug size="1em" />}
      </span>
    ),
    label: pm.label,
    onClick: () => {
      navigate(pm.key);
      onSelect?.(pm.key);
    },
  }));

  // P2-02 能力过滤：agent_gateway 关闭时隐藏代理菜单（平铺层单层 filter，逻辑不变）
  const capabilityItems = [...baseMenuItems, ...pluginMenuItems].filter(
    (item) => item?.key !== MENU_KEY_AGENT || isCapabilityEnabled(capabilities, "agent_gateway"),
  );
  const itemByKey = new Map(capabilityItems.map((item) => [item!.key as string, item!]));

  // 侧边菜单按业务域分组：无组区（首页 / 策略智能体）→「交易」→「研究」→ 插件项；
  // 分组容器 items 是 type:'group'，叶子项全部来自上面已过滤的平铺 Map
  const menuItems: Required<MenuProps>["items"] = [
    ...capabilityItems.filter(
      (item) => item!.key === MENU_KEY_HOME || item!.key === MENU_KEY_AGENT,
    ),
    {
      key: "nav-group-trade",
      type: "group" as const,
      label: t("nav_group_trade"),
      children: [MENU_KEY_STRATEGY, MENU_KEY_STRATEGY_TASK, "/backtest", MENU_KEY_RISK].map(
        (key) => itemByKey.get(key)!,
      ),
    },
    {
      key: "nav-group-research",
      type: "group" as const,
      label: t("nav_group_research_data"),
      children: [MENU_KEY_CHART, MENU_KEY_FACTOR, MENU_KEY_RESEARCH, MENU_KEY_DATA, MENU_KEY_MODEL_HUB].map(
        (key) => itemByKey.get(key)!,
      ),
    },
    ...pluginMenuItems,
  ];

  const [menuSelectedKey, setMenuSelectedKey] = useState<string>();

  const getActiveMenuItem = () => {
    // 分组后顶层是 type:'group' 容器（无路由 key），先拍平到叶子项再匹配
    const flatItems = menuItems.flatMap((item) =>
      item && "children" in item && Array.isArray(item.children) ? item.children : [item],
    );
    const item =
      flatItems.find((it) => it?.key === location.pathname) ??
      flatItems.find(
        (it) => it?.key !== MENU_KEY_CHART && location.pathname.startsWith(it?.key as string),
      );
    return item;
  };

  useEffect(() => {
    const item = getActiveMenuItem();
    if (item) {
      setMenuSelectedKey(item.key as string);
    } else {
      setMenuSelectedKey(void 0);
    }

    // ponytail: 统一自动设置浏览器 tab 标题 — 从 ROUTE_TITLE_KEYS 找最长前缀匹配
    // 子路由（如 /strategy-worker/123、/backtest/detail/456）会匹配到父路径的标题
    // 页面内手动 setPageTitle 会在子组件挂载后覆盖这里的值（允许的）
    const matched = ROUTE_TITLE_KEYS
      .filter(([path]) => location.pathname === path || location.pathname.startsWith(`${path}/`))
      .sort((a, b) => b[0].length - a[0].length)[0];
    if (matched) {
      setPageTitle(t(matched[1]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [location.pathname]);

  useEffect(() => {
    if (menuSelectedKey && menuSelectedKey !== getActiveMenuItem()?.key) {
      navigate(menuSelectedKey);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [menuSelectedKey]);

  return (
    <>
      <div className="h-[64px] w-full overflow-hidden px-4 py-2 max-md:py-0">
        <div className="flex size-full items-center justify-around gap-2">
          <img src="/logo.svg" className="size-[36px]" />
          {!collapsed && (
            <span className="truncate text-base leading-[64px] font-semibold">QuantCell</span>
          )}
        </div>
      </div>
      <div className="w-full grow overflow-x-hidden overflow-y-auto">
        <Menu
          style={{ background: "transparent", borderInlineEnd: "none" }}
          // 分组名居中：antd group 标题默认 padding 8px 16px + 左对齐，80px 折叠栏里贴左且
          // 英文 Research（≈58px）放不进 47px 内容区会换行；去内边距后两态均居中且不折行
          className="[&_.ant-menu-item-group-title]:px-0 [&_.ant-menu-item-group-title]:text-center"
          items={menuItems}
          mode="inline"
          inlineCollapsed={collapsed}
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
        destroyOnHidden
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
