/* eslint-disable react-refresh/only-export-components -- 默认导出为组件集合对象（Dropdown/Icon/LinkButton），属刻意的复合组件 API，插件无法识别，禁用后降级为整页刷新 */
import { useTranslation } from "react-i18next";
import { IconDeviceDesktop, IconMoon, IconSun, type IconProps } from "@tabler/icons-react";
import { Dropdown, type DropdownProps } from "antd";
import type { MenuProps } from "antd";

import Show from "./Show";

export type ThemeMode = "light" | "dark" | "system";

export interface AppThemeProps {
  themeMode: ThemeMode;
  setThemeMode: (mode: ThemeMode) => void;
}

// 仅 AppTheme 内部使用的菜单项 hook，无需导出（避免 react-refresh mixed export 告警）
const useAppThemeMenuItems = (props: AppThemeProps) => {
  const { t } = useTranslation();
  const { themeMode, setThemeMode } = props;

  const items: MenuProps["items"] = [
    {
      key: "light",
      label: t("theme_light"),
      icon: <IconSun className="size-4" />,
      onClick: () => {
        if (themeMode !== "light") {
          setThemeMode("light");
        }
      },
    },
    {
      key: "dark",
      label: t("theme_dark"),
      icon: <IconMoon className="size-4" />,
      onClick: () => {
        if (themeMode !== "dark") {
          setThemeMode("dark");
        }
      },
    },
    {
      key: "system",
      label: t("theme_system"),
      icon: <IconDeviceDesktop className="size-4" />,
      onClick: () => {
        if (themeMode !== "system") {
          setThemeMode("system");
        }
      },
    },
  ];

  return items;
};

export interface AppThemeDropdownProps extends AppThemeProps {
  children?: React.ReactNode;
  trigger?: DropdownProps["trigger"];
}

const AppThemeDropdown = ({ children, trigger = ["click"], ...props }: AppThemeDropdownProps) => {
  const items = useAppThemeMenuItems(props);

  return (
    <Dropdown menu={{ items }} trigger={trigger} placement="bottomRight">
      {children}
    </Dropdown>
  );
};

export interface AppThemeIconProps extends IconProps {
  themeMode: ThemeMode;
}

const AppThemeIcon = ({ themeMode, ...props }: AppThemeIconProps) => {
  return (
    <Show>
      <Show.Case when={themeMode === "light"}>
        <IconSun {...props} />
      </Show.Case>
      <Show.Case when={themeMode === "dark"}>
        <IconMoon {...props} />
      </Show.Case>
      <Show.Default>
        <IconDeviceDesktop {...props} />
      </Show.Default>
    </Show>
  );
};

export interface AppThemeLinkButtonProps extends AppThemeProps {
  className?: string;
  style?: React.CSSProperties;
}

const AppThemeLinkButton = ({ className, style, ...props }: AppThemeLinkButtonProps) => {
  const { t } = useTranslation();
  const { themeMode } = props;

  return (
    <AppThemeDropdown trigger={["click", "hover"]} {...props}>
      {/* 主题入口胶囊（§6.15/§5 Header）：30px 高、15px 圆角、muted 底、16px 主色图标。
       * 几何与配色在 global.css .qc-theme-pill；小屏只留图标（label 隐藏），
       * 当前模式由可见文案直接表达，触发器本身用 aria-haspopup 而非 aria-pressed。 */}
      <button
        type="button"
        className={`qc-theme-pill cursor-pointer ${className || ""}`}
        style={style}
        aria-haspopup="menu"
      >
        <AppThemeIcon themeMode={themeMode} />
        <span className="qc-theme-pill-label">{t(`theme_${themeMode}`)}</span>
      </button>
    </AppThemeDropdown>
  );
};

export default {
  Dropdown: AppThemeDropdown,
  Icon: AppThemeIcon,
  LinkButton: AppThemeLinkButton,
};
