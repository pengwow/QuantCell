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

  // bgColor 映射到 antd token 的 colorXxxBg 语义色
  const bgMap: Record<string, { color: string; bg: string }> = {
    '策略工程师': { color: token.colorInfo,        bg: token.colorInfoBg ?? '#e6f7ff' },
    '回测分析师': { color: token.colorSuccess,     bg: token.colorSuccessBg ?? '#f6ffed' },
    '风控顾问':   { color: token.colorWarning,     bg: token.colorWarningBg ?? '#fff7e6' },
    '交易助手':   { color: '#722ed1',              bg: '#f9f0ff' },  // 紫色/粉色保留行业配色
    '数据分析师': { color: token.colorInfo,        bg: '#e6fffb' },  // cyan bg 无对应 token，保留
    'AI 训练师':  { color: '#eb2f96',              bg: '#fff0f6' },  // 粉色保留
    'AI 助手':    { color: token.colorInfo,        bg: token.colorInfoBg ?? '#e6f7ff' },
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
  const codeText = typeof structuredData.code === 'string' ? structuredData.code : '';
  const strategyName = typeof structuredData.strategy_name === 'string' ? structuredData.strategy_name : '';

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>策略代码</span>
        </Space>
      }
      style={{ marginTop: 12, backgroundColor: theme.bgColor, borderColor: theme.color }}
    >
      {codeText && (
        <Collapse defaultActiveKey={['1']}>
          <Panel header="策略代码" key="1">
            <pre style={{
              background: '#1f1f1f',
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
          <Text strong>策略名称：</Text>
          <Tag color={theme.color}>{strategyName}</Tag>
        </div>
      )}

      {actions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Title level={5}>快速操作</Title>
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

  const metrics = [
    { key: '年化收益率', value: structuredData['年化收益率'], suffix: '%', color: '#52c41a' },
    { key: '夏普比率', value: structuredData['夏普比率'], suffix: '', color: '#1890ff' },
    { key: '最大回撤', value: structuredData['最大回撤'], suffix: '%', color: '#ff4d4f' },
    { key: '总收益', value: structuredData['总收益'], suffix: '%', color: '#52c41a' },
    { key: '胜率', value: structuredData['胜率'], suffix: '%', color: '#722ed1' },
  ].filter((m) => m.value !== undefined);

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>回测结果</span>
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
                  <Text>{metric.key}</Text>
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
        <Text type="secondary">暂无回测指标数据</Text>
      )}

      {actions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Title level={5}>分析操作</Title>
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

  const riskLevel = typeof structuredData.risk_level === 'string' ? structuredData.risk_level : '未知';
  const riskColors: Record<string, string> = {
    '低风险': '#52c41a',
    '中风险': '#fa8c16',
    '高风险': '#ff4d4f',
    '未知': '#999999',
  };

  const riskInfo = [
    { label: '风险等级', value: riskLevel, color: riskColors[riskLevel] || '#999999' },
    { label: '评估时间', value: new Date().toLocaleString(), color: '#1890ff' },
  ];

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>风险评估</span>
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
        <Title level={5}>风险提示</Title>
        <div style={{ padding: 12, background: '#fff2f0', borderRadius: 8 }}>
          <Text type="danger">
            ⚠️ 投资有风险，交易需谨慎。以上评估仅供参考，不构成投资建议。
          </Text>
        </div>
      </div>

      {actions.length > 0 && (
        <div>
          <Title level={5}>风控操作</Title>
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

  const direction = typeof structuredData.direction === 'string' ? structuredData.direction : '等待信号';
  const position = typeof structuredData.position === 'string' ? structuredData.position : '0%';
  const confidence = toNumber(structuredData.confidence);

  const tradeInfo = [
    { label: '建议方向', value: direction, color: '#1890ff' },
    { label: '建议仓位', value: position, color: '#52c41a' },
    { label: '置信度', value: confidence ? `${confidence * 100}%` : '未知', color: '#722ed1' },
  ];

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>交易决策</span>
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
          <Title level={5}>交易操作</Title>
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

  const dataColumns = [
    { title: '指标', dataIndex: 'key', key: 'key' },
    { title: '数值', dataIndex: 'value', key: 'value' },
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
          <span>数据查询</span>
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
        <Text type="secondary">暂无结构化数据</Text>
      )}

      {actions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Title level={5}>数据操作</Title>
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

  return (
    <Card
      title={
        <Space>
          <Tag color={theme.color}>{roleName}</Tag>
          <span>对话</span>
        </Space>
      }
      style={{ marginTop: 12, backgroundColor: theme.bgColor, borderColor: theme.color }}
    >
      {actions.length > 0 && (
        <div>
          <Title level={5}>快捷操作</Title>
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
