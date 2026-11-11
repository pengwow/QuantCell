/**
 * Worker 成交分组 Tab（round-trip 一开一平合并显示）
 *
 * - 服务端按组分页（组不跨页切断），15s 轮询对齐持仓 Tab 节奏
 * - 表格复用共享 TradeTable，展开行看逐笔 fill
 * - 无配对的历史 / live 成交：每行自成一组，标记「未配对」
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Col, DatePicker, Empty, Pagination, Row, Select, Space } from 'antd';
import { workerApi } from '@/api/workerApi';
import TradeTable from '@/components/TradeTable';
import { usePolling } from '@/hooks/usePolling';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';
import { PAGE_SIZE_OPTIONS } from '@/constants/pagination';
import type { Trade } from '@/types/backtest';

interface WorkerTradesGroupedTabProps {
  workerId: number;
  /** tab 是否激活；激活时才轮询 */
  active?: boolean;
}

type DirectionFilter = 'all' | 'long' | 'short';

const WorkerTradesGroupedTab: React.FC<WorkerTradesGroupedTabProps> = ({ workerId, active = true }) => {
  const { t } = useTranslation();
  const [items, setItems] = useState<Trade[]>([]);
  const [totalGroups, setTotalGroups] = useState(0);
  const [page, setPage] = useState(1);
  // 分页大小跟随全局配置（条数切换器即全站开关）
  const [pageSize, setPageSize] = useGlobalPageSize();
  const [loading, setLoading] = useState(false);
  // 标的筛选项：累积已出现过的 symbol，避免翻页/筛选后候选列表缩水
  const [symbols, setSymbols] = useState<string[]>([]);
  const [filterSymbol, setFilterSymbol] = useState('all');
  const [filterDirection, setFilterDirection] = useState<DirectionFilter>('all');
  const [filterDateRange, setFilterDateRange] = useState<[string, string] | null>(null);

  const fetchGrouped = useCallback(async () => {
    setLoading(true);
    try {
      const res = await workerApi.getWorkerTradesGrouped(workerId, {
        symbol: filterSymbol === 'all' ? undefined : filterSymbol,
        direction: filterDirection === 'all' ? undefined : filterDirection,
        // 日期只给到「日」，后端会自行补到当日末（end 传 23:59:59 也一致）
        start_time: filterDateRange ? `${filterDateRange[0]}T00:00:00` : undefined,
        end_time: filterDateRange ? `${filterDateRange[1]}T23:59:59` : undefined,
        page,
        page_size: pageSize,
      });
      setItems(res.items ?? []);
      setTotalGroups(res.total_groups ?? 0);
      setSymbols((prev) =>
        Array.from(new Set([...prev, ...(res.items ?? []).map((it) => it.symbol)])).sort()
      );
    } catch (error) {
      console.error('获取成交分组失败:', error);
      setItems([]);
      setTotalGroups(0);
    } finally {
      setLoading(false);
    }
  }, [workerId, filterSymbol, filterDirection, filterDateRange, page, pageSize]);

  usePolling(fetchGrouped, { interval: 15000, enabled: active });

  // 筛选变化回到第一页，避免筛选后停在越界页码
  const handleSymbolChange = (value: string) => {
    setFilterSymbol(value);
    setPage(1);
  };
  const handleDirectionChange = (value: DirectionFilter) => {
    setFilterDirection(value);
    setPage(1);
  };
  const resetFilters = () => {
    setFilterSymbol('all');
    setFilterDirection('all');
    setFilterDateRange(null);
    setPage(1);
  };

  const statsText = useMemo(() => {
    const parts = [t('worker_total_groups', { total: totalGroups })];
    if (filterSymbol !== 'all') parts.push(t('worker_filter_symbol', { symbol: filterSymbol }));
    if (filterDirection !== 'all') {
      parts.push(t('worker_filter_direction', { direction: filterDirection === 'long' ? t('long') : t('short') }));
    }
    if (filterDateRange) parts.push(t('worker_filter_date', { start: filterDateRange[0], end: filterDateRange[1] }));
    return parts.join(' | ');
  }, [totalGroups, filterSymbol, filterDirection, filterDateRange, t]);

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card title={t('worker_trades_grouped')}>
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          <Row gutter={[16, 16]} align="middle">
            <Col xs={24} sm={12} md={6}>
              <div style={{ marginBottom: 8 }}>{t('trading_symbols')}</div>
              <Select value={filterSymbol} onChange={handleSymbolChange} style={{ width: '100%' }}>
                {/* 「全部」在任何筛选态下都可能是当前值，必须始终渲染 */}
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
              <Select value={filterDirection} onChange={handleDirectionChange} style={{ width: '100%' }}>
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
                  setFilterDateRange(
                    dates && dates[0] && dates[1]
                      ? [dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]
                      : null
                  );
                  setPage(1);
                }}
              />
            </Col>
            <Col xs={24} sm={12} md={6} style={{ textAlign: 'right' }}>
              <Button onClick={resetFilters}>{t('reset')}</Button>
            </Col>
          </Row>

          <span style={{ color: '#8c8c8c' }}>{statsText}</span>

          {items.length === 0 && !loading ? (
            <Empty description={t('worker_no_trades_grouped')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            // 服务端已分页，关掉表格内部分页，避免对当前 10 条再切一次
            <TradeTable data={items} loading={loading} pagination={false} />
          )}

          <Pagination
            current={page}
            pageSize={pageSize}
            total={totalGroups}
            showSizeChanger
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            showTotal={(total) => t('worker_total_groups', { total })}
            onChange={(nextPage, nextSize) => {
              // 条数变化写回全局配置并回到第一页，避免服务端分页越界
              setPage(nextSize !== pageSize ? 1 : nextPage);
              setPageSize(nextSize);
            }}
          />
        </Space>
      </Card>
    </Space>
  );
};

export default WorkerTradesGroupedTab;
