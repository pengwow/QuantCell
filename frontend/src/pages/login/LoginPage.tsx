/**
 * 登录页面
 * 参考 certimate 项目登录页面设计
 * 支持普通用户登录和访客登录
 */
import { useMemo, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { IconArrowRight, IconLock, IconUser, IconUserCircle } from "@tabler/icons-react";
import { Button, Card, Form, Input, Space, Typography, message, Divider, Tag } from "antd";
import { saveToken } from "../../utils/tokenManager";
import { configApi } from "../../api";

const { Title, Text } = Typography;

// 应用主题函数
const applyTheme = (theme: 'light' | 'dark' | 'auto') => {
  const root = document.documentElement;
  let effectiveTheme: 'light' | 'dark';

  if (theme === 'auto') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    effectiveTheme = prefersDark ? 'dark' : 'light';
  } else {
    effectiveTheme = theme;
  }

  // 设置 data-theme 属性（用于 CSS 变量选择）
  root.setAttribute('data-theme', effectiveTheme);

  // 同时设置/移除 dark class（用于 App.tsx 中的主题监听和 Tailwind 暗色模式）
  if (effectiveTheme === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }

  // 同步到 localStorage（用于 useBrowserTheme hook）
  localStorage.setItem('quantcell-ui-theme', effectiveTheme);
};

// 加载主题配置
const loadThemeConfig = async () => {
  try {
    // 先尝试从 localStorage 获取
    const savedTheme = localStorage.getItem('quantcell-ui-theme');
    if (savedTheme) {
      applyTheme(savedTheme as 'light' | 'dark' | 'auto');
      return;
    }

    // 如果没有，从后端获取
    const response = await configApi.getConfig();
    const groupedConfig = response?.data || response;

    // 将分组配置扁平化
    const flattenConfig: Record<string, any> = {};
    if (groupedConfig && typeof groupedConfig === 'object') {
      Object.entries(groupedConfig).forEach(([, groupValues]) => {
        if (groupValues && typeof groupValues === 'object') {
          Object.entries(groupValues as Record<string, any>).forEach(([key, value]) => {
            flattenConfig[key] = value;
          });
        }
      });
    }

    const theme = flattenConfig['theme'] || 'light';
    applyTheme(theme as 'light' | 'dark' | 'auto');
  } catch (error) {
    console.error('加载主题配置失败:', error);
    // 默认使用浅色主题
    applyTheme('light');
  }
};

const LoginPage = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  // 加载主题配置
  useEffect(() => {
    loadThemeConfig();
  }, []);

  // 背景样式 - 参考 certimate 的网格背景
  const bgStyle = useMemo<React.CSSProperties>(() => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32" fill="none" stroke="rgb(100 100 100 / 0.08)"><path d="M0 .5H31.5V32"/></svg>`;

    return {
      backgroundImage: `url('data:image/svg+xml;base64,${btoa(svg)}')`,
      maskImage: `linear-gradient(to bottom right, transparent, black, transparent)`,
    };
  }, []);

  /**
   * 获取登录后跳转的目标路径
   * 优先使用sessionStorage中保存的redirect_after_login
   */
  const getRedirectPath = (): string => {
    const savedPath = sessionStorage.getItem('redirect_after_login');
    if (savedPath && savedPath !== '/login') {
      // 清除保存的路径，避免重复跳转
      sessionStorage.removeItem('redirect_after_login');
      return savedPath;
    }
    return '/';
  };

  // 处理登录
  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      // 调用后端登录 API 获取 JWT token
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(values),
      });

      if (!response.ok) {
        throw new Error("登录失败");
      }

      const data = await response.json();

      if (data.code === 0 && data.data?.access_token) {
        // 保存 token 使用 tokenManager
        saveToken({
          access_token: data.data.access_token,
          refresh_token: data.data.refresh_token || "",
          token_type: data.data.token_type || "Bearer",
        });
        // 保存用户角色信息到 localStorage
        localStorage.setItem('user_role', data.data.role || 'user');
        localStorage.setItem('is_guest', String(data.data.is_guest || false));
        localStorage.setItem('username', data.data.username || '访客');

        const loginMessage = data.data.is_guest
          ? (t("guest_login_success") || "访客登录成功")
          : (t("login_success") || "登录成功");
        message.success(loginMessage);
        // 跳转到之前保存的页面或首页
        const redirectPath = getRedirectPath();
        navigate(redirectPath);
      } else {
        message.error(data.message || t("login_failed") || "登录失败");
      }
    } catch (error) {
      console.error("登录错误:", error);
      message.error(t("login_failed") || "登录失败");
    } finally {
      setLoading(false);
    }
  };

  // 处理访客登录
  const handleGuestLogin = async () => {
    setLoading(true);
    try {
      // 调用后端登录 API，不传递用户名和密码
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ username: "", password: "" }),
      });

      if (!response.ok) {
        throw new Error("访客登录失败");
      }

      const data = await response.json();

      if (data.code === 0 && data.data?.access_token) {
        // 保存 token 使用 tokenManager
        saveToken({
          access_token: data.data.access_token,
          refresh_token: data.data.refresh_token || "",
          token_type: data.data.token_type || "Bearer",
        });
        // 保存用户角色信息到 localStorage
        localStorage.setItem('user_role', data.data.role || 'guest');
        localStorage.setItem('is_guest', 'true');
        localStorage.setItem('username', '访客');

        message.success(t("guest_login_success") || "访客登录成功");
        // 跳转到之前保存的页面或首页
        const redirectPath = getRedirectPath();
        navigate(redirectPath);
      } else {
        message.error(data.message || t("guest_login_failed") || "访客登录失败");
      }
    } catch (error) {
      console.error("访客登录错误:", error);
      message.error(t("guest_login_failed") || "访客登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full bg-background text-foreground">
      {/* 背景 */}
      <div
        className="pointer-events-none fixed inset-0"
        style={bgStyle}
      />

      {/* 登录卡片 */}
      <div className="flex h-screen w-full items-center justify-center px-4">
        <Card className="w-full max-w-md rounded-lg shadow-lg bg-white dark:bg-gray-800 dark:border-gray-700">
          <div className="px-6 py-8">
            {/* Logo */}
            <div className="mb-8 flex flex-col items-center justify-center">
              <img
                src="/logo.svg"
                alt="QuantCell"
                className="mb-4 h-16 w-16"
                onError={(e) => {
                  // 如果 logo 加载失败，显示文字
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
              <Title level={3} className="m-0 dark:text-white">
                QuantCell
              </Title>
              <Text type="secondary" className="dark:text-gray-400">
                {t("login_subtitle") || "量化交易平台"}
              </Text>
            </div>

            {/* 登录表单 */}
            <Form
              form={form}
              layout="vertical"
              onFinish={handleLogin}
              autoComplete="off"
            >
              <Form.Item
                name="username"
                label={<span className="dark:text-gray-300">{t("username") || "用户名"}</span>}
                rules={[
                  {
                    required: true,
                    message: t("username_required") || "请输入用户名",
                  },
                ]}
                validateTrigger="onSubmit"
              >
                <Space.Compact block className="h-10">
                  <Button
                    icon={<IconUser size="1.25em" />}
                    disabled
                    className="h-10 flex items-center justify-center dark:bg-gray-700 dark:border-gray-600 dark:text-gray-300"
                  />
                  <Input
                    placeholder={t("enter_username") || "请输入用户名"}
                    className="h-10 dark:bg-gray-700 dark:border-gray-600 dark:text-white dark:placeholder-gray-400"
                    autoFocus
                  />
                </Space.Compact>
              </Form.Item>

              <Form.Item
                name="password"
                label={<span className="dark:text-gray-300">{t("password") || "密码"}</span>}
                rules={[
                  {
                    required: true,
                    message: t("password_required") || "请输入密码",
                  },
                ]}
                validateTrigger="onSubmit"
              >
                <Space.Compact block className="h-10">
                  <Button
                    icon={<IconLock size="1.25em" />}
                    disabled
                    className="h-10 flex items-center justify-center dark:bg-gray-700 dark:border-gray-600 dark:text-gray-300"
                  />
                  <Input.Password
                    placeholder={t("enter_password") || "请输入密码"}
                    className="h-10 dark:bg-gray-700 dark:border-gray-600 dark:text-white dark:placeholder-gray-400"
                  />
                </Space.Compact>
              </Form.Item>

              <Form.Item className="mb-0 mt-8">
                <Button
                  type="primary"
                  htmlType="submit"
                  block
                  size="large"
                  loading={loading}
                  icon={<IconArrowRight size="1.25em" />}
                  iconPosition="end"
                >
                  {t("login") || "登录"}
                </Button>
              </Form.Item>
            </Form>

            {/* 提示信息 */}
            <div className="mt-6 text-center">
              <Text type="secondary" className="text-sm dark:text-gray-400">
                {t("login_hint") || "请输入用户名和密码进行登录"}
              </Text>
            </div>

            {/* 访客登录选项 */}
            <Divider className="dark:border-gray-600">
              <Text type="secondary" className="text-xs dark:text-gray-400">
                {t("or") || "或"}
              </Text>
            </Divider>

            <Button
              type="default"
              block
              size="large"
              loading={loading}
              icon={<IconUserCircle size="1.25em" />}
              onClick={handleGuestLogin}
              className="dark:bg-gray-700 dark:border-gray-600 dark:text-gray-300"
            >
              {t("guest_login") || "访客登录"}
            </Button>

            <div className="mt-4 text-center">
              <Tag color="orange" className="dark:bg-orange-900 dark:text-orange-200">
                {t("guest_hint") || "访客：仅可浏览，部分功能受限"}
              </Tag>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default LoginPage;
