/**
 * 模型 Tab 行动作「回测」→ 工作台内嵌抽屉（P1 batch3）。
 * 调用形状抄自模型中心 RLBacktestModal（POST /rl/backtest → RLBacktestResult，
 * model_id 取 data/models 文件 stem）；权益曲线与 RLBacktestDetailDrawer 同源
 * （backtestApi.getBacktestDetail → EquityChart）。结果指标同步返回，曲线二次拉取
 * 失败不阻断（关键结果仍在页面）。完成后「去部署」联动 DeployConfirmModal（prefill 参数）。
 */
import { useEffect, useState } from 'react';
import { Alert, App, Button, Descriptions, Drawer, Form, InputNumber, Select, Space, Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'ahooks';
import { rlApi } from '@/api/rlApi';
import type { RLBacktestResult } from '@/api/rlApi';
import { backtestApi } from '@/api';
import type { UnifiedModelRow } from '@/api/modelApi';
import type { EquityData } from '@/types/backtest';
import EquityChart from '@/components/EquityChart';
import type { DeployPrefill } from './DeployConfirmModal';

interface ModelBacktestDrawerProps {
  row: UnifiedModelRow | null; // 待回测的模型行（null = 关闭）
  onClose: () => void;
  onDeploy: (prefill: DeployPrefill) => void;
}

interface BtFormValues {
  symbol: string;
  interval: string;
  initial_capital: number;
}

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err));

export default function ModelBacktestDrawer({ row, onClose, onDeploy }: ModelBacktestDrawerProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { theme } = useTheme({ localStorageKey: 'quantcell-ui-theme' });
  const [form] = Form.useForm<BtFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<RLBacktestResult | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [curve, setCurve] = useState<EquityData[] | null>(null);
  const [curveLoading, setCurveLoading] = useState(false);
  const [curveError, setCurveError] = useState<string | null>(null);
  /** 本次回测的用户参数（去部署 prefill + 曲线 initialCash 兜底线） */
  const [lastRun, setLastRun] = useState<BtFormValues | null>(null);

  // 换行重开清掉上一次结果，避免误读旧模型指标（RLBacktestModal 同款）
  useEffect(() => {
    if (row) {
      setResult(null);
      setSubmitError(null);
      setCurve(null);
      setCurveError(null);
      setCurveLoading(false);
      setLastRun(null);
    }
  }, [row]);

  const handleRun = async (values: BtFormValues) => {
    if (!row) return;
    setSubmitting(true);
    setResult(null);
    setSubmitError(null);
    setCurve(null);
    setCurveError(null);
    setLastRun(values);
    try {
      // 与 RLBacktestModal.handleOk 同一调用形状：model_id = data/models 文件 stem
      const res = await rlApi.backtest({
        model_id: row.file_name.replace(/\.zip$/, ''),
        symbol: values.symbol,
        interval: values.interval,
        initial_capital: values.initial_capital,
      });
      setResult(res);
      message.success(t('rlbt_msg_success'));
      // 权益曲线：结果已任务化落盘，凭 task_id 查详情（RLBacktestDetailDrawer 同源）
      setCurveLoading(true);
      try {
        const detail = await backtestApi.getBacktestDetail(String(res.task_id));
        setCurve(detail.equity_curve ?? []);
      } catch (err) {
        setCurveError(errText(err));
      } finally {
        setCurveLoading(false);
      }
    } catch (err) {
      // 失败 Alert 保留在抽屉内，表单可改参数重试
      setSubmitError(errText(err));
    } finally {
      setSubmitting(false);
    }
  };

  // 后端 win_rate 是 0~1 比例，展示转百分比（RLBacktestModal 同款 fmt）
  const fmt = (v: number | null | undefined, digits = 2, suffix = '') =>
    v == null ? '-' : `${v.toFixed(digits)}${suffix}`;

  return (
    <Drawer
      title={t('wb_bt_title', { name: row?.file_name.replace(/\.zip$/, '') ?? '' })}
      open={!!row}
      onClose={onClose}
      size={520}
      destroyOnHidden
    >
      <Form<BtFormValues>
        form={form}
        layout="vertical"
        size="small"
        disabled={submitting}
        key={row?.file_name ?? 'none'}
        initialValues={{ symbol: 'BTCUSDT', interval: '1h', initial_capital: 100000 }}
        onFinish={handleRun}
      >
        <Form.Item label={t('rlbt_label_symbol')} name="symbol" rules={[{ required: true }]}>
          <Select
            options={[
              { value: 'BTCUSDT', label: 'BTCUSDT' },
              { value: 'ETHUSDT', label: 'ETHUSDT' },
              { value: 'SOLUSDT', label: 'SOLUSDT' },
            ]}
          />
        </Form.Item>
        <Form.Item label={t('rlbt_label_interval')} name="interval">
          <Select
            options={[
              { value: '15m', label: t('rlcf_opt_15m') },
              { value: '1h', label: t('rlcf_opt_1h') },
              { value: '4h', label: t('rlcf_opt_4h') },
              { value: '1d', label: t('rlcf_opt_1d') },
            ]}
          />
        </Form.Item>
        <Form.Item label={t('rlbt_label_capital')} name="initial_capital">
          <InputNumber min={1000} max={10000000} step={1000} style={{ width: '100%' }} />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting} block>
          {t('rlbt_ok')}
        </Button>
      </Form>

      {submitting && (
        <>
          <div className="wb-center-spin">
            <Spin />
          </div>
          <div className="wb-train-hint">{t('wb_bt_running')}</div>
        </>
      )}

      {/* 回测失败 Alert 保留在抽屉内（不弹走），改参数可直接重试 */}
      {submitError && <Alert type="error" showIcon style={{ marginTop: 12 }} title={t('rlbt_msg_failed')} description={submitError} />}

      {result && (
        <Space orientation="vertical" size="middle" style={{ display: 'flex', marginTop: 16 }}>
          <Descriptions
            bordered
            size="small"
            column={2}
            title={t('rlbt_result_title')}
            items={[
              { key: 'bars', label: t('rlbt_res_bars'), children: fmt(result.data_bars, 0) },
              { key: 'symbol', label: t('rlbt_res_symbol'), children: `${result.symbol ?? '-'} ${result.interval ?? ''}` },
              { key: 'trades', label: t('rlbt_res_trades'), children: fmt(result.num_trades, 0) },
              { key: 'pnl', label: t('rlbt_res_pnl'), children: fmt(result.total_pnl) },
              { key: 'return', label: t('rlbt_res_return'), children: fmt(result.total_return_pct, 2, '%') },
              { key: 'sharpe', label: 'Sharpe', children: fmt(result.sharpe_ratio) },
              { key: 'drawdown', label: t('rlbt_res_drawdown'), children: fmt(result.max_drawdown_pct, 2, '%') },
              { key: 'win_rate', label: t('rlbt_res_win_rate'), children: fmt(result.win_rate * 100, 2, '%') },
            ]}
          />

          {curveLoading && (
            <div className="wb-center-spin">
              <Spin size="small" />
            </div>
          )}
          {!curveLoading && curveError && (
            <Alert type="warning" showIcon title={t('wb_bt_equity_failed', { err: curveError })} />
          )}
          {!curveLoading && !curveError && curve && (
            // EquityChart 空数据自带兜底文案（RLBacktestDetailDrawer 同款用法）
            <EquityChart data={curve} height="260px" isDark={theme === 'dark'} initialCash={lastRun?.initial_capital} />
          )}

          {/* 回测通过 → 一键去部署（联动任务 2 的确认卡，prefill 本次回测参数） */}
          <Button
            type="primary"
            block
            onClick={() =>
              row &&
              onDeploy({
                symbol: lastRun?.symbol,
                interval: lastRun?.interval,
                initialCapital: lastRun?.initial_capital,
              })
            }
          >
            {t('wb_bt_deploy')}
          </Button>
        </Space>
      )}
    </Drawer>
  );
}
