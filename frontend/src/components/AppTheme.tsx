import { useTranslation } from "react-i18next";
import { IconDeviceDesktop, IconMoon, IconSun, type IconProps } from "@tabler/icons-react";
import { Dropdown, type DropdownProps, Typography } from "antd";
import type { MenuProps } from "antd";

import Show from "./Show";

export type ThemeMode = "light" | "dark" | "system";

export interface AppThemeProps {
  themeMode: ThemeMode;
  setThemeMode: (mode: ThemeMode) => void;
}

export const useAppThemeMenuItems = (props: AppThemeProps) => {
  const { t } = useTranslation();
  const { themeMode, setThemeMode } = props;

  const items: MenuProps["items"] = [
    {
      key: "light",
      label: t("theme.light"),
      icon: <IconSun className="size-4" />,
      onClick: () => {
        if (themeMode !== "light") {
          setThemeMode("light");
        }
      },
    },
    {
      key: "dark",
      label: t("theme.dark"),
      icon: <IconMoon className="size-4" />,
      onClick: () => {
        if (themeMode !== "dark") {
          setThemeMode("dark");
        }
      },
    },
    {
      key: "system",
      label: t("theme.system"),
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
      <Typography.Text
        className={`cursor-pointer flex items-center gap-1 ${className || ""}`}
        style={style}
        type="secondary"
      >
        <AppThemeIcon className="size-4" themeMode={themeMode} />
        <span>{t(`theme.${themeMode}`)}</span>
      </Typography.Text>
    </AppThemeDropdown>
  );
};

export default {
  Dropdown: AppThemeDropdown,
  Icon: AppThemeIcon,
  LinkButton: AppThemeLinkButton,
};
