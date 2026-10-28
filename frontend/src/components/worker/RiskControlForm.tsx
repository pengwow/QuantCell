/**
 * Worker 人工风控表单块
 *
 * 受控于父级 FormInstance（CreateModal / EditModal 的单表单内嵌分组），不自带 Form。
 * 所有字段名 risk_ 前缀；% ↔ 0-1、分钟 ↔ 秒的单位转换收敛在本组件导出的纯函数中，
 * 外部（提交 / 回填）一律面对后端口径（0-1、秒）。
 *
 * 注意：Switch 关闭时字段区整体卸载（值经 antd Form preserve 保留在 store 中），
 * 父级提交时必须用 form.getFieldsValue([risk_ 字段名数组]) 取值，
 * validateFields 只返回挂载中的字段，拿不到隐藏字段的值。
 */
import React from 'react';
import {
  Col,
  Collapse,
  Divider,
  Form,
  InputNumber,
  Row,
  Space,
  Switch,
  Typography,
} from 'antd';
import type { FormInstance } from 'antd';
import type { RiskControlOut, RiskControlUpsert } from '../../types/worker';

const { Text } = Typography;

/**
 * 风控表单值（UI 口径：% 用 0-100、冷却用分钟；未填 null）
 */
export interface RiskFormValues {
  risk_enabled: boolean;
  risk_max_position_pct?: number | null;
  risk_max_position_size?: number | null;
  risk_daily_loss_amount?: number | null;
  risk_daily_loss_limit?: number | null;
  risk_max_drawdown?: number | null;
  risk_max_leverage?: number | null;
  /** UI 为分钟（提交 ×60 转秒），字段名与后端列保持 secs 口径 */
  risk_circuit_breaker_cooldown_secs?: number | null;
}

/** 全空默认（未配置过风控时的表单初值） */
export const EMPTY_RISK_VALUES: RiskFormValues = {
  risk_enabled: false,
  risk_max_position_pct: null,
  risk_max_position_size: null,
  risk_daily_loss_amount: null,
  risk_daily_loss_limit: null,
  risk_max_drawdown: null,
  risk_max_leverage: null,
  risk_circuit_breaker_cooldown_secs: null,
};

/** 父级提交/回填时取值用的 risk_ 字段名数组（含 enabled） */
export const RISK_FORM_FIELDS = [
  'risk_enabled',
  'risk_max_position_pct',
  'risk_max_position_size',
  'risk_daily_loss_amount',
  'risk_daily_loss_limit',
  'risk_max_drawdown',
  'risk_max_leverage',
  'risk_circuit_breaker_cooldown_secs',
] as const;

/** 空值统一为 null（null/undefined/空串等价——empty-is-null） */
const orNull = (v: number | string | null | undefined): number | null =>
  v === null || v === undefined || v === '' ? null : Number(v);

/** % (0-100) → 0-1 */
const toRatio = (v: number | null | undefined): number | null => {
  const n = orNull(v);
  return n === null ? null : n / 100;
};

/** 0-1 → % (0-100) */
const toPct = (v: number | null | undefined): number | null =>
  v === null || v === undefined ? null : v * 100;

/** 表单值(% 口径) → PUT payload(0-1 口径 + 绝对值字段)，未填一律 null */
export function formValueToPayload(values: Partial<RiskFormValues>): RiskControlUpsert {
  const mins = orNull(values.risk_circuit_breaker_cooldown_secs);
  return {
    enabled: Boolean(values.risk_enabled),
    max_position_pct: toRatio(values.risk_max_position_pct),
    max_position_size: orNull(values.risk_max_position_size),
    daily_loss_amount: orNull(values.risk_daily_loss_amount),
    daily_loss_limit: toRatio(values.risk_daily_loss_limit),
    max_drawdown: toRatio(values.risk_max_drawdown),
    max_leverage: orNull(values.risk_max_leverage),
    circuit_breaker_cooldown_secs: mins === null ? null : Math.round(mins * 60),
  };
}

/** GET 回填 → 表单值（pct/limit/drawdown ×100、冷却秒 ÷60、绝对值原样；out 为 null 时取 prev 或全空） */
export function payloadToFormValue(
  out: RiskControlOut | null,
  prev?: RiskFormValues
): RiskFormValues {
  if (!out) {
    return prev ?? EMPTY_RISK_VALUES;
  }
  return {
    risk_enabled: out.enabled,
    risk_max_position_pct: toPct(out.max_position_pct),
    risk_max_position_size: out.max_position_size,
    risk_daily_loss_amount: out.daily_loss_amount,
    risk_daily_loss_limit: toPct(out.daily_loss_limit),
    risk_max_drawdown: toPct(out.max_drawdown),
    risk_max_leverage: out.max_leverage,
    risk_circuit_breaker_cooldown_secs:
      out.circuit_breaker_cooldown_secs === null || out.circuit_breaker_cooldown_secs === undefined
        ? null
        : out.circuit_breaker_cooldown_secs / 60,
  };
}

/** empty-is-null 语义比较（null/undefined/空串视为等价空），用于判断用户是否改过风控字段 */
export function sameRiskValues(a: Partial<RiskFormValues>, b: Partial<RiskFormValues>): boolean {
  if (Boolean(a.risk_enabled) !== Boolean(b.risk_enabled)) return false;
  // slice(1) 运行时已排除 risk_enabled，但 TS 联合索引仍带出 boolean，断言收窄为数值口径
  return RISK_FORM_FIELDS.slice(1).every(
    (f) =>
      orNull(a[f] as number | string | null | undefined) ===
      orNull(b[f] as number | string | null | undefined)
  );
}

/** 通用数字输入：百分比口径（0-100） */
const pctInput = (placeholder: string) => (
  <InputNumber
    style={{ width: '100%' }}
    min={0}
    max={100}
    step={0.5}
    addonAfter="%"
    placeholder={placeholder}
  />
);

interface RiskControlFormProps {
  /** 父级表单实例（字段注册进父 Form） */
  form: FormInstance;
}

const RiskControlForm: React.FC<RiskControlFormProps> = ({ form }) => {
  // Switch 关 → 折叠字段区（值保留不清空，随 PUT 原样提交；重新启用后原值回填）
  const enabled = Form.useWatch('risk_enabled', form);

  return (
    <>
      <Divider>人工风控</Divider>
      <Form.Item
        name="risk_enabled"
        label="启用风控防护"
        valuePropName="checked"
        tooltip="启用后本 Worker 的交易在引擎风控层按下方阈值拦截；关闭后不再拦截任何交易"
      >
        <Switch />
      </Form.Item>
      <Text type="secondary">
        关闭后不再拦截交易，但已填字段值会保留，重新启用后自动恢复。未填写的项沿用引擎内置默认。
      </Text>

      {enabled && (
        <Space orientation="vertical" size="middle" style={{ display: 'flex', marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="risk_max_position_pct"
                label="单币种最大仓位占比"
                tooltip="持仓市值占账户权益的比例上限"
              >
                {pctInput('引擎默认：无')}
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="risk_daily_loss_limit"
                label="当日亏损占比上限"
                tooltip="当日累计亏损占账户权益的比例上限，超出后拦截新开仓"
              >
                {pctInput('引擎默认：无')}
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="risk_daily_loss_amount"
                label="当日亏损金额上限"
                tooltip="当日累计亏损金额（USDT）上限，超出后拦截新开仓"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  addonAfter="USDT"
                  placeholder="引擎默认：无"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="risk_max_drawdown"
                label="最大回撤上限"
                tooltip="账户净值自高点的最大回撤比例上限"
              >
                {pctInput('引擎默认：15%')}
              </Form.Item>
            </Col>
          </Row>
          <Text type="secondary">
            同组限制同时填写时取更严格者生效：仓位（占比 / 名义价值）、当日亏损（占比 / 金额）。
          </Text>

          <Collapse
            items={[
              {
                key: 'advanced',
                label: '高级设置',
                children: (
                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item
                        name="risk_max_position_size"
                        label="单币种最大持仓名义价值"
                        tooltip="持仓市值绝对值（USDT）上限"
                      >
                        <InputNumber
                          style={{ width: '100%' }}
                          min={0}
                          addonAfter="USDT"
                          placeholder="引擎默认：无"
                        />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="risk_max_leverage"
                        label="最大杠杆倍数"
                        tooltip="允许使用的最大杠杆"
                      >
                        <InputNumber
                          style={{ width: '100%' }}
                          min={1}
                          max={200}
                          addonAfter="x"
                          placeholder="引擎默认：5x"
                        />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="risk_circuit_breaker_cooldown_secs"
                        label="熔断冷却时长"
                        tooltip="触发熔断后的交易暂停时长，冷却期内不下新单"
                      >
                        <InputNumber
                          style={{ width: '100%' }}
                          min={0}
                          max={10080}
                          addonAfter="分钟"
                          placeholder="引擎默认：60 分钟"
                        />
                      </Form.Item>
                    </Col>
                  </Row>
                ),
              },
            ]}
          />
        </Space>
      )}
    </>
  );
};

export default RiskControlForm;
