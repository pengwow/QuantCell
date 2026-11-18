/**
 * 模型 Tab 行动作「部署」→ paper 部署二次确认卡（P1 batch3 + 契约纠偏 A）。
 *
 * 三步串联（后端方案 A：策略由 deploy-spec 端点注册，不再从策略库下拉选现成 RL 策略）：
 *   1. POST /rl/train/{task_id}/deploy-spec（rlApi.deploySpec，trainFetch 裸 JSON 通道）
 *      → {strategy, worker: 完整 WorkerCreate body（strategy_id/strategy_name 已回填）}
 *   2. 用户可编辑字段合并进返回的 worker body → workerApi.createWorker（POST /workers）
 *   3. workerApi.startWorker（POST /workers/{id}/lifecycle/start，/strategy-worker 页同款调用）
 * 任一步失败：toast 带步骤名与后端错误文本，卡片保持打开可重试；创建成功而启动失败时
 * 重试跳过重建（避免重复 worker），直接重试启动。
 *
 * task_id 关联：TrainPanel 把最近一次训练任务落在 localStorage（TASK_KEY），本卡打开时
 * 取回任务快照，仅当 status=done 且其 model_path 与当前模型行匹配才启用部署；否则降级
 * 禁用 + 说明文案，不伪造 task_id。
 *
 * 锁定项（RL paper 后端 v1 硬约束 + 方案 A 裁决）在卡片明示：exchange=binance、
 * market_type=futures、trading_mode=paper、多品种输入仅取第一个（RL host 单品种）。
 * live 仅灰态展示（主网闸门未开放，需另行授权流程），不提供选择。
 */
import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Descriptions, Form, Input, InputNumber, Modal, Select, Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { workerApi } from '@/api/workerApi';
import { rlApi } from '@/api/rlApi';
import type { CreateWorkerRequest } from '@/types/worker';
import type { UnifiedModelRow } from '@/api/modelApi';
import { TASK_KEY } from './TrainPanel';

/** 「去部署」联动 prefill：来自回测抽屉最后一次回测参数，缺省走表单默认值 */
export interface DeployPrefill {
  symbol?: string;
  interval?: string;
  initialCapital?: number;
}

interface DeployConfirmModalProps {
  row: UnifiedModelRow | null; // 待部署的模型行（null = 关闭）
  prefill?: DeployPrefill | null;
  onClose: () => void;
  onDeployed: (workerId: number) => void;
}

interface DeployFormValues {
  name: string;
  description?: string;
  symbol: string;
  interval: string;
  initial_capital: number;
  max_position_size: number;
  leverage: number;
}

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err));

/** interval 白名单（后端 _PAPER_INTERVAL_SECONDS 值域），选择器化 */
const INTERVALS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'] as const;
const INTERVAL_LABEL: Record<(typeof INTERVALS)[number], string> = {
  '1m': 'period_1m',
  '5m': 'period_5m',
  '15m': 'rlcf_opt_15m',
  '30m': 'period_30m',
  '1h': 'rlcf_opt_1h',
  '4h': 'rlcf_opt_4h',
  '1d': 'rlcf_opt_1d',
};

/** 三步串联的失败步骤名（toast/Alert 用 i18n 键） */
const STEP_KEY = {
  spec: 'wb_deploy_step_spec',
  create: 'wb_deploy_step_create',
  start: 'wb_deploy_step_start',
} as const;
type DeployStep = keyof typeof STEP_KEY;

/** 训练任务的 model_path / 行 file_name 归一成 stem（不含目录与 .zip 后缀） */
const stemOf = (p: string | null | undefined): string =>
  (p ?? '').replace(/\\/g, '/').split('/').pop()?.replace(/\.zip$/, '') ?? '';

export default function DeployConfirmModal({ row, prefill, onClose, onDeployed }: DeployConfirmModalProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [form] = Form.useForm<DeployFormValues>();
  const [submitting, setSubmitting] = useState(false);
  /** task 关联三态：loading（查询中）/ ready（task_id 可用）/ none（无可用任务，降级禁用） */
  const [taskState, setTaskState] = useState<{ status: 'loading' | 'ready' | 'none'; taskId?: string }>({
    status: 'loading',
  });
  /** 内联失败详情（toast 之外保留在卡片内，重试不清空表单） */
  const [fail, setFail] = useState<{ step: DeployStep; msg: string } | null>(null);
  /** 步骤 2 已成功创建的 worker id：启动失败重试时跳过重建，避免重复 worker */
  const createdIdRef = useRef<number | null>(null);

  // 打开时解析最近一次训练任务（TrainPanel localStorage 持久化）：done 且 model 匹配才可用
  useEffect(() => {
    if (!row) {
      setFail(null);
      createdIdRef.current = null;
      return;
    }
    let alive = true;
    setTaskState({ status: 'loading' });
    setFail(null);
    createdIdRef.current = null;
    const id = localStorage.getItem(TASK_KEY);
    if (!id) {
      setTaskState({ status: 'none' });
      return;
    }
    rlApi
      .getTrainTask(id)
      .then((task) => {
        if (!alive) return;
        const rowStem = row.file_name.replace(/\.zip$/, '');
        const modelMatched = stemOf(task.model_path) === rowStem || task.model_path === row.path;
        if (task.status === 'done' && modelMatched) setTaskState({ status: 'ready', taskId: id });
        else setTaskState({ status: 'none' });
      })
      .catch(() => {
        // 任务不存在（后端重启清空）/网络失败：同样降级，不伪造 task_id
        if (alive) setTaskState({ status: 'none' });
      });
    return () => {
      alive = false;
    };
  }, [row]);

  const modelStem = (row?.file_name ?? '').replace(/\.zip$/, '');
  const deployBlocked = taskState.status !== 'ready';

  const handleSubmit = async () => {
    if (!row) return;
    // 必填校验失败由表单 inline 报错呈现，不走失败 toast
    let values: DeployFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setSubmitting(true);
    setFail(null);
    // 三步串联，失败归属到具体步骤（toast + 卡片内 Alert，卡片保持打开可重试）
    let step: DeployStep = 'spec';
    try {
      // —— 步骤 1/3 deploy-spec：注册策略 + 取完整 WorkerCreate body（409/422/404 抛 HTTP 错误文本）
      const spec = await rlApi.deploySpec(taskState.taskId!);
      const body: CreateWorkerRequest = { ...(spec.worker ?? {}) };
      step = 'create';

      // —— 合并用户可编辑字段；锁定项强制覆盖（binance/futures/paper，锚定 RL paper v1 硬约束）
      const symbols = values.symbol
        .split(/[,，、\s]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      body.name = values.name;
      body.description = values.description;
      body.trading_config = {
        ...(body.trading_config ?? {}),
        exchange: 'binance',
        market_type: 'futures',
        trading_mode: 'paper',
        interval: values.interval,
        // 多品种仅取第一个并已在卡片明示（RL host 单品种）
        symbols_config: { type: 'symbols', symbols: [symbols[0]] },
      };
      body.config = {
        ...(body.config ?? {}),
        initial_capital: values.initial_capital,
        max_position_size: values.max_position_size,
        leverage: values.leverage,
      };

      // —— 步骤 2/3 创建工作进程（重试路径：上次已创建成功则跳过，避免重复 worker）
      if (createdIdRef.current == null) {
        const worker = await workerApi.createWorker(body);
        createdIdRef.current = worker.id;
      }
      step = 'start';

      // —— 步骤 3/3 启动（/strategy-worker 页 startWorker 同款：POST /workers/{id}/lifecycle/start）
      await workerApi.startWorker(createdIdRef.current);

      message.success(t('wb_deploy_success', { name: body.name, id: createdIdRef.current }));
      onDeployed(createdIdRef.current);
      onClose();
    } catch (err) {
      const msg = errText(err);
      setFail({ step, msg });
      message.error(t('wb_deploy_failed_step', { step: t(STEP_KEY[step]), err: msg }));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={t('wb_deploy_title', { name: modelStem })}
      open={!!row}
      onCancel={onClose}
      width={560}
      destroyOnHidden
      footer={
        <>
          <Button onClick={onClose}>{t('cancel')}</Button>
          <Button
            type="primary"
            onClick={handleSubmit}
            loading={submitting}
            disabled={deployBlocked}
          >
            {t('wb_deploy_confirm')}
          </Button>
        </>
      }
    >
      {/* 边界文案：说清「将创建 paper 工作进程并开始模拟交易」再允许确定 */}
      <Alert type="warning" showIcon title={t('wb_deploy_boundary_title')} description={t('wb_deploy_boundary')} style={{ marginBottom: 12 }} />

      {taskState.status === 'loading' && (
        <div className="wb-center-spin">
          <Spin size="small" />
        </div>
      )}
      {/* 无可关联的 done 训练任务：降级禁用 + 说明，不伪造 task_id */}
      {taskState.status === 'none' && (
        <Alert type="info" showIcon title={t('wb_deploy_no_task')} style={{ marginBottom: 12 }} />
      )}

      {/* 三步失败详情（含步骤名 + 后端错误文本）；创建成功而启动失败给出重试去向 */}
      {fail && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('wb_deploy_failed_step', { step: t(STEP_KEY[fail.step]), err: fail.msg })}
          description={createdIdRef.current != null ? t('wb_deploy_start_retry_hint') : undefined}
        />
      )}

      <Descriptions
        bordered
        size="small"
        column={2}
        style={{ marginBottom: 12 }}
        items={[
          { key: 'model', label: t('wb_train_model_path'), children: <span className="wb-nowrap-mono" title={row?.file_name}>{row?.file_name ?? '-'}</span>, span: 2 },
          { key: 'exchange', label: t('exchange'), children: t('wb_deploy_locked_exchange') },
          { key: 'market', label: t('market_type'), children: t('wb_deploy_locked_market') },
          {
            key: 'mode',
            label: t('trading_mode'),
            span: 2,
            children: (
              <>
                {t('wb_deploy_mode_paper')}
                <span style={{ marginLeft: 8, color: 'var(--text-hint)' }}>{t('wb_deploy_live_note')}</span>
              </>
            ),
          },
        ]}
      />

      <Form<DeployFormValues>
        form={form}
        layout="vertical"
        size="small"
        disabled={submitting}
        key={row?.file_name ?? 'none'}
        initialValues={{
          name: `${modelStem}-paper`,
          symbol: prefill?.symbol ?? 'BTCUSDT',
          interval: prefill?.interval ?? '1h',
          initial_capital: prefill?.initialCapital ?? 10000,
          max_position_size: 0.1,
          leverage: 1,
        }}
      >
        <Form.Item label={t('worker_name')} name="name" rules={[{ required: true }, { max: 50 }]}>
          <Input placeholder="my-model-paper" />
        </Form.Item>
        <Form.Item label={t('description')} name="description">
          <Input placeholder={modelStem} maxLength={200} />
        </Form.Item>

        <Form.Item
          label={t('rlbt_label_symbol')}
          name="symbol"
          rules={[{ required: true }]}
          extra={t('wb_deploy_symbol_hint')}
        >
          <Input placeholder="BTCUSDT" />
        </Form.Item>

        <Form.Item label={t('rlbt_label_interval')} name="interval" rules={[{ required: true }]}>
          <Select options={INTERVALS.map((v) => ({ value: v, label: t(INTERVAL_LABEL[v]) }))} />
        </Form.Item>

        <Form.Item label={t('rlbt_label_capital')} name="initial_capital" rules={[{ required: true }]}>
          <InputNumber min={100} step={1000} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label={t('max_position_size')} name="max_position_size">
          <InputNumber min={0.01} max={1} step={0.01} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label={t('leverage')} name="leverage">
          <InputNumber min={1} max={125} style={{ width: '100%' }} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
