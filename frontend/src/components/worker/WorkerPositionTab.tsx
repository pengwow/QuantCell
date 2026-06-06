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
import { Badge, Card, Col, Empty, Row, Spin, Statistic, Table, Tag } from 'antd';
import { workerApi } from '@/api/workerApi';
import { usePolling } from '@/hooks/usePolling';
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

interface Position {
  id: number;
  symbol: string;
  side: 'long' | 'short';
  quantity: number;
  entry_price: number;
  current_price: number;
  mark_price?: number;
  liquidation_price?: number;
  leverage?: number;
  margin_used?: number;
  unrealized_pnl: number;
  pnl_percentage: number;
  roe?: number;
  open_time?: string;
  holding_duration?: string;
  timestamp: string;
}

interface WorkerPositionTabProps {
  workerId: number;
  /** tab 是否激活；激活时才进行 5s 轮询，避免无效请求 */
  active?: boolean;
}

const WorkerPositionTab: React.FC<WorkerPositionTabProps> = ({ workerId, active = true }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [positions, setPositions] = useState<Position[]>([]);

  // 拉取持仓数据：兼容多种返回结构
  const fetchPositionData = useCallback(async () => {
    setLoading(true);
    try {
      // apiRequest.get() 已解包 ApiResponse.data，response 直接是持仓数组
      const response: any = await workerApi.getPositions(workerId);
      if (Array.isArray(response)) {
        setPositions(response);
      } else if (response && Array.isArray(response.items)) {
        // 兜底：万一后端未走 ApiResponse 包装
        setPositions(response.items);
      } else {
        setPositions([]);
      }
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error('获取持仓数据失败:', error);
      setPositions([]);
    } finally {
      setLoading(false);
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const columns: any = [
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

  if (loading && positions.length === 0) {
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

      {/* 持仓列表 */}
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
            rowKey="id"
            rowClassName={rowClassName}
            pagination={false}
            size="middle"
            scroll={{ x: 'max-content' }}
          />
        )}
      </Card>

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
