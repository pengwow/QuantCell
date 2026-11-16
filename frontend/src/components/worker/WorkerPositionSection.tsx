/**
 * 总览页持仓区（spec 2026-11-16 方案 A：持仓 tab 并入总览）
 * 代码逐字搬自 WorkerPositionTab.tsx（该文件随 T6 下线）：
 * 摘要 4 卡（总持仓价值/总未实现盈亏/总保证金/总 ROE）+ 当前持仓表（行高亮 |盈亏%|>5%）
 * 轮询/首帧行为保持不变：5s 轮询仅 active 时启用；initialized 保证首帧后 DOM 稳定不跳滚动
 * 原「成交明细」分表不随迁：成交视角由「交易」tab（订单明细，按状态区分挂单/成交）承接
 */
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge, Card, Col, Empty, Row, Space, Spin, Statistic, Table, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import { workerApi } from '@/api/workerApi';
import { usePolling } from '@/hooks/usePolling';
import type { PositionInfo } from '@/types/worker';
import {
  QUANT_COLORS,
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

  // 表格列：按量化行业标准排序
  const columns: TableColumnsType<Position> = [
    {
      title: t('symbol'),
      dataIndex: 'symbol',
      key: 'symbol',
      width: 120,
      render: (symbol: string) => <Tag color="blue">{symbol}</Tag>,
    },
    {
      title: t('direction'),
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: 'long' | 'short') => (
        <Tag color={side === 'long' ? 'green' : 'red'}>
          {side === 'long' ? t('long') : t('short')}
        </Tag>
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
        price === null || price === undefined ? <span style={{ color: '#999' }}>-</span> : formatUSD(price),
    },
    {
      title: t('worker_liquidation_price'),
      dataIndex: 'liquidation_price',
      key: 'liquidation_price',
      align: 'right',
      render: (price?: number) =>
        price === null || price === undefined ? <span style={{ color: '#999' }}>-</span> : formatUSD(price),
    },
    {
      title: t('leverage'),
      dataIndex: 'leverage',
      key: 'leverage',
      width: 80,
      align: 'center',
      render: (lev?: number) => (lev ? <Tag color="orange">{formatLeverage(lev)}</Tag> : '-'),
    },
    {
      title: t('backtest_margin'),
      dataIndex: 'margin_used',
      key: 'margin_used',
      align: 'right',
      render: (margin?: number) => formatUSD(margin),
    },
    {
      title: t('unrealized_pnl'),
      dataIndex: 'unrealized_pnl',
      key: 'unrealized_pnl',
      align: 'right',
      width: 140,
      render: (pnl: number) => (
        <span style={{ fontWeight: 600, color: pnl >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative }}>
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
          <span style={{ fontWeight: 600, color: value >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative }}>
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
      render: (time?: string) => (time ? formatTimestamp(time) : '-'),
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
      {/* 汇总卡片：总持仓价值 / 总未实现盈亏 / 总保证金 / 总 ROE */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title={t('total_position_value')}
              value={summary.totalPositionValue}
              precision={2}
              prefix="$"
              styles={{ content: { color: QUANT_COLORS.info } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title={t('unrealized_pnl')}
              value={summary.totalUnrealizedPnL}
              precision={2}
              prefix="$"
              styles={{
                content: {
                  color: summary.totalUnrealizedPnL >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
                },
              }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title={t('margin_used')}
              value={summary.totalMarginUsed}
              precision={2}
              prefix="$"
              styles={{ content: { color: QUANT_COLORS.warning } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title={t('worker_total_roe')}
              value={summary.totalROE}
              precision={2}
              suffix="%"
              styles={{
                content: {
                  color: summary.totalROE >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
                },
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* 持仓列表（成交明细不在此处：由「交易」tab 承接；Card 间距由 Space 统一管理） */}
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card
        title={
          <span>
            {t('current_position')}
            {active && (
              <Badge
                status="processing"
                text={t('worker_realtime')}
                style={{ marginLeft: 12, color: QUANT_COLORS.info }}
              />
            )}
          </span>
        }
      >
        {positions.length === 0 ? (
          <Empty
            description={t('no_position_data')}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Table
            columns={columns}
            dataSource={positions}
            rowKey={(record) => `${record.symbol}-${record.side}`}
            rowClassName={rowClassName}
            pagination={false}
            size="middle"
            scroll={{ x: 'max-content' }}
          />
        )}
      </Card>
      </Space>

      {/* 高亮行样式：盈亏绝对值 > 5% */}
      <style>{`
        .position-row-highlight {
          background-color: #fff7e6 !important;
        }
        .position-row-highlight:hover td {
          background-color: #ffe7ba !important;
        }
      `}</style>
    </div>
  );
};

export default WorkerPositionSection;
