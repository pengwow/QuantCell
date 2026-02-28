import { useTranslation } from "react-i18next";
import { Dropdown, type DropdownProps, Typography } from "antd";
import type { MenuProps } from "antd";

import { IconLanguageEnZh, IconLanguageZhEn } from "./icons";

import Show from "./Show";

export const useAppLocaleMenuItems = () => {
  const { i18n } = useTranslation();

  const items: MenuProps["items"] = [
    {
      key: "zh-CN",
      label: "简体中文",
      icon: <IconLanguageZhEn className="size-4" />,
      onClick: () => {
        if (i18n.language !== "zh-CN" && i18n.language !== "zh") {
          i18n.changeLanguage("zh-CN");
        }
      },
    },
    {
      key: "en-US",
      label: "English",
      icon: <IconLanguageEnZh className="size-4" />,
      onClick: () => {
        if (i18n.language !== "en-US" && i18n.language !== "en") {
          i18n.changeLanguage("en-US");
        }
      },
    },
  ];

  return items;
};

export interface AppLocaleDropdownProps {
  children?: React.ReactNode;
  trigger?: DropdownProps["trigger"];
}

const AppLocaleDropdown = ({ children, trigger = ["click"] }: AppLocaleDropdownProps) => {
  const items = useAppLocaleMenuItems();

  return (
    <Dropdown menu={{ items }} trigger={trigger} placement="bottomRight">
      {children}
    </Dropdown>
  );
};

export interface AppLocaleIconProps extends Omit<React.SVGProps<SVGSVGElement>, 'ref'> {}

const AppLocaleIcon = (props: AppLocaleIconProps) => {
  const { i18n } = useTranslation();

  return (
    <Show>
      <Show.Case when={i18n.language === "zh-CN" || i18n.language === "zh"}>
        <IconLanguageZhEn {...props} />
      </Show.Case>
      <Show.Default>
        <IconLanguageEnZh {...props} />
      </Show.Default>
    </Show>
  );
};

export interface AppLocaleLinkButtonProps {
  className?: string;
  style?: React.CSSProperties;
}

const AppLocaleLinkButton = ({ className, style }: AppLocaleLinkButtonProps) => {
  const { i18n } = useTranslation();

  return (
    <AppLocaleDropdown trigger={["click", "hover"]}>
      <Typography.Text
        className={`cursor-pointer flex items-center gap-1 ${className || ""}`}
        style={style}
        type="secondary"
      >
        <AppLocaleIcon className="size-4" />
        <Show>
          <Show.Case when={i18n.language === "zh-CN" || i18n.language === "zh"}>
            <span>中文</span>
          </Show.Case>
          <Show.Default>
            <span>EN</span>
          </Show.Default>
        </Show>
      </Typography.Text>
    </AppLocaleDropdown>
  );
};

export default {
  Dropdown: AppLocaleDropdown,
  Icon: AppLocaleIcon,
  LinkButton: AppLocaleLinkButton,
};
