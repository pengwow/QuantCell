/**
 * 设置页面布局组件
 * 功能：提供设置页面的整体布局
 */
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  IconPalette,
  IconBell,
  IconInfoCircle,
  IconRobot,
  IconBuildingBank,
  IconVariable,
  IconPuzzle,
} from "@tabler/icons-react";
import { Menu } from "antd";
import { SettingsProvider } from "./SettingsContext";
import { setPageTitle } from "@/utils/pageTitle";
import PageContainer from "@/components/PageContainer";

const SettingLayout = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();

  // 菜单配置
  const menus = [
    ["general", t("general_settings") || "通用设置", <IconPalette size="1em" />],
    ["env", t("env_variables") || "环境变量", <IconVariable size="1em" />],
    ["exchange", t("exchange_settings") || "交易所设置", <IconBuildingBank size="1em" />],
    ["notifications", t("notification_settings") || "通知设置", <IconBell size="1em" />],
    ["model", t("model_settings") || "模型设置", <IconRobot size="1em" />],
    ["info", t("system_info") || "系统信息", <IconInfoCircle size="1em" />],
    ["plugins", t("plugin_management") || "插件管理", <IconPuzzle size="1em" />],
  ] satisfies [string, string, React.ReactElement][];

  // 当前选中的菜单项由路由 URL 推导，避免 setState-in-effect 与状态不同步问题
  const menuKey = location.pathname.split("/")[2] || "general";

  // 监听路由变化，无子路径时重定向到通用设置
  useEffect(() => {
    const subpath = location.pathname.split("/")[2];
    if (!subpath) {
      navigate("/setting/general");
      return;
    }
  }, [location.pathname, navigate]);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t("setting") || "设置");
  }, [t]);

  // 处理菜单点击
  const handleMenuClick = ({ key }: { key: string }) => {
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
