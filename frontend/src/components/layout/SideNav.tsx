/* eslint-disable react-refresh/only-export-components -- pickRouteTitleKey 与菜单/选中态共用同一张 ROUTE_TITLE_KEYS 表，拆文件反而制造第二份真相源；降级为整页刷新 */
/**
 * 侧栏导航（design-spec §6.15）
 *
 * 原型导航是 .nav-item 裸按钮（选中态含左侧 3px 主色竖条 + primary 9% tint 底、
 * 分组标题 10.5px/.16em），antd Menu 的折叠态会对 icon 写 line-height/height 硬规则，
 * 覆盖这些值需要的 hack 比自绘更多，故按规范自绘；折叠态用 antd Tooltip 补足
 * 纯图标模式的可发现性（对齐 Menu inlineCollapsed 的体验）。
 *
 * 职责：菜单数据（能力过滤 + 插件订阅）、选中态（含二级路由高亮父菜单 §7）、
 * 文档标题（ROUTE_TITLE_KEYS，面包屑共用同一张表）。
 */
import { memo, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import {
  IconBotId,
  IconChartBar,
  IconChartHistogram,
  IconCode,
  IconDatabase,
  IconFlask,
  IconHome,
  IconMicroscope,
  IconPlug,
  IconRobot,
  IconStack,
} from "@tabler/icons-react";
import { Tooltip } from "antd";

// P2-02 能力开关：菜单按部署能力过滤（agent_gateway 关闭时隐藏代理菜单）
import { isCapabilityEnabled, useCapabilityStore } from "@/store/capabilityStore";
import { setPageTitle } from "@/utils/pageTitle";
import { pluginRegistry } from "@/plugins/PluginRegistry";

const MENU_KEY_HOME = "/home";
const MENU_KEY_CHART = "/chart";
const MENU_KEY_AGENT = "/agent";
const MENU_KEY_STRATEGY = "/strategy-management";
const MENU_KEY_STRATEGY_TASK = "/strategy-worker";
const MENU_KEY_DATA = "/data-management";
const MENU_KEY_FACTOR = "/factor-analysis";
const MENU_KEY_MODEL_HUB = "/model-hub";
const MENU_KEY_RESEARCH = "/research";
const MENU_KEY_BACKTEST = "/backtest";

/** 路由路径 → 翻译键映射表：文档标题与 Header 面包屑共用（§7 用同一标题表） */
const ROUTE_TITLE_KEYS: Array<[string, string]> = [
  [MENU_KEY_HOME, "home"],
  [MENU_KEY_CHART, "chart"],
  [MENU_KEY_AGENT, "strategy_agent"],
  [MENU_KEY_STRATEGY, "strategy_management"],
  [MENU_KEY_STRATEGY_TASK, "strategy_task"],
  [MENU_KEY_DATA, "data_management"],
  [MENU_KEY_MODEL_HUB, "model_hub"],
  // 子路由补全 — menu 里没有但需要正确标题的页面
  [MENU_KEY_BACKTEST, "backtest"],
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

/** 最长前缀匹配出标题键；找不到返回 undefined（Keep 默认标题） */
export function pickRouteTitleKey(pathname: string): string | undefined {
  return ROUTE_TITLE_KEYS.filter(
    ([path]) => pathname === path || pathname.startsWith(`${path}/`),
  ).sort((a, b) => b[0].length - a[0].length)[0]?.[1];
}

/**
 * 二级路由 → 父菜单高亮（§7）：二级页不占侧栏项，但命中时父菜单保持选中。
 * 未在此表也未精确命中叶子项的路径，走通用「最长前缀」兜底（插件页等）。
 */
const ROUTE_PARENT_MAP: Array<[string, string]> = [
  ["/strategy-editor", MENU_KEY_STRATEGY],
  ["/strategy-worker", MENU_KEY_STRATEGY_TASK],
  ["/data-management/market-replay", MENU_KEY_DATA],
  ["/model-management", MENU_KEY_MODEL_HUB],
  ["/backtest", MENU_KEY_BACKTEST],
  ["/research", MENU_KEY_RESEARCH],
];

interface NavLeaf {
  key: string;
  icon: React.ReactNode;
  label: string;
}

interface SideNavProps {
  /** 折叠态：只显图标居中 + hover Tooltip。Drawer 内不传（恒展开）。 */
  collapsed?: boolean;
  /** 导航点击后的额外回调（Drawer 内用于关闭抽屉） */
  onSelect?: (key: string) => void;
}

const SideNav = memo(({ collapsed, onSelect }: SideNavProps) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();

  // P2-02：能力集启动时加载一次；未就绪时按兼容默认渲染（不阻塞首屏）
  const capabilities = useCapabilityStore((s) => s.capabilities);
  useEffect(() => {
    void useCapabilityStore.getState().loadCapabilities();
  }, []);

  const [pluginMenus, setPluginMenus] = useState(pluginRegistry.getMenuItems());

  useEffect(() => {
    const unsubscribe = pluginRegistry.subscribe(() => {
      setPluginMenus(pluginRegistry.getMenuItems());
    });
    return unsubscribe;
  }, []);

  const leafByKey = useMemo(() => {
    const base: NavLeaf[] = [
      { key: MENU_KEY_HOME, icon: <IconHome size={16} stroke={1.5} />, label: t("home") },
      { key: MENU_KEY_CHART, icon: <IconChartBar size={16} stroke={1.5} />, label: t("chart") },
      { key: MENU_KEY_AGENT, icon: <IconRobot size={16} stroke={1.5} />, label: t("strategy_agent") },
      { key: MENU_KEY_STRATEGY, icon: <IconCode size={16} stroke={1.5} />, label: t("strategy_management") },
      { key: MENU_KEY_STRATEGY_TASK, icon: <IconBotId size={16} stroke={1.5} />, label: t("strategy_task") },
      { key: MENU_KEY_BACKTEST, icon: <IconFlask size={16} stroke={1.5} />, label: t("backtest_center") },
      { key: MENU_KEY_FACTOR, icon: <IconChartHistogram size={16} stroke={1.5} />, label: t("factor_analysis") },
      { key: MENU_KEY_RESEARCH, icon: <IconMicroscope size={16} stroke={1.5} />, label: t("research") },
      { key: MENU_KEY_DATA, icon: <IconDatabase size={16} stroke={1.5} />, label: t("data_management") },
      { key: MENU_KEY_MODEL_HUB, icon: <IconStack size={16} stroke={1.5} />, label: t("model_hub") },
    ];
    const plugins: NavLeaf[] = pluginMenus.map((pm) => ({
      key: pm.key,
      icon: pm.icon || <IconPlug size={16} stroke={1.5} />,
      label: pm.label,
    }));
    // P2-02 能力过滤：agent_gateway 关闭时隐藏代理菜单
    const all = [...base, ...plugins].filter(
      (leaf) => leaf.key !== MENU_KEY_AGENT || isCapabilityEnabled(capabilities, "agent_gateway"),
    );
    return new Map(all.map((leaf) => [leaf.key, leaf]));
  }, [t, pluginMenus, capabilities]);

  // 分组结构：无组区（首页 / 策略智能体）→「交易」→「研究」→ 插件项
  const sections = useMemo(() => {
    const pick = (...keys: string[]): NavLeaf[] =>
      keys.map((key) => leafByKey.get(key)).filter((leaf): leaf is NavLeaf => Boolean(leaf));
    return [
      { type: "items" as const, items: pick(MENU_KEY_HOME, MENU_KEY_AGENT) },
      { type: "group" as const, title: t("nav_group_trade"), items: pick(MENU_KEY_STRATEGY, MENU_KEY_STRATEGY_TASK, MENU_KEY_BACKTEST) },
      {
        type: "group" as const,
        title: t("nav_group_research_data"),
        items: pick(MENU_KEY_CHART, MENU_KEY_FACTOR, MENU_KEY_RESEARCH, MENU_KEY_DATA, MENU_KEY_MODEL_HUB),
      },
      {
        type: "items" as const,
        items: pluginMenus.map((pm) => pm.key).map((key) => leafByKey.get(key)).filter((leaf): leaf is NavLeaf => Boolean(leaf)),
      },
    ];
  }, [leafByKey, pluginMenus, t]);

  const flatLeaves = useMemo(() => [...leafByKey.values()], [leafByKey]);

  /** 当前应高亮的菜单键：精确命中 → 二级路由父级映射 → 通用最长前缀 */
  const activeKey = useMemo(() => {
    const exact = flatLeaves.find((leaf) => leaf.key === location.pathname);
    if (exact) return exact.key;
    const mapped = ROUTE_PARENT_MAP.find(
      ([prefix]) => location.pathname === prefix || location.pathname.startsWith(`${prefix}/`),
    );
    if (mapped && leafByKey.has(mapped[1])) return mapped[1];
    const fuzzy = flatLeaves
      .filter((leaf) => leaf.key !== MENU_KEY_CHART && location.pathname.startsWith(leaf.key))
      .sort((a, b) => b.key.length - a.key.length)[0];
    return fuzzy?.key;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [location.pathname, flatLeaves]);

  // 统一自动设置浏览器 tab 标题 — 从 ROUTE_TITLE_KEYS 找最长前缀匹配
  // 子路由（如 /strategy-worker/123、/backtest/detail/456）会匹配到父路径的标题
  // 页面内手动 setPageTitle 会在子组件挂载后覆盖这里的值（允许的）
  useEffect(() => {
    const titleKey = pickRouteTitleKey(location.pathname);
    if (titleKey) {
      setPageTitle(t(titleKey));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 同上，pathname 变化时执行
  }, [location.pathname]);

  const handleNavigate = (key: string) => {
    navigate(key);
    onSelect?.(key);
  };

  const renderItem = (leaf: NavLeaf) => {
    const node = (
      <button
        key={leaf.key}
        type="button"
        className={`qc-nav-item${leaf.key === activeKey ? " on" : ""}`}
        aria-current={leaf.key === activeKey ? "page" : undefined}
        onClick={() => handleNavigate(leaf.key)}
      >
        {leaf.icon}
        <span className="qc-nav-label">{leaf.label}</span>
      </button>
    );
    // 折叠态只显图标：hover 浮出 label（对齐 antd inlineCollapsed 的 Tooltip 体验）
    if (!collapsed) return node;
    return (
      <Tooltip key={leaf.key} title={leaf.label} placement="right">
        {node}
      </Tooltip>
    );
  };

  return (
    <nav className="qc-nav" aria-label={t("side_navigation")}>
      {sections.map((section, index) => {
        const body = section.items.map(renderItem);
        if (!body.length) return null;
        if (section.type === "group") {
          return (
            <div key={`group-${index}`} role="presentation">
              <div className="qc-nav-group-t">{section.title}</div>
              {body}
            </div>
          );
        }
        // ponytail: index 作 key —— 无组区/插件区在渲染期是稳定集合，分组重排不会跨区移动
        return <div key={`items-${index}`} className="contents">{body}</div>;
      })}
    </nav>
  );
});

export default SideNav;
