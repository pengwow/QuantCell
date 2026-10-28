/**
 * Worker 持仓 Tab
 *
 * 展示当前 Worker 的实时持仓情况：
 * - 5s 轮询刷新（仅在 tab 激活时启用）
 * - 量化行业标准列：标记价、强平价、ROE、持仓时长
 * - 汇总卡片：总持仓价值、总未实现盈亏、总保证金、总 ROE
 * - 盈亏绝对值 > 5% 的行高亮提示
 */

import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge, Card, Col, Empty, Row, Space, Spin, Statistic, Table, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import { workerApi } from '@/api/workerApi';
import { usePolling } from '@/hooks/usePolling';
import type { PositionInfo, WorkerTrade } from '@/types/worker';
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

interface WorkerPositionTabProps {
  workerId: number;
  /** tab 是否激活；激活时才进行 5s 轮询，避免无效请求 */
  active?: boolean;
}

const WorkerPositionTab: React.FC<WorkerPositionTabProps> = ({ workerId, active = true }) => {
  const { t } = useTranslation();
  // initialized：首帧数据是否已返回。轮询刷新只做局部 setState 更新，
  // 不再用 loading 把整个面板替换成 Spin——DOM 被替换会丢失浏览器滚动位置（页面跳回顶部）
  const [initialized, setInitialized] = useState(false);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<WorkerTrade[]>([]);
  const [tradeTotal, setTradeTotal] = useState(0);
  const [tradePage, setTradePage] = useState(1);
  const [tradeLoading, setTradeLoading] = useState(false);

  // 拉取持仓数据：兼容多种返回结构
  const fetchPositionData = useCallback(async () => {
    try {
      // apiRequest.get() 已解包 ApiResponse.data，getPositions 直接返回 PositionInfo[]
      const items = await workerApi.getPositions(workerId);
      setPositions(items);
    } catch (error) {
      console.error('获取持仓数据失败:', error);
      setPositions([]);
    } finally {
      setInitialized(true);
    }
  }, [workerId]);

  // 5s 轮询：仅在 tab 激活时启用
  usePolling(fetchPositionData, { interval: 5000, enabled: active });

  // 成交明细：展示全部 fill 行，与总览「总交易次数」口径一致（count 所有 fill）。
  // realized_pnl 为 null = 开仓 fill 尚未配对出 round-trip（即当前持仓），标记「持仓中」；
  // 之前按 pnl_status='closed' 过滤导致未平仓的 entry fill 在所有 tab 都不可见
  const fetchTrades = useCallback(async (page: number) => {
    setTradeLoading(true);
    try {
      const res = await workerApi.getWorkerTrades(workerId, {
        page,
        page_size: 10,
      });
      setTrades(res.items);
      setTradeTotal(res.total);
      setTradePage(page);
    } catch (error) {
      console.error('获取成交记录失败:', error);
      setTrades([]);
    } finally {
      setTradeLoading(false);
    }
  }, [workerId]);

  usePolling(() => fetchTrades(tradePage), { interval: 15000, enabled: active });

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
      title: t('symbol') || '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 120,
      render: (symbol: string) => <Tag color="blue">{symbol}</Tag>,
    },
    {
      title: t('direction') || '方向',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: 'long' | 'short') => (
        <Tag color={side === 'long' ? 'green' : 'red'}>
          {side === 'long' ? t('long') || '做多' : t('short') || '做空'}
        </Tag>
      ),
    },
    {
      title: t('quantity') || '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (qty: number) => formatQuantity(qty),
    },
    {
      title: t('entry_price') || '开仓价',
      dataIndex: 'entry_price',
      key: 'entry_price',
      align: 'right',
      render: (price: number) => formatUSD(price),
    },
    {
      title: t('current_price') || '最新价',
      dataIndex: 'current_price',
      key: 'current_price',
      align: 'right',
      render: (price: number) => formatUSD(price),
    },
    {
      title: '标记价',
      dataIndex: 'mark_price',
      key: 'mark_price',
      align: 'right',
      render: (price?: number) =>
        price === null || price === undefined ? <span style={{ color: '#999' }}>-</span> : formatUSD(price),
    },
    {
      title: '强平价',
      dataIndex: 'liquidation_price',
      key: 'liquidation_price',
      align: 'right',
      render: (price?: number) =>
        price === null || price === undefined ? <span style={{ color: '#999' }}>-</span> : formatUSD(price),
    },
    {
      title: t('leverage') || '杠杆',
      dataIndex: 'leverage',
      key: 'leverage',
      width: 80,
      align: 'center',
      render: (lev?: number) => (lev ? <Tag color="orange">{formatLeverage(lev)}</Tag> : '-'),
    },
    {
      title: '保证金',
      dataIndex: 'margin_used',
      key: 'margin_used',
      align: 'right',
      render: (margin?: number) => formatUSD(margin),
    },
    {
      title: t('unrealized_pnl') || '未实现盈亏',
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
      title: t('open_time') || '开仓时间',
      dataIndex: 'open_time',
      key: 'open_time',
      width: 170,
      render: (time?: string) => (time ? formatTimestamp(time) : '-'),
    },
    {
      title: '持仓时长',
      dataIndex: 'open_time',
      key: 'holding_duration',
      width: 110,
      render: (time?: string, record?: Position) =>
        formatHoldingDuration(record?.holding_duration ? null : time),
    },
  ];

  // 高亮 |pnl| > 5% 的持仓行
  const rowClassName = (record: Position) => {
    const pnlPct = Math.abs(record.pnl_percentage || 0);
    return pnlPct > 5 ? 'position-row-highlight' : '';
  };

  // 成交明细表格列：时间优先取平仓时间，未平仓行回退为成交时间
  const tradeColumns: TableColumnsType<WorkerTrade> = [
    {
      title: '时间',
      dataIndex: 'exit_time',
      key: 'exit_time',
      width: 170,
      render: (time: string | undefined, record: WorkerTrade) => {
        const t0 = time || record.created_at;
        return t0 ? formatTimestamp(t0) : '-';
      },
    },
    {
      title: t('symbol') || '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 120,
      render: (symbol: string) => <Tag color="blue">{symbol}</Tag>,
    },
    {
      title: t('direction') || '方向',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: 'buy' | 'sell') => (
        <Tag color={side === 'buy' ? 'green' : 'red'}>{side === 'buy' ? '买入' : '卖出'}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'realized_pnl',
      key: 'trade_status',
      width: 90,
      render: (pnl?: number | null) =>
        pnl === undefined || pnl === null ? <Tag color="gold">持仓中</Tag> : <Tag>已平仓</Tag>,
    },
    {
      title: t('quantity') || '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (qty: number) => formatQuantity(qty),
    },
    {
      title: '成交价',
      dataIndex: 'price',
      key: 'price',
      align: 'right',
      render: (price: number) => formatUSD(price),
    },
    {
      title: t('realized_pnl') || '已实现盈亏',
      dataIndex: 'realized_pnl',
      key: 'realized_pnl',
      align: 'right',
      width: 140,
      render: (pnl?: number | null) =>
        pnl === undefined || pnl === null ? (
          <span style={{ color: '#999' }}>—</span>
        ) : (
          <span style={{ fontWeight: 600, color: pnl >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative }}>
            {formatUSD(pnl, { showSign: true })}
          </span>
        ),
    },
    {
      title: '收益率',
      dataIndex: 'realized_pnl_pct',
      key: 'realized_pnl_pct',
      align: 'right',
      width: 100,
      render: (pct?: number) =>
        pct === undefined || pct === null ? (
          '-'
        ) : (
          <span style={{ fontWeight: 600, color: pct >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative }}>
            {formatPercent(pct, { showSign: true })}
          </span>
        ),
    },
  ];

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
              title={t('total_position_value') || '总持仓价值'}
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
              title={t('unrealized_pnl') || '总未实现盈亏'}
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
              title={t('margin_used') || '总保证金占用'}
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
              title="总 ROE"
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

      {/* 持仓列表 + 历史平仓记录（Card 间距由 Space 统一管理） */}
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card
        title={
          <span>
            {t('current_position') || '当前持仓'}
            {active && (
              <Badge
                status="processing"
                text="实时"
                style={{ marginLeft: 12, color: QUANT_COLORS.info }}
              />
            )}
          </span>
        }
      >
        {positions.length === 0 ? (
          <Empty
            description={t('no_position_data') || '暂无持仓数据'}
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

      {/* 成交明细：全部 fill 行（含持仓中/未平仓），服务端分页（数据 append-only，翻页/15s 轮询按当前页刷新） */}
      <Card title="成交明细">
        <Table
          columns={tradeColumns}
          dataSource={trades}
          rowKey="trade_id"
          loading={tradeLoading}
          locale={{
            emptyText: <Empty description="暂无成交记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />,
          }}
          pagination={{
            current: tradePage,
            pageSize: 10,
            total: tradeTotal,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 笔`,
            onChange: (page) => fetchTrades(page),
          }}
          size="middle"
          scroll={{ x: 'max-content' }}
        />
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

export default WorkerPositionTab;
