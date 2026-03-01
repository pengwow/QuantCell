/**
 * 交易所设置页面
 * 功能：管理交易所配置，包括交易模式、计价货币、手续费、代理设置等
 * 参考：ModelSettingsPage 和 SystemConfigPage
 */
import { useState, useEffect } from "react";
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
} from "@tabler/icons-react";
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

const PRESET_EXCHANGES: PresetExchange[] = [
  { id: "binance", name: "币安", icon: EXCHANGE_ICONS.binance },
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
const TRADING_MODES = [
  { value: "spot", label: "现货" },
  { value: "futures", label: "合约" },
  { value: "margin", label: "杠杆" },
];

const ExchangeSettingsPage = () => {
  const { t } = useTranslation();
  const [exchanges, setExchanges] = useState<ExchangeConfig[]>([]);
  const [selectedExchangeId, setSelectedExchangeId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // 从localStorage加载配置
  useEffect(() => {
    setLoading(true);
    const savedExchanges = localStorage.getItem("exchange_configs");
    if (savedExchanges) {
      const parsed = JSON.parse(savedExchanges);
      // 合并新交易所
      const mergedExchanges = PRESET_EXCHANGES.map((preset) => {
        const existing = parsed.find((e: ExchangeConfig) => e.id === preset.id);
        if (existing) {
          return { ...existing, name: preset.name, icon: preset.icon };
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
        };
      });
      setExchanges(mergedExchanges);
      setSelectedExchangeId(mergedExchanges[0]?.id || "");
    } else {
      // 初始化默认配置
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
    }
    setLoading(false);
  }, []);

  // 保存到localStorage
  useEffect(() => {
    if (exchanges.length > 0) {
      localStorage.setItem("exchange_configs", JSON.stringify(exchanges));
    }
  }, [exchanges]);

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

  // 保存配置
  const handleSave = async () => {
    setSaving(true);
    try {
      localStorage.setItem("exchange_configs", JSON.stringify(exchanges));
      message.success(t("config_saved") || "配置已保存");
    } catch (error) {
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

  return (
    <Spin spinning={loading} tip={t("loading") || "加载中..."}>
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
            <Button onClick={handleReset} disabled={saving}>
              {t("reset") || "重置"}
            </Button>
            <Button type="primary" onClick={handleSave} loading={saving}>
              {t("save") || "保存"}
            </Button>
          </Space>
        </div>
      </div>
    </Spin>
  );
};

export default ExchangeSettingsPage;
