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
import { IconPlug } from "@tabler/icons-react";
import { Tooltip } from "antd";

// P2-02 能力开关：菜单按部署能力过滤（agent_gateway 关闭时隐藏代理菜单）
import { isCapabilityEnabled, useCapabilityStore } from "@/store/capabilityStore";
import { setPageTitle } from "@/utils/pageTitle";
import { pluginRegistry } from "@/plugins/PluginRegistry";

/**
 * 侧栏图标：demo 原型（docs/design/qc-prototype-demo.html <aside class="sider">）的
 * 16px 手绘描边 SVG，路径/线宽数值原样照抄。stroke 写在每个元素上（demo 原样），
 * 颜色由 .qc-nav-item svg 的 color → currentColor 继承。
 */
const NavIconHome = () => (
  <svg width={16} height={16} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M2.7 7.3 8 2.9l5.3 4.4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M4 6.6v6.7h8V6.6" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M6.6 13.3V9.9h2.8v3.4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const NavIconAgent = () => (
  <svg width={16} height={16} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x={2.6} y={4.9} width={10.8} height={8} rx={2.1} stroke="currentColor" strokeWidth={1.4} />
    <path d="M8 4.9V2.3" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    <circle cx={5.9} cy={8.9} r={1.05} fill="currentColor" />
    <circle cx={10.1} cy={8.9} r={1.05} fill="currentColor" />
  </svg>
);

const NavIconStrategy = () => (
  <svg width={16} height={16} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M2.5 4.2h4.6M11.3 4.2h2.2M2.5 8h.9M7.3 8h6.2M2.5 11.8h3.2M10.2 11.8h3.3" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    <circle cx={9.5} cy={4.2} r={1.8} stroke="currentColor" strokeWidth={1.4} />
    <circle cx={5.3} cy={8} r={1.8} stroke="currentColor" strokeWidth={1.4} />
    <circle cx={8.2} cy={11.8} r={1.8} stroke="currentColor" strokeWidth={1.4} />
  </svg>
);

const NavIconStrategyAgent = () => (
  <svg width={16} height={16} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x={2.8} y={3.8} width={10.4} height={8.4} rx={2} stroke="currentColor" strokeWidth={1.4} />
    <path d="M4.9 8h1.7l1.1-2.4 1.6 4.6 1.1-2.2h1.7" stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M5.6 12.2v1.5M10.4 12.2v1.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
  </svg>
);

const NavIconBacktest = () => (
  <svg width={16} height={16} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M2.5 2.8v10.7h11" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
    <path d="m4.6 10.7 2.4-2.9 2.2 1.7 3.4-4.3" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M10.6 5h2.2v2.2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const NavIconChart = () => (
  <svg width={16} height={16} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x={3.9} y={4.6} width={2.7} height={5} rx={0.7} stroke="currentColor" strokeWidth={1.3} />
    <path d="M5.25 2.5v2.1M5.25 9.6v2.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    <rect x={9.3} y={6.1} width={2.7} height={4.4} rx={0.7} stroke="currentColor" strokeWidth={1.3} />
    <path d="M10.65 3.9v2.2M10.65 10.5v2.4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
  </svg>
);

const NavIconFactor = () => (
  <svg width={16} height={16} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx={3.4} cy={11.2} r={1.7} stroke="currentColor" strokeWidth={1.4} />
    <circle cx={8.2} cy={4.6} r={1.7} stroke="currentColor" strokeWidth={1.4} />
    <circle cx={12.8} cy={10.2} r={1.7} stroke="currentColor" strokeWidth={1.4} />
    <path d="m4.6 9.7 2.5-3.6M9.8 5.9l2 2.9M5.1 11.2l6-.6" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" />
  </svg>
);

const NavIconResearch = () => (
  <svg width={16} height={16} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M6.4 2.4h3.2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    <path d="M7.2 2.4v3.5L3.9 11.8a1.6 1.6 0 0 0 1.4 2.4h5.4a1.6 1.6 0 0 0 1.4-2.4L8.8 5.9V2.4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M5.4 10.1h5.2" stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" />
  </svg>
);

const NavIconData = () => (
  <svg width={16} height={16} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <ellipse cx={8} cy={3.6} rx={5} ry={1.9} stroke="currentColor" strokeWidth={1.3} />
    <path d="M3 3.6v8.8c0 1 2.2 1.9 5 1.9s5-.9 5-1.9V3.6" stroke="currentColor" strokeWidth={1.4} />
    <path d="M3 8c0 1 2.2 1.9 5 1.9s5-.9 5-1.9" stroke="currentColor" strokeWidth={1.4} />
  </svg>
);

const NavIconModelHub = () => (
  <svg width={16} height={16} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M8 2.2 14 5 8 7.8 2 5l6-2.8Z" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round" />
    <path d="m2.7 8.3 5.3 2.5 5.3-2.5M2.7 11.3 8 13.8l5.3-2.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const MENU_KEY_HOME = "/home";
const MENU_KEY_CHART = "/chart";
const MENU_KEY_AGENT = "/agent";
const MENU_KEY_STRATEGY = "/strategy-management";
const MENU_KEY_STRATEGY_AGENT = "/strategy-worker";
const MENU_KEY_DATA = "/data-management";
const MENU_KEY_FACTOR = "/factor-analysis";
const MENU_KEY_MODEL_HUB = "/model-hub";
const MENU_KEY_RESEARCH = "/research";
const MENU_KEY_BACKTEST = "/backtest";

/** 路由路径 → 翻译键映射表：文档标题与 Header 面包屑共用（§7 用同一标题表） */
const ROUTE_TITLE_KEYS: Array<[string, string]> = [
  [MENU_KEY_HOME, "home"],
  [MENU_KEY_CHART, "chart"],
  [MENU_KEY_AGENT, "agent_workspace"],
  [MENU_KEY_STRATEGY, "strategy_management"],
  [MENU_KEY_STRATEGY_AGENT, "strategy_agent"],
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
  ["/strategy-worker", MENU_KEY_STRATEGY_AGENT],
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
      { key: MENU_KEY_HOME, icon: <NavIconHome />, label: t("home") },
      { key: MENU_KEY_CHART, icon: <NavIconChart />, label: t("chart") },
      { key: MENU_KEY_AGENT, icon: <NavIconAgent />, label: t("agent_workspace") },
      { key: MENU_KEY_STRATEGY, icon: <NavIconStrategy />, label: t("strategy_management") },
      { key: MENU_KEY_STRATEGY_AGENT, icon: <NavIconStrategyAgent />, label: t("strategy_agent") },
      { key: MENU_KEY_BACKTEST, icon: <NavIconBacktest />, label: t("backtest_center") },
      { key: MENU_KEY_FACTOR, icon: <NavIconFactor />, label: t("factor_analysis") },
      { key: MENU_KEY_RESEARCH, icon: <NavIconResearch />, label: t("research") },
      { key: MENU_KEY_DATA, icon: <NavIconData />, label: t("data_management") },
      { key: MENU_KEY_MODEL_HUB, icon: <NavIconModelHub />, label: t("model_hub") },
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

  // 分组结构：无组区（首页 / 智能体工作台）→「交易」→「研究」→ 插件项
  const sections = useMemo(() => {
    const pick = (...keys: string[]): NavLeaf[] =>
      keys.map((key) => leafByKey.get(key)).filter((leaf): leaf is NavLeaf => Boolean(leaf));
    return [
      { type: "items" as const, items: pick(MENU_KEY_HOME, MENU_KEY_AGENT) },
      { type: "group" as const, title: t("nav_group_trade"), items: pick(MENU_KEY_STRATEGY, MENU_KEY_STRATEGY_AGENT, MENU_KEY_BACKTEST) },
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
