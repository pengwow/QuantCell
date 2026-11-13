/**
 * 指标信号提醒 Tab（P2-07）
 *
 * 在指标编辑器内展示/管理当前指标的信���提醒规则：
 * 规则列表（启停、测试发送、删除）+ 新建规则弹窗。
 * 条件语义与后端 indicators/alerts.py 对齐：gt/lt 比较最新值，cross_up/cross_down 比较最近两根。
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  BellOutlined,
  EyeOutlined,
  SendOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  theme,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { indicatorApi, notificationApi } from '../api';
import { dataApi } from '../api/dataApi';

interface AlertRule {
  id: number;
  indicator_id: number;
  /** 系统内置指标标识（builtin_alerts.py 的 key），indicator_id=0 时由它指向指标 */
  builtin_id?: string | null;
  name: string;
  symbol: string;
  period: string;
  market_type: string;
  crypto_type: string;
  plot_name: string;
  op: string;
  threshold: number;
  channels: string[];
  frequency: number;
  enabled: boolean;
  last_fired_at: string | null;
}

const OP_LABEL_KEYS: Record<string, string> = {
  gt: 'indicator.alertOpGt',
  lt: 'indicator.alertOpLt',
  cross_up: 'indicator.alertOpCrossUp',
  cross_down: 'indicator.alertOpCrossDown',
};

/** 渠道展示名 i18n key（websocket 为站内推送，不在系统通知配置里） */
const CHANNEL_LABEL_KEYS: Record<string, string> = {
  websocket: 'indicator.channelWs',
  email: 'indicator.channelEmail',
  wecom: 'indicator.channelWecom',
  feishu: 'indicator.channelFeishu',
};

/** 后端 reason_code -> 前端文案 key（detail 作为插值参数） */
const CHANNEL_REASON_KEYS: Record<string, string> = {
  not_enabled: 'indicator.channelReasonNotEnabled',
  config_missing: 'indicator.channelReasonConfigMissing',
  unreachable: 'indicator.channelReasonUnreachable',
};

interface ChannelStatus {
  id: string;
  valid: boolean;
  reason_code?: string;
  detail?: string;
}

/** 提醒间隔的表单时间单位 → 分钟换算（后端去重粒度为分钟，最小 1 分钟） */
const UNIT_TO_MINUTES: Record<string, number> = {
  second: 1 / 60,
  minute: 1,
  hour: 60,
  day: 1440,
};

/** 预演结果：evaluation 为真实评估值，preview 为消息文案；send_result 仅模拟发送时存在 */
interface AlertPreviewData {
  evaluation: { triggered: boolean; value?: number; error?: string };
  preview: { title: string; content: string; channels: string[] };
  send_result?: {
    success: boolean;
    error?: string;
    channels?: Record<string, { success: boolean; error?: string }>;
  };
}

interface IndicatorAlertTabProps {
  /** 自定义指标 ID（与 builtinId 二选一；指标编辑器入口只传它） */
  indicatorId?: number;
  /** 系统内置指标标识（信号提醒直达弹窗入口） */
  builtinId?: string;
  /** 弹窗外层当前选中的指标名称，作为新建规则名称的默认值 */
  indicatorName?: string;
  /** 内置指标的输出线列表，plot_name 变为下拉选择 */
  builtinPlots?: string[];
  /** 图表当前交易对，作为新建规则的默认 symbol */
  defaultSymbol?: string;
  /** 图表当前周期，作为新建规则的默认 period */
  defaultPeriod?: string;
}

const IndicatorAlertTab: React.FC<IndicatorAlertTabProps> = ({
  indicatorId,
  builtinId,
  indicatorName = '',
  builtinPlots,
  defaultSymbol,
  defaultPeriod,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();

  const [rules, setRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  // 提醒间隔单位（useWatch 保证改单位时校验规则立即使用新值换算）
  const frequencyUnit = (Form.useWatch('frequency_unit', form) as string | undefined) ?? 'minute';
  // 交易对可搜索下拉的数据源（复用图表交易对接口）
  const [symbolOptions, setSymbolOptions] = useState<string[]>([]);

  // 通知渠道可用性状态（无效项置灰 + 原因提示 + 去配置入口)
  const [channelStatuses, setChannelStatuses] = useState<ChannelStatus[]>([]);
  const [channelChecking, setChannelChecking] = useState(false);
  // 预演（预览/模拟发送）状态：previewData 为弹窗内展示的消息预览
  const [previewData, setPreviewData] = useState<AlertPreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState<'none' | 'preview' | 'send'>('none');
  const { token } = theme.useToken();

  const loadChannelStatus = useCallback(async () => {
    setChannelChecking(true);
    try {
      const res = await notificationApi.getChannels();
      const remote = (res?.channels ?? []) as {
        id: string;
        enabled: boolean;
        config: Record<string, unknown>;
      }[];
      const payload = remote
        .filter((c) => CHANNEL_LABEL_KEYS[c.id])
        .map((c) => ({
          id: c.id,
          enabled: Boolean(c.enabled),
          config: c.config ?? {},
        }));
      let statuses: ChannelStatus[] = [{ id: 'websocket', valid: true }];
      try {
        // 后端校验启用/配置完整性/连通性（不发真消息）；接口异常时退化为全部可选，不阻塞建规则
        const vr = await notificationApi.validateChannels(payload);
        statuses = [...statuses, ...(vr?.results ?? [])];
      } catch {
        statuses = [...statuses, ...payload.map((c) => ({ id: c.id, valid: true }))];
      }
      setChannelStatuses(statuses);
    } catch {
      setChannelStatuses([{ id: 'websocket', valid: true }]);
    } finally {
      setChannelChecking(false);
    }
  }, []);

  // 弹窗打开即校验一次；从「去配置」页返回（窗口重新聚焦）时自动刷新状态
  useEffect(() => {
    if (!modalOpen) return undefined;
    void loadChannelStatus();
    // 交易对列表：拉一次热门交易对供搜索选择；失败不阻塞（保留手输数据的默认值场景）
    dataApi
      .getProducts({ filter: '', limit: 100 })
      .then((res) => {
        setSymbolOptions((res?.products ?? []).map((p) => p.symbol));
      })
      .catch(() => setSymbolOptions([]));
    const onFocus = () => void loadChannelStatus();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [modalOpen, loadChannelStatus]);

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      // 内置指标规则按 builtin_id 过滤（indicator_id 恒为 0），自定义按 id 过滤
      const data = await indicatorApi.listAlertRules(indicatorId, builtinId);
      setRules(Array.isArray(data) ? data : []);
    } catch {
      message.error(t('indicator.alertLoadFailed'));
    } finally {
      setLoading(false);
    }
  }, [indicatorId, builtinId, message, t]);

  useEffect(() => {
    if (indicatorId || builtinId) {
      loadRules();
    }
  }, [indicatorId, builtinId, loadRules]);

  const handleToggle = async (rule: AlertRule, checked: boolean) => {
    try {
      await indicatorApi.updateAlertRule(rule.id, { enabled: checked });
      message.success(checked ? t('indicator.alertEnabled') : t('indicator.alertDisabled'));
      loadRules();
    } catch {
      message.error(t('indicator.alertSaveFailed'));
    }
  };

  const handleDelete = async (rule: AlertRule) => {
    try {
      await indicatorApi.deleteAlertRule(rule.id);
      message.success(t('indicator.alertDeleted'));
      loadRules();
    } catch {
      message.error(t('indicator.alertSaveFailed'));
    }
  };

  const handleTestSend = async (rule: AlertRule) => {
    try {
      const result = await indicatorApi.testAlertRule(rule.id);
      const evaluation = (result as { evaluation?: { triggered?: boolean } })?.evaluation;
      message.success(
        evaluation?.triggered ? t('indicator.alertTestFired') : t('indicator.alertTestOk'),
      );
    } catch {
      message.error(t('indicator.alertSaveFailed'));
    }
  };

  /**
   * 表单值 → 创建/预演请求体（两处共用，保证口径一致）：
   * - 频率（值+单位）换算为分钟（后端契约单位为分钟）
   * - 内置指标规则带 builtin_id，indicator_id 置 0；自定义规则只带 indicator_id
   */
  const buildPayload = (values: Record<string, unknown>) => {
    const { frequency_value, frequency_unit, ...rest } = values;
    const unit = (frequency_unit as string) ?? 'minute';
    const minutes = Math.round(Number(frequency_value ?? 0) * UNIT_TO_MINUTES[unit]);
    return {
      ...rest,
      // 换算结果由表单 validator 保证 >= 1 分钟；Math.round 只兜浮点误差
      frequency: minutes,
      indicator_id: builtinId ? 0 : indicatorId,
      market_type: 'crypto',
      crypto_type: 'spot',
      ...(builtinId ? { builtin_id: builtinId } : {}),
    };
  };

  /** 预演：send=false 仅生成消息预览；send=true 按所选渠道真实发送（标题带 [测试] 前缀） */
  const handlePreview = async (send: boolean) => {
    let values: Record<string, unknown>;
    try {
      values = await form.validateFields();
    } catch {
      // 必填项未填：表单项内已展示错误提示
      return;
    }
    setPreviewLoading(send ? 'send' : 'preview');
    try {
      // api 层已负责包装为 { rule, send }，这里只传 rule 负载
      const data = await indicatorApi.previewAlertRule(buildPayload(values), send);
      const preview = data as AlertPreviewData;
      setPreviewData(preview);
      if (send && preview.send_result?.success) {
        message.success(t('indicator.alertSimulateSent'));
      }
    } catch {
      message.error(t('indicator.alertPreviewFailed'));
    } finally {
      setPreviewLoading('none');
    }
  };

  const handleCreate = async () => {
    let values: Record<string, unknown>;
    try {
      values = await form.validateFields();
    } catch {
      // 校验失败：表单项内已展示错误提示，阻断提交即可
      return;
    }
    setSaving(true);
    try {
      await indicatorApi.createAlertRule(buildPayload(values));
      message.success(t('indicator.alertSaved'));
      setModalOpen(false);
      setPreviewData(null);
      form.resetFields();
      loadRules();
    } catch {
      message.error(t('indicator.alertSaveFailed'));
    } finally {
      setSaving(false);
    }
  };

  /** 频率（分钟，后端契约单位）→ 展示文本：整小时/整日向上归约，其余按分钟展示 */
  const formatFrequency = (minutes: number) => {
    if (minutes == null) return '-';
    if (minutes % 1440 === 0) return `${minutes / 1440} ${t('indicator.alertFreqDays')}`;
    if (minutes % 60 === 0) return `${minutes / 60} ${t('indicator.alertFreqHours')}`;
    return t('indicator.alertFrequencyUnit', { minutes });
  };

  const columns = [
    {
      title: t('indicator.alertName'),
      dataIndex: 'name',
      render: (name: string) => name || '-',
    },
    {
      title: t('indicator.alertCondition'),
      render: (_: unknown, rule: AlertRule) =>
        `${rule.plot_name || t('indicator.alertDefaultPlot')} ${t(OP_LABEL_KEYS[rule.op] ?? rule.op)} ${rule.threshold}`,
    },
    {
      title: t('indicator.alertTarget'),
      render: (_: unknown, rule: AlertRule) => `${rule.symbol} · ${rule.period}`,
    },
    {
      title: t('indicator.alertChannels'),
      dataIndex: 'channels',
      render: (channels: string[]) => (channels || []).join(', '),
    },
    {
      title: t('indicator.alertFrequency'),
      dataIndex: 'frequency',
      render: (frequency: number) => formatFrequency(frequency),
    },
    {
      title: t('indicator.alertLastFired'),
      dataIndex: 'last_fired_at',
      render: (time: string | null) =>
        time ? new Date(time).toLocaleString() : t('indicator.alertNever'),
    },
    {
      title: t('indicator.alertEnabled'),
      dataIndex: 'enabled',
      render: (enabled: boolean, rule: AlertRule) => (
        <Switch size="small" checked={enabled} onChange={(checked) => handleToggle(rule, checked)} />
      ),
    },
    {
      title: t('indicator.alertActions'),
      key: 'actions',
      width: 140,
      render: (_: unknown, rule: AlertRule) => (
        <Space size="small">
          <Tooltip title={t('indicator.alertTestSend')}>
            <Button size="small" icon={<SendOutlined />} onClick={() => handleTestSend(rule)} />
          </Tooltip>
          <Button size="small" danger onClick={() => handleDelete(rule)}>
            {t('common.delete')}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="indicator-alert-container">
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title={t('indicator.alertsTip')}
      />
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button type="primary" icon={<BellOutlined />} onClick={() => setModalOpen(true)}>
          {t('indicator.alertAdd')}
        </Button>
      </div>
      <Table
        size="small"
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rules}
        pagination={false}
        locale={{ emptyText: t('indicator.alertsEmpty') }}
      />

      <Modal
        title={t('indicator.alertAddTitle')}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setPreviewData(null);
        }}
        // 底部额外提供「预览/模拟发送」：不落库直接预演，配置时即可确认消息效果
        footer={[
          <Button
            key="preview"
            icon={<EyeOutlined />}
            loading={previewLoading === 'preview'}
            onClick={() => handlePreview(false)}
          >
            {t('indicator.alertPreview')}
          </Button>,
          <Button
            key="simulate"
            icon={<SendOutlined />}
            loading={previewLoading === 'send'}
            onClick={() => handlePreview(true)}
          >
            {t('indicator.alertSimulateSend')}
          </Button>,
          <Button key="cancel" onClick={() => setModalOpen(false)}>
            {t('common.cancel')}
          </Button>,
          <Button key="save" type="primary" loading={saving} onClick={handleCreate}>
            {t('common.save')}
          </Button>,
        ]}
        destroyOnHidden
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex', width: '100%' }}>
        <Form
          form={form}
          layout="vertical"
          // 默认值对齐弹窗外层：规则名=当前指标名、交易对/周期=图表当前值；间隔默认 30 分钟
          initialValues={{
            name: indicatorName,
            symbol: defaultSymbol ?? '',
            period: defaultPeriod || '1h',
            op: 'gt',
            threshold: 0,
            frequency_value: 30,
            frequency_unit: 'minute',
            channels: ['websocket'],
          }}
        >
          <Form.Item name="name" label={t('indicator.alertName')}>
            <Input placeholder={t('indicator.alertNamePlaceholder')} maxLength={100} />
          </Form.Item>
          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item
              name="symbol"
              label={t('indicator.alertSymbol')}
              rules={[{ required: true, message: t('indicator.alertSymbolRequired') }]}
              style={{ width: 260 }}
            >
              {/* 可搜索下拉：输入关键词实时匹配交易对；列表拉取失败时选项为空，但仍展示默认值 */}
              <Select
                showSearch
                placeholder={t('indicator.alertSymbolPlaceholder')}
                optionFilterProp="value"
                options={symbolOptions.map((s) => ({ value: s, label: s }))}
              />
            </Form.Item>
            <Form.Item name="period" label={t('indicator.alertPeriod')} style={{ width: 120 }}>
              <Select
                // 与图表周期条（PERIOD_BAR_ITEMS）取值范围对齐
                options={['1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', '1w', '1M', '1y'].map(
                  (p) => ({ value: p, label: p }),
                )}
              />
            </Form.Item>
          </Space>
          <Space size="middle" style={{ display: 'flex' }} align="center">
            <Form.Item name="plot_name" label={t('indicator.alertPlot')} style={{ width: 160 }}>
              {/* 内置指标输出线已知 → 下拉选线；自定义指标线名由用户定义 → 保留手输 */}
              {builtinPlots && builtinPlots.length > 0 ? (
                <Select
                  allowClear
                  placeholder={t('indicator.alertDefaultPlot')}
                  options={builtinPlots.map((p) => ({ value: p, label: p }))}
                />
              ) : (
                <Input maxLength={100} placeholder={t('indicator.alertDefaultPlot')} />
              )}
            </Form.Item>
            <Form.Item name="op" label={t('indicator.alertOp')} style={{ width: 130 }}>
              <Select
                options={[
                  { value: 'gt', label: t('indicator.alertOpGt') },
                  { value: 'lt', label: t('indicator.alertOpLt') },
                  { value: 'cross_up', label: t('indicator.alertOpCrossUp') },
                  { value: 'cross_down', label: t('indicator.alertOpCrossDown') },
                ]}
              />
            </Form.Item>
            <Form.Item
              name="threshold"
              label={t('indicator.alertThreshold')}
              style={{ width: 140 }}
            >
              <InputNumber style={{ width: '100%' }} step="any" />
            </Form.Item>
          </Space>
          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item
              name="channels"
              label={t('indicator.alertChannels')}
              rules={[{ required: true, message: t('indicator.alertChannelsRequired') }]}
              // 与同行「提醒间隔」组合控件（170）合计约 416，保证不超出弹窗内容宽度
              style={{ width: 230 }}
            >
              <Select
                mode="multiple"
                style={{ width: '100%' }}
                loading={channelChecking}
                optionFilterProp="label"
                // 每次展开都重新校验，保证读到系统通知配置的最新状态
                onOpenChange={(open) => open && void loadChannelStatus()}
                options={Object.entries(CHANNEL_LABEL_KEYS).map(([id, key]) => {
                  const status = channelStatuses.find((s) => s.id === id);
                  return {
                    value: id,
                    label: t(key),
                    disabled: status ? !status.valid : false,
                  };
                })}
                optionRender={(option) => {
                  const status = channelStatuses.find((s) => s.id === option.value);
                  if (!status || status.valid) {
                    return <span>{option.label}</span>;
                  }
                  // 无效渠道：置灰 + 失效原因 hover 提示 + 快捷跳转通知配置页（新标签页，保留当前编辑状态）
                  const reason = t(
                    CHANNEL_REASON_KEYS[status.reason_code ?? ''] ?? 'indicator.channelReasonUnknown',
                    { detail: status.detail ?? '' },
                  );
                  return (
                    <Tooltip title={reason}>
                      <Flex
                        align="center"
                        justify="space-between"
                        gap={8}
                        style={{ width: '100%' }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <span style={{ color: token.colorTextDisabled }}>{option.label}</span>
                        <Button
                          size="small"
                          type="link"
                          icon={<SettingOutlined />}
                          onClick={() => window.open(`${window.location.origin}/setting/notifications`, '_blank')}
                        >
                          {t('indicator.channelGoConfig')}
                        </Button>
                      </Flex>
                    </Tooltip>
                  );
                }}
              />
            </Form.Item>
            <Form.Item
              label={t('indicator.alertFrequency')}
              tooltip={t('indicator.alertFrequencyTip')}
            >
              {/* 数值 + 单位组合控件（秒/分钟/小时/天）；换算成分钟由 buildPayload 统一处理 */}
              <Space.Compact style={{ width: 170 }}>
                <Form.Item
                  name="frequency_value"
                  noStyle
                  rules={[
                    { required: true, message: t('indicator.alertFrequencyRequired') },
                    {
                      // 后端按分钟粒度去重：秒类取值换算后需 ≥ 1 分钟
                      validator: (_, value) =>
                        Number(value ?? 0) * UNIT_TO_MINUTES[frequencyUnit] >= 1
                          ? Promise.resolve()
                          : Promise.reject(new Error(t('indicator.alertFrequencyMin'))),
                    },
                  ]}
                >
                  <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="frequency_unit" noStyle>
                  <Select
                    style={{ width: 92 }}
                    options={[
                      { value: 'second', label: t('indicator.alertFreqUnitSecond') },
                      { value: 'minute', label: t('indicator.alertFreqUnitMinute') },
                      { value: 'hour', label: t('indicator.alertFreqUnitHour') },
                      { value: 'day', label: t('indicator.alertFreqUnitDay') },
                    ]}
                  />
                </Form.Item>
              </Space.Compact>
            </Form.Item>
          </Space>
        </Form>
        {previewData && (
          // 模拟通知样式：标题+触发状态+正文+渠道；文案与真实触发同源（后端同一构造函数），所见即所得
          <div
            style={{
              border: `1px dashed ${token.colorBorder}`,
              borderRadius: token.borderRadiusLG,
              padding: 16,
            }}
          >
            <Flex justify="space-between" align="center" gap={8}>
              <span style={{ fontWeight: 600 }}>{previewData.preview.title}</span>
              <Tag color={previewData.evaluation.triggered ? 'green' : 'default'}>
                {previewData.evaluation.triggered
                  ? t('indicator.alertPreviewTriggered')
                  : t('indicator.alertPreviewNotTriggered')}
              </Tag>
            </Flex>
            <div style={{ marginTop: 8, whiteSpace: 'pre-wrap' }}>{previewData.preview.content}</div>
            <Flex gap={4} wrap="wrap" style={{ marginTop: 8 }}>
              {previewData.preview.channels.map((c) => (
                <Tag key={c}>{t(CHANNEL_LABEL_KEYS[c] ?? c)}</Tag>
              ))}
            </Flex>
            {previewData.evaluation.error && (
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 8 }}
                title={t('indicator.alertEvaluateError', { error: previewData.evaluation.error })}
              />
            )}
            {previewData.send_result?.channels && (
              <Flex gap={4} wrap="wrap" style={{ marginTop: 8 }}>
                {Object.entries(previewData.send_result.channels).map(([name, r]) => (
                  <Tag key={name} color={r.success ? 'green' : 'red'}>
                    {`${t(CHANNEL_LABEL_KEYS[name] ?? name)}: ${
                      r.success ? t('indicator.alertSendOk') : (r.error ?? t('indicator.alertSendFail'))
                    }`}
                  </Tag>
                ))}
              </Flex>
            )}
            {previewData.send_result && !previewData.send_result.success && (
              <Alert
                type="error"
                showIcon
                style={{ marginTop: 8 }}
                title={previewData.send_result.error ?? t('indicator.alertSimulateFailed')}
              />
            )}
          </div>
        )}
        </Space>
      </Modal>
    </div>
  );
};

export default IndicatorAlertTab;
