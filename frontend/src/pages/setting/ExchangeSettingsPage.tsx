/**
 * 交易所设置页面
 * 功能：管理交易所配置，包括交易模式、计价货币、手续费、代理设置等
 * 参考：ModelSettingsPage 和 SystemConfigPage
 */
import { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  Card,
  Input,
  Button,
  Switch,
  Select,
  Space,
  Typography,
  message,
  Divider,
  Form,
  InputNumber,
  Spin,
} from "antd";
import {
  IconBuildingBank,
  IconPlugConnected,
} from "@tabler/icons-react";
import { configApi, exchangeApi } from "../../api";
import { useGuestRestriction } from "../../hooks/useGuestRestriction";
// @web3icons/react 交易所图标
import {
  ExchangeBinance,
  ExchangeOkx,
  ExchangeBybit,
  ExchangeGateIo,
  ExchangeKucoin,
  ExchangeBitget,
} from "@web3icons/react";

const { Text } = Typography;

// 交易所配置接口
interface ExchangeConfig {
  id: string;
  name: string;
  icon: React.ReactNode;
  tradingMode: 'spot' | 'futures' | 'margin'; // 交易模式
  quoteCurrency: string; // 计价货币
  commission: number; // 手续费率
  proxyEnabled: boolean; // 是否启用代理
  proxyUrl?: string; // 代理地址
  proxyUsername?: string; // 代理用户名
  proxyPassword?: string; // 代理密码
  apiKey?: string; // API Key
  apiSecret?: string; // API Secret
  isEnabled: boolean; // 是否启用
  isDefault: boolean; // 是否为默认交易所
  key?: string; // 后端系统配置的key（交易所英文名称）
}

// 预设的交易所
interface PresetExchange {
  id: string;
  name: string;
  icon: React.ReactNode;
}

// 交易所图标映射
const EXCHANGE_ICONS: Record<string, React.ReactNode> = {
  binance: <ExchangeBinance size={32} variant="branded" />,
  okx: <ExchangeOkx size={32} variant="branded" />,
  bybit: <ExchangeBybit size={32} variant="branded" />,
  gate: <ExchangeGateIo size={32} variant="branded" />,
  kucoin: <ExchangeKucoin size={32} variant="branded" />,
  // huobi: <span className="text-xl">🔥</span>, // 火币暂无图标，使用emoji
  // mexc: <span className="text-xl">Ⓜ️</span>, // MEXC暂无图标，使用emoji
  bitget: <ExchangeBitget size={32} variant="branded" />,
};

const getPresetExchanges = (t: any): PresetExchange[] => [
  { id: "binance", name: t('exchange_binance') || "币安", icon: EXCHANGE_ICONS.binance },
  { id: "okx", name: "OKX", icon: EXCHANGE_ICONS.okx },
  { id: "bybit", name: "Bybit", icon: EXCHANGE_ICONS.bybit },
  { id: "gate", name: "Gate.io", icon: EXCHANGE_ICONS.gate },
  { id: "kucoin", name: "KuCoin", icon: EXCHANGE_ICONS.kucoin },
  // { id: "huobi", name: "火币", icon: EXCHANGE_ICONS.huobi },
  // { id: "mexc", name: "MEXC", icon: EXCHANGE_ICONS.mexc },
  { id: "bitget", name: "Bitget", icon: EXCHANGE_ICONS.bitget },
];

// 计价货币选项
const QUOTE_CURRENCIES = [
  { value: "USDT", label: "USDT" },
  { value: "USDC", label: "USDC" },
  { value: "BTC", label: "BTC" },
  { value: "ETH", label: "ETH" },
  { value: "USD", label: "USD" },
];

// 交易模式选项
const getTradingModes = (t: any) => [
  { value: "spot", label: t('trading_mode_spot') || "现货" },
  { value: "futures", label: t('trading_mode_futures') || "合约" },
  { value: "margin", label: t('trading_mode_margin') || "杠杆" },
];

const ExchangeSettingsPage = () => {
  const { t } = useTranslation();
  const { isGuest } = useGuestRestriction();
  const [exchanges, setExchanges] = useState<ExchangeConfig[]>([]);
  const [selectedExchangeId, setSelectedExchangeId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);

  // 使用 useMemo 缓存翻译后的配置数组
  const PRESET_EXCHANGES = useMemo(() => getPresetExchanges(t), [t]);
  const TRADING_MODES = useMemo(() => getTradingModes(t), [t]);

  // 从后端API加载配置
  useEffect(() => {
    loadExchanges();
  }, []);

  // 加载交易所配置（从扁平化配置加载）
  const loadExchanges = async () => {
    setLoading(true);
    try {
      // 使用 configApi 获取所有配置（返回格式为按 name 分组）
      const groupedConfigs = await configApi.getConfig() as Record<string, Record<string, string>>;

      // 获取 exchange 分组的配置
      const exchangeGroup = groupedConfigs.exchange || {};

      // 将扁平化配置按交易所ID分组
      const exchangeConfigs: Record<string, Record<string, string>> = {};
      Object.entries(exchangeGroup).forEach(([key, value]) => {
        if (key.startsWith('exchange.')) {
          const parts = key.split('.');
          if (parts.length >= 3) {
            const exchangeId = parts[1];
            const field = parts[2];
            if (!exchangeConfigs[exchangeId]) {
              exchangeConfigs[exchangeId] = {};
            }
            exchangeConfigs[exchangeId][field] = value;
          }
        }
      });

      // 将后端数据转换为前端格式
      const loadedExchanges = PRESET_EXCHANGES.map((preset) => {
        const existing = exchangeConfigs[preset.id];
        if (existing && Object.keys(existing).length > 0) {
          return {
            id: preset.id,
            name: preset.name,
            icon: preset.icon,
            tradingMode: (existing.trading_mode as 'spot' | 'futures' | 'margin') || "spot",
            quoteCurrency: existing.quote_currency || "USDT",
            commission: parseFloat(existing.commission_rate) || 0.001,
            proxyEnabled: existing.proxy_enabled === '1',
            proxyUrl: existing.proxy_url || "",
            proxyUsername: existing.proxy_username || "",
            proxyPassword: existing.proxy_password || "",
            apiKey: existing.api_key || "",
            apiSecret: existing.api_secret || "",
            isEnabled: existing.is_enabled === '1',
            isDefault: existing.is_default === '1',
            key: preset.id,
          };
        }
        return {
          ...preset,
          tradingMode: "spot" as const,
          quoteCurrency: "USDT",
          commission: 0.001,
          proxyEnabled: false,
          proxyUrl: "",
          proxyUsername: "",
          proxyPassword: "",
          apiKey: "",
          apiSecret: "",
          isEnabled: false,
          isDefault: false,
          key: preset.id,
        };
      });
      setExchanges(loadedExchanges);
      setSelectedExchangeId(loadedExchanges[0]?.id || "");
    } catch (error) {
      console.error("加载交易所配置失败:", error);
      message.error(t("load_failed") || "加载配置失败");
      initDefaultExchanges();
    } finally {
      setLoading(false);
    }
  };

  // 初始化默认配置
  const initDefaultExchanges = () => {
    const initialExchanges = PRESET_EXCHANGES.map((preset, index) => ({
      ...preset,
      tradingMode: "spot" as const,
      quoteCurrency: "USDT",
      commission: 0.001,
      proxyEnabled: false,
      proxyUrl: "",
      proxyUsername: "",
      proxyPassword: "",
      apiKey: "",
      apiSecret: "",
      isEnabled: index === 0,
      isDefault: index === 0,
    }));
    setExchanges(initialExchanges);
    setSelectedExchangeId(initialExchanges[0]?.id || "");
  };

  // 获取当前选中的交易所
  const selectedExchange = exchanges.find((e) => e.id === selectedExchangeId);

  // 更新交易所配置
  const updateExchange = (exchangeId: string, updates: Partial<ExchangeConfig>) => {
    setExchanges((prev) =>
      prev.map((e) => (e.id === exchangeId ? { ...e, ...updates } : e))
    );
  };

  // 设置默认交易所
  const setDefaultExchange = (exchangeId: string) => {
    setExchanges((prev) =>
      prev.map((e) => ({
        ...e,
        isDefault: e.id === exchangeId,
      }))
    );
    message.success(t("default_exchange_set") || "默认交易所已设置");
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

      exchanges.forEach((exchange) => {
        const prefix = `exchange.${exchange.id}`;
        const exchangeName = exchange.name;

        batchConfigs.push(
          { key: `${prefix}.name`, value: exchange.name, name: 'exchange', description: `${exchangeName}交易所名称` },
          { key: `${prefix}.trading_mode`, value: exchange.tradingMode, name: 'exchange', description: `${exchangeName}交易模式` },
          { key: `${prefix}.quote_currency`, value: exchange.quoteCurrency, name: 'exchange', description: `${exchangeName}计价货币` },
          { key: `${prefix}.commission_rate`, value: String(exchange.commission), name: 'exchange', description: `${exchangeName}手续费率` },
          { key: `${prefix}.api_key`, value: exchange.apiKey || '', name: 'exchange', description: `${exchangeName}API Key` },
          { key: `${prefix}.api_secret`, value: exchange.apiSecret || '', name: 'exchange', description: `${exchangeName}API Secret` },
          { key: `${prefix}.proxy_enabled`, value: exchange.proxyEnabled ? '1' : '0', name: 'exchange', description: `${exchangeName}是否启用代理` },
          { key: `${prefix}.proxy_url`, value: exchange.proxyUrl || '', name: 'exchange', description: `${exchangeName}代理地址` },
          { key: `${prefix}.proxy_username`, value: exchange.proxyUsername || '', name: 'exchange', description: `${exchangeName}代理用户名` },
          { key: `${prefix}.proxy_password`, value: exchange.proxyPassword || '', name: 'exchange', description: `${exchangeName}代理密码` },
          { key: `${prefix}.is_enabled`, value: exchange.isEnabled ? '1' : '0', name: 'exchange', description: `${exchangeName}是否启用` },
          { key: `${prefix}.is_default`, value: exchange.isDefault ? '1' : '0', name: 'exchange', description: `${exchangeName}是否为默认` }
        );
      });

      // 使用批量更新接口保存所有配置（对象数组格式）
      await configApi.updateConfig(batchConfigs);

      message.success(t("config_saved") || "配置已保存");
    } catch (error) {
      console.error("保存配置失败:", error);
      message.error(t("save_failed") || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  // 重置配置
  const handleReset = () => {
    const initialExchanges = PRESET_EXCHANGES.map((preset, index) => ({
      ...preset,
      tradingMode: "spot" as const,
      quoteCurrency: "USDT",
      commission: 0.001,
      proxyEnabled: false,
      proxyUrl: "",
      proxyUsername: "",
      proxyPassword: "",
      apiKey: "",
      apiSecret: "",
      isEnabled: index === 0,
      isDefault: index === 0,
    }));
    setExchanges(initialExchanges);
    setSelectedExchangeId(initialExchanges[0]?.id || "");
    message.success(t("config_reset") || "配置已重置");
  };

  // 测试交易所连接
  const handleTestConnection = async () => {
    if (!selectedExchange) return;

    setTestingConnection(true);
    setTestResult(null);

    try {
      const result = await exchangeApi.testConnection({
        exchange_name: selectedExchange.id,
        api_key: selectedExchange.apiKey || undefined,
        secret_key: selectedExchange.apiSecret || undefined,
        proxy_url: selectedExchange.proxyEnabled ? selectedExchange.proxyUrl : undefined,
        trading_mode: selectedExchange.tradingMode,
      });

      setTestResult(result);

      if (result.success) {
        message.success(result.message);
      } else {
        message.error(result.message);
      }
    } catch (error: any) {
      const errorMsg = error.message || "测试连接失败";
      setTestResult({ success: false, message: errorMsg });
      message.error(errorMsg);
    } finally {
      setTestingConnection(false);
    }
  };

  return (
    <Spin spinning={loading} description={t("loading") || "加载中..."}>
      <div className="space-y-6">
        {/* 主内容区域 - 响应式布局 */}
        <div className="flex flex-col lg:flex-row gap-6">
          {/* 左侧交易所列表 */}
          <div className="w-full lg:w-64 flex-shrink-0">
            <div className="text-base font-medium mb-4 leading-8 h-8">{t("exchange_list") || "交易所列表"}</div>
            <Card className="shadow-sm" bodyStyle={{ padding: 8 }}>
              {/* 小屏幕：水平排列自动换行；大屏幕：垂直列表 */}
              <div className="flex flex-wrap gap-2 lg:flex-col lg:gap-1">
                {exchanges.map((exchange) => (
                  <div
                    key={exchange.id}
                    className={`cursor-pointer rounded-lg transition-all duration-200 px-3 py-2 flex items-center gap-2 lg:gap-3 lg:w-full ${
                      selectedExchangeId === exchange.id
                        ? "bg-gray-100 dark:bg-gray-800"
                        : "hover:bg-gray-50 dark:hover:bg-gray-900"
                    }`}
                    onClick={() => setSelectedExchangeId(exchange.id)}
                  >
                    <span className="w-8 h-8 flex items-center justify-center shrink-0">
                      {exchange.icon}
                    </span>
                    <div className="flex-1 min-w-0 hidden lg:block">
                      <div className="font-medium text-sm truncate">{exchange.name}</div>
                      <div className="text-xs text-gray-400 truncate">{exchange.id}</div>
                    </div>
                    <span className="lg:hidden font-medium text-sm">{exchange.name}</span>
                    {exchange.isEnabled && (
                      <span className="w-2 h-2 bg-green-500 rounded-full shrink-0"></span>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* 右侧配置区域 */}
          <div className="flex-1">
            {selectedExchange ? (
              <div className="space-y-4">
                {/* 交易所标题和默认设置 - 与左侧标题对齐 */}
                <div className="flex items-center justify-between h-8">
                  <div className="text-base font-medium">{selectedExchange.name}</div>
                  <Space>
                    <Text type="secondary" className="text-sm">
                      {t("default_exchange") || "默认交易所"}
                    </Text>
                    <Switch
                      checked={selectedExchange.isDefault}
                      onChange={(checked) => {
                        if (checked) setDefaultExchange(selectedExchange.id);
                      }}
                    />
                  </Space>
                </div>

                <Card className="shadow-sm">
                  <Form layout="vertical">
                    {/* 启用开关 */}
                    <Form.Item className="mb-4">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{t("enabled") || "启用"}</span>
                        <Switch
                          checked={selectedExchange.isEnabled}
                          onChange={(checked) =>
                            updateExchange(selectedExchange.id, { isEnabled: checked })
                          }
                        />
                      </div>
                    </Form.Item>

                    <Divider />

                    {/* 交易模式 */}
                    <Form.Item label={t("trading_mode") || "交易模式"}>
                      <Select
                        value={selectedExchange.tradingMode}
                        onChange={(value) =>
                          updateExchange(selectedExchange.id, { tradingMode: value })
                        }
                        options={TRADING_MODES}
                      />
                    </Form.Item>

                    {/* 计价货币 */}
                    <Form.Item label={t("quote_currency") || "计价货币"}>
                      <Select
                        value={selectedExchange.quoteCurrency}
                        onChange={(value) =>
                          updateExchange(selectedExchange.id, { quoteCurrency: value })
                        }
                        options={QUOTE_CURRENCIES}
                      />
                    </Form.Item>

                    {/* 手续费 */}
                    <Form.Item label={t("commission_rate") || "手续费率"}>
                      <InputNumber
                        value={selectedExchange.commission}
                        onChange={(value) =>
                          updateExchange(selectedExchange.id, { commission: value || 0 })
                        }
                        min={0}
                        max={1}
                        step={0.0001}
                        formatter={(value) => `${(Number(value) * 100).toFixed(2)}%`}
                        parser={(value) => Number(value?.replace("%", "")) / 100}
                        className="w-full"
                      />
                    </Form.Item>

                    <Divider />

                    {/* API Key */}
                    <Form.Item label={t("api_key") || "API Key"}>
                      <Input.Password
                        value={selectedExchange.apiKey}
                        onChange={(e) =>
                          updateExchange(selectedExchange.id, { apiKey: e.target.value })
                        }
                        placeholder={t("enter_api_key") || "请输入 API Key"}
                      />
                    </Form.Item>

                    {/* API Secret */}
                    <Form.Item label={t("api_secret") || "API Secret"}>
                      <Input.Password
                        value={selectedExchange.apiSecret}
                        onChange={(e) =>
                          updateExchange(selectedExchange.id, { apiSecret: e.target.value })
                        }
                        placeholder={t("enter_api_secret") || "请输入 API Secret"}
                      />
                    </Form.Item>

                    <Divider />

                    {/* 代理设置 */}
                    <Form.Item className="mb-4">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{t("proxy_enabled") || "启用代理"}</span>
                        <Switch
                          checked={selectedExchange.proxyEnabled}
                          onChange={(checked) =>
                            updateExchange(selectedExchange.id, { proxyEnabled: checked })
                          }
                        />
                      </div>
                    </Form.Item>

                    {selectedExchange.proxyEnabled && (
                      <>
                        <Form.Item label={t("proxy_url") || "代理地址"}>
                          <Input
                            value={selectedExchange.proxyUrl}
                            onChange={(e) =>
                              updateExchange(selectedExchange.id, { proxyUrl: e.target.value })
                            }
                            placeholder="http://proxy.example.com:8080"
                          />
                        </Form.Item>

                        <Form.Item label={t("proxy_username") || "代理用户名"}>
                          <Input
                            value={selectedExchange.proxyUsername}
                            onChange={(e) =>
                              updateExchange(selectedExchange.id, { proxyUsername: e.target.value })
                            }
                            placeholder={t("optional") || "可选"}
                          />
                        </Form.Item>

                        <Form.Item label={t("proxy_password") || "代理密码"}>
                          <Input.Password
                            value={selectedExchange.proxyPassword}
                            onChange={(e) =>
                              updateExchange(selectedExchange.id, { proxyPassword: e.target.value })
                            }
                            placeholder={t("optional") || "可选"}
                          />
                        </Form.Item>
                      </>
                    )}

                    <Divider />

                    {/* 测试连接按钮 */}
                    <Form.Item>
                      <Button
                        type="primary"
                        icon={<IconPlugConnected size={16} />}
                        onClick={handleTestConnection}
                        loading={testingConnection}
                        disabled={testingConnection}
                        block
                      >
                        {testingConnection ? t("testing") || "测试中..." : t("test_connection") || "测试连接"}
                      </Button>
                      <div className="text-xs text-gray-400 mt-1">
                        {t("test_connection_hint") || "测试交易所连接、API Key有效性及代理设置（不会产生实际交易）"}
                      </div>
                    </Form.Item>

                    {/* 测试结果 */}
                    {testResult && (
                      <Form.Item>
                        <div className={`p-3 rounded-lg ${testResult.success ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'}`}>
                          <div className="flex items-center gap-2 mb-2">
                            {testResult.success ? (
                              <span className="text-green-500">✓</span>
                            ) : (
                              <span className="text-red-500">✗</span>
                            )}
                            <span className={testResult.success ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}>
                              {testResult.message}
                            </span>
                            {testResult.response_time_ms && (
                              <span className="text-xs text-gray-500">({testResult.response_time_ms}ms)</span>
                            )}
                          </div>
                          {testResult.details?.tests && (
                            <div className="text-xs space-y-1 mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                              <div className="flex justify-between">
                                <span className="text-gray-500">{t("network") || "网络连接"}:</span>
                                <span className={testResult.details.tests.ping?.success ? 'text-green-600' : 'text-red-600'}>
                                  {testResult.details.tests.ping?.success ? (t("success") || "通过") : (t("failed") || "失败")}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-gray-500">{t("market_data") || "市场数据"}:</span>
                                <span className={testResult.details.tests.market_data?.success ? 'text-green-600' : 'text-red-600'}>
                                  {testResult.details.tests.market_data?.success ? (t("success") || "正常") : (t("failed") || "异常")}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-gray-500">{t("websocket") || "WebSocket"}:</span>
                                <span className={
                                  testResult.details.tests.websocket?.skipped
                                    ? 'text-gray-500'
                                    : testResult.details.tests.websocket?.success
                                      ? 'text-green-600'
                                      : 'text-red-600'
                                }>
                                  {testResult.details.tests.websocket?.skipped
                                    ? (t("not_tested") || "未测试")
                                    : testResult.details.tests.websocket?.success
                                      ? (t("success") || "通过")
                                      : (t("failed") || "失败")}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-gray-500">{t("authentication") || "API认证"}:</span>
                                <span className={
                                  testResult.details.tests.authentication?.skipped
                                    ? 'text-gray-500'
                                    : testResult.details.tests.authentication?.success
                                      ? 'text-green-600'
                                      : 'text-red-600'
                                }>
                                  {testResult.details.tests.authentication?.skipped
                                    ? (t("not_tested") || "未测试")
                                    : testResult.details.tests.authentication?.success
                                      ? (t("success") || "通过")
                                      : (t("failed") || "失败")}
                                </span>
                              </div>
                            </div>
                          )}
                        </div>
                      </Form.Item>
                    )}
                  </Form>
                </Card>
              </div>
            ) : (
              <Card className="shadow-sm">
                <div className="text-center py-12 text-gray-500">
                  <IconBuildingBank size="48" className="mx-auto mb-4 opacity-50" />
                  <p>{t("select_exchange") || "请选择一个交易所"}</p>
                </div>
              </Card>
            )}
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex justify-end gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Space>
            <Button onClick={handleReset} disabled={saving || isGuest}>
              {t("reset") || "重置"}
            </Button>
            <Button type="primary" onClick={handleSave} loading={saving} disabled={isGuest}>
              {t("save") || "保存"}
            </Button>
          </Space>
        </div>
      </div>
    </Spin>
  );
};

export default ExchangeSettingsPage;
