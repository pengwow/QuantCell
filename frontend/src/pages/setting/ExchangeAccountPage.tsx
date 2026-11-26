/**
 * 账户总览（真实数据版）
 * 路由 /setting/exchange-account，由交易所设置页「账户总览」按钮进入。
 * 数据来自 GET /exchanges/account-snapshot：后端按已保存的交易所配置
 * （live → 实盘端点；testnet → 币安模拟盘 demo-api/demo-fapi）拉取
 * 余额 / 持仓 / 委托 / 成交。筛选、检索、图表与 CSV 导出均为本地实现。
 * 未配置密钥 → 引导空态；部分接口失败 → 区块级告警，不整页阻塞。
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Empty,
  Input,
  Progress,
  Segmented,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { IconDownload, IconRefresh } from "@tabler/icons-react";
import dayjs, { type Dayjs } from "dayjs";
import type { EChartsOption, TooltipComponentFormatterCallbackParams } from "echarts";
import PageContainer from "@/components/PageContainer";
import EChart from "@/components/EChart";
import { useQuantColors } from "@/utils/colors";
import { exchangeApi } from "@/api";
import {
  assetDonut,
  fmtNum,
  fmtSigned,
  orderInViewStatus,
  positionPnl,
  toCsv,
} from "./exacctData";
import type { AccountSnapshot, OrderRow, OrderStatus, PositionRow, TradeRow } from "./exacctData";

const { RangePicker } = DatePicker;
const { Text } = Typography;

type Range = [Dayjs | null, Dayjs | null] | null;
type AcctTab = "spot" | "futures";
type PosTab = "pos" | "risk";

// 语义色（正/负）取主题令牌，区分盈亏、多空、买卖
const pnlColor = (v: number) =>
  v >= 0 ? "var(--qc-success)" : "var(--qc-error)";

const ExchangeAccountPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const exchangeId = params.get("exchange") || "binance";
  // 环境来自入口显式携带（设置页正在查看的环境，可能尚未保存）；不传则由后端按已保存配置决定
  const envParam = params.get("env") || "";
  const qc = useQuantColors();
  // 缓存在后端（+定时同步，间隔 5min）：进入时后端命中即秒回（旧数据 + 旧「刷新于」），
  // 手动刷新按钮带 refresh=1 强制拉新。
  const [snap, setSnap] = useState<AccountSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  const [acctTab, setAcctTab] = useState<AcctTab>("spot");
  const [posTab, setPosTab] = useState<PosTab>("pos");
  const [orderStatus, setOrderStatus] = useState<OrderStatus | "all">("all");
  const [orderRange, setOrderRange] = useState<Range>(null);
  const [tradeSearch, setTradeSearch] = useState("");
  const [tradeRange, setTradeRange] = useState<Range>(null);
  const [distTab, setDistTab] = useState<"coin" | "account">("coin");

  const fetchSnap = useCallback(
    async (refresh = false) => {
      setLoading(true);
      try {
        const data = await exchangeApi.getAccountSnapshot(exchangeId, envParam, refresh);
        setSnap(data);
        setLoadErr(null);
      } catch (e) {
        setLoadErr(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [exchangeId, envParam]
  );

  useEffect(() => {
    void fetchSnap(); // 进入：吃后端缓存秒回（首次无缓存会同步等一次）
  }, [fetchSnap]);

  const err = snap?.errors ?? {};
  const spotRows = useMemo(() => snap?.spot?.balances ?? [], [snap]);
  const spotTotal = snap?.spot?.totalUsdt ?? 0;
  const fut = snap?.futures?.totals ?? null;
  const positions = useMemo(() => snap?.futures?.positions ?? [], [snap]);

  const futEquity = fut?.equityUsdt ?? snap?.futures?.equityUsdt ?? 0;
  const futUnrealized = fut?.unrealizedUsdt ?? snap?.futures?.unrealizedUsdt ?? 0;
  const futAvailable = fut?.availableUsdt ?? 0;
  const futUsed = fut?.usedUsdt ?? positions.reduce((s, p) => s + p.initialMargin, 0);
  const futUsage = futEquity > 0 ? futUsed / futEquity : 0;

  const spotFreeValue = spotRows.reduce((s, r) => s + r.free * (r.priceUsdt ?? 0), 0);
  const spotFrozenValue = spotRows.reduce((s, r) => s + r.used * (r.priceUsdt ?? 0), 0);

  const totalAsset = spotTotal + futEquity;
  const available = spotFreeValue + futAvailable;
  const frozen = spotFrozenValue + futUsed;

  // ── 图表 ──────────────────────────────────────────────────
  const byCoin = useMemo(
    () => assetDonut(spotRows, { name: t("exacct_tab_futures"), value: futEquity }),
    [spotRows, futEquity, t]
  );
  const byAccount = useMemo(
    () =>
      [
        { name: t("exacct_tab_spot"), value: spotTotal },
        { name: t("exacct_tab_futures"), value: futEquity },
      ].filter((r) => r.value > 0),
    [spotTotal, futEquity, t]
  );
  const distData = distTab === "coin" ? byCoin : byAccount;
  const loadedAt = snap?.fetchedAt ? dayjs(snap.fetchedAt) : null;
  const pieOption: EChartsOption = useMemo(
    () => ({
      tooltip: {
        trigger: "item",
        formatter: (p: TooltipComponentFormatterCallbackParams) => {
          const d = (Array.isArray(p) ? p[0] : p) as unknown as { name: string; value: number; percent: number };
          return `${d.name}<br/>${fmtNum(d.value, 2)} USDT (${d.percent}%)`;
        },
      },
      legend: {
        bottom: 0,
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { color: qc.chartAxis, fontSize: 11 },
      },
      title: {
        text: fmtNum(totalAsset, 0),
        subtext: "USDT",
        left: "center",
        top: "36%",
        textStyle: { color: qc.chartAxis, fontSize: 20, fontWeight: 650 },
        subtextStyle: { color: qc.chartAxis, fontSize: 10 },
      },
      series: [
        {
          type: "pie",
          radius: ["48%", "70%"],
          center: ["50%", "44%"],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 4, borderColor: qc.chartSplit, borderWidth: 2 },
          label: { color: qc.chartAxis, fontSize: 11, formatter: "{b} {d}%" },
          data: distData,
        },
      ],
    }),
    [distData, totalAsset, qc]
  );

  // ── 筛选 ──────────────────────────────────────────────────
  const inRange = (time: number, range: Range) => {
    if (!range || !range[0] || !range[1]) return true;
    const d = dayjs(time);
    return !d.isBefore(range[0].startOf("day")) && !d.isAfter(range[1].endOf("day"));
  };
  const orderRowsAll: OrderRow[] = snap?.orders ?? [];
  const filteredOrders = orderRowsAll.filter((o) => {
    const st = orderInViewStatus(o);
    return (orderStatus === "all" || st === orderStatus) && inRange(o.time, orderRange);
  });
  const filteredTrades = (snap?.trades ?? []).filter(
    (r: TradeRow) =>
      r.pair.toLowerCase().includes(tradeSearch.trim().toLowerCase()) &&
      inRange(r.time, tradeRange)
  );

  // ── 导出 CSV ──────────────────────────────────────────────
  const handleExport = () => {
    const headers = [
      t("exacct_col_time"),
      t("exacct_col_pair"),
      t("exacct_col_side"),
      t("exacct_col_trade_price"),
      t("exacct_col_qty"),
      t("exacct_col_turnover"),
      t("exacct_col_fee"),
    ];
    const rows = filteredTrades.map((r: TradeRow) => [
      dayjs(r.time).format("YYYY-MM-DD HH:mm:ss"),
      r.pair,
      r.side === "buy" ? t("exacct_side_buy") : t("exacct_side_sell"),
      fmtNum(r.price, r.price < 10 ? 4 : 2),
      fmtNum(r.qty, r.qty < 10 ? 4 : 0),
      fmtNum(r.price * r.qty, 2),
      fmtNum(r.fee, 2),
    ]);
    const blob = new Blob([toCsv(headers, rows)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trades_${dayjs().format("YYYYMMDD_HHmmss")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── 列定义 ────────────────────────────────────────────────
  const spotCols: ColumnsType<(typeof spotRows)[number]> = [
    { title: t("exacct_col_coin"), dataIndex: "currency", width: 90, render: (v: string) => <span className="font-medium">{v}</span> },
    { title: t("exacct_col_available"), dataIndex: "free", align: "right", render: (v: number) => fmtNum(v, 4) },
    { title: t("exacct_col_frozen"), dataIndex: "used", align: "right", render: (v: number) => fmtNum(v, 4) },
    {
      title: t("exacct_col_value", { quote: snap?.quote || "USDT" }),
      key: "value",
      align: "right",
      render: (_: unknown, r) =>
        r.priceUsdt == null ? (
          <Text type="secondary">—</Text> // 行情缺失，无法估值
        ) : (
          fmtNum(r.valueUsdt, 2)
        ),
    },
    {
      title: t("exacct_col_weight"),
      key: "weight",
      align: "right",
      width: 150,
      render: (_: unknown, r) => {
        const pct = spotTotal > 0 && r.priceUsdt != null ? (r.valueUsdt / spotTotal) * 100 : 0;
        return (
          <div className="flex items-center justify-end gap-2">
            <span className="tabular-nums">{pct.toFixed(1)}%</span>
            <Progress
              percent={pct}
              showInfo={false}
              size="small"
              style={{ width: 64, margin: 0 }}
              strokeColor="var(--qc-primary)"
              railColor="var(--qc-surface-muted)"
            />
          </div>
        );
      },
    },
  ];

  const sideTag = (side: "long" | "short") => (
    <Tag
      style={{
        color: side === "long" ? "var(--qc-success)" : "var(--qc-error)",
        background: side === "long" ? "var(--qc-success-soft-bg)" : "var(--qc-error-soft-bg)",
        border: "none",
        marginInlineEnd: 0,
      }}
    >
      {side === "long" ? t("exacct_side_long") : t("exacct_side_short")}
    </Tag>
  );

  const statusTag = (s: OrderStatus) => {
    const map: Record<OrderStatus, { key: string; color?: string }> = {
      filled: { key: "exacct_status_filled", color: "success" },
      partial: { key: "exacct_status_partial", color: "warning" },
      open: { key: "exacct_status_open" },
      canceled: { key: "exacct_status_canceled" },
    };
    const m = map[s];
    return m.color ? <Tag color={m.color}>{t(m.key)}</Tag> : <Tag>{t(m.key)}</Tag>;
  };

  const riskColor = (v: number) =>
    v < 50 ? "var(--qc-success)" : v < 75 ? "var(--qc-warning)" : "var(--qc-error)";

  const posCols: ColumnsType<PositionRow> = [
    { title: t("exacct_col_pair"), dataIndex: "pair", render: (v: string) => <span className="font-medium">{v}</span> },
    { title: t("exacct_col_side"), dataIndex: "side", width: 80, render: (v: "long" | "short") => sideTag(v) },
    { title: t("exacct_col_leverage"), dataIndex: "leverage", width: 70, align: "right", render: (v: number) => `${v}x` },
    { title: t("exacct_col_qty"), dataIndex: "qty", align: "right", render: (v: number) => fmtNum(v, v < 100 ? 4 : 0) },
    { title: t("exacct_col_entry"), dataIndex: "entry", align: "right", render: (v: number) => fmtNum(v, v < 10 ? 4 : 2) },
    {
      title: t("exacct_col_mark"),
      dataIndex: "mark",
      align: "right",
      render: (v: number) => <span className="tabular-nums">{fmtNum(v, v < 10 ? 4 : 2)}</span>,
    },
    {
      title: t("exacct_col_breakeven"),
      dataIndex: "breakeven",
      align: "right",
      render: (v: number) => (v > 0 ? <span className="tabular-nums">{fmtNum(v, v < 10 ? 4 : 2)}</span> : <Text type="secondary">—</Text>),
    },
    {
      title: t("exacct_col_liq"),
      dataIndex: "liqPrice",
      align: "right",
      render: (v: number) => (v > 0 ? <span style={{ color: "var(--qc-warning)" }}>{fmtNum(v, v < 10 ? 4 : 2)}</span> : <Text type="secondary">—</Text>),
    },
    {
      title: t("exacct_kpi_unrealized"),
      key: "unrealized",
      align: "right",
      render: (_: unknown, p) => {
        const u = positionPnl(p);
        return <span style={{ color: pnlColor(u) }}>{fmtSigned(u, 2)}</span>;
      },
    },
    {
      title: t("exacct_col_roi"),
      key: "roi",
      align: "right",
      render: (_: unknown, p) => {
        const roi = p.initialMargin > 0 ? (positionPnl(p) / p.initialMargin) * 100 : 0;
        return <span style={{ color: pnlColor(roi) }}>{fmtSigned(roi, 2)}%</span>;
      },
    },
  ];

  // 保证金视图列组：维持保证金/保证金比率/强平价 —— 本质是风险敞口列
  const riskCols: ColumnsType<PositionRow> = [
    { title: t("exacct_col_pair"), dataIndex: "pair", render: (v: string) => <span className="font-medium">{v}</span> },
    {
      title: t("exacct_pos_mode"),
      dataIndex: "mode",
      width: 80,
      render: (v: string) => (
        <Tag>{v === "isolated" ? t("exacct_isolated") : t("exacct_cross")}</Tag>
      ),
    },
    { title: t("exacct_col_leverage"), dataIndex: "leverage", width: 70, align: "right", render: (v: number) => `${v}x` },
    { title: t("exacct_col_margin"), dataIndex: "initialMargin", align: "right", render: (v: number) => fmtNum(v, 2) },
    { title: t("exacct_col_maint"), dataIndex: "maintMargin", align: "right", render: (v: number) => fmtNum(v, 2) },
    {
      title: t("exacct_col_liq"),
      dataIndex: "liqPrice",
      align: "right",
      render: (v: number) => (v > 0 ? fmtNum(v, v < 10 ? 4 : 2) : <Text type="secondary">—</Text>),
    },
    {
      title: t("exacct_col_ratio"),
      dataIndex: "marginRatio",
      width: 170,
      render: (v: number) =>
        v > 0 ? (
          <div className="flex items-center gap-2">
            <span className="tabular-nums" style={{ color: riskColor(v) }}>{v.toFixed(2)}%</span>
            <Progress
              percent={v}
              showInfo={false}
              size="small"
              style={{ width: 72, margin: 0 }}
              strokeColor={riskColor(v)}
              railColor="var(--qc-surface-muted)"
            />
          </div>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
  ];

  const orderCols: ColumnsType<OrderRow> = [
    { title: t("exacct_col_time"), dataIndex: "time", width: 170, render: (v: number) => dayjs(v).format("MM-DD HH:mm:ss") },
    { title: t("exacct_col_pair"), dataIndex: "pair", render: (v: string) => <span className="font-medium">{v}</span> },
    { title: t("exacct_col_type"), dataIndex: "type", width: 80, render: (v: "limit" | "market") => <Tag>{v === "limit" ? t("exacct_type_limit") : t("exacct_type_market")}</Tag> },
    {
      title: t("exacct_col_side"),
      dataIndex: "side",
      width: 80,
      render: (v: "buy" | "sell") => (
        <span style={{ color: v === "buy" ? "var(--qc-success)" : "var(--qc-error)" }}>
          {v === "buy" ? t("exacct_side_buy") : t("exacct_side_sell")}
        </span>
      ),
    },
    { title: t("exacct_col_order_price"), dataIndex: "price", align: "right", render: (v: number) => fmtNum(v, v < 10 ? 4 : 2) },
    { title: t("exacct_col_order_qty"), dataIndex: "qty", align: "right", render: (v: number) => fmtNum(v, v < 100 ? 4 : 0) },
    { title: t("exacct_col_filled_qty"), dataIndex: "filled", align: "right", render: (v: number) => fmtNum(v, v < 100 ? 4 : 0) },
    {
      title: t("exacct_col_status"),
      key: "status",
      width: 100,
      render: (_: unknown, o) => statusTag(orderInViewStatus(o)),
    },
  ];

  const tradeCols: ColumnsType<TradeRow> = [
    { title: t("exacct_col_time"), dataIndex: "time", width: 170, render: (v: number) => dayjs(v).format("MM-DD HH:mm:ss") },
    { title: t("exacct_col_pair"), dataIndex: "pair", render: (v: string) => <span className="font-medium">{v}</span> },
    {
      title: t("exacct_col_side"),
      dataIndex: "side",
      width: 80,
      render: (v: "buy" | "sell") => (
        <span style={{ color: v === "buy" ? "var(--qc-success)" : "var(--qc-error)" }}>
          {v === "buy" ? t("exacct_side_buy") : t("exacct_side_sell")}
        </span>
      ),
    },
    { title: t("exacct_col_trade_price"), dataIndex: "price", align: "right", render: (v: number) => fmtNum(v, v < 10 ? 4 : 2) },
    { title: t("exacct_col_qty"), dataIndex: "qty", align: "right", render: (v: number) => fmtNum(v, v < 100 ? 4 : 0) },
    { title: t("exacct_col_turnover"), key: "turnover", align: "right", render: (_: unknown, r) => fmtNum(r.price * r.qty, 2) },
    {
      title: t("exacct_col_fee"),
      dataIndex: "fee",
      align: "right",
      render: (v: number) => (v > 0 ? fmtNum(v, 2) : <Text type="secondary">—</Text>),
    },
  ];

  // ── 卡片片段 ──────────────────────────────────────────────
  const kpis = [
    { label: t("exacct_kpi_total_asset"), value: fmtNum(totalAsset, 2), color: "var(--qc-text)", sub: t("exacct_sub_total_asset", { quote: snap?.quote || "USDT" }) },
    { label: t("exacct_kpi_available"), value: fmtNum(available, 2), color: "var(--qc-text)", sub: t("exacct_sub_available") },
    { label: t("exacct_kpi_frozen"), value: fmtNum(frozen, 2), color: "var(--qc-text)", sub: t("exacct_sub_frozen") },
    { label: t("exacct_kpi_unrealized"), value: fmtSigned(futUnrealized, 2), color: pnlColor(futUnrealized), sub: t("exacct_unrealized_note") },
    { label: t("exacct_kpi_margin_balance"), value: fmtNum(futEquity, 2), color: "var(--qc-text)", sub: t("exacct_sub_margin") },
    { label: t("exacct_kpi_positions"), value: fmtNum(positions.length, 0), color: "var(--qc-text)", sub: t("exacct_sub_positions") },
  ];

  const futKpis: Array<[string, string, string?]> = [
    [t("exacct_kpi_fut_equity"), fmtNum(futEquity, 2)],
    [t("exacct_kpi_fut_unrealized"), fmtSigned(futUnrealized, 2), pnlColor(futUnrealized)],
    [t("exacct_kpi_fut_margin"), fmtNum(futUsed, 2)],
    [t("exacct_kpi_fut_available"), fmtNum(futAvailable, 2)],
    [
      t("exacct_kpi_fut_usage"),
      `${(futUsage * 100).toFixed(1)}%`,
      futUsage > 0.8 ? "var(--qc-error)" : futUsage > 0.6 ? "var(--qc-warning)" : "var(--qc-success)",
    ],
  ];

  const sectionTitle = (title: string, extra?: React.ReactNode) => (
    <div className="mb-3 flex items-center justify-between">
      <span className="font-[650]" style={{ fontSize: 13 }}>{title}</span>
      {extra}
    </div>
  );

  // ── 未配置 / 失败 空态 ─────────────────────────────────────
  if (snap && !snap.configured) {
    const isPaper = (snap as { paper?: boolean }).paper === true || snap.env === "paper";
    return (
      <PageContainer title={t("exacct_title")} onBack={() => navigate("/setting/exchange")}>
        <Card className="qc-card" styles={{ body: { padding: 48 } }}>
          <Empty description={<Space direction="vertical" size={4}>
            <span className="font-[650]">{isPaper ? t("exacct_paper_title") : t("exacct_not_configured_title")}</span>
            <Text type="secondary" className="max-w-[420px]">
              {isPaper ? t("exacct_paper_desc") : t("exacct_not_configured_desc")}
            </Text>
          </Space>}>
            <Button type="primary" onClick={() => navigate("/setting/exchange")}>
              {t("exacct_btn_configure")}
            </Button>
          </Empty>
        </Card>
      </PageContainer>
    );
  }

  if (loadErr && !snap) {
    return (
      <PageContainer
        title={t("exacct_title")}
        onBack={() => navigate("/setting/exchange")}
        actions={
          <Button size="small" icon={<IconRefresh size={14} />} onClick={() => void fetchSnap(true)}>
            {t("refresh")}
          </Button>
        }
      >
        <Card className="qc-card" styles={{ body: { padding: 48 } }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<Text type="secondary">{t("exacct_load_failed")}: {loadErr}</Text>}
          >
            <Button type="primary" onClick={() => void fetchSnap(true)}>{t("refresh")}</Button>
          </Empty>
        </Card>
      </PageContainer>
    );
  }

  const envLabel = snap?.env === "testnet" ? t("env_testnet") : t("env_live");
  const modeKey = snap?.mode === "future" || snap?.mode === "futures" ? "trading_mode_futures" : snap?.mode === "margin" ? "trading_mode_margin" : "trading_mode_spot";

  return (
    <PageContainer
      title={t("exacct_title")}
      onBack={() => navigate("/setting/exchange")}
      subtitle={t("exacct_refreshed", { time: loadedAt ? loadedAt.format("HH:mm:ss") : "--:--:--" })}
      titleExtra={
        snap ? (
          <Space size={6}>
            <Tag color={snap.env === "testnet" ? "warning" : "success"}>{envLabel}</Tag>
            <Tag>{t(modeKey)}</Tag>
          </Space>
        ) : null
      }
      actions={
        <Space>
          <Button size="small" icon={<IconRefresh size={14} />} onClick={() => void fetchSnap(true)} loading={loading}>
            {t("refresh")}
          </Button>
        </Space>
      }
    >
      <Spin spinning={loading && !snap}>
        {/* 纵向节奏用 flex+gap：space-y 的 margin 会被 preflight 的 * { margin: 0 } 覆盖清零 */}
        <div className="flex flex-col gap-6">
          {/* 行情/余额级别的全局告警（如代理不通、鉴权失败） */}
          {(err.balance || err.prices) && (
            <Alert
              type="warning"
              showIcon
              message={t("exacct_section_error")}
              description={err.balance || err.prices}
            />
          )}

          {/* 1. 核心概览 KPI */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {kpis.map((k) => (
              <div key={k.label} className="qc-card rounded-xl p-3.5">
                <div className="text-xs" style={{ color: "var(--qc-text-tertiary)" }}>{k.label}</div>
                <div className="mt-1.5 text-[20px] leading-7 font-[650] tabular-nums" style={{ color: k.color }}>
                  {k.value}
                </div>
                <div className="mt-0.5 text-[11px]" style={{ color: "var(--qc-text-quaternary)" }}>{k.sub}</div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1.15fr]">
            {/* 4. 资产分布可视化 */}
            <Card className="qc-card" styles={{ body: { padding: "16px 16px 8px" } }}>
              {sectionTitle(
                t("exacct_distribution"),
                <Segmented
                  size="small"
                  value={distTab}
                  onChange={(v) => setDistTab(v as typeof distTab)}
                  options={[
                    { label: t("exacct_dist_by_coin"), value: "coin" },
                    { label: t("exacct_dist_by_account"), value: "account" },
                  ]}
                />
              )}
              {distData.length > 0 ? (
                <EChart option={pieOption} style={{ height: 278, width: "100%" }} notMerge />
              ) : (
                <div style={{ height: 278 }} className="flex items-center justify-center">
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("exacct_no_assets")} />
                </div>
              )}
            </Card>

            {/* 2. 分类型账户明细 */}
            <Card className="qc-card" styles={{ body: { padding: 16 } }}>
              {sectionTitle(
                t("exacct_accounts"),
                <Segmented
                  size="small"
                  value={acctTab}
                  onChange={(v) => setAcctTab(v as AcctTab)}
                  options={[
                    { label: t("exacct_tab_spot"), value: "spot" },
                    { label: t("exacct_tab_futures"), value: "futures" },
                  ]}
                />
              )}
              {acctTab === "spot" ? (
                <Table
                  size="small"
                  rowKey="currency"
                  columns={spotCols}
                  dataSource={spotRows}
                  loading={loading}
                  pagination={false}
                  locale={{ emptyText: t("exacct_no_assets") }}
                  summary={
                    spotRows.length > 0
                      ? () => (
                          <Table.Summary.Row>
                            <Table.Summary.Cell index={0}>
                              <Text strong>{t("exacct_total_row")}</Text>
                            </Table.Summary.Cell>
                            <Table.Summary.Cell index={1} colSpan={2} />
                            <Table.Summary.Cell index={3} align="right">
                              <Text strong>{fmtNum(spotTotal, 2)}</Text>
                            </Table.Summary.Cell>
                            <Table.Summary.Cell index={4} />
                          </Table.Summary.Row>
                        )
                      : undefined
                  }
                />
              ) : (
                <div>
                  <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
                    {futKpis.map(([label, value, color]) => (
                      <div key={label} className="rounded-lg px-3 py-2.5" style={{ background: "var(--qc-surface-muted)" }}>
                        <div className="text-[11px]" style={{ color: "var(--qc-text-tertiary)" }}>{label}</div>
                        <div className="mt-0.5 tabular-nums text-[15px] font-[650]" style={{ color: color ?? "var(--qc-text)" }}>
                          {value}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-3">
                    <div className="mb-1 flex items-center justify-between text-[11px]" style={{ color: "var(--qc-text-tertiary)" }}>
                      <span>{t("exacct_usage_bar")}</span>
                      <span className="tabular-nums">{(futUsage * 100).toFixed(1)}%</span>
                    </div>
                    <Progress
                      percent={futUsage * 100}
                      showInfo={false}
                      strokeColor={futUsage > 0.8 ? "var(--qc-error)" : futUsage > 0.6 ? "var(--qc-warning)" : "var(--qc-primary)"}
                      railColor="var(--qc-surface-muted)"
                    />
                  </div>
                </div>
              )}
            </Card>
          </div>

          {/* 3 + 5. 实时持仓 / 仓位与保证金 */}
          <Card className="qc-card" styles={{ body: { padding: 16 } }}>
            {sectionTitle(
              t("exacct_positions"),
              <Space>
                {err.positions && (
                  <Text type="danger" className="text-xs">{t("exacct_section_error")}</Text>
                )}
                <Segmented
                  size="small"
                  value={posTab}
                  onChange={(v) => setPosTab(v as PosTab)}
                  options={[
                    { label: t("exacct_tab_pos"), value: "pos" },
                    // 内部 key=risk（该视图=风险敞口列），标签走 i18n「仓位与保证金」
                    { label: t("exacct_tab_margin"), value: "risk" },
                  ]}
                />
              </Space>
            )}
            <Table
              size="small"
              rowKey="symbol"
              columns={posTab === "pos" ? posCols : riskCols}
              dataSource={positions}
              loading={loading}
              pagination={false}
              scroll={{ x: "max-content" }}
              locale={{ emptyText: t("exacct_no_positions") }}
            />
          </Card>

          {/* 6. 历史委托 */}
          <Card className="qc-card" styles={{ body: { padding: 16 } }}>
            {sectionTitle(
              t("exacct_orders"),
              <Space wrap>
                <RangePicker
                  size="small"
                  value={orderRange}
                  onChange={(v) => setOrderRange(v as Range)}
                  allowClear
                />
                <Select
                  size="small"
                  style={{ width: 120 }}
                  value={orderStatus}
                  onChange={setOrderStatus}
                  options={[
                    { value: "all", label: t("exacct_status_all") },
                    { value: "filled", label: t("exacct_status_filled") },
                    { value: "partial", label: t("exacct_status_partial") },
                    { value: "open", label: t("exacct_status_open") },
                    { value: "canceled", label: t("exacct_status_canceled") },
                  ]}
                />
              </Space>
            )}
            {(err.openOrders || err.history) && (
              <Alert type="warning" showIcon className="mb-2" message={t("exacct_section_error")} description={err.openOrders || err.history} />
            )}
            <Table
              size="small"
              rowKey="id"
              columns={orderCols}
              dataSource={filteredOrders}
              loading={loading}
              pagination={{ pageSize: 8, showSizeChanger: false, hideOnSinglePage: true }}
              scroll={{ x: "max-content" }}
              locale={{ emptyText: t("exacct_no_orders") }}
            />
          </Card>

          {/* 7. 历史成交 */}
          <Card className="qc-card" styles={{ body: { padding: 16 } }}>
            {sectionTitle(
              t("exacct_trades"),
              <Space wrap>
                <Input.Search
                  size="small"
                  style={{ width: 180 }}
                  placeholder={t("exacct_search_pair")}
                  value={tradeSearch}
                  onChange={(e) => setTradeSearch(e.target.value)}
                  allowClear
                />
                <RangePicker
                  size="small"
                  value={tradeRange}
                  onChange={(v) => setTradeRange(v as Range)}
                  allowClear
                />
                <Button
                  size="small"
                  icon={<IconDownload size={14} />}
                  onClick={handleExport}
                  disabled={filteredTrades.length === 0}
                >
                  {t("exacct_export_csv")}
                </Button>
              </Space>
            )}
            <Table
              size="small"
              rowKey="id"
              columns={tradeCols}
              dataSource={filteredTrades}
              loading={loading}
              pagination={{ pageSize: 8, showSizeChanger: false, hideOnSinglePage: true }}
              scroll={{ x: "max-content" }}
              locale={{ emptyText: t("exacct_no_trades") }}
            />
          </Card>
        </div>
      </Spin>
    </PageContainer>
  );
};

export default ExchangeAccountPage;
