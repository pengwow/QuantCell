/**
 * 指标参数编辑弹窗（TradingView 式：图例 ⚙ → 小浮窗 → 确认即时重算）
 * 表单按指标的 defaultParams 键动态生成，确认后由 ChartPage 走 overrideIndicator / 重算链路。
 */
import { useEffect } from 'react';
import { Form, InputNumber, Modal } from 'antd';
import type { IndicatorParams } from '../hooks/useIndicators';

// 常见参数键的中文名，未命中回显原键名
const PARAM_LABELS: Record<string, string> = {
  length: '周期',
  k: 'K 值',
  d: 'D 值',
  j: 'J 值',
  m: '均线周期',
  n: '均线周期',
  fast: '快线周期',
  slow: '慢线周期',
  signal: '信号平滑',
  smooth: '平滑周期',
  ma1: '均线 1',
  ma2: '均线 2',
  stdDev: '标准差倍数',
};

interface Props {
  open: boolean;
  indicatorName: string;
  /** 可编辑参数（键 = defaultParams 的键） */
  paramSchema: IndicatorParams;
  initialValues: IndicatorParams;
  onOk: (values: IndicatorParams) => void;
  onCancel: () => void;
}

export const IndicatorParamModal = ({ open, indicatorName, paramSchema, initialValues, onOk, onCancel }: Props) => {
  const [form] = Form.useForm();

  // 每次打开回显当前值（Modal 不销毁，避免脏值残留）
  useEffect(() => {
    if (open) form.setFieldsValue(initialValues as Record<string, number>);
  }, [open, initialValues, form]);

  const keys = Object.keys(paramSchema || {});

  return (
    <Modal
      title={`${indicatorName} 参数`}
      open={open}
      onCancel={onCancel}
      destroyOnHidden // antd v6：「destroyOnClose」已废弃，关闭即销毁表单避免脏值残留
      width={380}
      onOk={() => form.submit()}
    >
      <Form form={form} layout="vertical" onFinish={(values) => {
        // 只透传数值参数（InputNumber 已约束），与 klinecharts calcParams 语义一致
        const numeric: IndicatorParams = {};
        keys.forEach((k) => {
          const v = values[k];
          if (typeof v === 'number' && isFinite(v)) numeric[k] = v;
        });
        onOk(numeric);
      }}>
        {keys.length === 0 && (
          // OBV/AD 等无可调参数的指标：不留空弹窗，明确告知
          <div style={{ color: 'var(--ant-color-text-secondary)' }}>该指标无可调参数</div>
        )}
        {keys.map((k) => (
          <Form.Item key={k} name={k} label={`${PARAM_LABELS[k] || k} (${k})`} rules={[{ required: true, message: '请输入数值' }]}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
        ))}
      </Form>
    </Modal>
  );
};
