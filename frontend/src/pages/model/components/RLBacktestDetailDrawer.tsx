/**
 * RL 模型回测详情抽屉（模型中心内嵌）。
 * RL 回测结果按策略回测同一契约落盘，直接复用 backtestApi.getBacktestDetail 拉
 * 全量数据：核心指标 + 净值/回撤对齐图（EquityChart 自带回撤水下子图）。
 * 逐笔明细 / 决策记录 / 回放等完整视图引导到回测详情页，抽屉保持轻量。
 */
import { useEffect, useState } from 'react';
import { Alert, Button, Descriptions, Drawer, Space, Spin } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useTheme } from 'ahooks';
import { useTranslation } from 'react-i18next';
import { backtestApi } from '@/api';
import type { BacktestDetailData } from '@/types/backtest';
import EquityChart from '@/components/EquityChart';
import { METRIC_CARDS, formatMetricValue } from '@/pages/backtest/metricCards';

interface RLBacktestDetailDrawerProps {
  taskId: string | number | null; // 回测任务 id；null 表示关闭
  onClose: () => void;
}

// 抽屉顶部核心指标 key（顺序即展示顺序），label/单位复用详情页卡片规格
const DRAWER_METRIC_KEYS = ['total_return', 'max_drawdown', 'sharpe_ratio', 'win_rate', 'total_pnl', 'total_trades'];

const RLBacktestDetailDrawer = ({ taskId, onClose }: RLBacktestDetailDrawerProps) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { theme } = useTheme({ localStorageKey: 'quantcell-ui-theme' });
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<BacktestDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (taskId == null) return;
    setLoading(true);
    setData(null);
    setError(null);
    // 与策略回测详情页同一数据源：RL 回测的 task_id 直接可查
    backtestApi
      .getBacktestDetail(String(taskId))
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [taskId]);

  const config = data?.backtest_config;
  const metricItems = (data?.metrics ?? [])
    // 缺失的指标行不展示；按 DRAWER_METRIC_KEYS 的顺序排列
    .filter((m) => DRAWER_METRIC_KEYS.includes(m.key))
    .sort((a, b) => DRAWER_METRIC_KEYS.indexOf(a.key) - DRAWER_METRIC_KEYS.indexOf(b.key))
    .map((m) => {
      const spec = METRIC_CARDS.find((c) => c.key === m.key);
      const value = spec && typeof m.value === 'number' ? formatMetricValue(spec, m.value) : String(m.value ?? '-');
      return { key: m.key, label: spec?.label ?? m.name, children: value };
    });

  return (
    <Drawer title={t('rlbt_drawer_title')} open={taskId != null} onClose={onClose} size={860} destroyOnHidden>
      {loading && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
          <Spin />
        </div>
      )}

      {!loading && error && <Alert type="error" showIcon title={t('rlbt_msg_failed')} description={error} />}

      {!loading && !error && data && (
        <Space orientation="vertical" size="large" style={{ display: 'flex' }}>
          <Descriptions
            bordered
            size="small"
            column={2}
            items={[
              { key: 'strategy', label: t('backtest_strategy_name'), children: data.strategy_name || '-' },
              {
                key: 'symbol',
                label: t('rlbt_res_symbol'),
                children: `${config?.symbols?.[0] ?? '-'} ${config?.interval ?? ''}`,
              },
              ...metricItems,
            ]}
          />

          {/* EquityChart 空数据自带兜底文案，无需再包 Empty */}
          <EquityChart
            data={data.equity_curve ?? []}
            isDark={theme === 'dark'}
            initialCash={config?.initial_cash}
          />

          {/* 完整视图（逐笔明细 / 决策记录 / 回放）在回测详情页；路由注册的是 detail/:backtestId，缺 detail/ 段会 404 */}
          <Button type="primary" block onClick={() => navigate(`/backtest/detail/${data.id}`)}>
            {t('rlbt_open_full_page')}
          </Button>
        </Space>
      )}
    </Drawer>
  );
};

export default RLBacktestDetailDrawer;
