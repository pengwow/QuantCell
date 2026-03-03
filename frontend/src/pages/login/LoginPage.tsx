/**
 * 登录页面
 * 参考 certimate 项目登录页面设计
 * 默认填充 admin/123456 用于演示生成 JWT token
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { IconArrowRight, IconLock, IconUser } from "@tabler/icons-react";
import { Button, Card, Form, Input, Space, Typography, message } from "antd";
import { saveToken } from "../../utils/tokenManager";

const { Title, Text } = Typography;

// 默认登录凭据
const DEFAULT_CREDENTIALS = {
  username: "admin",
  password: "123456",
};

const LoginPage = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  // 背景样式 - 参考 certimate 的网格背景
  const bgStyle = useMemo<React.CSSProperties>(() => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32" fill="none" stroke="rgb(100 100 100 / 0.08)"><path d="M0 .5H31.5V32"/></svg>`;

    return {
      backgroundImage: `url('data:image/svg+xml;base64,${btoa(svg)}')`,
      maskImage: `linear-gradient(to bottom right, transparent, black, transparent)`,
    };
  }, []);

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
        message.success(t("login_success") || "登录成功");
        navigate("/");
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

  return (
    <div className="relative min-h-screen w-full">
      {/* 背景 */}
      <div
        className="pointer-events-none fixed inset-0"
        style={bgStyle}
      />

      {/* 登录卡片 */}
      <div className="flex h-screen w-full items-center justify-center px-4">
        <Card className="w-full max-w-md rounded-lg shadow-lg">
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
              <Title level={3} className="m-0">
                QuantCell
              </Title>
              <Text type="secondary">
                {t("login_subtitle") || "量化交易平台"}
              </Text>
            </div>

            {/* 登录表单 */}
            <Form
              form={form}
              layout="vertical"
              initialValues={DEFAULT_CREDENTIALS}
              onFinish={handleLogin}
              autoComplete="off"
            >
              <Form.Item
                name="username"
                label={t("username") || "用户名"}
                rules={[
                  {
                    required: true,
                    message: t("username_required") || "请输入用户名",
                  },
                ]}
              >
                <Space.Compact block className="h-10">
                  <Button 
                    icon={<IconUser size="1.25em" />} 
                    disabled 
                    className="h-10 flex items-center justify-center"
                  />
                  <Input
                    placeholder={t("enter_username") || "请输入用户名"}
                    className="h-10"
                    autoFocus
                  />
                </Space.Compact>
              </Form.Item>

              <Form.Item
                name="password"
                label={t("password") || "密码"}
                rules={[
                  {
                    required: true,
                    message: t("password_required") || "请输入密码",
                  },
                ]}
              >
                <Space.Compact block className="h-10">
                  <Button 
                    icon={<IconLock size="1.25em" />} 
                    disabled 
                    className="h-10 flex items-center justify-center"
                  />
                  <Input.Password
                    placeholder={t("enter_password") || "请输入密码"}
                    className="h-10"
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
              <Text type="secondary" className="text-sm">
                {t("demo_hint") || "演示模式：默认已填写用户名和密码"}
              </Text>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default LoginPage;
