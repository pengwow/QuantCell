/**
 * 回测详情页面
 * 功能：显示单个回测任务的详细信息，包括配置、指标、图表和交易记录
 * 适配后端返回格式：{ id, strategy_name, backtest_config, metrics, trades, equity_curve, ... }
 */
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  Button,
  Row,
  Col,
  Select,
  Spin,
  message,
  Empty,
  Descriptions,
  Space,
  Table,
  DatePicker,
  Modal,
  Tag,
  Alert,
  Flex,
  Tooltip,
} from 'antd';
import {
  PlayCircleOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import { backtestApi } from '../../api';
import DecisionDetailDrawer, { fmtDecisionTs, humanizeFallbackReason } from './DecisionDetailDrawer';
import MetricCard from '../../components/MetricCard';
import { formatMetricValue, visibleMetricCards } from './metricCards';
import TradeTable, { type Trade } from '../../components/TradeTable';
import { buildLeverageMap, type EffectiveMarginSpec } from '../../types/backtest';
import EquityChart from '../../components/EquityChart';
import EChart from '@/components/EChart';
import { useQuantColors } from '@/utils/colors';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'ahooks';

// 后端返回的数据类型定义
interface BacktestMetrics {
  name: string;
  key: string;
  value: number;
  description: string;
  type: string;
}

interface EquityCurvePoint {
  timestamp: number;
  formatted_time: string;
  equity: number;
  balance: number;
  margin?: number;
}

// 逐档部分强平事件（引擎产出；字段按可选处理，旧任务结果 JSON 无此项）
interface LiquidationEventRecord {
  timestamp_ns: number;
  symbol: string;
  margin_mode?: string;
  tier_from?: number;
  tier_to?: number;
  reduced_qty?: number;
  price?: number;
  fee?: number;
  reason?: string;
  price_basis?: string;
}

// 因子分析载荷（后端结果 JSON factors 字段）
interface FactorTimeSeries {
  timestamps: number[];
  formatted_times: string[];
  // 每因子一列值（NaN 用 null 表示）；列式紧凑编码，前端按因子名取列
  [factorName: string]: number[] | string[] | null;
}

interface FactorAttribution {
  stats: { mean: number; std: number; min: number; max: number; median: number; q25: number; q75: number };
  ic: number | null;
  rank_ic: number | null;
  icir: number | null;
  group_returns: Record<string, number>;
  long_short_return: number | null;
}

interface BacktestFactors {
  names: string[];
  thresholds: Record<string, { buy?: number; sell?: number }>;
  time_series: FactorTimeSeries;
  trade_factors: Array<Record<string, number | string | null>>;
  attribution: Record<string, FactorAttribution>;
}

// cascade 策略决策记录（后端 decisions 字段）
interface CascadeDecisionRecord {
  _seq?: number;          // 录制 JSONL 原始行号，详情弹窗定位键；旧任务无此字段不显示详情按钮
  fingerprint?: string;
  action: string;         // buy / sell / hold
  confidence: number;     // 0.0 ~ 1.0
  probabilities?: Record<string, number>;
  source: string;         // sdm_direct / fallback
  fallback_reason?: string;
  sdm_usage?: unknown;
  sub_signals?: Record<string, unknown>;
  _ts?: string;           // ISO 8601 录制时间
  _s1_model?: string;
  _s2_model?: string;
  _decider?: string; // 录制侧标注的实际决策者（S1:xxx / S2:xxx / 规则 / 回放）；旧录制缺失
}

// 后端实际返回的数据结构
interface BacktestResponse {
  id: string;
  strategy_name: string;
  backtest_config: {
    symbols: string[];
    interval: string;
    start_time: string;
    end_time: string;
    initial_cash?: number;
    capital_mode?: string;
    // 创建回测时的杠杆配置（提交体落在 backtest_config 里，旧任务缺失）
    margin_settings?: EffectiveMarginSpec[];
    // 创建回测时的策略参数（后端入库时随 backtest_config 保存；旧任务可能缺失）
    strategy_params?: Record<string, unknown>;
    [key: string]: unknown;
  };
  strategy_config: Record<string, unknown>;
  metrics: BacktestMetrics[];
  trades: Trade[];
  equity_curve: EquityCurvePoint[];
  factors?: BacktestFactors;
  // 多品种结果：实际有数据的品种列表、当前返回品种
  symbols?: string[];
  selected_symbol?: string | null;
  is_multi_symbol?: boolean;
  // 因无数据被跳过的品种：{品种: 原因}，据此提示用户「选了 N 个标的只剩 M 个」的原因
  skipped_symbols?: Record<string, string>;
  // 保证金模拟结果：生效规格、档位来源、强平/缩量统计
  // 旧任务的结果 JSON 没有这些字段，读取侧统一按空值降级
  margin_applied?: boolean;
  margin_specs_effective?: EffectiveMarginSpec[];
  liquidation_count?: number;
  margin_shortfall_count?: number;
  liquidation_events?: LiquidationEventRecord[];
  insurance_fund_loss?: number;
  // cascade 策略决策记录（回测结束后从录制 JSONL 采集；非 cascade 策略无此字段）
  decisions?: CascadeDecisionRecord[];
  status: string;
  created_at: string;
}

const BacktestDetail = () => {
  const { backtestId } = useParams<{ backtestId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { theme } = useTheme({ localStorageKey: "quantcell-ui-theme" });
  const isDark = theme === 'dark';
  const qc = useQuantColors();

  const [loading, setLoading] = useState(true);
  const [backtestData, setBacktestData] = useState<BacktestResponse | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('all');
  // 多品种时实际传给后端的品种（undefined = 后端默认第一个品种）
  const [querySymbol, setQuerySymbol] = useState<string | undefined>(undefined);
  const [isMultiSymbol, setIsMultiSymbol] = useState(false);
  const [symbols, setSymbols] = useState<string[]>([]);
  // 因无数据被跳过的品种（详情接口 skipped_symbols 字段）
  const [skippedSymbols, setSkippedSymbols] = useState<Record<string, string>>({});
  const [showAllSymbols, setShowAllSymbols] = useState(false);
  const [exporting, setExporting] = useState(false);
  // 高级筛选状态
  const [filterSide, setFilterSide] = useState<string>('all');
  const [filterDateRange, setFilterDateRange] = useState<[string, string] | null>(null);
  const [showAdvancedFilter, setShowAdvancedFilter] = useState(false);
  const [detailRecord, setDetailRecord] = useState<CascadeDecisionRecord | null>(null);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('backtest_detail') || '回测详情');
  }, [t]);

  // 加载回测详情数据
  useEffect(() => {
    if (!backtestId) {
      message.error('回测ID不存在');
      navigate('/backtest');
      return;
    }

    const fetchDetail = async () => {
      try {
        setLoading(true);
        const response = await backtestApi.getBacktestDetail(backtestId, querySymbol);

        // apiRequest 拦截器已经处理了 ApiResponse，直接返回 data 字段
        // api 层类型遵循共享的 BacktestDetailData，而本页以 BacktestResponse（后端实际结构）为准，二者字段存在差异需桥接断言
        if (response && response.id) {
          setBacktestData(response as unknown as BacktestResponse);
          // 无数据被跳过的品种（旧结果 JSON 无此字段，回退空对象）
          const skipped = (response as unknown as BacktestResponse).skipped_symbols || {};
          setSkippedSymbols(skipped);

          // 品种列表优先用结果 JSON 中实际有数据的品种，回退到回测配置
          const symbolKeys = (response as unknown as BacktestResponse).symbols?.length
            ? ((response as unknown as BacktestResponse).symbols as string[])
            : response.backtest_config?.symbols || [];
          setSymbols(symbolKeys);
          const multi = (response as unknown as BacktestResponse).is_multi_symbol ?? symbolKeys.length > 1;
          setIsMultiSymbol(multi);
          // 多品种默认选中后端返回的品种；单品种保持“全部”
          setSelectedSymbol(multi
            ? ((response as unknown as BacktestResponse).selected_symbol || symbolKeys[0] || 'all')
            : 'all');
        } else {
          message.error('获取回测数据失败');
        }
      } catch (error) {
        message.error('加载回测详情失败');
        console.error(error);
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
  }, [backtestId, navigate, querySymbol]);

  /** 多品种切换：驱动后端重新拉取该品种的指标/曲线/成交；切回「全部」时恢复组合视图请求 */
  const handleSymbolChange = (value: string) => {
    setSelectedSymbol(value);
    setFilterSide('all');
    setFilterDateRange(null);
    setQuerySymbol(isMultiSymbol && value !== 'all' ? value : undefined);
  };

  // 从指标数组中获取指定key的指标值
  const getMetricValue = (key: string): number => {
    if (!backtestData?.metrics) return 0;
    const metric = backtestData.metrics.find(m => m.key === key);
    return metric?.value || 0;
  };

  // 完整新契约识别：timestamp + entry_price 同时存在（排除旧 fill 与无 timestamp 的中间版）
  const isContractTrade = (t: Trade) => t.timestamp != null && t.entry_price != null;
  // 是否整个为旧版本引擎产出的结果（无契约字段，无成交明细可展示）
  const rawTrades = backtestData?.trades ?? [];
  const isLegacyOnly = rawTrades.length > 0 && rawTrades.every((t) => !isContractTrade(t));

  // 获取交易列表，根据高级筛选条件进行筛选
  const getTrades = (): Trade[] => {
    // 非契约记录（旧格式/中间版）不适配新表格，直接滤掉
    let trades = rawTrades.filter(isContractTrade);

    // 根据货币对筛选
    if (selectedSymbol && selectedSymbol !== 'all') {
      // 统一去掉 / _ . - 等分隔符再比较，兼容 "BTC/USDT"、"BTCUSDT"、"BTCUSDT.BINANCE" 等写法
      const normalizeSym = (s: string) => s.replace(/[/_.-]/g, '').replace('BINANCE', '').toUpperCase();
      const normalizedSelected = normalizeSym(selectedSymbol);
      trades = trades.filter((trade) => {
        const normalizedTrade = normalizeSym(trade.symbol);
        // 任一方包含另一方即视为同一品种（兼容带交易所后缀等情况）
        return normalizedTrade.includes(normalizedSelected) || normalizedSelected.includes(normalizedTrade);
      });
    }

    // 根据方向筛选（契约 direction 为持仓方向 long/short）
    if (filterSide && filterSide !== 'all') {
      trades = trades.filter((trade) => trade.direction === filterSide);
    }

    // 根据日期范围筛选（契约 timestamp 为秒级）
    if (filterDateRange && filterDateRange[0] && filterDateRange[1]) {
      const startDate = new Date(filterDateRange[0]).getTime();
      const endDate = new Date(filterDateRange[1]).getTime();
      trades = trades.filter((trade) => {
        const tradeTime = trade.timestamp * 1000;
        return tradeTime >= startDate && tradeTime <= endDate;
      });
    }

    return trades;
  };

  // 重置筛选条件
  const resetFilters = () => {
    setSelectedSymbol('all');
    setQuerySymbol(undefined);
    setFilterSide('all');
    setFilterDateRange(null);
  };

  // 获取权益曲线数据，转换为 EquityChart 组件期望的格式
  // 包含结余(balance)和净值(equity)两条线
  const getEquityCurve = (): Array<{ datetime: string; equity: number; balance: number; margin?: number }> => {
    return (backtestData?.equity_curve || []).map(point => ({
      datetime: point.formatted_time || new Date(point.timestamp * 1000).toISOString(),
      equity: point.equity,
      balance: point.balance,
      margin: point.margin,
    }));
  };

  // 格式化数字
  const formatNumber = (value: number, decimals = 2): string => {
    if (typeof value === 'number') {
      return value.toFixed(decimals);
    }
    return String(value);
  };

  // 导出报告：后端生成自包含 HTML（配置/指标/权益曲线/成交明细，口径与详情页一致）
  const handleExport = async () => {
    if (!backtestId) return;

    try {
      setExporting(true);
      // 多品种且选了具体品种 → 导出该品种视角；否则由后端导出组合视角
      const symbol = isMultiSymbol && selectedSymbol !== 'all' ? selectedSymbol : undefined;
      const blob = await backtestApi.getBacktestReport(backtestId, symbol);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      // 与后端 report_filename 保持一致（blob 下载取 download 属性名）
      link.download = `回测报告_${backtestId.slice(0, 8)}_${new Date().toISOString().slice(0, 10)}.html`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      message.success('报告已导出');
    } catch (error) {
      message.error('导出报告失败');
      console.error(error);
    } finally {
      setExporting(false);
    }
  };

  // 跳转到回放页面
  const handleReplay = () => {
    if (backtestId) {
      // 多品种时把当前查看的品种带给回放页
      const qs = isMultiSymbol && selectedSymbol !== 'all' ? `?symbol=${encodeURIComponent(selectedSymbol)}` : '';
      navigate(`/backtest/replay/${backtestId}${qs}`);
    }
  };

  // 渲染加载状态
  if (loading) {
    return (
      <PageContainer title="回测详情">
        <div style={{ display: 'flex', justifyContent: 'center', padding: '100px 0' }}>
          <Spin size="large" description="加载中..." />
        </div>
      </PageContainer>
    );
  }

  // 渲染空状态
  if (!backtestData) {
    return (
      <PageContainer title="回测详情">
        <div style={{ padding: '100px 0' }}>
          <Empty description="未找到回测数据" />
        </div>
      </PageContainer>
    );
  }

  const strategyName = backtestData.strategy_name || 'Unknown';
  const backtestConfig = backtestData.backtest_config || {};
  // 生效规格优先（引擎回填的实际值）；旧任务没有结果字段，回退到任务配置，
  // 后者没有 bracket_source，前端标注为「配置回显」
  const effectiveSpecs: EffectiveMarginSpec[] =
    backtestData.margin_specs_effective?.length
      ? backtestData.margin_specs_effective
      : backtestConfig.margin_settings ?? [];
  const marginApplied = backtestData.margin_applied ?? false;
  // 交易表「保证金占用」列的口径来源：仅启用保证金时传杠杆，否则表格不渲染该列
  const leverageBySymbol: Record<string, number> | undefined = buildLeverageMap(marginApplied, effectiveSpecs);
  const liquidationCount = backtestData.liquidation_count ?? 0;
  const shortfallCount = backtestData.margin_shortfall_count ?? 0;
  // 旧任务没有保证金结果字段，一律按“无强平”处理
  const liquidationEvents: LiquidationEventRecord[] = backtestData.liquidation_events ?? [];
  const insuranceFundLoss = backtestData.insurance_fund_loss ?? 0;
  // 档位来源：db=交易所档位、snapshot=内置快照、default=默认档位；无来源即旧任务配置回显
  const bracketSourceLabel = (item: EffectiveMarginSpec): string =>
    item.bracket_source === 'db'
      ? '交易所档位'
      : item.bracket_source === 'snapshot'
        ? '内置快照'
        : item.bracket_source === 'default'
          ? '默认档位'
          : '配置回显';

  return (
    <PageContainer title={`${strategyName} - 回测详情`}>
      <div className="space-y-6">
        {/* 页面操作按钮 */}
        <div className="flex flex-wrap justify-start sm:justify-end gap-2">
          <Button
            icon={<PlayCircleOutlined />}
            onClick={handleReplay}
            type="primary"
          >
            回放
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExport}
            loading={exporting}
          >
            导出报告
          </Button>
        </div>

        {/* 配置信息 */}
        <Card title="配置信息" className="mb-6">
          <Flex vertical gap={12}>
          <Descriptions bordered column={{ xs: 1, sm: 2, md: 3, lg: 4 }}>
            <Descriptions.Item label="策略名称">
              {strategyName}
            </Descriptions.Item>
            <Descriptions.Item label="交易标的">
              {symbols.length === 0 ? '-' : (
                <>
                  {symbols.slice(0, 3).join('、')}
                  {symbols.length > 3 && (
                    <>
                      {' '}等 {symbols.length} 个
                      <Button type="link" size="small" style={{ padding: 0, marginLeft: 8 }} onClick={() => setShowAllSymbols(true)}>
                        查看全部
                      </Button>
                    </>
                  )}
                </>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="时间周期">
              {backtestConfig.interval || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="交易模式">
              {backtestConfig.trading_mode === 'futures' ? '永续合约' : '现货'}
            </Descriptions.Item>
            <Descriptions.Item label="回测时间">
              {backtestConfig.start_time && backtestConfig.end_time
                ? `${backtestConfig.start_time} 至 ${backtestConfig.end_time}`
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="初始资金">
              {formatNumber(backtestConfig.initial_cash || 0)}
            </Descriptions.Item>
            <Descriptions.Item label="资金使用方式">
              {backtestConfig.capital_mode === 'shared' ? '组合共享资金池' : '各品种独立资金池'}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {backtestData.status}
            </Descriptions.Item>
          </Descriptions>
          {/* 杠杆与保证金：整块常显，未启用时明确告诉用户「没算保证金」，而不是悄悄消失 */}
          <div>
            <div className="mb-2 text-sm font-medium">杠杆与保证金</div>
            <Space size={4} wrap>
              {effectiveSpecs.map((item) => (
                <Tag key={item.symbol} className="mb-0">
                  {`${item.symbol} ${item.leverage}x ${item.margin_mode === 'isolated' ? '逐仓' : '全仓'} · ${bracketSourceLabel(item)}`}
                </Tag>
              ))}
              {marginApplied && (
                <>
                  <Tag color="blue" className="mb-0">{`强平 ${liquidationCount} 次`}</Tag>
                  {shortfallCount > 0 && (
                    <Tag color="orange" className="mb-0">{`保证金受限缩量 ${shortfallCount} 次`}</Tag>
                  )}
                </>
              )}
            </Space>
            {!marginApplied && (
              <div style={{ color: '#999', fontSize: 12, marginTop: 4 }}>
                未启用保证金模拟（1x，无强平判定）
              </div>
            )}
          </div>
          {/* 策略参数独占一块：参数条目数量不定，塞进 Descriptions 格子会显示不全 */}
          <div>
            <div className="mb-2 text-sm font-medium">策略参数</div>
            {Object.keys(backtestConfig.strategy_params || {}).length === 0 ? (
              '-'
            ) : (
              <Space size={4} wrap>
                {Object.entries(backtestConfig.strategy_params!).map(([k, v]) => (
                  <Tag key={k} className="mb-0">
                    {k}: {String(v)}
                  </Tag>
                ))}
              </Space>
            )}
          </div>
          </Flex>
        </Card>

        {/* 强平记录：逐档部分强平的审计视图；无事件（含旧任务缺失字段）时整块不渲染 */}
        {liquidationEvents.length > 0 && (
          <Card title="强平记录" className="mb-6">
            <Flex vertical gap={12}>
              {insuranceFundLoss > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  message={`穿仓损失 ${formatNumber(insuranceFundLoss)} 由保险基金承担`}
                />
              )}
              <Table
                size="small"
                pagination={false}
                scroll={{ x: 'max-content' }}
                dataSource={liquidationEvents}
                rowKey={(record) =>
                  `${record.timestamp_ns}-${record.symbol}-${record.tier_from}-${record.tier_to}`
                }
                columns={[
                  {
                    title: '时间',
                    dataIndex: 'timestamp_ns',
                    // 引擎时间戳是纳秒，换成毫秒再本地化展示
                    render: (value: number) => new Date(value / 1e6).toLocaleString(),
                  },
                  { title: '品种', dataIndex: 'symbol' },
                  {
                    title: '模式',
                    dataIndex: 'margin_mode',
                    render: (value: string) => (value === 'isolated' ? '逐仓' : '全仓'),
                  },
                  {
                    title: '档位',
                    render: (_: unknown, record: LiquidationEventRecord) =>
                      `${record.tier_from ?? '-'} → ${record.tier_to ?? '-'}`,
                  },
                  {
                    title: '减仓量',
                    dataIndex: 'reduced_qty',
                    render: (value: number) => formatNumber(value ?? 0, 4),
                  },
                  {
                    title: '强平费',
                    dataIndex: 'fee',
                    render: (value: number) => formatNumber(value ?? 0),
                  },
                ]}
              />
            </Flex>
          </Card>
        )}

        {/* 回测概览指标（多品种时右上角切换品种，指标/曲线/成交均按品种展示） */}
        <Card
          title="回测概览"
          className="mb-6"
          extra={isMultiSymbol && symbols.length > 0 ? (
            <Space>
              <span>品种</span>
              <Select
                value={selectedSymbol}
                onChange={handleSymbolChange}
                style={{ width: 150 }}
                options={[{ label: '全部', value: 'all' }, ...symbols.map((s) => ({ label: s, value: s }))]}
              />
            </Space>
          ) : undefined}
        >
          {/* 卡片由 metricCards 清单驱动；共享资金池 + 品种视角只渲染按品种归因的指标 */}
          <Flex vertical gap={16}>
            {/* 无数据被跳过的品种提示：解释「选了 N 个标的跑完只剩 M 个」的原因 */}
            {Object.keys(skippedSymbols).length > 0 && (
              <Alert
                type="warning"
                showIcon
                message={
                  Object.keys(skippedSymbols).length === 1
                    ? `${Object.keys(skippedSymbols)[0]} 在所选时间范围内无本地数据，已跳过本次回测，请补齐数据或调整时间范围`
                    : `以下品种在所选时间范围内无本地数据，已跳过：${Object.keys(skippedSymbols).join('、')}`
                }
              />
            )}
            <Row gutter={[16, 16]}>
              {visibleMetricCards(backtestConfig.capital_mode, selectedSymbol).map((spec) => {
                const value = getMetricValue(spec.key);
                return (
                  <Col key={spec.key} xs={12} sm={8} md={6} lg={4}>
                    <MetricCard
                      label={spec.label}
                      value={formatMetricValue(spec, value)}
                      type={spec.color(value, getMetricValue)}
                      hint={spec.hint}
                    />
                  </Col>
                );
              })}
            </Row>
          </Flex>
        </Card>

        {/* 绩效分析图表 */}
        <Card title="权益曲线" className="mb-6">
          {getEquityCurve().length > 0 ? (
            <EquityChart data={getEquityCurve()} isDark={isDark} initialCash={backtestData?.backtest_config?.initial_cash} />
          ) : (
            <Empty description="暂无权益曲线数据" />
          )}
        </Card>

        {/* 因子分析（品种维度数据，组合视图「全部」下无口径，仅具体品种且配置了 factor_names 时渲染） */}
        {selectedSymbol !== 'all' && backtestData.factors && backtestData.factors.names && backtestData.factors.names.length > 0 && (
          <Card title="因子分析" className="mb-6">
            <Space orientation="vertical" size="large" style={{ display: 'flex', width: '100%' }}>
              {/* 因子概览：名称 + 阈值 */}
              <Descriptions bordered column={{ xs: 1, sm: 2, md: 3 }} size="small">
                <Descriptions.Item label="使用因子">
                  {backtestData.factors.names.join('、')}
                </Descriptions.Item>
                {Object.entries(backtestData.factors.thresholds || {}).map(([fname, th]) => (
                  <Descriptions.Item key={fname} label={`${fname} 阈值`}>
                    {th.buy != null && `买入 ≥ ${th.buy}`}
                    {th.buy != null && th.sell != null && ' / '}
                    {th.sell != null && `卖出 ≤ ${th.sell}`}
                  </Descriptions.Item>
                ))}
              </Descriptions>

              {/* 因子时序曲线 */}
              <div>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>因子时序</div>
                {(() => {
                  const ts = backtestData.factors!.time_series;
                  const xData = ts.formatted_times as string[];
                  const series = backtestData.factors!.names.map((name) => ({
                    name,
                    type: 'line',
                    data: (ts[name] as (number | null)[]) || [],
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1.5 },
                  }));
                  return (
                    <EChart
                      option={{
                        tooltip: { trigger: 'axis' },
                        legend: { data: backtestData.factors!.names, top: 0 },
                        grid: { left: 50, right: 20, top: 40, bottom: 40 },
                        xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 10 } },
                        yAxis: { type: 'value', scale: true },
                        dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16 }],
                        series,
                        color: qc.chartSeries,
                      }}
                      style={{ height: 320, width: '100%' }}
                    />
                  );
                })()}
              </div>

              {/* 因子归因指标 + 分组收益 */}
              {Object.entries(backtestData.factors.attribution || {}).map(([fname, attr]) => (
                <div key={fname}>
                  <div style={{ fontWeight: 600, marginBottom: 8 }}>{fname} · 绩效归因</div>
                  <Row gutter={[12, 12]}>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="IC" value={attr.ic != null ? attr.ic.toFixed(4) : 'N/A'} type={attr.ic && attr.ic >= 0 ? 'positive' : 'negative'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="Rank IC" value={attr.rank_ic != null ? attr.rank_ic.toFixed(4) : 'N/A'} type={attr.rank_ic && attr.rank_ic >= 0 ? 'positive' : 'negative'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="ICIR" value={attr.icir != null ? attr.icir.toFixed(4) : 'N/A'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="多空收益" value={attr.long_short_return != null ? (attr.long_short_return * 100).toFixed(2) + '%' : 'N/A'} type={attr.long_short_return && attr.long_short_return >= 0 ? 'positive' : 'negative'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="因子均值" value={attr.stats?.mean != null ? attr.stats.mean.toFixed(4) : 'N/A'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="因子标准差" value={attr.stats?.std != null ? attr.stats.std.toFixed(4) : 'N/A'} />
                    </Col>
                  </Row>
                  {/* 分组收益柱状图 */}
                  {attr.group_returns && Object.keys(attr.group_returns).length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <EChart
                        option={{
                          tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => (v as number).toFixed(4) },
                          grid: { left: 60, right: 20, top: 20, bottom: 40 },
                          xAxis: { type: 'category', data: Object.keys(attr.group_returns) },
                          yAxis: { type: 'value', axisLabel: { formatter: (v: number) => (v * 100).toFixed(1) + '%' } },
                          series: [{
                            type: 'bar',
                            data: Object.values(attr.group_returns),
                            itemStyle: { color: (p: any) => (p.value >= 0 ? qc.positive : qc.negative) },
                          }],
                        }}
                        style={{ height: 220, width: '100%' }}
                      />
                    </div>
                  )}
                </div>
              ))}
            </Space>
          </Card>
        )}

        {/* 交易详情 */}
        <Card
          title="交易详情"
          className="mb-6"
          extra={
            <Space>
              <Button
                type={showAdvancedFilter ? 'primary' : 'default'}
                onClick={() => setShowAdvancedFilter(!showAdvancedFilter)}
              >
                筛选
              </Button>
            </Space>
          }
        >
          {/* 高级筛选区域 */}
          {showAdvancedFilter && (
            <div style={{ marginBottom: 16, padding: 16, backgroundColor: 'transparent', border: '1px solid var(--ant-color-border)', borderRadius: 8 }}>
              <Row gutter={[16, 16]} align="middle">
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>交易标的</div>
                  <Select
                    value={selectedSymbol}
                    onChange={handleSymbolChange}
                    style={{ width: '100%' }}
                    placeholder="选择交易标的"
                  >
                    {/* 「全部」在单/多品种下都可能是当前值，必须始终渲染 */}
                    <Select.Option value="all">全部</Select.Option>
                    {symbols.map((symbol) => (
                      <Select.Option key={symbol} value={symbol}>
                        {symbol}
                      </Select.Option>
                    ))}
                  </Select>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>交易方向</div>
                  <Select
                    value={filterSide}
                    onChange={setFilterSide}
                    style={{ width: '100%' }}
                    placeholder="选择方向"
                  >
                    <Select.Option value="all">全部</Select.Option>
                    <Select.Option value="long">做多</Select.Option>
                    <Select.Option value="short">做空</Select.Option>
                  </Select>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>日期范围</div>
                  <DatePicker.RangePicker
                    style={{ width: '100%' }}
                    onChange={(dates) => {
                      if (dates && dates[0] && dates[1]) {
                        setFilterDateRange([dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]);
                      } else {
                        setFilterDateRange(null);
                      }
                    }}
                  />
                </Col>
              </Row>
              <Row style={{ marginTop: 16 }}>
                <Col span={24} style={{ textAlign: 'right' }}>
                  <Button onClick={resetFilters}>重置</Button>
                </Col>
              </Row>
            </div>
          )}

          {/* 筛选结果统计 */}
          <div style={{ marginBottom: 16 }}>
            <span style={{ color: '#8c8c8c' }}>
              共 {getTrades().length} 条记录
              {selectedSymbol !== 'all' && ` | 标的: ${selectedSymbol}`}
              {filterSide !== 'all' && ` | 方向: ${filterSide === 'long' ? '做多' : '做空'}`}
              {filterDateRange && ` | 日期: ${filterDateRange[0]} 至 ${filterDateRange[1]}`}
            </span>
          </div>

          {getTrades().length > 0 ? (
            <TradeTable data={getTrades()} leverageBySymbol={leverageBySymbol} />
          ) : isLegacyOnly ? (
            <Empty description="该回测由旧版本引擎生成，无成交明细" />
          ) : rawTrades.length === 0 ? (
            <Empty
              description={
                getMetricValue('total_trades') > 0
                  ? `该回测有 ${getMetricValue('total_trades')} 笔成交但尚未平仓，无完整交易记录`
                  : '该回测未产生任何成交，请检查策略参数（如价格区间）是否与市场行情匹配'
              }
            />
          ) : (
            <Empty description="暂无交易记录" />
          )}
        </Card>

        {/* cascade 决策详情：只在策略产出 decisions 时展示 */}
        {(() => {
          const decisions = backtestData?.decisions;
          if (!decisions || decisions.length === 0) return null;

          const actionCounts: Record<string, number> = {};
          const reasonCounts: Record<string, number> = {};
          const deciderCounts: Record<string, number> = {};
          // 旧录制无 _decider：按 source+_s1_model 保守推断，无从知晓 S2/规则，统一「降级兜底」
          const deciderOf = (d: CascadeDecisionRecord): string => {
            if (d._decider) return d._decider;
            if (d.source === 'sdm_direct') return d._s1_model ? `S1:${d._s1_model}` : 'S1';
            if (d.source === 'fallback') return '降级兜底';
            return '其他';
          };
          // 降级原因聚合键：新格式「类别: 细分: 详情」收敛到「类别: 细分」避免按详情炸开；
          // 旧格式两段以内（含 low_confidence: buy=0.63 旧写法）取原串
          const reasonBucket = (reason: string): string => {
            const parts = reason.split(':');
            return parts.length >= 3 ? `${parts[0].trim()}: ${parts[1].trim()}` : reason.trim();
          };
          decisions.forEach((d) => {
            actionCounts[d.action] = (actionCounts[d.action] || 0) + 1;
            if (d.fallback_reason) {
              const bucket = reasonBucket(d.fallback_reason);
              reasonCounts[bucket] = (reasonCounts[bucket] || 0) + 1;
            }
            const dv = deciderOf(d);
            deciderCounts[dv] = (deciderCounts[dv] || 0) + 1;
          });

          const deciderColor = (v: string): string | undefined => {
            if (v.startsWith('S1')) return 'blue';
            if (v.startsWith('S2')) return 'purple';
            if (v === '规则') return 'cyan';
            return undefined; // 回放 / 降级兜底 / 其他 → antd 默认灰
          };
          const actionColor: Record<string, string> = {
            buy: 'green',
            sell: 'red',
            hold: 'default',
          };

          // 只展示前 100 条 + 分页，3 万条全渲染卡浏览器
          const PAGE_SIZE = 200;

          return (
            <Card title="决策详情" className="mb-6">
              <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
                {/* 统计摘要 */}
                <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{ color: '#8c8c8c' }}>
                    共 <strong>{decisions.length.toLocaleString()}</strong> 条决策
                  </span>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ color: '#8c8c8c' }}>决策者：</span>
                    {Object.entries(deciderCounts).map(([dv, cnt]) => (
                      <Tag key={dv} color={deciderColor(dv)}>
                        {dv}: {cnt.toLocaleString()}
                      </Tag>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ color: '#8c8c8c' }}>动作：</span>
                    {Object.entries(actionCounts).map(([act, cnt]) => (
                      <Tag key={act} color={actionColor[act] || 'default'}>
                        {act === 'buy' ? '买入' : act === 'sell' ? '卖出' : '持有'}: {cnt.toLocaleString()}
                      </Tag>
                    ))}
                  </div>
                </div>
                {Object.keys(reasonCounts).length > 0 && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    <span style={{ color: '#8c8c8c' }}>降级原因 Top：</span>
                    {Object.entries(reasonCounts)
                      .sort((a, b) => b[1] - a[1])
                      .slice(0, 5)
                      .map(([reason, cnt]) => (
                        <Tag key={reason}>{humanizeFallbackReason(reason)}: {cnt.toLocaleString()}</Tag>
                      ))}
                  </div>
                )}

                {/* 决策表格 */}
                <Table
                  size="small"
                  scroll={{ x: 'max-content' }}
                  dataSource={decisions}
                  rowKey={(_, idx) => String(idx)}
                  pagination={{
                    pageSize: PAGE_SIZE,
                    showSizeChanger: false,
                    showQuickJumper: true,
                    showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条，共 ${total.toLocaleString()} 条`,
                  }}
                  columns={[
                    {
                      title: '时间',
                      dataIndex: '_ts',
                      width: 200,
                      render: (_v: unknown, record: CascadeDecisionRecord) => (
                        <Tooltip title={record._ts}>{fmtDecisionTs(record._ts)}</Tooltip>
                      ),
                    },
                    {
                      title: '动作',
                      dataIndex: 'action',
                      width: 80,
                      render: (v: string) => {
                        const label = v === 'buy' ? '买入' : v === 'sell' ? '卖出' : '持有';
                        const color = actionColor[v] || 'default';
                        return <Tag color={color}>{label}</Tag>;
                      },
                    },
                    {
                      title: '置信度',
                      dataIndex: 'confidence',
                      width: 100,
                      align: 'right',
                      render: (v: number) => (v != null ? (v * 100).toFixed(1) + '%' : '-'),
                    },
                    {
                      title: '决策者',
                      dataIndex: '_decider',
                      width: 200,
                      ellipsis: true,
                      render: (_v: unknown, record: CascadeDecisionRecord) => {
                        const dv = deciderOf(record);
                        return <Tag color={deciderColor(dv)}>{dv}</Tag>;
                      },
                    },
                    {
                      title: '降级原因',
                      dataIndex: 'fallback_reason',
                      ellipsis: true,
                      render: (v: string) => humanizeFallbackReason(v),
                    },
                    {
                      title: '操作',
                      key: 'detail',
                      width: 80,
                      fixed: 'right' as const,
                      render: (_v: unknown, record: CascadeDecisionRecord) =>
                        record._seq == null ? (
                          <Tooltip title="旧任务无行号定位键，无法查看录制详情">-</Tooltip>
                        ) : (
                          <Button size="small" onClick={() => setDetailRecord(record)}>
                            详情
                          </Button>
                        ),
                    },
                  ]}
                />
              </Space>
            </Card>
          );
        })()}
        <DecisionDetailDrawer
          backtestId={backtestId!}
          record={detailRecord}
          onClose={() => setDetailRecord(null)}
        />
      </div>

      {/* 全部交易标的弹窗（标的过多时点开查看） */}
      <Modal
        title={`全部交易标的（共 ${symbols.length} 个）`}
        open={showAllSymbols}
        onCancel={() => setShowAllSymbols(false)}
        footer={<Button onClick={() => setShowAllSymbols(false)}>关闭</Button>}
        width={640}
      >
        <div style={{ maxHeight: 500, overflowY: 'auto' }}>
          <Space wrap size={[8, 8]}>
            {symbols.map((s) => (
              <Tag key={s} style={{ fontSize: 13, fontFamily: 'monospace' }}>{s}</Tag>
            ))}
          </Space>
        </div>
      </Modal>
    </PageContainer>
  );
};

export default BacktestDetail;
