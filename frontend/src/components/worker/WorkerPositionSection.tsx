/**
 * 总览页持仓区（spec 2026-11-16 方案 A：持仓 tab 并入总览）
 * 代码逐字搬自 WorkerPositionTab.tsx（该文件随 T6 下线）：
 * 摘要 4 卡（总持仓价值/总未实现盈亏/总保证金/总 ROE）+ 当前持仓表（行高亮 |盈亏%|>5%）
 * 轮询/首帧行为保持不变：5s 轮询仅 active 时启用；initialized 保证首帧后 DOM 稳定不跳滚动
 * 原「成交明细」分表不随迁：成交视角由「交易」tab（订单明细，按状态区分挂单/成交）承接
 */
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Space, Spin } from 'antd';
import { workerApi } from '@/api/workerApi';
import { usePolling } from '@/hooks/usePolling';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import type { TableColumnsType } from 'antd';
import type { PositionInfo, PositionSide } from '@/types/worker';
import {
  calcROE,
  formatHoldingDuration,
  formatLeverage,
  formatPercent,
  formatQuantity,
  formatTimestamp,
  formatUSD,
} from '@/utils/format';

// 持仓数据模型：直接复用 workerApi.getPositions 的返回类型（PositionInfo）与后端保持一致
type Position = PositionInfo;

interface WorkerPositionSectionProps {
  workerId: number;
  /** tab 是否激活；激活时才进行 5s 轮询，避免无效请求 */
  active?: boolean;
}

const WorkerPositionSection: React.FC<WorkerPositionSectionProps> = ({ workerId, active = true }) => {
  const { t } = useTranslation();
  // initialized：首帧数据是否已返回。轮询刷新只做局部 setState 更新，
  // 不再用 loading 把整个面板替换成 Spin——DOM 被替换会丢失浏览器滚动位置（页面跳回顶部）
  const [initialized, setInitialized] = useState(false);
  const [positions, setPositions] = useState<Position[]>([]);

  // 拉取持仓数据：兼容多种返回结构
  const fetchPositionData = useCallback(async () => {
    try {
      // apiRequest.get() 已解包 ApiResponse.data，getPositions 直接返回 PositionInfo[]
      const items = await workerApi.getPositions(workerId);
      setPositions(items);
    } catch (error) {
      console.error(t('worker_positions_load_failed'), error);
      setPositions([]);
    } finally {
      setInitialized(true);
    }
  }, [workerId]);

  // 5s 轮询：仅在 tab 激活时启用
  usePolling(fetchPositionData, { interval: 5000, enabled: active });

  // 汇总指标
  const summary = useMemo(() => {
    const totalPositionValue = positions.reduce(
      (sum, p) => sum + p.quantity * p.current_price,
      0,
    );
    const totalUnrealizedPnL = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);
    const totalMarginUsed = positions.reduce((sum, p) => sum + (p.margin_used || 0), 0);
    // 总 ROE：总未实现盈亏 / 总保证金 × 100
    const totalROE = totalMarginUsed > 0 ? (totalUnrealizedPnL / totalMarginUsed) * 100 : 0;
    return { totalPositionValue, totalUnrealizedPnL, totalMarginUsed, totalROE };
  }, [positions]);

  // 表格列：按量化行业标准排序（§6.5：标识 mono、方向涨跌色、时间弱色；类别值不上色）
  const columns: TableColumnsType<Position> = [
    {
      title: t('symbol'),
      dataIndex: 'symbol',
      key: 'symbol',
      width: 120,
      render: (symbol: string) => <span className="qc-mono">{symbol}</span>,
    },
    {
      title: t('direction'),
      dataIndex: 'position_side',
      key: 'position_side',
      width: 80,
      render: (side: PositionSide) => (
        <span className={`qc-mono${side === 'long' ? ' qc-cell-up' : side === 'short' ? ' qc-cell-down' : ''}`}>
          {side === 'long' ? t('position_side_long') : side === 'short' ? t('position_side_short') : t('position_side_both')}
        </span>
      ),
    },
    {
      title: t('quantity'),
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (qty: number) => formatQuantity(qty),
    },
    {
      title: t('entry_price'),
      dataIndex: 'entry_price',
      key: 'entry_price',
      align: 'right',
      render: (price: number) => formatUSD(price),
    },
    {
      title: t('current_price'),
      dataIndex: 'current_price',
      key: 'current_price',
      align: 'right',
      render: (price: number) => formatUSD(price),
    },
    {
      title: t('worker_mark_price'),
      dataIndex: 'mark_price',
      key: 'mark_price',
      align: 'right',
      render: (price?: number) =>
        price === null || price === undefined ? <span style={{ color: 'var(--qc-text-tertiary)' }}>-</span> : formatUSD(price),
    },
    {
      title: t('worker_liquidation_price'),
      dataIndex: 'liquidation_price',
      key: 'liquidation_price',
      align: 'right',
      render: (price?: number) =>
        price === null || price === undefined ? <span style={{ color: 'var(--qc-text-tertiary)' }}>-</span> : formatUSD(price),
    },
    {
      title: t('leverage'),
      dataIndex: 'leverage',
      key: 'leverage',
      width: 80,
      align: 'center',
      // 倍数值中性 mono（类别值不上色，同 WorkerOrderTab type 列口径）
      render: (lev?: number) => (lev ? <span className="qc-mono">{formatLeverage(lev)}</span> : <span className="qc-mono qc-cell-none">—</span>),
    },
    {
      title: t('backtest_margin'),
      dataIndex: 'margin_used',
      key: 'margin_used',
      align: 'right',
      render: (usedMargin?: number) => formatUSD(usedMargin),
    },
    {
      title: t('unrealized_pnl'),
      dataIndex: 'unrealized_pnl',
      key: 'unrealized_pnl',
      align: 'right',
      width: 140,
      render: (pnl: number) => (
        <span className={`qc-mono${pnl >= 0 ? ' qc-cell-up' : ' qc-cell-down'}`}>
          {formatUSD(pnl, { showSign: true })}
        </span>
      ),
    },
    {
      title: 'ROE (%)',
      dataIndex: 'roe',
      key: 'roe',
      align: 'right',
      width: 100,
      // 优先使用后端 roe 字段；缺失则前端计算（unrealized_pnl / margin_used * 100）
      render: (roe: number | undefined, record: Position) => {
        const value = roe !== undefined ? roe : calcROE(record.unrealized_pnl, record.margin_used || 0);
        return (
          <span className={`qc-mono${value >= 0 ? ' qc-cell-up' : ' qc-cell-down'}`}>
            {formatPercent(value, { showSign: true })}
          </span>
        );
      },
    },
    {
      title: t('open_time'),
      dataIndex: 'opened_at',
      key: 'opened_at',
      width: 170,
      render: (time?: string) => (
        <span className="qc-cell-time qc-mono">{time ? formatTimestamp(time) : '—'}</span>
      ),
    },
    {
      title: t('worker_holding_duration'),
      dataIndex: 'opened_at',
      key: 'holding_duration',
      width: 110,
      render: (time?: string) => formatHoldingDuration(time),
    },
  ];

  // 高亮 |盈亏%| > 5% 的持仓行（后端字段 unrealized_pnl_pct）
  const rowClassName = (record: Position) => {
    const pnlPct = Math.abs(record.unrealized_pnl_pct || 0);
    return pnlPct > 5 ? 'position-row-highlight' : '';
  };

  // 仅首帧未返回数据时用 Spin 占位；之后轮询不触发此分支，DOM 结构保持稳定
  if (!initialized) {
    return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div>
      {/* 摘要：总持仓价值 / 总未实现盈亏 / 总保证金 / 总 ROE —— §6.4 .qc-kpi
          * 语义档：名义额与占用类恒中性，只有盈亏/ROE 按方向染 */}
      <div className="qc-kpi-grid" style={{ marginBottom: 16 }}>
        <div className="qc-kpi">
          <div className="qc-kpi-top"><span className="qc-kpi-lb">{t('total_position_value')}</span></div>
          <div className="qc-kpi-num">${summary.totalPositionValue.toFixed(2)}</div>
        </div>
        <div className="qc-kpi">
          <div className="qc-kpi-top"><span className="qc-kpi-lb">{t('unrealized_pnl')}</span></div>
          <div className={`qc-kpi-num${summary.totalUnrealizedPnL >= 0 ? ' up' : ' down'}`}>
            {formatUSD(summary.totalUnrealizedPnL, { showSign: true })}
          </div>
        </div>
        <div className="qc-kpi">
          <div className="qc-kpi-top"><span className="qc-kpi-lb">{t('margin_used')}</span></div>
          <div className="qc-kpi-num">${summary.totalMarginUsed.toFixed(2)}</div>
        </div>
        <div className="qc-kpi">
          <div className="qc-kpi-top"><span className="qc-kpi-lb">{t('worker_total_roe')}</span></div>
          <div className={`qc-kpi-num${summary.totalROE >= 0 ? ' up' : ' down'}`}>
            {formatPercent(summary.totalROE, { showSign: true })}
          </div>
        </div>
      </div>

      {/* 持仓列表（成交明细不在此处：由「交易」tab 承接；Card 间距由 Space 统一管理） */}
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card
        className="qc-card"
        title={
          <Space size={12}>
            <span>{t('current_position')}</span>
            {active && (
              <span className="qc-chip info">
                <span className="qc-pdot" />
                {t('worker_realtime')}
              </span>
            )}
          </Space>
        }
      >
        {positions.length === 0 ? (
          <QcEmpty title={t('no_position_data')} />
        ) : (
          <DataTable
            columns={columns}
            dataSource={positions}
            rowKey={(record) => `${record.symbol}-${record.position_side}`}
            rowClassName={rowClassName}
            pagination={false}
          />
        )}
      </Card>
      </Space>

      {/* 高亮行样式：盈亏绝对值 > 5%。走 warning 语义组：行底 = --qc-warning-soft-bg，
        * 悬停在其上再混 16% 警示色（color-mix 为全站既有模式）；亮暗两模式均由 token 换挡 */}
      <style>{`
        .position-row-highlight {
          background-color: var(--qc-warning-soft-bg) !important;
        }
        .position-row-highlight:hover td {
          background-color: color-mix(in srgb, var(--qc-warning) 16%, var(--qc-warning-soft-bg)) !important;
        }
      `}</style>
    </div>
  );
};

export default WorkerPositionSection;
