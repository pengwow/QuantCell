/**
 * AI模型设置页面
 * 功能：管理AI大模型厂商配置，包括API Key、API Host、代理设置和模型列表
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
import { configApi, aiModelApi } from "../../api";
import { useGuestRestriction } from "../../hooks/useGuestRestriction";

const { Text } = Typography;

// 模型厂商配置接口
interface ModelProvider {
  id: string;
  name: string;
  icon: string;
  api_key: string;
  api_host: string;
  models: Model[];
  is_default: boolean;
  is_enabled: string | null; // 存储启用的模型ID，null表示未启用
  proxy_enabled: boolean; // 是否启用代理
  proxy_url?: string; // 代理地址
  proxy_username?: string; // 代理用户名
  proxy_password?: string; // 代理密码
}

// 模型接口
interface Model {
  id: string;
  name: string;
  // 删除 is_enabled 字段，改为在 provider 级别管理
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
  const { isGuest } = useGuestRestriction();
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState<string>("");
  const [isAddModelModalOpen, setIsAddModelModalOpen] = useState(false);
  const [addModelForm] = Form.useForm();
  const [checkingProvider, setCheckingProvider] = useState<string | null>(null);

  // 从后端API加载配置
  useEffect(() => {
    loadProviders();
  }, []);

  // 从系统配置加载模型配置（从扁平化配置加载）
  const loadProviders = async () => {
    try {
      // 使用 configApi 获取所有配置（返回格式为按 name 分组）
      const groupedConfigs = await configApi.getConfig() as Record<string, Record<string, string>>;

      // 获取 ai_model 分组的配置
      const aiModelGroup = groupedConfigs.ai_model || {};

      // 将扁平化配置按厂商ID分组
      const providerConfigs: Record<string, Record<string, string>> = {};
      Object.entries(aiModelGroup).forEach(([key, value]) => {
        if (key.startsWith('ai_model.')) {
          const parts = key.split('.');
          if (parts.length >= 3) {
            const providerId = parts[1];
            const field = parts[2];
            if (!providerConfigs[providerId]) {
              providerConfigs[providerId] = {};
            }
            providerConfigs[providerId][field] = value;
          }
        }
      });

      // 检查是否有保存的配置
      const hasSavedConfig = Object.keys(providerConfigs).length > 0;

      if (hasSavedConfig) {
        // 将后端数据转换为前端格式
        const loadedProviders = PRESET_PROVIDERS.map((preset) => {
          const existing = providerConfigs[preset.id];
          if (existing && Object.keys(existing).length > 0) {
            // 解析 models JSON
            let models: Model[] = [];
            try {
              if (existing.models) {
                models = JSON.parse(existing.models);
              }
            } catch (e) {
              console.warn(`解析 ${preset.id} 模型列表失败`, e);
            }

            return {
              id: preset.id,
              name: existing.name || preset.name,
              icon: preset.icon,
              api_key: existing.api_key || "",
              api_host: existing.api_host || getDefaultApiHost(preset.id),
              models: models.map(m => ({ id: m.id, name: m.name })), // 删除模型中的 is_enabled
              is_default: existing.is_default === '1',
              is_enabled: existing.is_enabled || null, // 直接存储模型ID
              proxy_enabled: existing.proxy_enabled === '1',
              proxy_url: existing.proxy_url || "",
              proxy_username: existing.proxy_username || "",
              proxy_password: existing.proxy_password || "",
            };
          }
          // 返回默认配置
          return {
            id: preset.id,
            name: preset.name,
            icon: preset.icon,
            api_key: "",
            api_host: getDefaultApiHost(preset.id),
            models: PRESET_MODELS[preset.id]?.map((name) => ({
              id: `${preset.id}-${name}`,
              name,
            })) || [],
            is_default: false,
            is_enabled: null,
            proxy_enabled: false,
            proxy_url: "",
            proxy_username: "",
            proxy_password: "",
          };
        });
        setProviders(loadedProviders);
        setSelectedProviderId(loadedProviders[0]?.id || "");
      } else {
        // 初始化默认配置
        initDefaultProviders();
      }
    } catch (error) {
      console.error("加载模型配置失败:", error);
      message.error(t("load_failed") || "加载配置失败");
      initDefaultProviders();
    }
  };

  // 初始化默认配置（所有状态默认关闭）
  const initDefaultProviders = () => {
    const initialProviders = PRESET_PROVIDERS.map((preset) => ({
      ...preset,
      api_key: "",
      api_host: getDefaultApiHost(preset.id),
      models: PRESET_MODELS[preset.id]?.map((name) => ({
        id: `${preset.id}-${name}`,
        name,
      })) || [],
      is_default: false,
      is_enabled: null as string | null,
      proxy_enabled: false,
      proxy_url: "",
      proxy_username: "",
      proxy_password: "",
    }));
    setProviders(initialProviders);
    setSelectedProviderId(initialProviders[0]?.id || "");
  };



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
        is_default: p.id === providerId,
      }))
    );
    message.success(t("default_provider_set") || "默认厂商已设置");
  };

  // 从其他厂商获取代理配置
  const getProxyFromOtherProviders = (): Partial<ModelProvider> | null => {
    const providerWithProxy = providers.find(
      (p) => p.proxy_enabled && p.proxy_url && p.id !== selectedProviderId
    );
    if (providerWithProxy) {
      return {
        proxy_url: providerWithProxy.proxy_url,
        proxy_username: providerWithProxy.proxy_username,
        proxy_password: providerWithProxy.proxy_password,
      };
    }
    return null;
  };

  // 处理代理开关变化
  const handleProxyToggle = (checked: boolean) => {
    if (checked && selectedProvider) {
      // 启用代理时，尝试从其他厂商获取代理配置
      const proxyConfig = getProxyFromOtherProviders();
      if (proxyConfig) {
        updateProvider(selectedProvider.id, {
          proxy_enabled: true,
          ...proxyConfig,
        });
        message.success(t("proxy_auto_filled") || "已自动填充代理配置");
      } else {
        updateProvider(selectedProvider.id, { proxy_enabled: true });
      }
    } else if (selectedProvider) {
      // 关闭代理时，清空代理配置
      updateProvider(selectedProvider.id, {
        proxy_enabled: false,
        proxy_url: "",
        proxy_username: "",
        proxy_password: "",
      });
    }
  };

  // 检查可用性
  const checkAvailability = async (providerId: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider?.api_key) {
      message.warning(t("please_enter_api_key") || "请输入API密钥");
      return;
    }
    
    setCheckingProvider(providerId);
    try {
      const result = await aiModelApi.checkAvailability({
        provider: provider.id,
        api_key: provider.api_key,
        api_host: provider.api_host,
        proxy_enabled: provider.proxy_enabled,
        proxy_url: provider.proxy_url,
        proxy_username: provider.proxy_username,
        proxy_password: provider.proxy_password,
      });
      
      if (result?.available) {
        message.success(result.message || t("api_key_valid") || "API密钥有效");
      } else {
        message.error(result.message || t("api_key_invalid") || "API密钥无效");
      }
    } catch (error: any) {
      console.error("检查可用性失败:", error);
      const errorMsg = error?.response?.data?.detail || error?.message || t("check_failed") || "检查失败";
      message.error(errorMsg);
    } finally {
      setCheckingProvider(null);
    }
  };

  // 启用/禁用模型
  const toggleModel = (providerId: string, model_id: string, enabled: boolean) => {
    setProviders((prev) =>
      prev.map((p) => {
        if (p.id !== providerId) return p;
        // 启用时设置为模型ID，禁用时设为null
        return {
          ...p,
          is_enabled: enabled ? model_id : null,
        };
      })
    );
  };

  // 删除模型
  const deleteModel = (providerId: string, model_id: string) => {
    setProviders((prev) =>
      prev.map((p) =>
        p.id === providerId
          ? { ...p, models: p.models.filter((m) => m.id !== model_id) }
          : p
      )
    );
    message.success(t("model_deleted") || "模型已删除");
  };

  // 添加模型
  const handleAddModel = (values: { model_id: string; name: string }) => {
    if (!selectedProvider) return;

    const newModel: Model = {
      id: `${selectedProvider.id}-${values.model_id}`,
      name: values.name,
    };

    // 添加模型时自动启用该模型
    setProviders((prev) =>
      prev.map((p) =>
        p.id === selectedProvider.id
          ? { ...p, models: [...p.models, newModel], is_enabled: newModel.id }
          : p
      )
    );

    setIsAddModelModalOpen(false);
    addModelForm.resetFields();
    message.success(t("model_added") || "模型已添加");
  };

  // 保存配置到系统配置表（使用扁平化存储格式）
  const handleSave = async () => {
    try {
      // 构建批量更新的配置数组，格式与 general 页面一致
      const batchConfigs: Array<{
        key: string;
        value: string;
        name: string;
        description: string;
      }> = [];

      providers.forEach((provider) => {
        const prefix = `ai_model.${provider.id}`;
        const providerName = provider.name;

        batchConfigs.push(
          { key: `${prefix}.name`, value: provider.name, name: 'ai_model', description: `${providerName}厂商名称` },
          { key: `${prefix}.api_key`, value: provider.api_key || '', name: 'ai_model', description: `${providerName}API Key` },
          { key: `${prefix}.api_host`, value: provider.api_host || '', name: 'ai_model', description: `${providerName}API Host` },
          { key: `${prefix}.models`, value: JSON.stringify(provider.models), name: 'ai_model', description: `${providerName}模型列表` },
          { key: `${prefix}.is_default`, value: provider.is_default ? '1' : '0', name: 'ai_model', description: `${providerName}是否为默认` },
          { key: `${prefix}.is_enabled`, value: provider.is_enabled || '', name: 'ai_model', description: `${providerName}启用的模型ID` },
          { key: `${prefix}.proxy_enabled`, value: provider.proxy_enabled ? '1' : '0', name: 'ai_model', description: `${providerName}是否启用代理` },
          { key: `${prefix}.proxy_url`, value: provider.proxy_url || '', name: 'ai_model', description: `${providerName}代理地址` },
          { key: `${prefix}.proxy_username`, value: provider.proxy_username || '', name: 'ai_model', description: `${providerName}代理用户名` },
          { key: `${prefix}.proxy_password`, value: provider.proxy_password || '', name: 'ai_model', description: `${providerName}代理密码` }
        );
      });

      // 调用系统配置批量更新接口
      await configApi.updateConfig(batchConfigs);
      message.success(t("config_saved") || "配置已保存");
    } catch (error) {
      console.error("保存配置失败:", error);
      message.error(t("save_failed") || "保存失败");
    }
  };

  // 重置配置
  const handleReset = () => {
    const initialProviders = PRESET_PROVIDERS.map((preset, index) => {
      const models = PRESET_MODELS[preset.id]?.map((name) => ({
        id: `${preset.id}-${name}`,
        name,
      })) || [];
      return {
        ...preset,
        api_key: "",
        api_host: getDefaultApiHost(preset.id),
        models: models,
        is_default: index === 0,
        is_enabled: index === 0 && models.length > 0 ? models[0].id : null as string | null,
        proxy_enabled: false,
        proxy_url: "",
        proxy_username: "",
        proxy_password: "",
      };
    });
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
      dashscope: "https://dashscope.console.aliyun.com/api_key",
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
                    checked={selectedProvider.is_default}
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
                      value={selectedProvider.api_key}
                      onChange={(e) =>
                        updateProvider(selectedProvider.id, { api_key: e.target.value })
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
                    value={selectedProvider.api_host}
                    onChange={(e) =>
                      updateProvider(selectedProvider.id, { api_host: e.target.value })
                    }
                    placeholder={t("enter_api_host") || "请输入 API Host"}
                  />
                </div>

                <Divider className="my-4" />

                {/* 代理设置 */}
                <div className="mb-4">
                  <div className="flex items-center justify-between mb-4">
                    <Text strong className="text-base">{t("proxy_settings") || "代理设置"}</Text>
                    <Space>
                      <Text type="secondary" className="text-sm">{t("proxy_enabled") || "启用代理"}</Text>
                      <Switch
                        checked={selectedProvider.proxy_enabled}
                        onChange={handleProxyToggle}
                      />
                    </Space>
                  </div>

                  {selectedProvider.proxy_enabled && (
                    <div className="space-y-4">
                      <div>
                        <Text strong className="block mb-2 text-sm">{t("proxy_url") || "代理地址"}</Text>
                        <Input
                          value={selectedProvider.proxy_url}
                          onChange={(e) =>
                            updateProvider(selectedProvider.id, { proxy_url: e.target.value })
                          }
                          placeholder="http://proxy.example.com:8080"
                        />
                      </div>

                      <div>
                        <Text strong className="block mb-2 text-sm">{t("proxy_username") || "代理用户名"}</Text>
                        <Input
                          value={selectedProvider.proxy_username}
                          onChange={(e) =>
                            updateProvider(selectedProvider.id, { proxy_username: e.target.value })
                          }
                          placeholder={t("optional") || "可选"}
                        />
                      </div>

                      <div>
                        <Text strong className="block mb-2 text-sm">{t("proxy_password") || "代理密码"}</Text>
                        <Input.Password
                          value={selectedProvider.proxy_password}
                          onChange={(e) =>
                            updateProvider(selectedProvider.id, { proxy_password: e.target.value })
                          }
                          placeholder={t("optional") || "可选"}
                        />
                      </div>
                    </div>
                  )}
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
                            checked={selectedProvider.is_enabled === model.id}
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
          <Button onClick={handleReset} disabled={isGuest}>
            {t("reset") || "重置"}
          </Button>
          <Button type="primary" onClick={handleSave} disabled={isGuest}>
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
            name="model_id"
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
