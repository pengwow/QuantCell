/**
 * 登录/注册页面
 * 支持用户注册和登录，不再支持访客模式
 */
import { useMemo, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { IconArrowRight, IconLock, IconUser, IconUserPlus } from "@tabler/icons-react";
import { Button, Card, Form, Input, Space, Typography, Divider, Tabs, App } from "antd";
import { saveToken } from "../../utils/tokenManager";
import { setPageTitle } from "@/router";

const { Title, Text } = Typography;

const applyTheme = (theme: 'light' | 'dark' | 'auto') => {
  const root = document.documentElement;
  let effectiveTheme: 'light' | 'dark';

  if (theme === 'auto') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    effectiveTheme = prefersDark ? 'dark' : 'light';
  } else {
    effectiveTheme = theme;
  }

  root.setAttribute('data-theme', effectiveTheme);
  if (effectiveTheme === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
  localStorage.setItem('quantcell-ui-theme', effectiveTheme);
};

const loadThemeConfig = async () => {
  try {
    const savedTheme = localStorage.getItem('quantcell-ui-theme');
    if (savedTheme) {
      applyTheme(savedTheme as 'light' | 'dark' | 'auto');
      return;
    }

    const response = await fetch("/api/config");
    const result = await response.json();
    const groupedConfig = result?.data || result;

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
    applyTheme('light');
  }
};

const LoginPage = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [loginForm] = Form.useForm();
  const [registerForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login');
  const { message } = App.useApp();

  useEffect(() => {
    loadThemeConfig();
  }, []);

  useEffect(() => {
    setPageTitle(t('login') || '登录');
  }, [t]);

  const bgStyle = useMemo<React.CSSProperties>(() => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32" fill="none" stroke="rgb(100 100 100 / 0.08)"><path d="M0 .5H31.5V32"/></svg>`;
    return {
      backgroundImage: `url('data:image/svg+xml;base64,${btoa(svg)}')`,
      maskImage: `linear-gradient(to bottom right, transparent, black, transparent)`,
    };
  }, []);

  const getRedirectPath = (): string => {
    const savedPath = sessionStorage.getItem('redirect_after_login');
    if (savedPath && savedPath !== '/login') {
      sessionStorage.removeItem('redirect_after_login');
      return savedPath;
    }
    return '/chart';
  };

  const saveUserInfo = (data: any) => {
    saveToken({
      access_token: data.access_token,
      refresh_token: data.refresh_token || "",
      token_type: data.token_type || "Bearer",
    });
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token || '');
    localStorage.setItem('user_role', data.role || 'user');
    localStorage.setItem('is_guest', 'false');
    localStorage.setItem('username', data.username || '');
    localStorage.setItem('user_id', String(data.user_id || ''));
    localStorage.setItem('nickname', data.nickname || '');
  };

  // 登录处理
  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });

      const data = await response.json();

      if (data.code === 0 && data.data?.access_token) {
        saveUserInfo(data.data);
        message.success(t("login_success") || "登录成功");
        navigate(getRedirectPath());
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

  // 注册处理
  const handleRegister = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });

      const data = await response.json();

      if (data.code === 0) {
        message.success(t("register_success") || "注册成功，请使用新账号登录");
        setActiveTab('login');
        loginForm.setFieldsValue({ username: values.username, password: '' });
      } else {
        message.error(data.message || t("register_failed") || "注册失败");
      }
    } catch (error) {
      console.error("注册错误:", error);
      message.error(t("register_failed") || "注册失败");
    } finally {
      setLoading(false);
    }
  };

  const tabItems = [
    {
      key: 'login',
      label: (
        <span className="flex items-center gap-1">
          <IconUser size="1em" />
          {t("login_tab") || "登录"}
        </span>
      ),
      children: (
        <Form
          form={loginForm}
          layout="vertical"
          onFinish={handleLogin}
          autoComplete="off"
          className="pt-2"
        >
          <Form.Item
            name="username"
            label={<span className="dark:text-gray-300">{t("username") || "用户名"}</span>}
            rules={[{ required: true, message: t("username_required") || "请输入用户名" }]}
            validateTrigger="onSubmit"
          >
            <Space.Compact block className="h-10">
              <Button icon={<IconUser size="1.25em" />} disabled className="h-10 flex items-center justify-center dark:bg-gray-700 dark:border-gray-600 dark:text-gray-300" />
              <Input placeholder={t("enter_username") || "请输入用户名"} className="h-10 dark:bg-gray-700 dark:border-gray-600 dark:text-white dark:placeholder-gray-400" autoFocus />
            </Space.Compact>
          </Form.Item>

          <Form.Item
            name="password"
            label={<span className="dark:text-gray-300">{t("password") || "密码"}</span>}
            rules={[{ required: true, message: t("password_required") || "请输入密码" }]}
            validateTrigger="onSubmit"
          >
            <Space.Compact block className="h-10">
              <Button icon={<IconLock size="1.25em" />} disabled className="h-10 flex items-center justify-center dark:bg-gray-700 dark:border-gray-600 dark:text-gray-300" />
              <Input.Password placeholder={t("enter_password") || "请输入密码"} className="h-10 dark:bg-gray-700 dark:border-gray-600 dark:text-white dark:placeholder-gray-400" />
            </Space.Compact>
          </Form.Item>

          <Form.Item className="mb-0 mt-8">
            <Button type="primary" htmlType="submit" block size="large" loading={loading} icon={<IconArrowRight size="1.25em" />} iconPlacement="end">
              {t("login") || "登录"}
            </Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'register',
      label: (
        <span className="flex items-center gap-1">
          <IconUserPlus size="1em" />
          {t("register_tab") || "注册"}
        </span>
      ),
      children: (
        <Form
          form={registerForm}
          layout="vertical"
          onFinish={handleRegister}
          autoComplete="off"
          className="pt-2"
        >
          <Form.Item
            name="username"
            label={<span className="dark:text-gray-300">{t("username") || "用户名"}</span>}
            rules={[
              { required: true, message: t("username_required") || "请输入用户名" },
              { min: 2, message: t("username_min_length") || "用户名至少2个字符" },
              { max: 50, message: t("username_max_length") || "用户名不超过50个字符" },
            ]}
            validateTrigger="onSubmit"
          >
            <Space.Compact block className="h-10">
              <Button icon={<IconUser size="1.25em" />} disabled className="h-10 flex items-center justify-center dark:bg-gray-700 dark:border-gray-600 dark:text-gray-300" />
              <Input placeholder={t("enter_username") || "请输入用户名"} className="h-10 dark:bg-gray-700 dark:border-gray-600 dark:text-white dark:placeholder-gray-400" autoFocus />
            </Space.Compact>
          </Form.Item>

          <Form.Item
            name="password"
            label={<span className="dark:text-gray-300">{t("password") || "密码"}</span>}
            rules={[
              { required: true, message: t("password_required") || "请输入密码" },
              { min: 6, message: t("password_min_length") || "密码至少6个字符" },
            ]}
            validateTrigger="onSubmit"
          >
            <Space.Compact block className="h-10">
              <Button icon={<IconLock size="1.25em" />} disabled className="h-10 flex items-center justify-center dark:bg-gray-700 dark:border-gray-600 dark:text-gray-300" />
              <Input.Password placeholder={t("enter_password") || "请输入密码（至少6位）"} className="h-10 dark:bg-gray-700 dark:border-gray-600 dark:text-white dark:placeholder-gray-400" />
            </Space.Compact>
          </Form.Item>

          <Form.Item className="mb-0 mt-8">
            <Button type="primary" htmlType="submit" block size="large" loading={loading} icon={<IconUserPlus size="1.25em" />} iconPlacement="end">
              {t("register_btn") || "立即注册"}
            </Button>
          </Form.Item>
        </Form>
      ),
    },
  ];

  return (
    <div className="relative min-h-screen w-full bg-background text-foreground">
      <div className="pointer-events-none fixed inset-0" style={bgStyle} />

      <div className="flex h-screen w-full items-center justify-center px-4">
        <Card className="w-full max-w-md rounded-lg shadow-lg bg-white dark:bg-gray-800 dark:border-gray-700">
          <div className="px-6 py-8">
            {/* Logo */}
            <div className="mb-8 flex flex-col items-center justify-center">
              <img src="/logo.svg" alt="QuantCell" className="mb-4 h-16 w-16" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
              <Title level={3} className="m-0 dark:text-white">QuantCell</Title>
              <Text type="secondary" className="dark:text-gray-400">{t("login_subtitle") || "量化交易平台"}</Text>
            </div>

            {/* 登录/注册 Tab 切换 */}
            <Tabs activeKey={activeTab} onChange={(key) => setActiveTab(key as 'login' | 'register')} centered items={tabItems} className="dark:[&_.ant-tabs-nav]:mb-4" />

            <div className="mt-4 text-center">
              <Text type="secondary" className="text-xs dark:text-gray-500">
                {activeTab === 'login'
                  ? (t("login_hint") || "已有账号？请输入用户名和密码登录")
                  : (t("register_hint") || "创建账号后即可使用完整功能")}
              </Text>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default LoginPage;
