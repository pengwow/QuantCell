/**
 * AI模型设置页面
 * 功能：管理AI大模型厂商配置，包括API Key、API Host、代理设置和模型列表
 */
import { useState, useEffect, useMemo } from "react";
import axios from "axios";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { ReactNode } from "react";
import {
  Card,
  Input,
  Button,
  Switch,
  Modal,
  Form,
  Space,
  Typography,
  App,
  Popconfirm,
  Divider,
  Tag,
} from "antd";
import {
  IconPlus,
  IconTrash,
  IconRobot,
} from "@tabler/icons-react";
import { configApi, aiModelApi } from "../../api";
import { useGuestRestriction } from "../../hooks/useGuestRestriction";

const { Text } = Typography;

// 模型类型：system_one 为 Laya 单次前向决策模型，system_two 为生成式大模型
type ModelCategory = "system_one" | "system_two";

// Laya 自托管决策模型的三个官方 checkpoint 与默认服务地址（裸地址，不含 /v1）
const LAYA_CHECKPOINTS = ["laya", "laya-multilingual", "laya-typed-decisions"];

// Jev 协议的 System One 决策模型（原生契约 POST {api_host}/v1/systemone）。
// 与 Laya 同属决策模型，归入 System 1 分组；数据来自 laya-ai.com/zh/jev-alternatives。
const SYSTEM_ONE_PROVIDERS = new Set([
  "laya",
  "jev",
  "kev",
  "von",
  "decider",
  "rizzo-flow",
  "openthai-systemone",
]);
const LAYA_API_HOST = "http://127.0.0.1:8787";

// 表单里的「标签 + 控件」统一用 Space 控制间距，避免 Tailwind margin 在 antd v6 下失效
const FieldGroup = ({ label, children }: { label: ReactNode; children: ReactNode }) => (
  <Space orientation="vertical" size="small" style={{ display: "flex" }}>
    <Text strong>{label}</Text>
    {children}
  </Space>
);

// 模型厂商配置接口
interface ModelProvider {
  id: string;
  name: string;
  icon: string;
  category: ModelCategory; // 模型类型，组内单独维护默认项
  api_key: string;
  api_host: string;
  models: Model[];
  is_default: boolean;
  is_enabled: string | null; // 当前选中的模型ID（null 表示未选择）
  proxy_enabled: boolean; // 是否启用代理
  proxy_url?: string; // 代理地址
  proxy_username?: string; // 代理用户名
  proxy_password?: string; // 代理密码
}

// 模型接口
interface Model {
  id: string;
  name: string;
  // is_enabled 在 provider 级别维护，存当前选中的模型 ID（system_config 语义）
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
  xiaomi: "/imgs/model_providers/xiaomi.png",
  laya: "/imgs/model_providers/laya.svg",
  jev: "/imgs/model_providers/jev.png",
  "rizzo-flow": "/imgs/model_providers/rizzo-flow.webp",
  "openthai-systemone": "/imgs/model_providers/openthai-systemone.png",
};

// 首字母圆圈调色板：无 logo 的厂商按 id hash 取色
const FALLBACK_COLORS = [
  "#3B82F6", "#8B5CF6", "#EC4899", "#EF4444",
  "#F97316", "#EAB308", "#10B981", "#14B8A6",
];
const colorForId = (id: string) =>
  FALLBACK_COLORS[id.split("").reduce((a, c) => a + c.charCodeAt(0), 0) % FALLBACK_COLORS.length];
const InitialAvatar = ({ id, name }: { id: string; name: string }) => (
  <span
    className="w-8 h-8 flex items-center justify-center shrink-0 rounded-md text-white text-sm font-semibold"
    style={{ backgroundColor: colorForId(id) }}
  >
    {name.charAt(0).toUpperCase()}
  </span>
);

const getPresetProviders = (t: TFunction): PresetProvider[] => [
  {
    id: "openrouter",
    name: "OpenRouter",
    icon: PROVIDER_ICONS.openrouter,
  },
  {
    id: "siliconflow",
    name: t('provider_siliconflow') || '硅基流动',
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
    name: t('provider_openai_compatible') || 'OpenAI兼容API',
    icon: PROVIDER_ICONS["openai-compatible"],
  },
  {
    id: "deepseek",
    name: t('provider_deepseek') || '深度求索',
    icon: PROVIDER_ICONS.deepseek,
  },
  {
    id: "dashscope",
    name: t('provider_aliyun') || '阿里云',
    icon: PROVIDER_ICONS.dashscope,
  },
  {
    id: "google",
    name: t('provider_google') || '谷歌云',
    icon: PROVIDER_ICONS.google,
  },
  {
    id: "azure",
    name: t('provider_azure') || '微软Azure OpenAI',
    icon: PROVIDER_ICONS.azure,
  },
  {
    id: "xiaomi",
    name: t('provider_xiaomi') || '小米',
    icon: PROVIDER_ICONS.xiaomi,
  },
  {
    id: "laya",
    name: "Laya AI",
    icon: PROVIDER_ICONS.laya,
  },
  // Jev 兼容的 System One 决策模型（自托管替代品 + 托管 API）
  { id: "jev", name: "Jev (TypeSafe)", icon: PROVIDER_ICONS.jev },
  { id: "kev", name: "Kev", icon: "" },
  { id: "von", name: "Von", icon: "" },
  { id: "decider", name: "Decider", icon: "" },
  { id: "rizzo-flow", name: "Rizzo Flow", icon: PROVIDER_ICONS["rizzo-flow"] },
  { id: "openthai-systemone", name: "OpenThai-SystemOne", icon: PROVIDER_ICONS["openthai-systemone"] },
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
  xiaomi: ["mimo-v2.5-pro", "mimo-v2.5", "mimo-v2.5-tts", "mimo-v2.5-tts-voicedesign", "mimo-v2.5-tts-voiceclone", "mimo-v2-pro", "mimo-v2-omni", "mimo-v2-tts", "mimo-v2-flash"],
  laya: LAYA_CHECKPOINTS,
  jev: ["jev-1"],
  // 其余 System One 模型的部署名随 HF repo / 量化文件 / 起服务参数而变，不预设、由用户填写
  kev: [],
  von: [],
  decider: [],
  "rizzo-flow": [],
  "openthai-systemone": [],
};

const ModelSettingsPage = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { isGuest } = useGuestRestriction();
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState<string>("");
  const [isAddModelModalOpen, setIsAddModelModalOpen] = useState(false);
  const [addModelForm] = Form.useForm();
  const [checkingProvider, setCheckingProvider] = useState<string | null>(null);
  const [fetchedModels, setFetchedModels] = useState<Array<{ id: string; name: string; description?: string }>>([]);
  const [fetchingModels, setFetchingModels] = useState(false);

  // 获取预设厂商列表（使用翻译）
  const PRESET_PROVIDERS = useMemo(() => getPresetProviders(t), [t]);

  // 从后端API加载配置
  useEffect(() => {
    loadProviders();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性初始化
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
              console.warn(t('parse_model_list_failed', { provider: preset.id }) || `解析 ${preset.id} 模型列表失败`, e);
            }

            return {
              id: preset.id,
              name: existing.name || preset.name,
              icon: preset.icon,
              category: resolveCategory(preset.id, existing.category),
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
            category: resolveCategory(preset.id),
            api_key: "",
            api_host: getDefaultApiHost(preset.id),
            models: PRESET_MODELS[preset.id]?.map((name) => ({
              id: name,
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
      console.error(t('load_model_config_failed', { message: error }) || "加载模型配置失败:", error);
      message.error(t("load_failed") || "加载配置失败");
      initDefaultProviders();
    }
  };

  // 初始化默认配置（所有状态默认关闭）
  const initDefaultProviders = () => {
    const initialProviders = PRESET_PROVIDERS.map((preset) => ({
      ...preset,
      category: resolveCategory(preset.id),
      api_key: "",
      api_host: getDefaultApiHost(preset.id),
      models: PRESET_MODELS[preset.id]?.map((name) => ({
        id: name,
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
      xiaomi: "https://token-plan-cn.xiaomimimo.com/v1",
      laya: LAYA_API_HOST,
    };
    return hosts[providerId] || "";
  }

  // 获取当前选中的厂商
  const selectedProvider = providers.find((p) => p.id === selectedProviderId);

  // 归属判定：Jev 协议的决策模型归 System 1，其余厂商一律 System 2
  // （用户在表单里显式选了 system_two 时尊重其选择，例如用决策模型做生成式任务的场景）
  function resolveCategory(providerId: string, saved?: string): ModelCategory {
    if (saved === "system_two") return "system_two";
    return SYSTEM_ONE_PROVIDERS.has(providerId) ? "system_one" : "system_two";
  }

  // 更新厂商配置
  const updateProvider = (providerId: string, updates: Partial<ModelProvider>) => {
    setProviders((prev) =>
      prev.map((p) => (p.id === providerId ? { ...p, ...updates } : p))
    );
  };

  // 设置默认厂商：仅在同类分组内唯一，避免 System 1 / System 2 互相覆盖
  const setDefaultProvider = (providerId: string) => {
    const target = providers.find((p) => p.id === providerId);
    if (!target) return;
    setProviders((prev) =>
      prev.map((p) =>
        p.category === target.category
          ? { ...p, is_default: p.id === providerId }
          : p
      )
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

  // 检查可用性并获取模型列表
  const checkAvailability = async (providerId: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider) return;

    // System One 决策服务多为自托管、通常无鉴权，API Key 非必填
    const isSystemOne = provider.category === "system_one";
    if (!isSystemOne && !provider.api_key) {
      message.warning(t("please_enter_api_key") || "请输入API密钥");
      return;
    }

    setCheckingProvider(providerId);
    setFetchingModels(true);
    try {
      const result = await aiModelApi.checkAvailability({
        provider: provider.id,
        api_key: provider.api_key || "",
        // 决策模型的 api_host 必须是裸地址（不含 /v1），适配器会自行拼接
        api_host: isSystemOne ? provider.api_host.replace(/\/v1\/?$/, "") : provider.api_host,
        proxy_enabled: provider.proxy_enabled,
        proxy_url: provider.proxy_url,
        proxy_username: provider.proxy_username,
        proxy_password: provider.proxy_password,
      });

      if (result?.available) {
        message.success(result.message || t("api_key_valid") || "API密钥有效");
        // 只有探测到真实模型才覆盖，空列表说明服务不提供 /v1/models，保留用户预设
        if (Array.isArray(result.models) && result.models.length > 0) {
          const newModels: Model[] = result.models.map((m) => ({
            id: m.id,
            name: m.name || m.id,
          }));
          setFetchedModels(newModels);
          setProviders((prev) =>
            prev.map((p) =>
              p.id === providerId ? { ...p, models: newModels } : p
            )
          );
        }
      } else {
        message.error(result.message || t("api_key_invalid") || "API密钥无效");
        setFetchedModels([]);
      }
    } catch (error) {
      console.error("检查可用性失败:", error);
      const errorMsg = (axios.isAxiosError(error) ? error.response?.data?.detail : undefined) || (error instanceof Error ? error.message : undefined) || t("check_failed") || "检查失败";
      message.error(errorMsg);
      setFetchedModels([]);
    } finally {
      setCheckingProvider(null);
      setFetchingModels(false);
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
      id: values.model_id,
      name: values.name,
    };

    // 添加模型时默认不启用（保持原有启用状态）
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
          { key: `${prefix}.category`, value: provider.category, name: 'ai_model', description: `${providerName}模型类型` },
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
      const errorMsg = (error instanceof Error ? error.message : undefined) || (axios.isAxiosError(error) ? error.response?.data?.detail : undefined) || t("save_failed") || "保存失败";
      console.error(t('save_model_config_failed', { message: error }) || "保存配置失败:", error);
      if ((error as { code?: number })?.code === 401 || (axios.isAxiosError(error) && error.response?.status === 401)) {
        message.warning(errorMsg);
      } else {
        message.error(errorMsg);
      }
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
        category: resolveCategory(preset.id),
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
    <Space orientation="vertical" size="large" style={{ display: "flex" }}>
      {/* 主内容区域 - 响应式布局 */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* 左侧厂商列表：按模型类型分组，每组独立维护默认项 */}
        <div className="w-full lg:w-64 flex-shrink-0">
          <div className="text-base font-medium mb-4 leading-8 h-8">{t("model_provider") || "模型提供商"}</div>
          <Space orientation="vertical" size="middle" style={{ display: "flex" }}>
            {(["system_one", "system_two"] as ModelCategory[]).map((category) => {
              const groupProviders = providers.filter((p) => p.category === category);
              return (
                <Card
                  key={category}
                  className="shadow-sm"
                  size="small"
                  title={<span className="text-sm font-medium">{category === "system_one" ? t("system_one_label") : t("system_two_label")}</span>}
                  styles={{ body: { padding: 8 } }}
                >
                  <div className="flex flex-wrap gap-2 lg:flex-col lg:gap-1">
                    {groupProviders.map((provider) => (
                      <div
                        key={provider.id}
                        className={`cursor-pointer rounded-lg transition-all duration-200 px-3 py-2 flex items-center gap-2 lg:gap-3 lg:w-full ${
                          selectedProviderId === provider.id
                            ? "bg-gray-100 dark:bg-gray-800"
                            : "hover:bg-gray-50 dark:hover:bg-gray-900"
                        }`}
                        onClick={() => {
                          setSelectedProviderId(provider.id);
                          setFetchedModels([]);
                        }}
                      >
                        <span className="w-8 h-8 flex items-center justify-center shrink-0 overflow-hidden">
                          {provider.icon ? (
                            <img src={provider.icon} alt={provider.name} className="w-6 h-6 object-contain" />
                          ) : (
                            <InitialAvatar id={provider.id} name={provider.name} />
                          )}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-sm truncate">{provider.name}</div>
                          {/* 只展示厂商标识：模型名多时会撑爆这一行灰字，详情在右侧表单里看 */}
                          <div className="text-xs text-gray-400 truncate">{provider.id}</div>
                        </div>
                        <Button
                          size="small"
                          type={provider.is_default ? "default" : "link"}
                          disabled={provider.is_default}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDefaultProvider(provider.id);
                          }}
                        >
                          {provider.is_default ? "默认" : "设为默认"}
                        </Button>
                      </div>
                    ))}
                    {groupProviders.length === 0 && (
                      <div className="text-center py-4 text-gray-400 text-sm">
                        {category === "system_one" ? t("no_system_one_provider") : t("no_system_two_provider")}
                      </div>
                    )}
                  </div>
                </Card>
              );
            })}
          </Space>
        </div>

        {/* 右侧配置区域 */}
        <div className="flex-1">
          {selectedProvider ? (
            <Space orientation="vertical" size="middle" style={{ display: "flex" }}>
              {/* 厂商标题和默认设置 - 与左侧标题对齐 */}
              <div className="flex items-center justify-between h-8">
                <div className="text-base font-medium">{selectedProvider.name}</div>
                <Space>
                  <Text type="secondary" className="text-sm">{t("default_provider") || "组内默认"}</Text>
                  <Switch
                    checked={selectedProvider.is_default}
                    onChange={(checked) => {
                      if (checked) setDefaultProvider(selectedProvider.id);
                    }}
                  />
                </Space>
              </div>

              <Card className="shadow-sm">
                <Space orientation="vertical" size="middle" style={{ display: "flex" }}>
                  {/* 模型类型：厂商固有属性，只读展示 */}
                  <FieldGroup label={t("model_category") || "模型类型"}>
                    <Tag color={selectedProvider.category === "system_one" ? "blue" : "purple"}>
                      {selectedProvider.category === "system_one" ? t("system_one_label") : t("system_two_label")}
                    </Tag>
                    {selectedProvider.category === "system_one" && (
                      <Text type="secondary" className="text-xs">
                        {t("system_one_jev_hint")}
                      </Text>
                    )}
                  </FieldGroup>

                  {/* API Key */}
                  <FieldGroup label={t("api_key") || "API密钥"}>
                    <Space.Compact className="w-full">
                      <Input.Password
                        value={selectedProvider.api_key}
                        onChange={(e) =>
                          updateProvider(selectedProvider.id, { api_key: e.target.value })
                        }
                        placeholder={
                          selectedProvider.category === "system_one"
                            ? t("system_one_apikey_optional")
                            : t("enter_api_key") || "输入API密钥"
                        }
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
                        className="text-sm text-gray-600 hover:text-gray-800 underline"
                      >
                        {t("click_to_get_api_key") || "点击此处获取API密钥"}
                      </a>
                    )}
                  </FieldGroup>

                  {/* API Host */}
                  <FieldGroup label={t("api_host") || "API主机"}>
                    <Input
                      value={selectedProvider.api_host}
                      onChange={(e) =>
                        updateProvider(selectedProvider.id, { api_host: e.target.value })
                      }
                      placeholder={t("enter_api_host") || "请输入 API Host"}
                    />
                  </FieldGroup>

                  <Divider className="my-0" />

                  {/* 代理设置 */}
                  <Space orientation="vertical" size="small" style={{ display: "flex" }}>
                    <div className="flex items-center justify-between">
                      <Text strong>{t("proxy_settings") || "代理设置"}</Text>
                      <Space>
                        <Text type="secondary" className="text-sm">{t("proxy_enabled") || "启用代理"}</Text>
                        <Switch
                          checked={selectedProvider.proxy_enabled}
                          onChange={handleProxyToggle}
                        />
                      </Space>
                    </div>

                    {selectedProvider.proxy_enabled && (
                      <Space orientation="vertical" size="small" style={{ display: "flex" }}>
                        <FieldGroup label={t("proxy_url") || "代理地址"}>
                          <Input
                            value={selectedProvider.proxy_url}
                            onChange={(e) =>
                              updateProvider(selectedProvider.id, { proxy_url: e.target.value })
                            }
                            placeholder="http://proxy.example.com:8080"
                          />
                        </FieldGroup>

                        <FieldGroup label={t("proxy_username") || "代理用户名"}>
                          <Input
                            value={selectedProvider.proxy_username}
                            onChange={(e) =>
                              updateProvider(selectedProvider.id, { proxy_username: e.target.value })
                            }
                            placeholder={t("optional") || "可选"}
                          />
                        </FieldGroup>

                        <FieldGroup label={t("proxy_password") || "代理密码"}>
                          <Input.Password
                            value={selectedProvider.proxy_password}
                            onChange={(e) =>
                              updateProvider(selectedProvider.id, { proxy_password: e.target.value })
                            }
                            placeholder={t("optional") || "可选"}
                          />
                        </FieldGroup>
                      </Space>
                    )}
                  </Space>

                  <Divider className="my-0" />

                  {/* 模型列表 */}
                  <Space orientation="vertical" size="small" style={{ display: "flex" }}>
                    <div className="flex items-center justify-between">
                      <Text strong>{t("models") || "模型"}</Text>
                      <Button
                        type="default"
                        icon={<IconPlus size="1em" />}
                        onClick={() => setIsAddModelModalOpen(true)}
                      >
                        {t("add") || "添加"}
                      </Button>
                    </div>

                    <div className="flex flex-col gap-2">
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
                  </Space>
                </Space>
              </Card>
            </Space>
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
        width={560}
      >
        <Form form={addModelForm} onFinish={handleAddModel} layout="vertical" className="mt-4">
          {/* 从API获取的模型列表 */}
          {fetchedModels.length > 0 && (
            <Form.Item label={<span className="font-medium">{t("available_models") || "可用模型"}</span>}>
              <div className="flex flex-wrap gap-2 max-h-48 overflow-y-auto p-1">
                {fetchedModels.map((model) => {
                  const alreadyAdded = selectedProvider?.models.some((m) => m.id === model.id);
                  return (
                    <Button
                      key={model.id}
                      size="small"
                      type={alreadyAdded ? "default" : "primary"}
                      ghost={alreadyAdded}
                      disabled={alreadyAdded}
                      onClick={() => {
                        addModelForm.setFieldsValue({
                          model_id: model.id,
                          name: model.name || model.id,
                        });
                      }}
                      title={model.description || model.id}
                    >
                      {model.name || model.id}
                      {alreadyAdded && ` ✓`}
                    </Button>
                  );
                })}
              </div>
            </Form.Item>
          )}

          {fetchedModels.length === 0 && !fetchingModels && (
            <div className="text-center py-3 text-gray-400 text-sm mb-4">
              {t("click_check_to_fetch_models") || "请先点击「检查可用性」获取模型列表"}
            </div>
          )}

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
    </Space>
  );
};

export default ModelSettingsPage;
