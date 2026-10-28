import { useTranslation } from 'react-i18next';
import {
  Button,
  Card,
  Row,
  Col,
  Descriptions,
  Tag,
  Space,
  Tooltip,
} from 'antd';
import type { Worker as WorkerType, StrategyParameter, RiskControlOut } from '../../types/worker';
import { CodeOutlined, ExclamationCircleOutlined, TagOutlined } from '@ant-design/icons';
import { getRiskControl, getStrategyParameters } from '../../api/workerApi';
import { QUANT_COLORS } from '@/utils/colors';
import { useState, useEffect } from 'react';

/** 人工风控展示行的 7 个数值字段（key 收窄为字面量联合，risk[key] 无需断言） */
type RiskDisplayKey =
  | 'max_position_pct'
  | 'max_position_size'
  | 'daily_loss_limit'
  | 'daily_loss_amount'
  | 'max_drawdown'
  | 'max_leverage'
  | 'circuit_breaker_cooldown_secs';

/**
 * 人工风控展示行（启用明细态）：key 为 RiskControlOut 数值字段。
 * engineDefault = 该字段未配置（null）时引擎实际生效的默认档，硬编码出处：
 * - 亏损/回撤/杠杆/冷却：axon-risk config.rs `RiskConfig::default()`
 * - 仓位两行：axon-worker risk_check.rs 桥接口径 max_position_value=None = 不做仓位检查
 *   （引擎默认的数量口径仓位限额已在桥层禁用，未配置就是真不限制）
 * - 「亏损上限占比」引擎无占比默认档，生效的是固定金额 10,000 USDT，故与金额行同文
 * ponytail: 前端内嵌默认值有与引擎漂移的风险，升级路径是后端接口回带默认值字段
 */
const RISK_DISPLAY_ROWS: { key: RiskDisplayKey; label: string; unit: 'pct' | 'usdt' | 'x' | 'min'; engineDefault: string }[] = [
  { key: 'max_position_pct', label: '单币种最大仓位占比', unit: 'pct', engineDefault: '不限制' },
  { key: 'max_position_size', label: '单币种最大名义价值', unit: 'usdt', engineDefault: '不限制' },
  { key: 'daily_loss_limit', label: '当日亏损上限占比', unit: 'pct', engineDefault: '10,000 USDT' },
  { key: 'daily_loss_amount', label: '当日亏损上限金额', unit: 'usdt', engineDefault: '10,000 USDT' },
  { key: 'max_drawdown', label: '最大回撤上限', unit: 'pct', engineDefault: '15%' },
  { key: 'max_leverage', label: '最大杠杆', unit: 'x', engineDefault: '5x' },
  { key: 'circuit_breaker_cooldown_secs', label: '熔断冷却时长', unit: 'min', engineDefault: '60 分钟' },
];

/**
 * 后端口径 → 展示文本：% 字段 0-1 → xx%，冷却秒 → 分钟；加零位小数避免 15.0%。
 * 只负责已配置值的格式化，未配置（null）的「引擎默认」分支在渲染处处理。
 */
const fmtRiskValue = (v: number, unit: 'pct' | 'usdt' | 'x' | 'min'): string => {
  switch (unit) {
    case 'pct':
      return `${+(v * 100).toFixed(4)}%`;
    case 'usdt':
      return `${v.toLocaleString('en-US')} USDT`;
    case 'x':
      return `${v}x`;
    case 'min':
      return `${+(v / 60).toFixed(2)} 分钟`;
  }
};

interface WorkerParamsTabProps {
  worker: WorkerType;
  /** 风控卡片「编辑」按钮回调（父页面联动 EditModal） */
  onEdit?: () => void;
  /** 递增触发风控配置重拉：编辑弹窗保存成功后由父页面更新，避免展示旧值 */
  reloadKey?: number;
}

const WorkerParamsTab: React.FC<WorkerParamsTabProps> = ({ worker, onEdit, reloadKey = 0 }) => {
  const { t } = useTranslation();

  // 从 config 中提取策略参数（如果存在）
  const config: Record<string, unknown> = worker.config ?? {};

  // 动态策略参数
  const [strategyParams, setStrategyParams] = useState<StrategyParameter[]>([]);
  const [loadingParams, setLoadingParams] = useState(false);

  // Worker 实际配置的策略参数值（从 config 或 trading_config 获取）
  const rawParams =
    (worker.trading_config as Record<string, unknown> | undefined)?.strategy_params ??
    config.strategy_params ??
    {};
  const currentStrategyParams: Record<string, unknown> =
    rawParams && typeof rawParams === 'object' ? (rawParams as Record<string, unknown>) : {};

  // 加载策略参数定义（后端合并策略库 schema + worker 覆盖值，按 worker 维度查询）
  useEffect(() => {
    const loadParams = async () => {
      if (!worker.id) {
        setStrategyParams([]);
        return;
      }
      setLoadingParams(true);
      try {
        const params = await getStrategyParameters(worker.id);
        setStrategyParams(params);
      } catch (error) {
        console.error('加载策略参数失败:', error);
        setStrategyParams([]);
      } finally {
        setLoadingParams(false);
      }
    };
    loadParams();
  }, [worker.id]);

  // 人工风控配置（GET null = 从未配置过 → 继承策略参数）
  const [risk, setRisk] = useState<RiskControlOut | null>(null);
  const [riskLoaded, setRiskLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getRiskControl(worker.id)
      .then((out) => {
        if (!cancelled) setRisk(out);
      })
      .catch((error) => {
        console.error('加载风控配置失败:', error);
      })
      .finally(() => {
        if (!cancelled) setRiskLoaded(true);
      });
    return () => {
      cancelled = true;
    };
    // reloadKey 仅作为重拉信号（编辑保存成功后由父页面递增），不参与 effect 内部逻辑
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [worker.id, reloadKey]);

  return (
    <div>
      {/* 策略信息 */}
      {worker.strategy_info && (
        <Card
          title={
            <Space>
              <CodeOutlined />
              <span>{t('strategy_info') || '策略信息'}</span>
            </Space>
          }
          style={{ marginBottom: 16 }}
        >
          <Row gutter={[24, 16]}>
            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                <Descriptions.Item label={t('strategy_name') || '策略名称'}>
                  <Tag color="blue">{worker.strategy_info.name}</Tag>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                <Descriptions.Item label={t('strategy_type') || '策略类型'}>
                  {/* 值域对齐策略库 models（rule/rl）；'default' 为无关联策略时的兜底档，未知值归默认 */}
                  <Tag icon={<TagOutlined />} color={worker.strategy_info.strategy_type === 'rl' ? 'purple' : 'green'}>
                    {worker.strategy_info.strategy_type === 'rl'
                      ? t('rl_strategy')
                      : worker.strategy_info.strategy_type === 'rule'
                        ? t('rule_strategy')
                        : t('default_strategy')}
                  </Tag>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                <Descriptions.Item label={t('strategy_version') || '策略版本'}>
                  <span style={{ fontWeight: 500 }}>v{worker.strategy_info.version}</span>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            {worker.strategy_info.description && (
              <Col span={24}>
                <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                  <Descriptions.Item label={t('strategy_description') || '策略描述'}>
                    <span>{worker.strategy_info.description}</span>
                  </Descriptions.Item>
                </Descriptions>
              </Col>
            )}
          </Row>
        </Card>
      )}

      {/* 基础配置 */}
      <Card
        title={
          <Space>
            <span>⚙️</span>
            <span>{t('basic_config') || '基础配置'}</span>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Row gutter={[24, 16]}>
          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('symbol') || '交易对'}>
                <Tag color="blue">{worker.trading_config?.symbols_config?.symbols?.join(', ') || '-'}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('exchange') || '交易所'}>
                <Tag>{worker.trading_config?.exchange}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('trading_mode') || '交易模式'}>
                {/* live 红色提醒真实资金，testnet 橙色表示测试网，paper 蓝色本地模拟；文案与创建/编辑弹窗的 TRADING_MODES 保持一致 */}
                <Tag color={worker.trading_config?.trading_mode === 'live' ? 'red' : worker.trading_config?.trading_mode === 'testnet' ? 'orange' : 'blue'}>
                  {worker.trading_config?.trading_mode === 'live'
                    ? '实盘交易'
                    : worker.trading_config?.trading_mode === 'testnet'
                      ? '测试网'
                      : '本地模拟'}
                </Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('timeframe') || 'K线周期'}>
                <Tag color="blue">{worker.trading_config?.timeframe}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('leverage') || '杠杆倍数'}>
                <Tag color="orange">{config.leverage ? `${String(config.leverage)}x` : '1x'}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('total_investment') || '总投入金额'}>
                {/* config 里没有 total_investment；创建/编辑弹窗提交与启动参数读的都是 initial_capital（worker 初始资金） */}
                <span style={{ fontWeight: 600, color: QUANT_COLORS.info }}>
                  ${typeof config.initial_capital === 'number' ? config.initial_capital.toFixed(2) : '-'}
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('order_type') || '下单方式'}>
                {/* config.order_type 是死字段（worker 配置从未支持过下单方式，读了必是 undefined）。
                    实际执行：paper/live 主回路按目标仓位差额固定下市价单，与 paper_trade_sync「paper 撮合只产市价单」同口径，
                    故此处如实显示市价单；limit 仅存在于订单/成交记录的筛选条件 */}
                <Tag color="cyan">{t('market_order') || '市价单'}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>

      {/* 策略参数 - 动态加载 */}
      <Card
        title={
          <Space>
            <span>📊</span>
            <span>{t('strategy_params') || '策略参数'}</span>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        {strategyParams.length > 0 ? (
          <Row gutter={[24, 16]}>
            {strategyParams.map((param) => {
              const currentValue = currentStrategyParams[param.param_name];
              // 生效值优先级：运行配置覆盖 > 后端合并的 param_value（快照覆盖 ?? schema 默认）> schema 默认
              const displayValue = currentValue ?? param.param_value ?? param.default_value ?? '-';
              let valueDisplay: React.ReactNode;
              const valueStyle: React.CSSProperties = { fontWeight: 500 };

              if (typeof displayValue === 'number' && param.param_type === 'float') {
                valueDisplay = typeof displayValue === 'number' ? displayValue.toFixed(2) : String(displayValue);
                if (param.param_name?.includes('loss') || param.param_name?.includes('stop')) {
                  valueStyle.color = QUANT_COLORS.negative;
                } else if (param.param_name?.includes('profit')) {
                  valueStyle.color = QUANT_COLORS.positive;
                }
              } else if (typeof displayValue === 'boolean') {
                valueDisplay = (
                  <Tag color={displayValue ? 'green' : 'red'}>
                    {displayValue ? '是' : '否'}
                  </Tag>
                );
              } else {
                valueDisplay = String(displayValue);
              }

              return (
                <Col key={param.param_name} xs={24} sm={12} md={8}>
                  <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                    <Descriptions.Item
                      label={
                        <Space size={4}>
                          <span>{param.param_name}</span>
                          {param.description && (
                            <Tag
                              style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}
                              color="processing"
                            >
                              {param.description.length > 20 ? `${param.description.slice(0, 18)}...` : param.description}
                            </Tag>
                          )}
                        </Space>
                      }
                    >
                      <span style={valueStyle}>{valueDisplay}</span>
                    </Descriptions.Item>
                  </Descriptions>
                </Col>
              );
            })}
          </Row>
        ) : loadingParams ? (
          <div style={{ textAlign: 'center', padding: 30 }}>
            <Tag icon={<CodeOutlined />} color="processing">加载中...</Tag>
          </div>
        ) : Object.keys(currentStrategyParams).length > 0 ? (
          <Row gutter={[24, 16]}>
            {Object.entries(currentStrategyParams).map(([key, value]) => (
              <Col key={key} xs={24} sm={12} md={8}>
                <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                  <Descriptions.Item label={key}>
                    <span style={{ fontWeight: 500 }}>{String(value)}</span>
                  </Descriptions.Item>
                </Descriptions>
              </Col>
            ))}
          </Row>
        ) : (
          <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
            <Tag>该策略无可编辑参数</Tag>
          </div>
        )}
      </Card>

      {/* 人工风控（三态：启用明细 / 已停用 / 继承策略参数） */}
      <Card
        title={
          <Space>
            <span>🛡️</span>
            <span>{t('risk_params') || '风控参数'}</span>
            {risk?.enabled && <Tag color="green">风控防护启用中</Tag>}
          </Space>
        }
        extra={onEdit && <Button size="small" onClick={onEdit}>编辑</Button>}
      >
        {!riskLoaded ? (
          <div style={{ textAlign: 'center', padding: 30 }}>
            <Tag icon={<CodeOutlined />} color="processing">加载中...</Tag>
          </div>
        ) : risk === null ? (
          <div style={{ textAlign: 'center', padding: 30, color: '#999' }}>
            继承策略参数配置
          </div>
        ) : !risk.enabled ? (
          <div style={{ textAlign: 'center', padding: 30, color: '#999' }}>
            风控防护已停用
          </div>
        ) : (
          <Row gutter={[24, 16]}>
            {RISK_DISPLAY_ROWS.map(({ key, label, unit, engineDefault }) => {
              // 联合键索引直接比较 narrowing 不可靠，先提取局部变量
              const v = risk[key];
              return (
                <Col key={key} xs={24} sm={12} md={8}>
                  <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                    <Descriptions.Item label={label}>
                      {v === null || v === undefined ? (
                        // 未配置 → 引擎默认档：保持原染色警示，感叹号悬浮展示具体默认值
                        <span
                          style={{
                            fontWeight: 500,
                            color: unit === 'pct' || unit === 'usdt' ? QUANT_COLORS.negative : undefined,
                          }}
                        >
                          引擎默认
                          <Tooltip title={`未配置该项，当前按引擎内置默认生效：${engineDefault}`}>
                            <ExclamationCircleOutlined
                              style={{ marginLeft: 4, fontSize: 12, color: '#faad14', cursor: 'help' }}
                            />
                          </Tooltip>
                        </span>
                      ) : (
                        <span
                          style={{
                            fontWeight: 500,
                            color: unit === 'pct' || unit === 'usdt' ? QUANT_COLORS.negative : undefined,
                          }}
                        >
                          {fmtRiskValue(v, unit)}
                        </span>
                      )}
                    </Descriptions.Item>
                  </Descriptions>
                </Col>
              );
            })}
            <Col span={24}>
              <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                <Descriptions.Item label="更新时间">
                  <span style={{ color: '#999' }}>
                    {risk.updated_at ? new Date(risk.updated_at).toLocaleString() : '-'}
                  </span>
                </Descriptions.Item>
              </Descriptions>
            </Col>
          </Row>
        )}
      </Card>
    </div>
  );
};

export default WorkerParamsTab;
