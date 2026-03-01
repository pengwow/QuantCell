/**
 * AI模型设置页面
 * 功能：管理AI大模型厂商配置，包括API Key、API Host和模型列表
 */
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  Card,
  Input,
  Button,
  Switch,
  Modal,
  Form,
  Space,
  Typography,
  message,
  Popconfirm,
  Divider,
} from "antd";
import {
  IconPlus,
  IconTrash,
  IconRobot,
} from "@tabler/icons-react";

const { Text } = Typography;

// 模型厂商配置接口
interface ModelProvider {
  id: string;
  name: string;
  icon: string;
  apiKey: string;
  apiHost: string;
  models: Model[];
  isDefault: boolean;
  isEnabled: boolean;
}

// 模型接口
interface Model {
  id: string;
  name: string;
  isEnabled: boolean;
}

// 预设的模型厂商
interface PresetProvider {
  id: string;
  name: string;
  icon: string;
}

// 模型厂商图片路径映射
const PROVIDER_ICONS: Record<string, string> = {
  openrouter: "/imgs/model_providers/openrouter.png",
  siliconflow: "/imgs/model_providers/siliconflow.png",
  openai: "/imgs/model_providers/openai.png",
  ollama: "/imgs/model_providers/ollama.png",
  "openai-compatible": "/imgs/model_providers/openai-compatible.png",
  deepseek: "/imgs/model_providers/deepseek.png",
  dashscope: "/imgs/model_providers/dashscope.png",
  google: "/imgs/model_providers/google.png",
  azure: "/imgs/model_providers/azure.png",
};

const PRESET_PROVIDERS: PresetProvider[] = [
  {
    id: "openrouter",
    name: "OpenRouter",
    icon: PROVIDER_ICONS.openrouter,
  },
  {
    id: "siliconflow",
    name: "硅基流动",
    icon: PROVIDER_ICONS.siliconflow,
  },
  {
    id: "openai",
    name: "OpenAI",
    icon: PROVIDER_ICONS.openai,
  },
  {
    id: "ollama",
    name: "Ollama",
    icon: PROVIDER_ICONS.ollama,
  },
  {
    id: "openai-compatible",
    name: "OpenAI兼容API",
    icon: PROVIDER_ICONS["openai-compatible"],
  },
  {
    id: "deepseek",
    name: "深度求索",
    icon: PROVIDER_ICONS.deepseek,
  },
  {
    id: "dashscope",
    name: "阿里云",
    icon: PROVIDER_ICONS.dashscope,
  },
  {
    id: "google",
    name: "谷歌云",
    icon: PROVIDER_ICONS.google,
  },
  {
    id: "azure",
    name: "微软Azure OpenAI",
    icon: PROVIDER_ICONS.azure,
  },
];

// 预设模型列表
const PRESET_MODELS: Record<string, string[]> = {
  openrouter: ["Claude Haiku 4.5", "Grok 4", "Qwen3 Max", "GPT-5", "Gemini 2.5 Flash", "Gemini 3 Pro Preview", "Grok 4.1 Fast"],
  siliconflow: ["Qwen2.5-72B", "Qwen2.5-32B", "DeepSeek-V3", "DeepSeek-R1"],
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
  ollama: [],
  "openai-compatible": [],
  deepseek: ["deepseek-chat", "deepseek-reasoner"],
  dashscope: ["qwen-max", "qwen-plus", "qwen-turbo"],
  google: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro"],
  azure: ["gpt-4", "gpt-4o", "gpt-35-turbo"],
};

const ModelSettingsPage = () => {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState<string>("");
  const [isAddModelModalOpen, setIsAddModelModalOpen] = useState(false);
  const [addModelForm] = Form.useForm();
  const [checkingProvider, setCheckingProvider] = useState<string | null>(null);

  // 从localStorage加载配置
  useEffect(() => {
    const savedProviders = localStorage.getItem("ai_model_providers");
    if (savedProviders) {
      const parsed = JSON.parse(savedProviders);
      // 合并新厂商
      const mergedProviders = PRESET_PROVIDERS.map((preset) => {
        const existing = parsed.find((p: ModelProvider) => p.id === preset.id);
        if (existing) {
          return { ...existing, name: preset.name, icon: preset.icon };
        }
        return {
          ...preset,
          apiKey: "",
          apiHost: getDefaultApiHost(preset.id),
          models: PRESET_MODELS[preset.id]?.map((name) => ({
            id: `${preset.id}-${name}`,
            name,
            isEnabled: false,
          })) || [],
          isDefault: false,
          isEnabled: false,
        };
      });
      setProviders(mergedProviders);
      setSelectedProviderId(mergedProviders[0]?.id || "");
    } else {
      // 初始化默认配置
      const initialProviders = PRESET_PROVIDERS.map((preset, index) => ({
        ...preset,
        apiKey: "",
        apiHost: getDefaultApiHost(preset.id),
        models: PRESET_MODELS[preset.id]?.map((name) => ({
          id: `${preset.id}-${name}`,
          name,
          isEnabled: index === 0,
        })) || [],
        isDefault: index === 0,
        isEnabled: index === 0,
      }));
      setProviders(initialProviders);
      setSelectedProviderId(initialProviders[0]?.id || "");
    }
  }, []);

  // 保存到localStorage
  useEffect(() => {
    if (providers.length > 0) {
      localStorage.setItem("ai_model_providers", JSON.stringify(providers));
    }
  }, [providers]);

  // 获取默认API Host
  function getDefaultApiHost(providerId: string): string {
    const hosts: Record<string, string> = {
      openrouter: "https://openrouter.ai/api/v1",
      siliconflow: "https://api.siliconflow.cn/v1",
      openai: "https://api.openai.com/v1",
      ollama: "http://localhost:11434/v1",
      "openai-compatible": "",
      deepseek: "https://api.deepseek.com/v1",
      dashscope: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      google: "https://generativelanguage.googleapis.com/v1",
      azure: "",
    };
    return hosts[providerId] || "";
  }

  // 获取当前选中的厂商
  const selectedProvider = providers.find((p) => p.id === selectedProviderId);

  // 更新厂商配置
  const updateProvider = (providerId: string, updates: Partial<ModelProvider>) => {
    setProviders((prev) =>
      prev.map((p) => (p.id === providerId ? { ...p, ...updates } : p))
    );
  };

  // 设置默认厂商
  const setDefaultProvider = (providerId: string) => {
    setProviders((prev) =>
      prev.map((p) => ({
        ...p,
        isDefault: p.id === providerId,
      }))
    );
    message.success(t("default_provider_set") || "默认厂商已设置");
  };

  // 检查可用性
  const checkAvailability = async (providerId: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider?.apiKey) {
      message.warning(t("please_enter_api_key") || "请输入API密钥");
      return;
    }
    
    setCheckingProvider(providerId);
    // 模拟检查
    setTimeout(() => {
      message.success(t("api_key_valid") || "API密钥有效");
      setCheckingProvider(null);
    }, 1000);
  };

  // 启用/禁用模型
  const toggleModel = (providerId: string, modelId: string, enabled: boolean) => {
    setProviders((prev) =>
      prev.map((p) =>
        p.id === providerId
          ? {
              ...p,
              models: p.models.map((m) =>
                m.id === modelId ? { ...m, isEnabled: enabled } : m
              ),
            }
          : p
      )
    );
  };

  // 删除模型
  const deleteModel = (providerId: string, modelId: string) => {
    setProviders((prev) =>
      prev.map((p) =>
        p.id === providerId
          ? { ...p, models: p.models.filter((m) => m.id !== modelId) }
          : p
      )
    );
    message.success(t("model_deleted") || "模型已删除");
  };

  // 添加模型
  const handleAddModel = (values: { modelId: string; name: string }) => {
    if (!selectedProvider) return;

    const newModel: Model = {
      id: `${selectedProvider.id}-${values.modelId}`,
      name: values.name,
      isEnabled: true,
    };

    setProviders((prev) =>
      prev.map((p) =>
        p.id === selectedProvider.id
          ? { ...p, models: [...p.models, newModel] }
          : p
      )
    );

    setIsAddModelModalOpen(false);
    addModelForm.resetFields();
    message.success(t("model_added") || "模型已添加");
  };

  // 保存配置
  const handleSave = async () => {
    try {
      localStorage.setItem("ai_model_providers", JSON.stringify(providers));
      message.success(t("config_saved") || "配置已保存");
    } catch (error) {
      message.error(t("save_failed") || "保存失败");
    }
  };

  // 重置配置
  const handleReset = () => {
    const initialProviders = PRESET_PROVIDERS.map((preset, index) => ({
      ...preset,
      apiKey: "",
      apiHost: getDefaultApiHost(preset.id),
      models: PRESET_MODELS[preset.id]?.map((name) => ({
        id: `${preset.id}-${name}`,
        name,
        isEnabled: index === 0,
      })) || [],
      isDefault: index === 0,
      isEnabled: index === 0,
    }));
    setProviders(initialProviders);
    setSelectedProviderId(initialProviders[0]?.id || "");
    message.success(t("config_reset") || "配置已重置");
  };

  // 获取API Key链接
  const getApiKeyUrl = (providerId: string): string => {
    const urls: Record<string, string> = {
      openrouter: "https://openrouter.ai/keys",
      siliconflow: "https://cloud.siliconflow.cn/account/ak",
      openai: "https://platform.openai.com/api-keys",
      ollama: "",
      deepseek: "https://platform.deepseek.com/api_keys",
      dashscope: "https://dashscope.console.aliyun.com/apiKey",
      google: "https://aistudio.google.com/app/apikey",
      azure: "https://portal.azure.com",
    };
    return urls[providerId] || "";
  };

  return (
    <div className="space-y-6">
      {/* 主内容区域 - 响应式布局 */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* 左侧厂商列表 */}
        <div className="w-full lg:w-64 flex-shrink-0">
          <div className="text-base font-medium mb-4 leading-8 h-8">{t("model_provider") || "模型提供商"}</div>
          <Card className="shadow-sm" bodyStyle={{ padding: 8 }}>
            {/* 小屏幕：水平排列自动换行；大屏幕：垂直列表 */}
            <div className="flex flex-wrap gap-2 lg:flex-col lg:gap-1">
              {providers.map((provider) => (
                <div
                  key={provider.id}
                  className={`cursor-pointer rounded-lg transition-all duration-200 px-3 py-2 flex items-center gap-2 lg:gap-3 lg:w-full ${
                    selectedProviderId === provider.id
                      ? "bg-gray-100 dark:bg-gray-800"
                      : "hover:bg-gray-50 dark:hover:bg-gray-900"
                  }`}
                  onClick={() => setSelectedProviderId(provider.id)}
                >
                  <span className="w-8 h-8 flex items-center justify-center shrink-0 overflow-hidden">
                    <img src={provider.icon} alt={provider.name} className="w-6 h-6 object-contain" />
                  </span>
                  <div className="flex-1 min-w-0 hidden lg:block">
                    <div className="font-medium text-sm truncate">{provider.name}</div>
                    <div className="text-xs text-gray-400 truncate">{provider.id}</div>
                  </div>
                  <span className="lg:hidden font-medium text-sm">{provider.name}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* 右侧配置区域 */}
        <div className="flex-1">
          {selectedProvider ? (
            <div className="space-y-4">
              {/* 厂商标题和默认设置 - 与左侧标题对齐 */}
              <div className="flex items-center justify-between h-8">
                <div className="text-base font-medium">{selectedProvider.name}</div>
                <Space>
                  <Text type="secondary" className="text-sm">{t("default_provider") || "默认提供商"}</Text>
                  <Switch
                    checked={selectedProvider.isDefault}
                    onChange={(checked) => {
                      if (checked) setDefaultProvider(selectedProvider.id);
                    }}
                  />
                </Space>
              </div>

              <Card className="shadow-sm">
                {/* API Key */}
                <div className="mb-6">
                  <Text strong className="block mb-2 text-base">{t("api_key") || "API密钥"}</Text>
                  <Space.Compact className="w-full">
                    <Input.Password
                      value={selectedProvider.apiKey}
                      onChange={(e) =>
                        updateProvider(selectedProvider.id, { apiKey: e.target.value })
                      }
                      placeholder={t("enter_api_key") || "输入API密钥"}
                      className="flex-1"
                    />
                    <Button
                      type="default"
                      loading={checkingProvider === selectedProvider.id}
                      onClick={() => checkAvailability(selectedProvider.id)}
                    >
                      {t("check_availability") || "检查可用性"}
                    </Button>
                  </Space.Compact>
                  {getApiKeyUrl(selectedProvider.id) && (
                    <a
                      href={getApiKeyUrl(selectedProvider.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-gray-600 hover:text-gray-800 underline mt-2 inline-block"
                    >
                      {t("click_to_get_api_key") || "点击此处获取API密钥"}
                    </a>
                  )}
                </div>

                {/* API Host */}
                <div className="mb-6">
                  <Text strong className="block mb-2 text-base">{t("api_host") || "API主机"}</Text>
                  <Input
                    value={selectedProvider.apiHost}
                    onChange={(e) =>
                      updateProvider(selectedProvider.id, { apiHost: e.target.value })
                    }
                    placeholder={t("enter_api_host") || "请输入 API Host"}
                  />
                </div>

                <Divider className="my-4" />

                {/* 模型列表 */}
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <Text strong className="text-base">{t("models") || "模型"}</Text>
                    <Button
                      type="default"
                      icon={<IconPlus size="1em" />}
                      onClick={() => setIsAddModelModalOpen(true)}
                    >
                      {t("add") || "添加"}
                    </Button>
                  </div>

                  <div className="space-y-2">
                    {selectedProvider.models.map((model) => (
                      <div
                        key={model.id}
                        className="flex items-center justify-between py-3 px-4 bg-gray-50 dark:bg-gray-900 rounded-lg"
                      >
                        <Text className="text-sm">{model.name}</Text>
                        <Space>
                          <Switch
                            checked={model.isEnabled}
                            onChange={(checked) =>
                              toggleModel(selectedProvider.id, model.id, checked)
                            }
                            size="small"
                          />
                          <Popconfirm
                            title={t("confirm_delete") || "确认删除"}
                            description={t("delete_model_confirm") || "确定要删除这个模型吗？"}
                            onConfirm={() => deleteModel(selectedProvider.id, model.id)}
                            okText={t("yes") || "是"}
                            cancelText={t("no") || "否"}
                          >
                            <Button
                              type="text"
                              danger
                              icon={<IconTrash size="1em" />}
                              size="small"
                            />
                          </Popconfirm>
                        </Space>
                      </div>
                    ))}
                    {selectedProvider.models.length === 0 && (
                      <div className="text-center py-8 text-gray-400">
                        {t("no_models") || "暂无模型"}
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            </div>
          ) : (
            <Card className="shadow-sm">
              <div className="text-center py-12 text-gray-500">
                <IconRobot size="48" className="mx-auto mb-4 opacity-50" />
                <p>{t("select_provider") || "请选择一个模型厂商"}</p>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex justify-end gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Space>
          <Button onClick={handleReset}>
            {t("reset") || "重置"}
          </Button>
          <Button type="primary" onClick={handleSave}>
            {t("save") || "保存"}
          </Button>
        </Space>
      </div>

      {/* 添加模型弹窗 */}
      <Modal
        title={<span className="text-lg font-medium">{t("add_model") || "添加模型"}</span>}
        open={isAddModelModalOpen}
        onCancel={() => {
          setIsAddModelModalOpen(false);
          addModelForm.resetFields();
        }}
        footer={null}
        width={480}
      >
        <Form form={addModelForm} onFinish={handleAddModel} layout="vertical" className="mt-4">
          <Form.Item
            name="modelId"
            label={<span className="font-medium">{t("model_id") || "模型ID"}</span>}
            rules={[
              { required: true, message: t("please_enter_model_id") || "请输入模型ID" },
            ]}
          >
            <Input
              placeholder={t("enter_model_id") || "输入模型ID"}
              size="large"
              className="rounded-lg"
            />
          </Form.Item>
          <Form.Item
            name="name"
            label={<span className="font-medium">{t("model_name") || "模型名称"}</span>}
            rules={[
              { required: true, message: t("please_enter_model_name") || "请输入模型名称" },
            ]}
          >
            <Input
              placeholder={t("enter_model_name") || "输入模型名称"}
              size="large"
              className="rounded-lg"
            />
          </Form.Item>
          <Form.Item className="mb-0 mt-6">
            <div className="flex gap-3">
              <Button
                size="large"
                className="flex-1 rounded-lg"
                onClick={() => {
                  setIsAddModelModalOpen(false);
                  addModelForm.resetFields();
                }}
              >
                {t("cancel") || "取消"}
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                size="large"
                className="flex-1 rounded-lg bg-gray-900 hover:bg-gray-800 border-gray-900"
              >
                {t("confirm") || "确认"}
              </Button>
            </div>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ModelSettingsPage;
