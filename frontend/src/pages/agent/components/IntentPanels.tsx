/**
 * 意图专属渲染组件
 * 根据不同的意图类型展示不同的 UI 面板
 */

import React from 'react';
import {
  Card,
  Tag,
  Button,
  Space,
  Typography,
  Progress,
  Table,
  Collapse,
  theme,
} from 'antd';
import {
  CodeOutlined,
  BarChartOutlined,
  SafetyOutlined,
  ShoppingCartOutlined,
  DatabaseOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import type { IntentAction } from '../store/agentStore';
import { useQuantColors } from '@/utils/colors';
import { useTranslation } from 'react-i18next';

const { Text, Title } = Typography;
const { Panel } = Collapse;

interface IntentPanelProps {
  intent: string;
  roleName: string;
  content: string;
  structuredData: Record<string, unknown>;
  actions: IntentAction[];
  onAction: (actionType: string) => void;
}

// 将结构化数据中的值安全转换为数字，非数字返回 0
const toNumber = (value: unknown): number => {
  const num = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(num) ? num : 0;
};

// 角色主题颜色映射
// ponytail: bgColor 和 color 都从 antd token 动态派生，跟随主题切换。
// icon 保持为静态常量（React 元素引用稳定，不触发重渲染）。
const ROLE_ICONS: Record<string, React.ReactNode> = {
  '策略工程师': <CodeOutlined />,
  '回测分析师': <BarChartOutlined />,
  '风控顾问': <SafetyOutlined />,
  '交易助手': <ShoppingCartOutlined />,
  '数据分析师': <DatabaseOutlined />,
  'AI 训练师': <PlayCircleOutlined />,
  'AI 助手': <CodeOutlined />,
};

export interface RoleTheme {
  color: string;
  bgColor: string;
  icon: React.ReactNode;
}

/** 从 antd token 派生角色主题 — 颜色跟随主题切换 */
function deriveRoleTheme(roleName: string, token: ReturnType<typeof theme.useToken>['token']): RoleTheme {
  const fallbackIcon = ROLE_ICONS['AI 助手'];
  const icon = ROLE_ICONS[roleName] ?? fallbackIcon;

  // bgColor 映射到 antd token 的 colorXxxBg 语义色（O2：antd token 恒有定义，无需 hex fallback）
  const bgMap: Record<string, { color: string; bg: string }> = {
    '策略工程师': { color: token.colorInfo,        bg: token.colorInfoBg },
    '回测分析师': { color: token.colorSuccess,     bg: token.colorSuccessBg },
    '风控顾问':   { color: token.colorWarning,     bg: token.colorWarningBg },
    '交易助手':   { color: '#722ed1',              bg: '#f9f0ff' },  // O2: 特殊装饰色，保留（紫色/粉色行业配色）
    '数据分析师': { color: token.colorInfo,        bg: '#e6fffb' },  // O2: 特殊装饰色，保留（cyan bg 无对应 token）
    'AI 训练师':  { color: '#eb2f96',              bg: '#fff0f6' },  // O2: 特殊装饰色，保留（粉色行业配色）
    'AI 助手':    { color: token.colorInfo,        bg: token.colorInfoBg },
  };
  const pair = bgMap[roleName] ?? bgMap['AI 助手'];
  return { color: pair.color, bgColor: pair.bg, icon };
}

/** React hook：跟随主题切换自动更新的角色主题 */
function useRoleTheme(roleName: string): RoleTheme {
  const { token } = theme.useToken();
  return deriveRoleTheme(roleName, token);
}

// 策略代码面板
export const StrategyCodePanel: React.FC<IntentPanelProps> = ({
  roleName,
  structuredData,
  actions,
  onAction,
}) => {
  const theme = useRoleTheme(roleName);
  const { t } = useTranslation();
  const codeText = typeof structuredData.code === 'string' ? structuredData.code : '';
  const strategyName = typeof structuredData.strategy_name === 'string' ? structuredData.strategy_name : '';

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>{t('agent_panel_strategy_code')}</span>
        </Space>
      }
      style={{ marginTop: 12, backgroundColor: theme.bgColor, borderColor: theme.color }}
    >
      {codeText && (
        <Collapse defaultActiveKey={['1']}>
          <Panel header={t('agent_panel_strategy_code')} key="1">
            <pre style={{
              background: '#1f1f1f', // O2: 特殊装饰色，保留（终端风代码块，亮暗恒深底）
              color: '#f0f0f0',
              padding: 16,
              borderRadius: 8,
              overflowX: 'auto',
              fontSize: 13,
            }}>
              {codeText}
            </pre>
          </Panel>
        </Collapse>
      )}

      {strategyName && (
        <div style={{ marginTop: 12 }}>
          <Text strong>{t('agent_strategy_name_label')}</Text>
          <Tag color={theme.color}>{strategyName}</Tag>
        </div>
      )}

      {actions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Title level={5}>{t('agent_quick_actions')}</Title>
          <Space wrap>
            {actions.map((action) => (
              <Button
                key={action.type}
                type="primary"
                ghost
                size="small"
                onClick={() => onAction(action.type)}
              >
                {action.label}
              </Button>
            ))}
          </Space>
        </div>
      )}
    </Card>
  );
};

// 回测结果面板
export const BacktestResultPanel: React.FC<IntentPanelProps> = ({
  roleName,
  structuredData,
  actions,
  onAction,
}) => {
  const theme = useRoleTheme(roleName);
  const quant = useQuantColors();
  const { t } = useTranslation();

  // 收益/夏普/回撤等指标色全部走量化语义色（O2），紫色为行业惯例强调色保留
  // key 为后端 structuredData 的中文字段名（数据契约不可改），label 为 i18n 显示文案
  const metrics = [
    { key: '年化收益率', label: t('annual_return'), value: structuredData['年化收益率'], suffix: '%', color: quant.positive },
    { key: '夏普比率', label: t('sharpe_ratio'), value: structuredData['夏普比率'], suffix: '', color: quant.info },
    { key: '最大回撤', label: t('max_drawdown'), value: structuredData['最大回撤'], suffix: '%', color: quant.negative },
    { key: '总收益', label: t('total_profit'), value: structuredData['总收益'], suffix: '%', color: quant.positive },
    { key: '胜率', label: t('win_rate'), value: structuredData['胜率'], suffix: '%', color: '#722ed1' }, // O2: 特殊装饰色，保留
  ].filter((m) => m.value !== undefined);

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>{t('agent_panel_backtest_result')}</span>
        </Space>
      }
      style={{ marginTop: 12, backgroundColor: theme.bgColor, borderColor: theme.color }}
    >
      {metrics.length > 0 ? (
        <div>
          {metrics.map((metric) => {
            const metricValue = toNumber(metric.value);
            return (
              <div key={metric.key} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                  <Text>{metric.label}</Text>
                  <Text strong style={{ color: metric.color }}>
                    {String(metric.value)}{metric.suffix}
                  </Text>
                </div>
                {metric.key === '最大回撤' && (
                  <Progress
                    percent={Math.abs(metricValue)}
                    status={metricValue > 20 ? 'exception' : metricValue > 10 ? 'active' : 'success'}
                    strokeColor={metric.color}
                    style={{ marginTop: 4 }}
                  />
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <Text type="secondary">{t('agent_no_backtest_metrics')}</Text>
      )}

      {actions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Title level={5}>{t('agent_analysis_actions')}</Title>
          <Space wrap>
            {actions.map((action) => (
              <Button
                key={action.type}
                type="primary"
                ghost
                size="small"
                onClick={() => onAction(action.type)}
              >
                {action.label}
              </Button>
            ))}
          </Space>
        </div>
      )}
    </Card>
  );
};

// 风险评估面板
export const RiskAssessmentPanel: React.FC<IntentPanelProps> = ({
  roleName,
  structuredData,
  actions,
  onAction,
}) => {
  const theme = useRoleTheme(roleName);
  const quant = useQuantColors();
  const { t } = useTranslation();

  // 后端 risk_level 的值是中文（低风险/中风险/高风险），作为数据值参与映射，不可 i18n
  const riskLevel = typeof structuredData.risk_level === 'string' ? structuredData.risk_level : t('agent_unknown');
  const riskColors: Record<string, string> = {
    '低风险': quant.positive,
    '中风险': quant.warning,
    '高风险': quant.negative,
  };

  const riskInfo = [
    { label: t('agent_risk_level'), value: riskLevel, color: riskColors[riskLevel] || quant.neutral },
    { label: t('agent_assess_time'), value: new Date().toLocaleString(), color: quant.info },
  ];

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>{t('agent_panel_risk_assessment')}</span>
        </Space>
      }
      style={{ marginTop: 12, backgroundColor: theme.bgColor, borderColor: theme.color }}
    >
      <div style={{ marginBottom: 16 }}>
        <Space orientation="vertical" size="middle">
          {riskInfo.map((item) => (
            <Space key={item.label}>
              <Text>{item.label}：</Text>
              <Tag color={item.color}>{item.value}</Tag>
            </Space>
          ))}
        </Space>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Title level={5}>{t('agent_risk_warning_title')}</Title>
        <div style={{ padding: 12, background: 'color-mix(in srgb, var(--tw-color-error) 8%, var(--tw-color-background))', borderRadius: 8 }}>
          <Text type="danger">
            {t('agent_risk_disclaimer')}
          </Text>
        </div>
      </div>

      {actions.length > 0 && (
        <div>
          <Title level={5}>{t('agent_risk_actions')}</Title>
          <Space wrap>
            {actions.map((action) => (
              <Button
                key={action.type}
                type="primary"
                ghost
                size="small"
                onClick={() => onAction(action.type)}
              >
                {action.label}
              </Button>
            ))}
          </Space>
        </div>
      )}
    </Card>
  );
};

// 交易决策面板
export const TradingDecisionPanel: React.FC<IntentPanelProps> = ({
  roleName,
  structuredData,
  actions,
  onAction,
}) => {
  const theme = useRoleTheme(roleName);
  const quant = useQuantColors();
  const { t } = useTranslation();

  // 后端 direction/position 的值是中文数据值，作为数据显示，fallback 文案走 i18n
  const direction = typeof structuredData.direction === 'string' ? structuredData.direction : t('agent_awaiting_signal');
  const position = typeof structuredData.position === 'string' ? structuredData.position : '0%';
  const confidence = toNumber(structuredData.confidence);

  const tradeInfo = [
    { label: t('agent_suggested_direction'), value: direction, color: quant.info },
    { label: t('agent_suggested_position'), value: position, color: quant.positive },
    { label: t('backtest_confidence'), value: confidence ? `${confidence * 100}%` : t('agent_unknown'), color: '#722ed1' }, // O2: 特殊装饰色，保留
  ];

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>{t('agent_panel_trading_decision')}</span>
        </Space>
      }
      style={{ marginTop: 12, backgroundColor: theme.bgColor, borderColor: theme.color }}
    >
      <div style={{ marginBottom: 16 }}>
        <Space orientation="vertical" size="middle">
          {tradeInfo.map((item) => (
            <Space key={item.label}>
              <Text>{item.label}：</Text>
              <Tag color={item.color}>{item.value}</Tag>
            </Space>
          ))}
        </Space>
      </div>

      {actions.length > 0 && (
        <div>
          <Title level={5}>{t('agent_trade_actions')}</Title>
          <Space wrap>
            {actions.map((action) => (
              <Button
                key={action.type}
                type="primary"
                size="small"
                onClick={() => onAction(action.type)}
              >
                {action.label}
              </Button>
            ))}
          </Space>
        </div>
      )}
    </Card>
  );
};

// 数据查询面板
export const DataQueryPanel: React.FC<IntentPanelProps> = ({
  roleName,
  structuredData,
  actions,
  onAction,
}) => {
  const theme = useRoleTheme(roleName);
  const { t } = useTranslation();

  const dataColumns = [
    { title: t('agent_metric'), dataIndex: 'key', key: 'key' },
    { title: t('agent_value'), dataIndex: 'value', key: 'value' },
  ];

  const dataSource = Object.entries(structuredData).map(([key, value]) => ({
    key,
    value: String(value),
  }));

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>{t('agent_panel_data_query')}</span>
        </Space>
      }
      style={{ marginTop: 12, backgroundColor: theme.bgColor, borderColor: theme.color }}
    >
      {dataSource.length > 0 ? (
        <Table
          dataSource={dataSource}
          columns={dataColumns}
          pagination={false}
          size="small"
        />
      ) : (
        <Text type="secondary">{t('agent_no_structured_data')}</Text>
      )}

      {actions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Title level={5}>{t('agent_data_actions')}</Title>
          <Space wrap>
            {actions.map((action) => (
              <Button
                key={action.type}
                type="primary"
                ghost
                size="small"
                onClick={() => onAction(action.type)}
              >
                {action.label}
              </Button>
            ))}
          </Space>
        </div>
      )}
    </Card>
  );
};

// 通用面板（默认）
export const GeneralPanel: React.FC<IntentPanelProps> = ({
  roleName,
  actions,
  onAction,
}) => {
  const theme = useRoleTheme(roleName);
  const { t } = useTranslation();

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>{t('agent_panel_general')}</span>
        </Space>
      }
      style={{ marginTop: 12, backgroundColor: theme.bgColor, borderColor: theme.color }}
    >
      {actions.length > 0 && (
        <div>
          <Title level={5}>{t('agent_quick_actions')}</Title>
          <Space wrap>
            {actions.map((action) => (
              <Button
                key={action.type}
                type="primary"
                ghost
                size="small"
                onClick={() => onAction(action.type)}
              >
                {action.label}
              </Button>
            ))}
          </Space>
        </div>
      )}
    </Card>
  );

};

// 根据意图类型选择面板组件
export const IntentPanelRenderer: React.FC<IntentPanelProps> = ({
  intent,
  ...props
}) => {
  const panelMap: Record<string, React.FC<IntentPanelProps>> = {
    strategy_generation: StrategyCodePanel,
    backtest: BacktestResultPanel,
    risk_assessment: RiskAssessmentPanel,
    trading_decision: TradingDecisionPanel,
    data_query: DataQueryPanel,
    rl_training: GeneralPanel,
    general: GeneralPanel,
  };

  const PanelComponent = panelMap[intent] || GeneralPanel;
  return <PanelComponent intent={intent} {...props} />;
};
