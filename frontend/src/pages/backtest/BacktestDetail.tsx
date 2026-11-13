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
import {
  buildLeverageMap,
  type BacktestFill,
  type CascadeDecisionRecord,
  type EffectiveMarginSpec,
} from '../../types/backtest';
import EquityChart from '../../components/EquityChart';
import EChart from '@/components/EChart';
import { useQuantColors } from '@/utils/colors';
import PageContainer from '@/components/PageContainer';
import { usePageBack } from '@/hooks/usePageBack';
import { setPageTitle } from '@/utils/pageTitle';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'ahooks';

// 逐笔成交兜底表：round-trip 稀疏（如 RL 目标仓位策略持仓长期不归零）时
// 在交易详情 Card 内展示 fill 粒度记录，替代误导性的「无完整交易记录」空态
const FillsDetailTable = ({ fills }: { fills: BacktestFill[] }) => {
  const { t } = useTranslation();
  return (
    <>
      <Alert type="info" showIcon style={{ marginBottom: 16 }} title={t('backtest_fills_detail_hint')} />
      <Table
        size="small"
        rowKey="fill_id"
        dataSource={fills}
        scroll={{ y: 480 }}
        pagination={{ pageSize: 50, showSizeChanger: true, showTotal: (total) => t('total_count', { count: total }) }}
        columns={[
          { title: t('trade_time'), dataIndex: 'formatted_time', key: 'ft' },
          {
            title: t('direction'),
            dataIndex: 'side',
            key: 'side',
            render: (v: string) => <Tag color={v === 'buy' ? 'green' : 'red'}>{v === 'buy' ? t('buy') : t('sell')}</Tag>,
          },
          { title: t('price'), dataIndex: 'price', key: 'p', align: 'right', render: (v: number) => v.toFixed(4) },
          { title: t('quantity'), dataIndex: 'quantity', key: 'q', align: 'right', render: (v: number) => v.toFixed(4) },
        ]}
      />
    </>
  );
};

// 后端返回的数据类型定义
interface BacktestMetrics {
  name: string;
  key: string;
  // P1-04 起 Deflated Sharpe 等指标在数据不足时显式输出 null（不降级伪值）
  value: number | null;
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
  /** 逐笔成交明细（fill 粒度）：round-trip 稀疏时（如 RL 目标仓位策略）兜底展示，旧任务无此键 */
  fills_detail?: BacktestFill[];
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
  // 统一返回逻辑：returnUrl 优先（保留列表筛选状态），否则历史返回
  const handleBack = usePageBack();

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
    // backtest_detail 词条由本次 i18n 迁移补齐，t() 不会返回空串，无需 fallback 字面量
    setPageTitle(t('backtest_detail'));
  }, [t]);

  // 加载回测详情数据
  useEffect(() => {
    if (!backtestId) {
      message.error(t('backtest_id_not_exist'));
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
          message.error(t('backtest_fetch_data_failed'));
        }
      } catch (error) {
        message.error(t('load_backtest_detail_failed'));
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
      // 复用 backtest_report_filename 词条，任务短 ID 与日期并入 {{id}} 插值
      link.download = `${t('backtest_report_filename', { id: `${backtestId.slice(0, 8)}_${new Date().toISOString().slice(0, 10)}` })}.html`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      message.success(t('export_report_success'));
    } catch (error) {
      message.error(t('export_report_failed'));
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
      <PageContainer title={t('backtest_detail')} onBack={handleBack}>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '100px 0' }}>
          <Spin size="large" description={t('loading')} />
        </div>
      </PageContainer>
    );
  }

  // 渲染空状态
  if (!backtestData) {
    return (
      <PageContainer title={t('backtest_detail')} onBack={handleBack}>
        <div style={{ padding: '100px 0' }}>
          <Empty description={t('backtest_not_found')} />
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
      ? t('backtest_bracket_source_db')
      : item.bracket_source === 'snapshot'
        ? t('backtest_bracket_source_snapshot')
        : item.bracket_source === 'default'
          ? t('backtest_bracket_source_default')
          : t('backtest_bracket_source_config');

  return (
    <PageContainer title={`${strategyName} - ${t('backtest_detail')}`} onBack={handleBack}>
      <div className="space-y-6">
        {/* 页面操作按钮 */}
        <div className="flex flex-wrap justify-start sm:justify-end gap-2">
          <Button
            icon={<PlayCircleOutlined />}
            onClick={handleReplay}
            type="primary"
          >
            {t('replay')}
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExport}
            loading={exporting}
          >
            {t('export_report')}
          </Button>
        </div>

        {/* 配置信息 */}
        <Card title={t('config_info')} className="mb-6">
          <Flex vertical gap={12}>
          <Descriptions bordered column={{ xs: 1, sm: 2, md: 3, lg: 4 }}>
            <Descriptions.Item label={t('backtest_strategy_name')}>
              {strategyName}
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_symbols')}>
              {symbols.length === 0 ? '-' : (
                <>
                  {symbols.slice(0, 3).join('、')}
                  {symbols.length > 3 && (
                    <>
                      {' '}{t('backtest_symbols_more', { num: symbols.length })}
                      <Button type="link" size="small" style={{ padding: 0, marginLeft: 8 }} onClick={() => setShowAllSymbols(true)}>
                        {t('home_view_all')}
                      </Button>
                    </>
                  )}
                </>
              )}
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_timeframe')}>
              {backtestConfig.interval || '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_trading_mode')}>
              {backtestConfig.trading_mode === 'futures' ? t('backtest_futures') : t('spot')}
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_period')}>
              {backtestConfig.start_time && backtestConfig.end_time
                ? t('backtest_date_span', { start: backtestConfig.start_time, end: backtestConfig.end_time })
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_initial_cash')}>
              {formatNumber(backtestConfig.initial_cash || 0)}
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_capital_mode')}>
              {backtestConfig.capital_mode === 'shared' ? t('backtest_capital_shared') : t('backtest_capital_per_symbol')}
            </Descriptions.Item>
            <Descriptions.Item label={t('status')}>
              {backtestData.status}
            </Descriptions.Item>
          </Descriptions>
          {/* 杠杆与保证金：整块常显，未启用时明确告诉用户「没算保证金」，而不是悄悄消失 */}
          <div>
            <div className="mb-2 text-sm font-medium">{t('backtest_margin_settings')}</div>
            <Space size={4} wrap>
              {effectiveSpecs.map((item) => (
                <Tag key={item.symbol} className="mb-0">
                  {`${item.symbol} ${item.leverage}x ${item.margin_mode === 'isolated' ? t('backtest_margin_isolated') : t('backtest_margin_cross')} · ${bracketSourceLabel(item)}`}
                </Tag>
              ))}
              {marginApplied && (
                <>
                  <Tag color="blue" className="mb-0">{t('backtest_liquidation_count', { num: liquidationCount })}</Tag>
                  {shortfallCount > 0 && (
                    <Tag color="orange" className="mb-0">{t('backtest_margin_shortfall_count', { num: shortfallCount })}</Tag>
                  )}
                </>
              )}
            </Space>
            {!marginApplied && (
              <div style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)', fontSize: 12, marginTop: 4 }}>
                {t('backtest_margin_disabled_hint')}
              </div>
            )}
          </div>
          {/* 策略参数独占一块：参数条目数量不定，塞进 Descriptions 格子会显示不全 */}
          <div>
            <div className="mb-2 text-sm font-medium">{t('strategy_params')}</div>
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
          <Card title={t('backtest_liquidation_records')} className="mb-6">
            <Flex vertical gap={12}>
              {insuranceFundLoss > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  title={t('backtest_insurance_fund_loss', { v: formatNumber(insuranceFundLoss) })}
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
                    title: t('backtest_time'),
                    dataIndex: 'timestamp_ns',
                    // 引擎时间戳是纳秒，换成毫秒再本地化展示
                    render: (value: number) => new Date(value / 1e6).toLocaleString(),
                  },
                  { title: t('backtest_symbol'), dataIndex: 'symbol' },
                  {
                    title: t('backtest_mode'),
                    dataIndex: 'margin_mode',
                    render: (value: string) => (value === 'isolated' ? t('backtest_margin_isolated') : t('backtest_margin_cross')),
                  },
                  {
                    title: t('backtest_tier'),
                    render: (_: unknown, record: LiquidationEventRecord) =>
                      `${record.tier_from ?? '-'} → ${record.tier_to ?? '-'}`,
                  },
                  {
                    title: t('backtest_reduced_qty'),
                    dataIndex: 'reduced_qty',
                    render: (value: number) => formatNumber(value ?? 0, 4),
                  },
                  {
                    title: t('backtest_liquidation_fee'),
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
          title={t('backtest_overview')}
          className="mb-6"
          extra={isMultiSymbol && symbols.length > 0 ? (
            <Space>
              <span>{t('backtest_symbol')}</span>
              <Select
                value={selectedSymbol}
                onChange={handleSymbolChange}
                style={{ width: 150 }}
                options={[{ label: t('all'), value: 'all' }, ...symbols.map((s) => ({ label: s, value: s }))]}
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
                title={
                  Object.keys(skippedSymbols).length === 1
                    ? t('backtest_symbol_skipped', { symbol: Object.keys(skippedSymbols)[0] })
                    : t('backtest_symbols_skipped', { symbols: Object.keys(skippedSymbols).join('、') })
                }
              />
            )}
            <Row gutter={[16, 16]}>
              {visibleMetricCards(backtestConfig.capital_mode, selectedSymbol).map((spec) => {
                // 指标显式为 null（如 Deflated Sharpe 数据不足）时展示 '—'，着色回退 0
                const raw = backtestData?.metrics?.find((m) => m.key === spec.key)?.value;
                const value = raw ?? 0;
                return (
                  <Col key={spec.key} xs={12} sm={8} md={6} lg={4}>
                    <MetricCard
                      label={spec.label}
                      value={raw == null ? '—' : formatMetricValue(spec, value)}
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
        <Card title={t('backtest_equity_curve')} className="mb-6">
          {getEquityCurve().length > 0 ? (
            <EquityChart data={getEquityCurve()} isDark={isDark} initialCash={backtestData?.backtest_config?.initial_cash} />
          ) : (
            <Empty description={t('no_equity_data')} />
          )}
        </Card>

        {/* 因子分析（品种维度数据，组合视图「全部」下无口径，仅具体品种且配置了 factor_names 时渲染） */}
        {selectedSymbol !== 'all' && backtestData.factors && backtestData.factors.names && backtestData.factors.names.length > 0 && (
          <Card title={t('factor_analysis')} className="mb-6">
            <Space orientation="vertical" size="large" style={{ display: 'flex', width: '100%' }}>
              {/* 因子概览：名称 + 阈值 */}
              <Descriptions bordered column={{ xs: 1, sm: 2, md: 3 }} size="small">
                <Descriptions.Item label={t('backtest_factors_used')}>
                  {backtestData.factors.names.join('、')}
                </Descriptions.Item>
                {Object.entries(backtestData.factors.thresholds || {}).map(([fname, th]) => (
                  <Descriptions.Item key={fname} label={t('backtest_factor_threshold', { name: fname })}>
                    {th.buy != null && `${t('buy')} ≥ ${th.buy}`}
                    {th.buy != null && th.sell != null && ' / '}
                    {th.sell != null && `${t('sell')} ≤ ${th.sell}`}
                  </Descriptions.Item>
                ))}
              </Descriptions>

              {/* 因子时序曲线 */}
              <div>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>{t('backtest_factor_time_series')}</div>
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
                  <div style={{ fontWeight: 600, marginBottom: 8 }}>{t('backtest_factor_attribution', { name: fname })}</div>
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
                      <MetricCard label={t('research_detail_metric_long_short')} value={attr.long_short_return != null ? (attr.long_short_return * 100).toFixed(2) + '%' : 'N/A'} type={attr.long_short_return && attr.long_short_return >= 0 ? 'positive' : 'negative'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label={t('backtest_factor_mean')} value={attr.stats?.mean != null ? attr.stats.mean.toFixed(4) : 'N/A'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label={t('backtest_factor_std')} value={attr.stats?.std != null ? attr.stats.std.toFixed(4) : 'N/A'} />
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
          title={t('trade_details')}
          className="mb-6"
          extra={
            <Space>
              <Button
                type={showAdvancedFilter ? 'primary' : 'default'}
                onClick={() => setShowAdvancedFilter(!showAdvancedFilter)}
              >
                {t('backtest_filter')}
              </Button>
            </Space>
          }
        >
          {/* 高级筛选区域 */}
          {showAdvancedFilter && (
            <div style={{ marginBottom: 16, padding: 16, backgroundColor: 'transparent', border: '1px solid var(--ant-color-border)', borderRadius: 8 }}>
              <Row gutter={[16, 16]} align="middle">
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>{t('backtest_symbols')}</div>
                  <Select
                    value={selectedSymbol}
                    onChange={handleSymbolChange}
                    style={{ width: '100%' }}
                    placeholder={t('select_trading_symbol')}
                  >
                    {/* 「全部」在单/多品种下都可能是当前值，必须始终渲染 */}
                    <Select.Option value="all">{t('all')}</Select.Option>
                    {symbols.map((symbol) => (
                      <Select.Option key={symbol} value={symbol}>
                        {symbol}
                      </Select.Option>
                    ))}
                  </Select>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>{t('direction')}</div>
                  <Select
                    value={filterSide}
                    onChange={setFilterSide}
                    style={{ width: '100%' }}
                    placeholder={t('backtest_side_placeholder')}
                  >
                    <Select.Option value="all">{t('all')}</Select.Option>
                    <Select.Option value="long">{t('long')}</Select.Option>
                    <Select.Option value="short">{t('short')}</Select.Option>
                  </Select>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>{t('backtest_date_range')}</div>
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
                  <Button onClick={resetFilters}>{t('reset')}</Button>
                </Col>
              </Row>
            </div>
          )}

          {/* 筛选结果统计（fills 兜底分支计数跟随展示粒度，避免「共 0 条」与逐笔表矛盾） */}
          <div style={{ marginBottom: 16 }}>
            <span style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)' }}>
              {t('total_count', { count: getTrades().length || (backtestData?.fills_detail?.length ?? 0) })}
              {selectedSymbol !== 'all' && t('backtest_filter_symbol', { v: selectedSymbol })}
              {filterSide !== 'all' && t('backtest_filter_side', { v: filterSide === 'long' ? t('long') : t('short') })}
              {filterDateRange && t('backtest_filter_date', { start: filterDateRange[0], end: filterDateRange[1] })}
            </span>
          </div>

          {getTrades().length > 0 ? (
            <TradeTable data={getTrades()} leverageBySymbol={leverageBySymbol} />
          ) : (backtestData?.fills_detail?.length ?? 0) > 0 ? (
            // round-trip 为空但有逐笔成交（RL 目标仓位策略常态）：展示 fill 粒度明细
            <FillsDetailTable fills={backtestData!.fills_detail!} />
          ) : isLegacyOnly ? (
            <Empty description={t('backtest_legacy_no_trades')} />
          ) : rawTrades.length === 0 ? (
            <Empty
              description={
                getMetricValue('total_trades') > 0
                  ? t('backtest_trades_unclosed', { num: getMetricValue('total_trades') })
                  : t('backtest_no_fills_hint')
              }
            />
          ) : (
            <Empty description={t('no_trade_records')} />
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
            if (d.source === 'fallback') return t('backtest_decider_fallback');
            return t('backtest_decider_other');
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
            // '规则' 是录制数据里 _decider 的历史取值（数据枚举值而非 UI 文案），翻译会导致英文环境下匹配失效，保留原样
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
            <Card title={t('backtest_decision_details')} className="mb-6">
              <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
                {/* 统计摘要 */}
                <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}>
                  {/* 原文案用 <strong> 包住数字，插值词条无法承载富文本，改为整句纯文本 */}
                  <span style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)' }}>
                    {t('backtest_decisions_total', { num: decisions.length.toLocaleString() })}
                  </span>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)' }}>{t('backtest_decider_prefix')}</span>
                    {Object.entries(deciderCounts).map(([dv, cnt]) => (
                      <Tag key={dv} color={deciderColor(dv)}>
                        {dv}: {cnt.toLocaleString()}
                      </Tag>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)' }}>{t('backtest_action_prefix')}</span>
                    {Object.entries(actionCounts).map(([act, cnt]) => (
                      <Tag key={act} color={actionColor[act] || 'default'}>
                        {act === 'buy' ? t('buy') : act === 'sell' ? t('sell') : t('backtest_hold')}: {cnt.toLocaleString()}
                      </Tag>
                    ))}
                  </div>
                </div>
                {Object.keys(reasonCounts).length > 0 && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    <span style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)' }}>{t('backtest_fallback_top')}</span>
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
                    showTotal: (total, range) => t('backtest_page_total', { start: range[0], end: range[1], total: total.toLocaleString() }),
                  }}
                  columns={[
                    {
                      title: t('backtest_time'),
                      dataIndex: '_ts',
                      width: 200,
                      render: (_v: unknown, record: CascadeDecisionRecord) => (
                        <Tooltip title={record._ts}>{fmtDecisionTs(record._ts)}</Tooltip>
                      ),
                    },
                    {
                      title: t('backtest_action'),
                      dataIndex: 'action',
                      width: 80,
                      render: (v: string) => {
                        const label = v === 'buy' ? t('buy') : v === 'sell' ? t('sell') : t('backtest_hold');
                        const color = actionColor[v] || 'default';
                        return <Tag color={color}>{label}</Tag>;
                      },
                    },
                    {
                      title: t('backtest_confidence'),
                      dataIndex: 'confidence',
                      width: 100,
                      align: 'right',
                      render: (v: number) => (v != null ? (v * 100).toFixed(1) + '%' : '-'),
                    },
                    {
                      title: t('backtest_decider'),
                      dataIndex: '_decider',
                      width: 200,
                      ellipsis: true,
                      render: (_v: unknown, record: CascadeDecisionRecord) => {
                        const dv = deciderOf(record);
                        return <Tag color={deciderColor(dv)}>{dv}</Tag>;
                      },
                    },
                    {
                      title: t('backtest_fallback_reason'),
                      dataIndex: 'fallback_reason',
                      ellipsis: true,
                      render: (v: string) => humanizeFallbackReason(v),
                    },
                    {
                      title: t('action'),
                      key: 'detail',
                      width: 80,
                      fixed: 'right' as const,
                      render: (_v: unknown, record: CascadeDecisionRecord) =>
                        record._seq == null ? (
                          <Tooltip title={t('backtest_no_seq_tooltip')}>-</Tooltip>
                        ) : (
                          <Button size="small" onClick={() => setDetailRecord(record)}>
                            {t('details')}
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
          fetchDetail={(seq, fp) => backtestApi.getDecisionDetail(backtestId!, seq, fp)}
          record={detailRecord}
          onClose={() => setDetailRecord(null)}
        />
      </div>

      {/* 全部交易标的弹窗（标的过多时点开查看） */}
      <Modal
        title={t('backtest_all_symbols_title', { num: symbols.length })}
        open={showAllSymbols}
        onCancel={() => setShowAllSymbols(false)}
        footer={<Button onClick={() => setShowAllSymbols(false)}>{t('backtest_close')}</Button>}
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
