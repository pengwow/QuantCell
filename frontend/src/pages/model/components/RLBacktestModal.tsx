import { useEffect, useState } from 'react';
import { Alert, App as AntdApp, Button, Descriptions, Form, InputNumber, Modal, Select, Space } from 'antd';
import type { UnifiedModelRow } from '@/api/modelApi';
import { rlApi, type RLBacktestResult } from '@/api/rlApi';
import { useTranslation } from 'react-i18next';
import RLBacktestDetailDrawer from './RLBacktestDetailDrawer';

interface RLBacktestModalProps {
  row: UnifiedModelRow | null; // 当前选中的模型文件行
  onClose: () => void;
}

// 回测引擎固定统一内核（与实盘同一条主回路）；结果按策略回测契约落盘，凭 task_id 打开详情抽屉
export default function RLBacktestModal({ row, onClose }: RLBacktestModalProps) {
  const [form] = Form.useForm();
  const { message } = AntdApp.useApp();
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<RLBacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detailTaskId, setDetailTaskId] = useState<string | number | null>(null); // 详情抽屉对应任务

  // 换行重新打开时清掉上一次的结果,避免误读旧模型指标
  useEffect(() => {
    if (row) {
      setResult(null);
      setError(null);
      setDetailTaskId(null);
    }
  }, [row]);

  const handleOk = async () => {
    if (!row) return;
    const values = await form.validateFields();
    setSubmitting(true);
    setResult(null);
    setError(null);
    try {
      const res = await rlApi.backtest({
        // 后端按 data/models/<model_id>.zip 解析文件,与 handleDelete 的 stem 逻辑一致
        model_id: row.file_name.replace(/\.zip$/, ''),
        ...values,
      });
      setResult(res);
      message.success(t('rlbt_msg_success'));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  // 后端 win_rate 是 0~1 比例,展示转百分比
  const fmt = (v: number | null | undefined, digits = 2, suffix = '') =>
    v == null ? '-' : `${v.toFixed(digits)}${suffix}`;

  return (
    <Modal
      title={t('rlbt_title', { name: row?.file_name ?? '' })}
      open={!!row}
      onOk={handleOk}
      onCancel={onClose}
      okText={t('rlbt_ok')}
      cancelText={t('rlbt_cancel')}
      // 回测同步执行,动辄几十秒:confirmLoading 关闭按钮,防止重复提交
      confirmLoading={submitting}
      destroyOnHidden
      width={640}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ symbol: 'BTCUSDT', interval: '1h', initial_capital: 100000 }}
        disabled={submitting}
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
      </Form>

      {/* Alert title 属性为 antd v6 写法,与 TrainingWorkbench 一致 */}
      {error && <Alert type="error" showIcon title={t('rlbt_msg_failed')} description={error} />}

      {result && (
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
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
          {/* 结果已任务化落盘：抽屉里看净值/回撤对齐图与核心指标，完整视图再进详情页 */}
          <Button type="primary" block onClick={() => setDetailTaskId(result.task_id)}>
            {t('rlbt_view_detail')}
          </Button>
        </Space>
      )}

      <RLBacktestDetailDrawer taskId={detailTaskId} onClose={() => setDetailTaskId(null)} />
    </Modal>
  );
}
