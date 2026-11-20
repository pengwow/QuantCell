/**
 * 登录/注册页面
 * 支持用户注册和登录，不再支持访客模式
 */
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { IconArrowRight, IconLock, IconUser, IconUserPlus } from "@tabler/icons-react";
import { Button, Card, Form, Input, Space, Typography, Tabs, App } from "antd";
import { saveToken } from "../../utils/tokenManager";
import { setPageTitle } from "@/utils/pageTitle";
import "./LoginPage.css";

const { Title, Text } = Typography;

// 登录接口返回的用户数据（access_token 在调用 saveUserInfo 前已确认存在）
interface LoginResponseData {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
  role?: string;
  username?: string;
  user_id?: string | number;
  nickname?: string;
}

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
    // 首帧预置脚本（index.html）已按 localStorage/系统偏好设置过 html 的 dark class 与 data-theme：
    // 用户（或上次会话）已显式选择主题时，登录页不重复应用，避免与控制台 useBrowserTheme 的取值来源不一致
    const savedTheme = localStorage.getItem('quantcell-ui-theme');
    if (savedTheme === 'light' || savedTheme === 'dark') {
      return;
    }

    const response = await fetch("/api/v1/config");
    const result = await response.json();
    const groupedConfig = result?.data || result;

    const flattenConfig: Record<string, unknown> = {};
    if (groupedConfig && typeof groupedConfig === 'object') {
      Object.entries(groupedConfig).forEach(([, groupValues]) => {
        if (groupValues && typeof groupValues === 'object') {
          Object.entries(groupValues as Record<string, unknown>).forEach(([key, value]) => {
            flattenConfig[key] = value;
          });
        }
      });
    }

    // 后端未显式配置主题时缺省 'auto'（跟随系统，与 useBrowserTheme / SettingsContext 的取值语义一致），
    // 而不是强制亮色：避免暗色系统用户在登录页被强制切亮、登录后又切回暗色导致前后不一致
    applyTheme((flattenConfig['theme'] as 'light' | 'dark' | 'auto') || 'auto');
  } catch (error) {
    // 后端不可用时保留首帧预置（index.html 已按 用户选择 > 系统偏好 设置），
    // 不再强制回退亮色，保证登录页与登录后主题一致
    console.error('加载主题配置失败，保持当前主题:', error);
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

  const getRedirectPath = (): string => {
    const savedPath = sessionStorage.getItem('redirect_after_login');
    if (savedPath && savedPath !== '/login') {
      sessionStorage.removeItem('redirect_after_login');
      return savedPath;
    }
    return '/home';
  };

  const saveUserInfo = (data: LoginResponseData) => {
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
      const response = await fetch("/api/v1/auth/login", {
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
      const response = await fetch("/api/v1/auth/register", {
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
        <span className="login-tab-label">
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
        >
          <Form.Item
            name="username"
            label={<span>{t("username") || "用户名"}</span>}
            rules={[{ required: true, message: t('enter_username') }]}
            validateTrigger="onSubmit"
          >
            <Space.Compact block>
              <Button icon={<IconUser size="1.25em" />} disabled />
              <Input placeholder={t("enter_username") || "请输入用户名"} autoFocus />
            </Space.Compact>
          </Form.Item>

          <Form.Item
            name="password"
            label={<span>{t("password") || "密码"}</span>}
            rules={[{ required: true, message: t('enter_password') }]}
            validateTrigger="onSubmit"
          >
            <Space.Compact block>
              <Button icon={<IconLock size="1.25em" />} disabled />
              <Input.Password placeholder={t("enter_password") || "请输入密码"} />
            </Space.Compact>
          </Form.Item>

          <Form.Item className="login-submit-item">
            <Button type="primary" htmlType="submit" block loading={loading} icon={<IconArrowRight size="1.25em" />}>
              {t("login") || "登录"}
            </Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'register',
      label: (
        <span className="login-tab-label">
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
        >
          <Form.Item
            name="username"
            label={<span>{t("username") || "用户名"}</span>}
            rules={[
              { required: true, message: t('enter_username') },
              { min: 2, message: t("username_min_length") || "用户名至少2个字符" },
              { max: 50, message: t("username_max_length") || "用户名不超过50个字符" },
            ]}
            validateTrigger="onSubmit"
          >
            <Space.Compact block>
              <Button icon={<IconUser size="1.25em" />} disabled />
              <Input placeholder={t("enter_username") || "请输入用户名"} autoFocus />
            </Space.Compact>
          </Form.Item>

          <Form.Item
            name="password"
            label={<span>{t("password") || "密码"}</span>}
            rules={[
              { required: true, message: t('enter_password') },
              { min: 6, message: t("password_min_length") || "密码至少6个字符" },
            ]}
            validateTrigger="onSubmit"
          >
            <Space.Compact block>
              <Button icon={<IconLock size="1.25em" />} disabled />
              <Input.Password placeholder={t("enter_password") || "请输入密码（至少6位）"} />
            </Space.Compact>
          </Form.Item>

          <Form.Item className="login-submit-item">
            <Button type="primary" htmlType="submit" block loading={loading} icon={<IconUserPlus size="1.25em" />}>
              {t("register_btn") || "立即注册"}
            </Button>
          </Form.Item>
        </Form>
      ),
    },
  ];

  return (
    <div className="login-page">
      <div className="login-grid" />

      <div className="login-center">
        <Card className="login-card qc-card">
          {/* Logo + 品牌（页内文案维持 i18n 词条） */}
          <div className="login-brand">
            <img src="/logo.svg" alt="QuantCell" className="login-logo" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
            <Title level={3} style={{ margin: 0 }}>QuantCell</Title>
            <Text className="login-subtitle">{t("login_subtitle") || "量化交易平台"}</Text>
          </div>

          {/* 登录/注册 Tab 切换 */}
          <div className="login-form-wrap">
            <Tabs activeKey={activeTab} onChange={(key) => setActiveTab(key as 'login' | 'register')} centered items={tabItems} />

            <div className="login-hint">
              <Text className="login-subtitle">
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
