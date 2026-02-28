/**
 * 设置页面布局组件
 * 功能：提供设置页面的整体布局
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  IconUser,
  IconSettings,
  IconBell,
  IconApi,
  IconInfoCircle,
} from "@tabler/icons-react";
import { Menu } from "antd";
import { SettingsProvider } from "./SettingsContext";
import { setPageTitle } from "@/router";
import PageContainer from "@/components/PageContainer";

const SettingLayout = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();

  // 菜单配置
  const menus = [
    ["basic", t("basic_settings") || "基本设置", <IconUser size="1em" />],
    ["system", t("system_config") || "系统配置", <IconSettings size="1em" />],
    ["notifications", t("notification_settings") || "通知设置", <IconBell size="1em" />],
    ["api", t("api_settings") || "API 设置", <IconApi size="1em" />],
    ["info", t("system_info") || "系统信息", <IconInfoCircle size="1em" />],
  ] satisfies [string, string, React.ReactElement][];

  // 当前选中的菜单项
  const [menuKey, setMenuKey] = useState<string>(() => {
    const pathParts = location.pathname.split("/");
    return pathParts[2] || "basic";
  });

  // 监听路由变化，更新选中菜单
  useEffect(() => {
    const subpath = location.pathname.split("/")[2];
    if (!subpath) {
      navigate("/setting/basic");
      return;
    }
    setMenuKey(subpath);
  }, [location.pathname, navigate]);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t("setting") || "设置");
  }, [t]);

  // 处理菜单点击
  const handleMenuClick = ({ key }: { key: string }) => {
    setMenuKey(key);
    navigate(`/setting/${key}`);
  };

  return (
    <PageContainer title={t("setting") || "设置"}>
      {/* 移动端水平菜单 */}
      <div className="hidden select-none max-lg:block mb-4">
        <Menu
          style={{ background: "transparent", borderInlineEnd: "none" }}
          mode="horizontal"
          selectedKeys={[menuKey]}
          items={menus.map(([key, label, icon]) => ({
            key,
            label,
            icon: (
              <span className="anticon scale-125" role="img">
                {icon}
              </span>
            ),
          }))}
          onClick={handleMenuClick}
        />
      </div>

      {/* 主内容区域 */}
      <div className="flex justify-stretch gap-x-4">
        {/* 桌面端左侧垂直菜单 */}
        <div className="w-[256px] select-none max-lg:hidden">
          <Menu
            style={{ background: "transparent", borderInlineEnd: "none" }}
            mode="vertical"
            selectedKeys={[menuKey]}
            items={menus.map(([key, label, icon]) => ({
              key,
              label,
              icon: (
                <span className="anticon scale-125" role="img">
                  {icon}
                </span>
              ),
            }))}
            onClick={handleMenuClick}
          />
        </div>

        {/* 右侧内容区域 */}
        <div className="w-full flex-1 min-w-0">
          <div className="px-4 max-lg:px-0 max-lg:py-6">
            <Outlet />
          </div>
        </div>
      </div>
    </PageContainer>
  );
};

// 导出带 Provider 的 Setting 组件
const Setting = () => {
  return (
    <SettingsProvider>
      <SettingLayout />
    </SettingsProvider>
  );
};

export default Setting;
