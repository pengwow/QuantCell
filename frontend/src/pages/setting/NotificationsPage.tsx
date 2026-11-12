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
import {
  getNotificationChannels,
  saveNotificationChannels,
  testNotificationChannel,
  type NotificationTestResult,
} from "../../services/notificationService";
import { useGuestRestriction } from "../../hooks/useGuestRestriction";
import { IconPlugConnected } from "@tabler/icons-react";

const { Text } = Typography;
const { Option } = Select;
const { TextArea } = Input;

// 通知渠道的详细配置结构（各渠道字段的并集，按渠道 id 分支出对应字段）
interface NotificationChannelConfig {
  smtpHost?: string;
  smtpPort?: number | string;
  security?: string;
  ignoreSSL?: boolean;
  username?: string;
  password?: string;
  senderEmail?: string;
  senderName?: string;
  recipientEmail?: string;
  webhookUrl?: string;
  useCustomFormat?: boolean;
  messageFormat?: string;
}

// 通知渠道类型
interface NotificationChannel {
  id: string;
  name: string;
  icon: string;
  enabled: boolean;
  isDefault: boolean;
  config: NotificationChannelConfig;
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
    name: "email",
    icon: CHANNEL_ICONS.email,
  },
  {
    id: "wecom",
    name: "wecom",
    icon: CHANNEL_ICONS.wecom,
  },
  {
    id: "feishu",
    name: "feishu",
    icon: CHANNEL_ICONS.feishu,
  },
];

// 默认配置
const DEFAULT_CONFIGS: Record<string, NotificationChannelConfig> = {
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
  const { isGuest } = useGuestRestriction();
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [selectedChannelId, setSelectedChannelId] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [testingChannel, setTestingChannel] = useState(false);
  const [testResult, setTestResult] = useState<NotificationTestResult | null>(null);

  // 从后端API加载配置
  useEffect(() => {
    loadChannels();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性初始化
  }, []);

  // 加载通知渠道配置（走通知渠道专用接口；后端对未保存渠道返回默认配置）
  // 注意：必须用这套接口保存/加载，真实发送时后端也只读这套存储（key=渠道ID 的整条 JSON）
  const loadChannels = async () => {
    try {
      setLoading(true);
      const res = await getNotificationChannels();
      const remote = (res?.channels ?? []) as Array<
        Partial<NotificationChannel> & { id?: string; displayName?: string }
      >;
      const loadedChannels = PRESET_CHANNELS.map((preset) => {
        const found = remote.find((c) => c.id === preset.id);
        return {
          id: preset.id,
          // displayName 为后端给的展示名；保存后 name 会回落为渠道ID
          name: t(found?.displayName || found?.name || preset.name),
          icon: preset.icon,
          enabled: Boolean(found?.enabled),
          isDefault: Boolean(found?.isDefault),
          // 与页面默认模板合并，防后端缺字段
          config: { ...DEFAULT_CONFIGS[preset.id], ...(found?.config ?? {}) },
        };
      });
      setChannels(loadedChannels);
      setSelectedChannelId(loadedChannels[0]?.id || "");
    } catch (error) {
      console.error("Failed to load notification channel config:", error);
      message.error(t("load_failed"));
      setSelectedChannelId(PRESET_CHANNELS[0]?.id || "");
    } finally {
      setLoading(false);
    }
  };

  // 获取当前选中的渠道
  const selectedChannel = channels.find((c) => c.id === selectedChannelId);

  // 更新渠道具体配置项
  const updateChannelConfig = (channelId: string, key: string, value: string | number | boolean) => {
    setChannels((prev) =>
      prev.map((c) =>
        c.id === channelId
          ? { ...c, config: { ...c.config, [key]: value } }
          : c
      )
    );
  };

  // 启用/停用渠道（enabled 是渠道级字段，不在 config 内；测试按钮与后端都要求渠道已启用）
  const toggleChannelEnabled = (channelId: string, enabled: boolean) => {
    setChannels((prev) => prev.map((c) => (c.id === channelId ? { ...c, enabled } : c)));
  };

  // 保存配置（走通知渠道专用接口，与真实发送读取的存储保持一致）
  const handleSave = async () => {
    setSaving(true);
    try {
      await saveNotificationChannels(
        channels.map((channel) => ({
          id: channel.id,
          enabled: channel.enabled,
          isDefault: channel.isDefault,
          config: channel.config,
        }))
      );
      message.success(t("settings_saved"));
    } catch (error) {
      console.error("Failed to save notification channel config:", error);
      message.error(t("save_failed"));
    } finally {
      setSaving(false);
    }
  };

  // 重置配置
  const handleReset = async () => {
    try {
      // 重新加载后端配置
      await loadChannels();
      message.success(t("config_reset"));
    } catch (error) {
      console.error("Failed to reset config:", error);
      message.error(t("reset_failed"));
    }
  };

  // 测试当前选中的通知渠道（页面级别）
  const handleTestChannel = async () => {
    if (!selectedChannel) return;

    // 检查渠道是否启用
    if (!selectedChannel.enabled) {
      message.warning(t("notification_channel_not_enabled"));
      return;
    }

    // 检查配置是否完整
    if (selectedChannel.id === "email" && (!selectedChannel.config.smtpHost || !selectedChannel.config.username || !selectedChannel.config.password)) {
      message.error(t("email_config_incomplete"));
      return;
    }
    if (selectedChannel.id === "wecom" && !selectedChannel.config.webhookUrl) {
      message.error(t("wechat_config_incomplete"));
      return;
    }
    if (selectedChannel.id === "feishu" && !selectedChannel.config.webhookUrl) {
      message.error(t("feishu_config_incomplete"));
      return;
    }

    setTestingChannel(true);
    setTestResult(null);

    try {
      // 拦截器对业务码非 0 的响应直接抛 ApiError，能走到这里说明后端确认发送成功
      await testNotificationChannel(selectedChannel.id, selectedChannel.config);
      setTestResult({ success: true, message: t("notification_test_success") });
      message.success(t("notification_test_success"));
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : t("test_send_failed");
      setTestResult({ success: false, message: errorMsg });
      message.error(errorMsg);
    } finally {
      setTestingChannel(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Text>{t("loading")}</Text>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 主内容区域 - 响应式布局 */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* 左侧渠道列表 */}
        <div className="w-full lg:w-64 flex-shrink-0">
          <div className="text-base font-medium mb-4 leading-8 h-8">
            {t("notification_channel")}
          </div>
          <Card className="shadow-sm" styles={{ body: { padding: 8 } }}>
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
              {/* 渠道标题和测试按钮 - 与左侧标题对齐 */}
              <div className="flex items-center justify-between h-8">
                <div className="flex items-center gap-2">
                  <span className="text-base font-medium">{selectedChannel.name}</span>
                  {/* 渠道启用开关：未启用时测试按钮置灰 */}
                  <Switch
                    size="small"
                    checked={selectedChannel.enabled}
                    checkedChildren={t("enabled")}
                    onChange={(checked) =>
                      toggleChannelEnabled(selectedChannel.id, checked)
                    }
                  />
                </div>
                <Space>
                  <Button
                    type="primary"
                    icon={<IconPlugConnected size={16} />}
                    onClick={handleTestChannel}
                    loading={testingChannel}
                    disabled={testingChannel || !selectedChannel.enabled}
                  >
                    {testingChannel ? t("testing") : t("notification_test_channel")}
                  </Button>
                </Space>
              </div>

              <Card className="shadow-sm">
                {/* 邮件配置 */}
                {selectedChannel.id === "email" && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Text strong className="block mb-2">
                          {t("smtp_server")}
                        </Text>
                        <Input
                          value={selectedChannel.config.smtpHost}
                          onChange={(e) =>
                            updateChannelConfig(selectedChannel.id, "smtpHost", e.target.value)
                          }
                          placeholder={t("notification_enter_smtp_host")}
                        />
                      </div>
                      <div>
                        <Text strong className="block mb-2">
                          {t("smtp_port")}
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
                          {t("connection_security")}
                        </Text>
                        <Select
                          value={selectedChannel.config.security}
                          onChange={(value) =>
                            updateChannelConfig(selectedChannel.id, "security", value)
                          }
                          className="w-full"
                        >
                          <Option value="ssl">{t("force_ssl")}</Option>
                          <Option value="starttls">STARTTLS</Option>
                          <Option value="none">{t("none")}</Option>
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
                          {t("ignore_ssl_error")}
                        </Text>
                      </div>
                    </div>

                    <div>
                      <Text strong className="block mb-2">
                        {t("username")}
                      </Text>
                      <Input
                        value={selectedChannel.config.username}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "username", e.target.value)
                        }
                        placeholder={t("enter_username")}
                      />
                    </div>

                    <div>
                      <Text strong className="block mb-2">
                        {t("password")}
                      </Text>
                      <Input.Password
                        value={selectedChannel.config.password}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "password", e.target.value)
                        }
                        placeholder={t("enter_password")}
                      />
                    </div>

                    <div>
                      <Text strong className="block mb-2">
                        {t("sender_email")}
                      </Text>
                      <Input
                        value={selectedChannel.config.senderEmail}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "senderEmail", e.target.value)
                        }
                        placeholder={t("notification_enter_sender_email")}
                      />
                    </div>

                    <div>
                      <Text strong className="block mb-2">
                        {t("sender_name")} ({t("optional")})
                      </Text>
                      <Input
                        value={selectedChannel.config.senderName}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "senderName", e.target.value)
                        }
                        placeholder={t("notification_enter_sender_name")}
                      />
                    </div>

                    <div>
                      <Text strong className="block mb-2">
                        {t("recipient_email")} ({t("optional")})
                      </Text>
                      <Input
                        value={selectedChannel.config.recipientEmail}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "recipientEmail", e.target.value)
                        }
                        placeholder={t("notification_enter_recipient_email")}
                      />
                    </div>

                  </div>
                )}

                {/* 企业微信配置 */}
                {selectedChannel.id === "wecom" && (
                  <div className="space-y-4">
                    <div>
                      <Text strong className="block mb-2">
                        {t("wecom_webhook_url")}
                      </Text>
                      <Input
                        value={selectedChannel.config.webhookUrl}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "webhookUrl", e.target.value)
                        }
                        placeholder={t("notification_enter_wecom_webhook")}
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
                        {t("use_custom_format")}
                      </Text>
                    </div>

                    {selectedChannel.config.useCustomFormat && (
                      <div>
                        <Text strong className="block mb-2">
                          {t("wechat_message_format")} ({t("optional")})
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

                  </div>
                )}

                {/* 飞书配置 */}
                {selectedChannel.id === "feishu" && (
                  <div className="space-y-4">
                    <div>
                      <Text strong className="block mb-2">
                        {t("feishu_webhook_url")}
                      </Text>
                      <Input
                        value={selectedChannel.config.webhookUrl}
                        onChange={(e) =>
                          updateChannelConfig(selectedChannel.id, "webhookUrl", e.target.value)
                        }
                        placeholder={t("notification_enter_feishu_webhook")}
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
                        {t("use_custom_format")}
                      </Text>
                    </div>

                    {selectedChannel.config.useCustomFormat && (
                      <div>
                        <Text strong className="block mb-2">
                          {t("feishu_message_format")} ({t("optional")})
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

                  </div>
                )}

                {/* 测试结果 */}
                {testResult && (
                  <div className={`mt-4 p-3 rounded-lg ${testResult.success ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'}`}>
                    <div className="flex items-center gap-2">
                      {testResult.success ? (
                        <span className="text-green-500">✓</span>
                      ) : (
                        <span className="text-red-500">✗</span>
                      )}
                      <span className={testResult.success ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}>
                        {testResult.message}
                      </span>
                    </div>
                  </div>
                )}

              </Card>
            </div>
          ) : (
            <Card className="shadow-sm">
              <div className="text-center py-12 text-gray-500">
                <IconMail size="48" className="mx-auto mb-4 opacity-50" />
                <p>{t("select_channel_first")}</p>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex justify-end gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Space>
          <Button onClick={handleReset} disabled={saving || loading || isGuest}>
            {t("reset")}
          </Button>
          <Button type="primary" onClick={handleSave} loading={saving} disabled={isGuest}>
            {t("save")}
          </Button>
        </Space>
      </div>
    </div>
  );
};

export default NotificationsPage;
