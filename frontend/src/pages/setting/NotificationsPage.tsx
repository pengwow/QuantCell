/**
 * 通知设置页面
 * 功能：管理不同类型的通知配置，包括邮件、企业微信、飞书等
 */
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  Card,
  Input,
  Button,
  Switch,
  Space,
  Typography,
  Select,
  message,
} from "antd";
import {
  IconMail,
} from "@tabler/icons-react";

const { Text } = Typography;
const { Option } = Select;
const { TextArea } = Input;

// 通知渠道类型
interface NotificationChannel {
  id: string;
  name: string;
  icon: string;
  enabled: boolean;
  isDefault: boolean;
  config: Record<string, any>;
}

// 通知渠道图片路径映射
const CHANNEL_ICONS: Record<string, string> = {
  email: "/imgs/notification_channel/youjian.png",
  wecom: "/imgs/notification_channel/qiyeweixin.png",
  feishu: "/imgs/notification_channel/feishu.png",
};

// 预设通知渠道
const PRESET_CHANNELS = [
  {
    id: "email",
    name: "邮件通知",
    icon: CHANNEL_ICONS.email,
  },
  {
    id: "wecom",
    name: "企业微信",
    icon: CHANNEL_ICONS.wecom,
  },
  {
    id: "feishu",
    name: "飞书",
    icon: CHANNEL_ICONS.feishu,
  },
];

// 默认配置
const DEFAULT_CONFIGS: Record<string, any> = {
  email: {
    smtpHost: "",
    smtpPort: 465,
    security: "ssl",
    ignoreSSL: false,
    username: "",
    password: "",
    senderEmail: "",
    senderName: "",
    recipientEmail: "",
  },
  wecom: {
    webhookUrl: "",
    useCustomFormat: false,
    messageFormat: JSON.stringify(
      {
        msgtype: "text",
        text: {
          content: "${NOTIFIER_SUBJECT}\n\n${NOTIFIER_MESSAGE}",
        },
      },
      null,
      2
    ),
  },
  feishu: {
    webhookUrl: "",
    useCustomFormat: false,
    messageFormat: JSON.stringify(
      {
        msg_type: "text",
        content: {
          text: "${NOTIFIER_SUBJECT}\n\n${NOTIFIER_MESSAGE}",
        },
      },
      null,
      2
    ),
  },
};

const NotificationsPage = () => {
  const { t } = useTranslation();
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [selectedChannelId, setSelectedChannelId] = useState<string>("");
  const [saving, setSaving] = useState(false);

  // 从localStorage加载配置
  useEffect(() => {
    const savedChannels = localStorage.getItem("notification_channels");
    if (savedChannels) {
      const parsed = JSON.parse(savedChannels);
      // 合并新渠道
      const mergedChannels = PRESET_CHANNELS.map((preset) => {
        const existing = parsed.find((c: NotificationChannel) => c.id === preset.id);
        if (existing) {
          return { ...existing, name: preset.name, icon: preset.icon };
        }
        return {
          ...preset,
          enabled: false,
          isDefault: false,
          config: DEFAULT_CONFIGS[preset.id],
        };
      });
      setChannels(mergedChannels);
      setSelectedChannelId(mergedChannels[0]?.id || "");
    } else {
      // 初始化默认配置
      const initialChannels = PRESET_CHANNELS.map((preset, index) => ({
        ...preset,
        enabled: index === 0,
        isDefault: index === 0,
        config: DEFAULT_CONFIGS[preset.id],
      }));
      setChannels(initialChannels);
      setSelectedChannelId(initialChannels[0]?.id || "");
    }
  }, []);

  // 保存到localStorage
  useEffect(() => {
    if (channels.length > 0) {
      localStorage.setItem("notification_channels", JSON.stringify(channels));
    }
  }, [channels]);

  // 获取当前选中的渠道
  const selectedChannel = channels.find((c) => c.id === selectedChannelId);

  // 更新渠道具体配置项
  const updateChannelConfig = (channelId: string, key: string, value: any) => {
    setChannels((prev) =>
      prev.map((c) =>
        c.id === channelId
          ? { ...c, config: { ...c.config, [key]: value } }
          : c
      )
    );
  };



  // 保存配置
  const handleSave = async () => {
    setSaving(true);
    // 模拟保存
    setTimeout(() => {
      message.success(t("settings_saved") || "设置已保存");
      setSaving(false);
    }, 500);
  };

  // 重置配置
  const handleReset = () => {
    const initialChannels = PRESET_CHANNELS.map((preset, index) => ({
      ...preset,
      enabled: index === 0,
      isDefault: index === 0,
      config: DEFAULT_CONFIGS[preset.id],
    }));
    setChannels(initialChannels);
    setSelectedChannelId(initialChannels[0]?.id || "");
    message.success(t("config_reset") || "配置已重置");
  };

  // 测试发送通知
  const handleTestSend = async (channelId: string) => {
    const channel = channels.find((c) => c.id === channelId);
    if (!channel) return;

    // 检查配置是否完整
    if (channel.id === "email" && (!channel.config.smtpHost || !channel.config.username || !channel.config.password)) {
      message.error(t("email_config_incomplete") || "邮件配置不完整，请填写 SMTP 服务器地址、用户名和密码");
      return;
    }
    if (channel.id === "wecom" && !channel.config.webhookUrl) {
      message.error(t("wecom_config_incomplete") || "企业微信配置不完整，请填写 Webhook 地址");
      return;
    }
    if (channel.id === "feishu" && !channel.config.webhookUrl) {
      message.error(t("feishu_config_incomplete") || "飞书配置不完整，请填写 Webhook 地址");
      return;
    }

    // 模拟发送测试消息
    message.loading(t("sending_test_message") || "正在发送测试消息...", 1);
    setTimeout(() => {
      message.success(t("test_message_sent") || "测试消息已发送");
    }, 1000);
  };

  return (
    <div className="space-y-6">
      {/* 主内容区域 - 响应式布局 */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* 左侧渠道列表 */}
        <div className="w-full lg:w-64 flex-shrink-0">
          <div className="text-base font-medium mb-4 leading-8 h-8">
            {t("notification_channel") || "通知渠道"}
          </div>
          <Card className="shadow-sm" bodyStyle={{ padding: 8 }}>
            {/* 小屏幕：水平排列自动换行；大屏幕：垂直列表 */}
            <div className="flex flex-wrap gap-2 lg:flex-col lg:gap-1">
              {channels.map((channel) => (
                <div
                  key={channel.id}
                  className={`cursor-pointer rounded-lg transition-all duration-200 px-3 py-2 flex items-center gap-2 lg:gap-3 lg:w-full ${
                    selectedChannelId === channel.id
                      ? "bg-gray-100 dark:bg-gray-800"
                      : "hover:bg-gray-50 dark:hover:bg-gray-900"
                  }`}
                  onClick={() => setSelectedChannelId(channel.id)}
                >
                  <span className="w-8 h-8 flex items-center justify-center shrink-0 overflow-hidden">
                    <img src={channel.icon} alt={channel.name} className="w-6 h-6 object-contain" />
                  </span>
                  <div className="flex-1 min-w-0 hidden lg:block">
                    <div className="font-medium text-sm truncate">{channel.name}</div>
                    <div className="text-xs text-gray-400 truncate">{channel.id}</div>
                  </div>
                  <span className="lg:hidden font-medium text-sm">{channel.name}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* 右侧配置区域 */}
        <div className="flex-1">
          {selectedChannel ? (
            <div className="space-y-4">
              {/* 渠道标题 - 与左侧标题对齐 */}
              <div className="flex items-center justify-between h-8">
                <div className="text-base font-medium">{selectedChannel.name}</div>
              </div>

              <Card className="shadow-sm">
                {/* 邮件配置 */}
                {selectedChannel.id === "email" && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Text strong className="block mb-2">
                          SMTP {t("server_address") || "服务器地址"}
                        </Text>
                        <Input
                          value={selectedChannel.config.smtpHost}
                          onChange={(e) =>
                            updateChannelConfig(selectedChannel.id, "smtpHost", e.target.value)
                          }
                          placeholder={t("enter_smtp_host") || "请输入 SMTP 服务器地址"}
                        />
                      </div>
                      <div>
                        <Text strong className="block mb-2">
                          SMTP {t("server_port") || "服务器端口"}
                        </Text>
                        <Input
                          value={selectedChannel.config.smtpPort}
                          onChange={(e) =>
                            updateChannelConfig(selectedChannel.id, "smtpPort", e.target.value)
                          }
                          placeholder="465"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Text strong className="block mb-2">
                          {t("connection_security") || "连接安全性"}
                        </Text>
                        <Select
                          value={selectedChannel.config.security}
                          onChange={(value) =>
                            updateChannelConfig(selectedChannel.id, "security", value)
                          }
                          className="w-full"
                        >
                          <Option value="ssl">{t("force_ssl") || "强制 SSL/TLS 连接"}</Option>
                          <Option value="starttls">STARTTLS</Option>
                          <Option value="none">{t("none") || "无"}</Option>
                        </Select>
                      </div>
                      <div className="flex items-center pt-6">
                        <Switch
                          checked={selectedChannel.config.ignoreSSL}
                          onChange={(checked) =>
                            updateChannelConfig(selectedChannel.id, "ignoreSSL", checked)
                          }
                        />
                        <Text className="ml-2">
                          {t("ignore_ssl_error") || "忽略 SSL/TLS 证书错误"}
                        </Text>
                      </div>
                    </div>

                    <div>
                      <Text strong className="block mb-2">
                        {t("username") || "用户名"}
                      </Text>
                      <Input
                        value={selectedChannel.config.username}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "username", e.target.value)
                        }
                        placeholder={t("enter_username") || "请输入用户名"}
                      />
                    </div>

                    <div>
                      <Text strong className="block mb-2">
                        {t("password") || "密码"}
                      </Text>
                      <Input.Password
                        value={selectedChannel.config.password}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "password", e.target.value)
                        }
                        placeholder={t("enter_password") || "请输入密码"}
                      />
                    </div>

                    <div>
                      <Text strong className="block mb-2">
                        {t("sender_email") || "发件人邮箱"}
                      </Text>
                      <Input
                        value={selectedChannel.config.senderEmail}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "senderEmail", e.target.value)
                        }
                        placeholder={t("enter_sender_email") || "请输入发件人邮箱"}
                      />
                    </div>

                    <div>
                      <Text strong className="block mb-2">
                        {t("sender_name") || "发件人名称"} ({t("optional") || "可选"})
                      </Text>
                      <Input
                        value={selectedChannel.config.senderName}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "senderName", e.target.value)
                        }
                        placeholder={t("enter_sender_name") || "请输入发件人名称"}
                      />
                    </div>

                    <div>
                      <Text strong className="block mb-2">
                        {t("recipient_email") || "收件人邮箱"} ({t("optional") || "可选"})
                      </Text>
                      <Input
                        value={selectedChannel.config.recipientEmail}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "recipientEmail", e.target.value)
                        }
                        placeholder={t("enter_recipient_email") || "请输入默认的收件人邮箱"}
                      />
                    </div>

                    {/* 测试发送按钮 */}
                    <div className="flex justify-end pt-4">
                      <Button onClick={() => handleTestSend(selectedChannel.id)}>
                        {t("test_send") || "测试发送"}
                      </Button>
                    </div>
                  </div>
                )}

                {/* 企业微信配置 */}
                {selectedChannel.id === "wecom" && (
                  <div className="space-y-4">
                    <div>
                      <Text strong className="block mb-2">
                        {t("wecom_webhook_url") || "企业微信群机器人 Webhook 地址"}
                      </Text>
                      <Input
                        value={selectedChannel.config.webhookUrl}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "webhookUrl", e.target.value)
                        }
                        placeholder={t("enter_wecom_webhook") || "请输入企业微信群机器人 Webhook 地址"}
                      />
                    </div>

                    <div className="flex items-center">
                      <Switch
                        checked={selectedChannel.config.useCustomFormat}
                        onChange={(checked) =>
                          updateChannelConfig(selectedChannel.id, "useCustomFormat", checked)
                        }
                      />
                      <Text className="ml-2">
                        {t("use_custom_format") || "使用自定义的消息数据格式"}
                      </Text>
                    </div>

                    {selectedChannel.config.useCustomFormat && (
                      <div>
                        <Text strong className="block mb-2">
                          {t("message_format") || "企业微信群机器人消息格式"} ({t("optional") || "可选"})
                        </Text>
                        <TextArea
                          value={selectedChannel.config.messageFormat}
                          onChange={(e) =>
                            updateChannelConfig(selectedChannel.id, "messageFormat", e.target.value)
                          }
                          rows={6}
                          className="font-mono text-sm"
                        />
                      </div>
                    )}

                    {/* 测试发送按钮 */}
                    <div className="flex justify-end pt-4">
                      <Button onClick={() => handleTestSend(selectedChannel.id)}>
                        {t("test_send") || "测试发送"}
                      </Button>
                    </div>
                  </div>
                )}

                {/* 飞书配置 */}
                {selectedChannel.id === "feishu" && (
                  <div className="space-y-4">
                    <div>
                      <Text strong className="block mb-2">
                        {t("feishu_webhook_url") || "飞书群机器人 Webhook 地址"}
                      </Text>
                      <Input
                        value={selectedChannel.config.webhookUrl}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "webhookUrl", e.target.value)
                        }
                        placeholder={t("enter_feishu_webhook") || "请输入飞书群机器人 Webhook 地址"}
                      />
                    </div>

                    <div className="flex items-center">
                      <Switch
                        checked={selectedChannel.config.useCustomFormat}
                        onChange={(checked) =>
                          updateChannelConfig(selectedChannel.id, "useCustomFormat", checked)
                        }
                      />
                      <Text className="ml-2">
                        {t("use_custom_format") || "使用自定义的消息数据格式"}
                      </Text>
                    </div>

                    {selectedChannel.config.useCustomFormat && (
                      <div>
                        <Text strong className="block mb-2">
                          {t("message_format") || "飞书群机器人消息格式"} ({t("optional") || "可选"})
                        </Text>
                        <TextArea
                          value={selectedChannel.config.messageFormat}
                          onChange={(e) =>
                            updateChannelConfig(selectedChannel.id, "messageFormat", e.target.value)
                          }
                          rows={6}
                          className="font-mono text-sm"
                        />
                      </div>
                    )}

                    {/* 测试发送按钮 */}
                    <div className="flex justify-end pt-4">
                      <Button onClick={() => handleTestSend(selectedChannel.id)}>
                        {t("test_send") || "测试发送"}
                      </Button>
                    </div>
                  </div>
                )}

              </Card>
            </div>
          ) : (
            <Card className="shadow-sm">
              <div className="text-center py-12 text-gray-500">
                <IconMail size="48" className="mx-auto mb-4 opacity-50" />
                <p>{t("select_channel") || "请选择一个通知渠道"}</p>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex justify-end gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Space>
          <Button onClick={handleReset} disabled={saving}>
            {t("reset") || "重置"}
          </Button>
          <Button type="primary" onClick={handleSave} loading={saving}>
            {t("save") || "保存"}
          </Button>
        </Space>
      </div>
    </div>
  );
};

export default NotificationsPage;
