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
  Descriptions,
  Space,
  DatePicker,
  Modal,
  Alert,
  Flex,
  Tooltip,
} from 'antd';
import {
  PlayCircleOutlined,
  DownloadOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { backtestApi } from '../../api';
import { getBacktestProgress } from '../../api/backtest';
import DecisionDetailDrawer, { fmtDecisionTs, humanizeFallbackReason } from './DecisionDetailDrawer';
import type { MetricColor } from './metricCards';
import { formatMetricValue, visibleMetricCards } from './metricCards';
import TradeTable, { type Trade } from '../../components/TradeTable';
import {
  buildLeverageMap,
  type BacktestFill,
  type BacktestProgressData,
  type CascadeDecisionRecord,
  type EffectiveMarginSpec,
} from '../../types/backtest';
import EquityChart from '../../components/EquityChart';
import EChart from '@/components/EChart';
import { useQuantColors } from '@/utils/colors';
import PageContainer from '@/components/PageContainer';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import { usePageBack } from '@/hooks/usePageBack';
import { setPageTitle } from '@/utils/pageTitle';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'ahooks';
// 页面级样式（.bt-kpi-grid / .bt-note 等缺口类）：全局原语在 global.css 的 .qc-*
import './backtest.css';

// metricCards 的着色档位 → §6.4 qc-kpi-num 语义类（+表示涨/盈、-表示跌/亏；中性不染色）
const kpiTone = (type: MetricColor): '' | 'up' | 'down' =>
  type === 'positive' ? 'up' : type === 'negative' ? 'down' : '';

/** §6.4 KPI 卡：label 11px → mono 22px/650（语义着色）；hint 悬浮/点击出说明 */
const KpiCard = ({ label, value, tone, hint }: { label: string; value: string; tone?: string; hint?: string }) => (
  <div className="qc-kpi">
    <div className="qc-kpi-top">
      <span className="qc-kpi-lb">{label}</span>
      {hint && (
        <Tooltip title={hint} trigger={['hover', 'click']}>
          <InfoCircleOutlined className="bt-kpi-hint" aria-label={hint} />
        </Tooltip>
      )}
    </div>
    <div className={`qc-kpi-num${tone ? ` ${tone}` : ''}`}>{value}</div>
  </div>
);

// 逐笔成交兜底表：round-trip 稀疏（如 RL 目标仓位策略持仓长期不归零）时
// 在交易详情 Card 内展示 fill 粒度记录，替代误导性的「无完整交易记录」空态
const FillsDetailTable = ({ fills }: { fills: BacktestFill[] }) => {
  const { t } = useTranslation();
  // 客户端分页（fill 是结果 JSON 附属数据，无服务端分页端点）；DataTable 必须受控传 current/onChange
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  return (
    <>
      <Alert type="info" showIcon style={{ marginBottom: 12 }} title={t('backtest_fills_detail_hint')} />
      <DataTable<BacktestFill>
        rowKey="fill_id"
        dataSource={fills}
        scroll={{ x: 'max-content', y: 480 }}
        pagination={{
          current: page,
          pageSize,
          onChange: (p, s) => {
            setPage(p);
            setPageSize(s);
          },
        }}
        columns={[
          { title: t('trade_time'), dataIndex: 'formatted_time', key: 'ft', render: (v: string) => <span className="qc-mono">{v || '—'}</span> },
          {
            title: t('direction'),
            dataIndex: 'side',
            key: 'side',
            render: (v: string) => (v === 'buy'
              ? <span className="qc-chip ok">{t('buy')}</span>
              : <span className="qc-chip down">{t('sell')}</span>),
          },
          { title: t('price'), dataIndex: 'price', key: 'p', align: 'right', render: (v: number) => <span className="qc-mono">{v?.toFixed(4)}</span> },
          { title: t('quantity'), dataIndex: 'quantity', key: 'q', align: 'right', render: (v: number) => <span className="qc-mono">{v?.toFixed(4)}</span> },
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
    margin_specs?: EffectiveMarginSpec[];
    // 创建回测时的策略参数（后端入库时随 backtest_config 保存；旧任务可能缺失）
    strategy_params?: Record<string, unknown>;
    // 创建回测时的按标的策略参数覆盖（后端入库随 backtest_config 保存；旧任务缺失）
    strategy_params_by_symbol?: Record<string, Record<string, unknown>>;
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
  shortfall_count?: number;
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
  // failed 任务的失败原因：progress 接口的 error.message（内存态快照，服务重启后取不到 → 整块不渲染）
  const [progress, setProgress] = useState<BacktestProgressData | null>(null);

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

  // failed 任务补失败原因（列表行内摘要同源：progress 接口 error.message）。
  // 快照只在内存里，服务重启后的旧任务接口返回空 → 页面只留状态 chip，不编原因
  useEffect(() => {
    if (!backtestId || backtestData?.status !== 'failed') return;
    let cancelled = false;
    getBacktestProgress(backtestId).then((data) => {
      if (!cancelled && data) setProgress(data);
    });
    return () => {
      cancelled = true;
    };
  }, [backtestId, backtestData?.status]);

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
  const getEquityCurve = (): Array<{ datetime: string; equity: number; balance: number }> => {
    return (backtestData?.equity_curve || []).map(point => ({
      datetime: point.formatted_time || new Date(point.timestamp * 1000).toISOString(),
      equity: point.equity,
      balance: point.balance,
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
          <QcEmpty title={t('backtest_not_found')} />
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
      : backtestConfig.margin_specs ?? [];
  const marginApplied = backtestData.margin_applied ?? false;
  // 交易表「保证金占用」列的口径来源：仅启用保证金时传杠杆，否则表格不渲染该列
  const leverageBySymbol: Record<string, number> | undefined = buildLeverageMap(marginApplied, effectiveSpecs);
  const liquidationCount = backtestData.liquidation_count ?? 0;
  const shortfallCount = backtestData.shortfall_count ?? 0;
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

  // §6.2 状态徽章：完成=ok、运行中=info+呼吸点、失败=down、等待中=quiet；未知值原样展示（数据枚举）
  const statusChip = (status: string) => {
    switch (status) {
      case 'completed':
        return <span className="qc-chip ok">{t('status_completed')}</span>;
      case 'running':
      case 'in_progress':
        return <span className="qc-chip info"><span className="qc-pdot" />{t('status_running')}</span>;
      case 'failed':
        return <span className="qc-chip down">{t('status_failed')}</span>;
      case 'pending':
        return <span className="qc-chip quiet">{t('status_pending')}</span>;
      default:
        return <span className="qc-chip quiet">{status}</span>;
    }
  };

  // 页头副标只写真实数据（§5）：标的（最多 3 个，余量以 … 收尾）· 周期 · 回测区间
  const symbolsLabel = symbols.length
    ? `${symbols.slice(0, 3).join(',')}${symbols.length > 3 ? '…' : ''}`
    : '';
  const rangeLabel = backtestConfig.start_time && backtestConfig.end_time
    ? `${backtestConfig.start_time} → ${backtestConfig.end_time}`
    : '';
  const detailSubtitle = [symbolsLabel, backtestConfig.interval, rangeLabel].filter(Boolean).join(' · ') || undefined;

  // 失败原因块（failed 才有；progress.error 缺失即不渲染，只留状态 chip）
  const failMessage = backtestData.status === 'failed' ? progress?.error?.message : undefined;

  return (
    <PageContainer
      title={`${strategyName} - ${t('backtest_detail')}`}
      subtitle={detailSubtitle}
      onBack={handleBack}
      actions={
        <>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleReplay}
            style={{ height: 30, padding: '0 12px', fontSize: 12, fontWeight: 550 }}
          >
            {t('replay')}
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExport}
            loading={exporting}
            style={{ height: 30, padding: '0 12px', fontSize: 12 }}
          >
            {t('export_report')}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {/* 失败原因：放页首，避免 failed 任务（KPI 全空）看起来像空壳；原文 mono 可换行 */}
        {failMessage && (
          <div className="bt-fail-block">
            <div className="bt-fail-title">
              {t('bt_fail_reason')}
              {progress?.error?.stage ? ` · ${progress.error.stage}` : ''}
            </div>
            <div className="qc-mono bt-fail-text">{failMessage}</div>
          </div>
        )}
        {/* 配置信息 */}
        <Card title={t('config_info')} className="qc-card">
          <Flex vertical gap={12}>
          <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3, lg: 4 }}>
            <Descriptions.Item label={t('backtest_strategy_name')}>
              {strategyName}
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_symbols')}>
              {symbols.length === 0 ? '—' : (
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
              <span className="qc-mono">{backtestConfig.interval || '—'}</span>
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_trading_mode')}>
              {backtestConfig.trading_mode === 'futures' ? t('backtest_futures') : t('spot')}
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_period')}>
              {backtestConfig.start_time && backtestConfig.end_time
                ? <span className="qc-mono">{t('backtest_date_span', { start: backtestConfig.start_time, end: backtestConfig.end_time })}</span>
                : '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_initial_cash')}>
              <span className="qc-mono">{formatNumber(backtestConfig.initial_cash || 0)}</span>
            </Descriptions.Item>
            <Descriptions.Item label={t('backtest_capital_mode')}>
              {backtestConfig.capital_mode === 'shared' ? t('backtest_capital_shared') : t('backtest_capital_per_symbol')}
            </Descriptions.Item>
            <Descriptions.Item label={t('status')}>
              {statusChip(backtestData.status)}
            </Descriptions.Item>
          </Descriptions>
          {/* 杠杆与保证金：整块常显，未启用时明确告诉用户「没算保证金」，而不是悄悄消失 */}
          <div>
            <div className="bt-subhead">{t('backtest_margin_specs')}</div>
            <Space size={4} wrap>
              {effectiveSpecs.map((item) => (
                <span key={item.symbol} className="qc-chip quiet">
                  {`${item.symbol} ${item.leverage}x ${item.margin_mode === 'isolated' ? t('backtest_margin_isolated') : t('backtest_margin_cross')} · ${bracketSourceLabel(item)}`}
                </span>
              ))}
              {marginApplied && (
                <>
                  <span className="qc-chip info">{t('backtest_liquidation_count', { num: liquidationCount })}</span>
                  {shortfallCount > 0 && (
                    <span className="qc-chip warn">{t('backtest_shortfall_count', { num: shortfallCount })}</span>
                  )}
                </>
              )}
            </Space>
            {!marginApplied && (
              <div className="bt-note" style={{ marginTop: 6 }}>
                {t('backtest_margin_disabled_hint')}
              </div>
            )}
          </div>
          {/* 策略参数独占一块：参数条目数量不定，塞进 Descriptions 格子会显示不全 */}
          <div>
            <div className="bt-subhead">{t('strategy_params')}</div>
            {Object.keys(backtestConfig.strategy_params || {}).length === 0 ? (
              <span className="qc-mono qc-cell-none">—</span>
            ) : (
              <Space size={4} wrap>
                {Object.entries(backtestConfig.strategy_params!).map(([k, v]) => (
                  <span key={k} className="qc-chip quiet">
                    {/* 参数可能为 null（未设上限/未启用），别把 JS 的 "null" 当值展示 */}
                    <span className="qc-mono">{`${k}: ${v == null ? '—' : String(v)}`}</span>
                  </span>
                ))}
              </Space>
            )}
          </div>
          {/* 按标的参数覆盖展示（spec 2026-11-28 §5.2；无覆盖项时不渲染） */}
          {Object.keys(backtestConfig.strategy_params_by_symbol || {}).length > 0 && (
            <div className="bt-subhead" style={{ marginTop: 12 }}>{t('strategyParams.override_button')}</div>
          )}
          {Object.entries(backtestConfig.strategy_params_by_symbol || {}).map(([sym, ov]) => (
            <div key={sym} className="bt-kv-row" style={{ fontSize: 12 }}>
              {sym}：{JSON.stringify(ov)}
            </div>
          ))}
          </Flex>
        </Card>

        {/* 强平记录：逐档部分强平的审计视图；无事件（含旧任务缺失字段）时整块不渲染 */}
        {liquidationEvents.length > 0 && (
          <Card title={t('backtest_liquidation_records')} className="qc-card">
            <Flex vertical gap={12}>
              {insuranceFundLoss > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  title={t('backtest_insurance_fund_loss', { v: formatNumber(insuranceFundLoss) })}
                />
              )}
              <DataTable<LiquidationEventRecord>
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
                    render: (value: number) => <span className="qc-mono">{new Date(value / 1e6).toLocaleString()}</span>,
                  },
                  { title: t('backtest_symbol'), dataIndex: 'symbol', render: (value: string) => <span className="qc-mono">{value}</span> },
                  {
                    title: t('backtest_mode'),
                    dataIndex: 'margin_mode',
                    render: (value: string) => (value === 'isolated' ? t('backtest_margin_isolated') : t('backtest_margin_cross')),
                  },
                  {
                    title: t('backtest_tier'),
                    render: (_: unknown, record: LiquidationEventRecord) =>
                      <span className="qc-mono">{`${record.tier_from ?? '—'} → ${record.tier_to ?? '—'}`}</span>,
                  },
                  {
                    title: t('backtest_reduced_qty'),
                    dataIndex: 'reduced_qty',
                    align: 'right',
                    render: (value: number) => <span className="qc-mono">{formatNumber(value ?? 0, 4)}</span>,
                  },
                  {
                    title: t('backtest_liquidation_fee'),
                    dataIndex: 'fee',
                    align: 'right',
                    render: (value: number) => <span className="qc-mono">{formatNumber(value ?? 0)}</span>,
                  },
                ]}
              />
            </Flex>
          </Card>
        )}

        {/* 回测概览指标（多品种时右上角切换品种，指标/曲线/成交均按品种展示） */}
        <Card
          title={t('backtest_overview')}
          className="qc-card"
          extra={isMultiSymbol && symbols.length > 0 ? (
            <Space>
              <span className="bt-subhead" style={{ margin: 0 }}>{t('backtest_symbol')}</span>
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
          <Flex vertical gap={12}>
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
            <div className="bt-kpi-grid">
              {visibleMetricCards(backtestConfig.capital_mode, selectedSymbol).map((spec) => {
                // 指标显式为 null（如 Deflated Sharpe 数据不足）时展示 '—'，着色回退 0
                const raw = backtestData?.metrics?.find((m) => m.key === spec.key)?.value;
                const value = raw ?? 0;
                return (
                  <KpiCard
                    key={spec.key}
                    label={spec.label}
                    value={raw == null ? '—' : formatMetricValue(spec, value)}
                    tone={kpiTone(spec.color(value, getMetricValue))}
                    hint={spec.hint}
                  />
                );
              })}
            </div>
          </Flex>
        </Card>

        {/* 绩效分析图表 */}
        <Card title={t('backtest_equity_curve')} className="qc-card">
          {getEquityCurve().length > 0 ? (
            <EquityChart data={getEquityCurve()} isDark={isDark} initialCash={backtestData?.backtest_config?.initial_cash} />
          ) : (
            <QcEmpty title={t('no_equity_data')} />
          )}
        </Card>

        {/* 因子分析（品种维度数据，组合视图「全部」下无口径，仅具体品种且配置了 factor_names 时渲染） */}
        {selectedSymbol !== 'all' && backtestData.factors && backtestData.factors.names && backtestData.factors.names.length > 0 && (
          <Card title={t('factor_analysis')} className="qc-card">
            <Space orientation="vertical" size="large" style={{ display: 'flex', width: '100%' }}>
              {/* 因子概览：名称 + 阈值 */}
              <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }}>
                <Descriptions.Item label={t('backtest_factors_used')}>
                  <span className="qc-mono">{backtestData.factors.names.join('、')}</span>
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
                <div className="bt-subhead" style={{ marginTop: 0 }}>{t('backtest_factor_time_series')}</div>
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
                  <div className="bt-subhead" style={{ marginTop: 0 }}>{t('backtest_factor_attribution', { name: fname })}</div>
                  <div className="bt-kpi-grid">
                    <KpiCard label="IC" value={attr.ic != null ? attr.ic.toFixed(4) : '—'} tone={kpiTone(attr.ic && attr.ic >= 0 ? 'positive' : 'negative')} />
                    <KpiCard label="Rank IC" value={attr.rank_ic != null ? attr.rank_ic.toFixed(4) : '—'} tone={kpiTone(attr.rank_ic && attr.rank_ic >= 0 ? 'positive' : 'negative')} />
                    <KpiCard label="ICIR" value={attr.icir != null ? attr.icir.toFixed(4) : '—'} />
                    <KpiCard label={t('research_detail_metric_long_short')} value={attr.long_short_return != null ? (attr.long_short_return * 100).toFixed(2) + '%' : '—'} tone={kpiTone(attr.long_short_return && attr.long_short_return >= 0 ? 'positive' : 'negative')} />
                    <KpiCard label={t('backtest_factor_mean')} value={attr.stats?.mean != null ? attr.stats.mean.toFixed(4) : '—'} />
                    <KpiCard label={t('backtest_factor_std')} value={attr.stats?.std != null ? attr.stats.std.toFixed(4) : '—'} />
                  </div>
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
          className="qc-card"
          extra={
            <Button
              size="small"
              type={showAdvancedFilter ? 'primary' : 'default'}
              onClick={() => setShowAdvancedFilter(!showAdvancedFilter)}
            >
              {t('backtest_filter')}
            </Button>
          }
        >
          {/* 高级筛选区域（§4 内嵌面板） */}
          {showAdvancedFilter && (
            <div className="bt-filter-box">
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
          <div style={{ marginBottom: 12 }}>
            <span className="bt-note">
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
            <QcEmpty title={t('backtest_legacy_no_trades')} />
          ) : rawTrades.length === 0 ? (
            <QcEmpty
              title={
                getMetricValue('total_trades') > 0
                  ? t('backtest_trades_unclosed', { num: getMetricValue('total_trades') })
                  : t('backtest_no_fills_hint')
              }
            />
          ) : (
            <QcEmpty title={t('no_trade_records')} />
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

          // 决策者 chip 语义（§6.2）：S1=info、S2=pri、规则=ok；回放/兜底/其他走 neutral
          const deciderClassOf = (v: string): string => {
            if (v.startsWith('S1')) return 'info';
            if (v.startsWith('S2')) return 'pri';
            // '规则' 是录制数据里 _decider 的历史取值（数据枚举值而非 UI 文案），翻译会导致英文环境下匹配失效，保留原样
            if (v === '规则') return 'ok';
            return 'quiet'; // 回放 / 降级兜底 / 其他 → 中性
          };
          // 新决策 action 词表为 long/short（Rust cascade 方向语义）；历史报表仍存 buy/sell，两套都备齐
          // §6.2 盈亏方向语义：开多/买入=ok、开空/卖出=down、持有=quiet
          const actionClasses: Record<string, string> = {
            long: 'ok',
            short: 'down',
            buy: 'ok',
            sell: 'down',
            hold: 'quiet',
          };
          const actionLabel = (v: string) =>
            v === 'long' || v === 'buy'
              ? t('long')
              : v === 'short' || v === 'sell'
                ? t('short')
                : t('backtest_hold');

          // 只展示前 100 条 + 分页，3 万条全渲染卡浏览器
          const PAGE_SIZE = 200;

          return (
            <Card title={t('backtest_decision_details')} className="qc-card">
              <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
                {/* 统计摘要 */}
                <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}>
                  {/* 原文案用 <strong> 包住数字，插值词条无法承载富文本，改为整句纯文本 */}
                  <span className="bt-note">
                    {t('backtest_decisions_total', { num: decisions.length.toLocaleString() })}
                  </span>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span className="bt-note">{t('backtest_decider_prefix')}</span>
                    {Object.entries(deciderCounts).map(([dv, cnt]) => (
                      <span key={dv} className={`qc-chip ${deciderClassOf(dv)}`}>
                        {dv}: <span className="qc-mono">{cnt.toLocaleString()}</span>
                      </span>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span className="bt-note">{t('backtest_action_prefix')}</span>
                    {Object.entries(actionCounts).map(([act, cnt]) => (
                      <span key={act} className={`qc-chip ${actionClasses[act] || 'quiet'}`}>
                        {actionLabel(act)}: <span className="qc-mono">{cnt.toLocaleString()}</span>
                      </span>
                    ))}
                  </div>
                </div>
                {Object.keys(reasonCounts).length > 0 && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    <span className="bt-note">{t('backtest_fallback_top')}</span>
                    {Object.entries(reasonCounts)
                      .sort((a, b) => b[1] - a[1])
                      .slice(0, 5)
                      .map(([reason, cnt]) => (
                        <span key={reason} className="qc-chip quiet">
                          {humanizeFallbackReason(reason)}: <span className="qc-mono">{cnt.toLocaleString()}</span>
                        </span>
                      ))}
                  </div>
                )}

                {/* 决策表格（只展示前 … 分页由 DataTable 承接，3 万条全渲染卡浏览器） */}
                <DataTable<CascadeDecisionRecord>
                  scroll={{ x: 'max-content' }}
                  dataSource={decisions}
                  rowKey={(_, idx) => String(idx)}
                  pagination={{
                    pageSize: PAGE_SIZE,
                    showSizeChanger: false,
                  }}
                  columns={[
                    {
                      title: t('backtest_time'),
                      dataIndex: '_ts',
                      width: 200,
                      render: (_v: unknown, record: CascadeDecisionRecord) => (
                        <Tooltip title={record._ts}>
                          <span className="qc-mono">{fmtDecisionTs(record._ts)}</span>
                        </Tooltip>
                      ),
                    },
                    {
                      title: t('backtest_action'),
                      dataIndex: 'action',
                      width: 90,
                      render: (v: string) => (
                        <span className={`qc-chip ${actionClasses[v] || 'quiet'}`}>{actionLabel(v)}</span>
                      ),
                    },
                    {
                      title: t('backtest_confidence'),
                      dataIndex: 'confidence',
                      width: 110,
                      align: 'right',
                      render: (v: number) =>
                        v != null
                          ? <span className="qc-mono">{(v * 100).toFixed(1)}%</span>
                          : <span className="qc-cell-none">—</span>,
                    },
                    {
                      title: t('backtest_decider'),
                      dataIndex: '_decider',
                      width: 200,
                      ellipsis: true,
                      render: (_v: unknown, record: CascadeDecisionRecord) => {
                        const dv = deciderOf(record);
                        return <span className={`qc-chip ${deciderClassOf(dv)}`}>{dv}</span>;
                      },
                    },
                    {
                      title: t('backtest_fallback_reason'),
                      dataIndex: 'fallback_reason',
                      ellipsis: true,
                      render: (v: string) => (v ? humanizeFallbackReason(v) : <span className="qc-cell-none">—</span>),
                    },
                    {
                      title: t('action'),
                      key: 'detail',
                      width: 80,
                      fixed: 'right' as const,
                      render: (_v: unknown, record: CascadeDecisionRecord) =>
                        record._seq == null ? (
                          <Tooltip title={t('backtest_no_seq_tooltip')}>
                            <span className="qc-cell-none">—</span>
                          </Tooltip>
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
        className="qc-modal"
      >
        <div style={{ maxHeight: 500, overflowY: 'auto' }}>
          <Space wrap size={[8, 8]}>
            {symbols.map((s) => (
              <span key={s} className="qc-chip quiet">
                <span className="qc-mono">{s}</span>
              </span>
            ))}
          </Space>
        </div>
      </Modal>
    </PageContainer>
  );
};

export default BacktestDetail;
