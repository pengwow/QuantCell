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
import { testNotificationChannel } from "../../services/notificationService";
import { configApi } from "../../api";
import { useGuestRestriction } from "../../hooks/useGuestRestriction";
import { IconPlugConnected } from "@tabler/icons-react";

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
  const { isGuest } = useGuestRestriction();
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [selectedChannelId, setSelectedChannelId] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [testingChannel, setTestingChannel] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);

  // 从后端API加载配置
  useEffect(() => {
    loadChannels();
  }, []);

  // 加载通知渠道配置（从扁平化配置加载）
  const loadChannels = async () => {
    try {
      setLoading(true);
      // 使用 configApi 获取所有配置（返回格式为按 name 分组）
      const groupedConfigs = await configApi.getConfig() as Record<string, Record<string, string>>;

      // 获取 notification 分组的配置
      const notificationGroup = groupedConfigs.notification || {};

      // 将扁平化配置按渠道ID分组
      const channelConfigs: Record<string, Record<string, string>> = {};
      Object.entries(notificationGroup).forEach(([key, value]) => {
        if (key.startsWith('notification.')) {
          const parts = key.split('.');
          if (parts.length >= 3) {
            const channelId = parts[1];
            const field = parts[2];
            if (!channelConfigs[channelId]) {
              channelConfigs[channelId] = {};
            }
            channelConfigs[channelId][field] = value;
          }
        }
      });

      // 检查是否有保存的配置
      const hasSavedConfig = Object.keys(channelConfigs).length > 0;

      if (hasSavedConfig) {
        // 将后端数据转换为前端格式
        const loadedChannels = PRESET_CHANNELS.map((preset) => {
          const existing = channelConfigs[preset.id];
          if (existing && Object.keys(existing).length > 0) {
            // 解析 config JSON
            let config = DEFAULT_CONFIGS[preset.id];
            try {
              if (existing.config) {
                config = JSON.parse(existing.config);
              }
            } catch (e) {
              console.warn(`解析 ${preset.id} 配置失败`, e);
            }

            return {
              id: preset.id,
              name: t(existing.name) || preset.name,
              icon: preset.icon,
              enabled: existing.enabled === '1',
              isDefault: existing.isDefault === '1',
              config: config,
            };
          }
          // 返回默认配置
          return {
            id: preset.id,
            name: t(preset.name) || preset.name,
            icon: preset.icon,
            enabled: false,
            isDefault: false,
            config: DEFAULT_CONFIGS[preset.id],
          };
        });
        setChannels(loadedChannels);
        setSelectedChannelId(loadedChannels[0]?.id || "");
      } else {
        // 使用默认配置
        initDefaultChannels();
      }
    } catch (error) {
      console.error("加载通知渠道配置失败:", error);
      message.error(t("load_failed") || "加载配置失败");
      initDefaultChannels();
    } finally {
      setLoading(false);
    }
  };

  // 初始化默认配置
  const initDefaultChannels = () => {
    const initialChannels = PRESET_CHANNELS.map((preset, index) => ({
      ...preset,
      enabled: index === 0,
      isDefault: index === 0,
      config: DEFAULT_CONFIGS[preset.id],
    }));
    setChannels(initialChannels);
    setSelectedChannelId(initialChannels[0]?.id || "");
  };

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

  // 保存配置（使用批量更新接口，对象数组格式）
  const handleSave = async () => {
    setSaving(true);
    try {
      // 构建批量更新的配置数组，格式与 general 页面一致
      const batchConfigs: Array<{
        key: string;
        value: string;
        name: string;
        description: string;
      }> = [];

      channels.forEach((channel) => {
        const prefix = `notification.${channel.id}`;
        const channelName = channel.name;

        batchConfigs.push(
          { key: `${prefix}.name`, value: channel.name, name: 'notification', description: `${channelName}通知渠道名称` },
          { key: `${prefix}.enabled`, value: channel.enabled ? '1' : '0', name: 'notification', description: `${channelName}是否启用` },
          { key: `${prefix}.isDefault`, value: channel.isDefault ? '1' : '0', name: 'notification', description: `${channelName}是否为默认` },
          { key: `${prefix}.config`, value: JSON.stringify(channel.config), name: 'notification', description: `${channelName}配置详情` }
        );
      });

      // 使用批量更新接口保存所有配置（对象数组格式）
      await configApi.updateConfig(batchConfigs);

      message.success(t("settings_saved") || "设置已保存");
    } catch (error) {
      console.error("保存通知渠道配置失败:", error);
      message.error(t("save_failed") || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  // 重置配置
  const handleReset = async () => {
    try {
      // 重新加载后端配置
      await loadChannels();
      message.success(t("config_reset") || "配置已重置");
    } catch (error) {
      console.error("重置配置失败:", error);
      message.error(t("reset_failed") || "重置失败");
    }
  };

  // 测试发送通知（渠道级别）
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

    // 发送测试消息
    message.loading(t("sending_test_message") || "正在发送测试消息...", 1);
    try {
      const response = await testNotificationChannel(channelId, channel.config);
      if (response.code === 0) {
        message.success(t("test_message_sent") || "测试消息已发送");
      } else {
        message.error(response.message || t("test_failed") || "测试发送失败");
      }
    } catch (error) {
      console.error("测试发送失败:", error);
      message.error(t("test_failed") || "测试发送失败");
    }
  };

  // 测试当前选中的通知渠道（页面级别）
  const handleTestChannel = async () => {
    if (!selectedChannel) return;

    // 检查渠道是否启用
    if (!selectedChannel.enabled) {
      message.warning(t("channel_not_enabled") || "该通知渠道未启用，请先启用后再测试");
      return;
    }

    // 检查配置是否完整
    if (selectedChannel.id === "email" && (!selectedChannel.config.smtpHost || !selectedChannel.config.username || !selectedChannel.config.password)) {
      message.error(t("email_config_incomplete") || "邮件配置不完整，请填写 SMTP 服务器地址、用户名和密码");
      return;
    }
    if (selectedChannel.id === "wecom" && !selectedChannel.config.webhookUrl) {
      message.error(t("wecom_config_incomplete") || "企业微信配置不完整，请填写 Webhook 地址");
      return;
    }
    if (selectedChannel.id === "feishu" && !selectedChannel.config.webhookUrl) {
      message.error(t("feishu_config_incomplete") || "飞书配置不完整，请填写 Webhook 地址");
      return;
    }

    setTestingChannel(true);
    setTestResult(null);

    try {
      const response = await testNotificationChannel(selectedChannel.id, selectedChannel.config);
      setTestResult(response);

      if (response.code === 0) {
        message.success(response.message || t("test_success") || "测试成功");
      } else {
        message.error(response.message || t("test_failed") || "测试失败");
      }
    } catch (error: any) {
      const errorMsg = error.message || t("test_failed") || "测试失败";
      setTestResult({ code: -1, message: errorMsg });
      message.error(errorMsg);
    } finally {
      setTestingChannel(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Text>{t("loading") || "加载中..."}</Text>
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
            {t("notification_channel") || "通知渠道"}
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
                <div className="text-base font-medium">{selectedChannel.name}</div>
                <Space>
                  <Button
                    type="primary"
                    icon={<IconPlugConnected size={16} />}
                    onClick={handleTestChannel}
                    loading={testingChannel}
                    disabled={testingChannel || !selectedChannel.enabled}
                  >
                    {testingChannel ? t("testing") || "测试中..." : t("test_channel") || "测试渠道"}
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

                {/* 测试结果 */}
                {testResult && (
                  <div className={`mt-4 p-3 rounded-lg ${testResult.code === 0 ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'}`}>
                    <div className="flex items-center gap-2">
                      {testResult.code === 0 ? (
                        <span className="text-green-500">✓</span>
                      ) : (
                        <span className="text-red-500">✗</span>
                      )}
                      <span className={testResult.code === 0 ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}>
                        {testResult.message}
                      </span>
                    </div>
                    {testResult.data?.result && (
                      <div className="text-xs text-gray-500 mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                        <div className="flex justify-between">
                          <span>{t("channel") || "渠道"}:</span>
                          <span>{selectedChannel?.name}</span>
                        </div>
                        {testResult.data.result.error && (
                          <div className="flex justify-between mt-1">
                            <span>{t("error_details") || "错误详情"}:</span>
                            <span className="text-red-600">{testResult.data.result.error}</span>
                          </div>
                        )}
                      </div>
                    )}
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
          <Button onClick={handleReset} disabled={saving || loading || isGuest}>
            {t("reset") || "重置"}
          </Button>
          <Button type="primary" onClick={handleSave} loading={saving} disabled={isGuest}>
            {t("save") || "保存"}
          </Button>
        </Space>
      </div>
    </div>
  );
};

export default NotificationsPage;
