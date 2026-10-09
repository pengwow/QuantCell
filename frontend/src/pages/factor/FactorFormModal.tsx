/**
 * 因子表单弹窗：新建与编辑共用。
 * - 新建：Segmented 切换「表达式 / Python 代码」
 * - 编辑：模式由因子来源锁定（表达式因子→表达式；代码因子→代码），名称只读
 * 代码模式走沙箱校验（/code/validate）与入库（/code/add）；表达式模式走 /factor/add。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  App as AntApp,
  Button,
  Form,
  Input,
  Modal,
  Segmented,
  Select,
  Space,
  Spin,
  theme,
} from 'antd';
import Editor from '@monaco-editor/react';
import { factorApi, type FactorCatalogItem } from '@/api/factor';
import { EDITABLE_CATEGORIES, categoryLabel, factorSource } from './factorMeta';

const errMsg = (e: unknown) => (e as Error)?.message || '操作失败';

/** 与后端 FactorService._CODE_NAME_RE 对齐：字母开头，字母数字下划线，1-100 */
const CODE_NAME_RE = /^[A-Za-z][A-Za-z0-9_]{0,99}$/;

/** Monaco 包装：适配 antd Form.Item 的 value/onChange 契约（antd 取首参为字段值） */
const CodeEditor: React.FC<{ value?: string; onChange?: (v: string) => void }> = ({
  value,
  onChange,
}) => {
  const { token } = theme.useToken();
  return (
    <div
      style={{
        border: `1px solid ${token.colorBorder}`,
        borderRadius: token.borderRadius,
        overflow: 'hidden',
      }}
    >
      <Editor
        height="260px"
        defaultLanguage="python"
        theme="vs-dark"
        value={value ?? ''}
        onChange={(v) => onChange?.(v ?? '')}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          lineNumbers: 'on',
          automaticLayout: true,
          tabSize: 4,
          wordWrap: 'on',
          scrollBeyondLastLine: false,
        }}
      />
    </div>
  );
};

interface Props {
  open: boolean;
  /** 传入则为编辑模式：名称只读、模式按因子来源锁定 */
  editing?: FactorCatalogItem | null;
  onCancel: () => void;
  /** 保存成功后回调，参数为因子名 */
  onSaved: (name: string) => void;
}

interface FormValues {
  factor_name: string;
  category?: string;
  expression?: string;
  code?: string;
  description?: string;
}

const FactorFormModal: React.FC<Props> = ({ open, editing, onCancel, onSaved }) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [form] = Form.useForm<FormValues>();
  const [kind, setKind] = useState<'expression' | 'code'>('expression');
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validateResult, setValidateResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [loadingDef, setLoadingDef] = useState(false);
  const [defError, setDefError] = useState<string | null>(null);

  const isEdit = !!editing;

  // 打开时初始化：新建重置为表达式模式；编辑按来源锁定模式，代码因子拉 definition 预填
  const init = useCallback(async () => {
    setValidateResult(null);
    setDefError(null);
    if (!editing) {
      setKind('expression');
      form.resetFields();
      form.setFieldsValue({ category: 'custom' });
      return;
    }
    const k = factorSource(editing) === 'code' ? 'code' : 'expression';
    setKind(k);
    form.resetFields();
    form.setFieldsValue({ factor_name: editing.name });
    if (k !== 'code') {
      form.setFieldsValue({ expression: editing.expression ?? '' });
      return;
    }
    // 代码因子：完整代码不在 catalog payload 里，走 definition 端点懒加载
    setLoadingDef(true);
    try {
      const def = await factorApi.getFactorDefinition(editing.name);
      if (def.kind === 'code') {
        form.setFieldsValue({ code: def.code, description: def.description ?? '' });
      }
    } catch (e) {
      setDefError(errMsg(e));
    } finally {
      setLoadingDef(false);
    }
  }, [editing, form]);

  // 仅在弹窗打开时初始化一次：用 ref 持有最新 init，避免 editing 引用变化重置用户输入
  const initRef = useRef(init);
  initRef.current = init;
  useEffect(() => {
    if (open) void initRef.current();
  }, [open]);

  const runValidate = async () => {
    const code = (form.getFieldValue('code') as string | undefined)?.trim();
    if (!code) {
      message.warning(t('factor_form_code_req') || '请输入代码');
      return;
    }
    setValidating(true);
    setValidateResult(null);
    try {
      const r = await factorApi.validateCodeFactor(code);
      setValidateResult(
        r.valid
          ? { ok: true, text: t('factor_form_validate_ok') || '校验通过' }
          : {
              ok: false,
              text:
                `${r.error_type ?? ''} ${r.message ?? ''}`.trim() ||
                (t('factor_form_validate_fail') || '校验失败'),
            },
      );
    } catch (e) {
      setValidateResult({ ok: false, text: errMsg(e) });
    } finally {
      setValidating(false);
    }
  };

  const submit = async () => {
    const v = await form.validateFields();
    const name = v.factor_name.trim();
    setSaving(true);
    try {
      if (kind === 'code') {
        await factorApi.addCodeFactor(name, (v.code ?? '').trim(), (v.description ?? '').trim());
      } else if (isEdit) {
        await factorApi.add(name, (v.expression ?? '').trim());
      } else {
        await factorApi.add(name, (v.expression ?? '').trim(), v.category);
      }
      message.success(t('factor_lib_toast_saved') || '因子已保存');
      onSaved(name);
    } catch (e) {
      message.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={
        isEdit
          ? t('factor_lib_edit_modal', { name: editing?.name ?? '' }) ||
            `编辑：${editing?.name ?? ''}`
          : t('factor_lib_create_modal') || '新建因子'
      }
      open={open}
      onOk={submit}
      confirmLoading={saving}
      onCancel={onCancel}
      okText={t('factor_lib_save') || '保存'}
      cancelText={t('factor_lib_cancel') || '取消'}
      destroyOnHidden
      mask={{ closable: false }}
      width={640}
    >
      {!isEdit && (
        <Segmented
          block
          value={kind}
          onChange={(v) => {
            setKind(v as 'expression' | 'code');
            setValidateResult(null);
          }}
          options={[
            { value: 'expression', label: t('factor_form_mode_expression') || '表达式' },
            { value: 'code', label: t('factor_form_mode_code') || 'Python 代码' },
          ]}
          style={{ marginBottom: 16 }}
        />
      )}

      {defError && (
        <Alert
          type="error"
          showIcon
          message={t('factor_code_load_failed') || '因子定义加载失败'}
          description={defError}
          action={
            <Button size="small" onClick={() => void init()}>
              {t('factor_code_retry') || '重试'}
            </Button>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="factor_name"
          label={t('factor_lib_form_name') || '因子名称（英文标识）'}
          rules={[
            { required: true, message: t('factor_lib_form_name_req') || '请输入名称' },
            ...(kind === 'code'
              ? [
                  {
                    pattern: CODE_NAME_RE,
                    message: t('factor_form_name_rule') || '名称需以字母开头，仅含字母数字下划线',
                  },
                ]
              : []),
          ]}
        >
          <Input disabled={isEdit} placeholder={t('factor_lib_form_name_ph') || '如 my_momentum'} />
        </Form.Item>

        {!isEdit && kind === 'expression' && (
          <Form.Item name="category" label={t('factor_lib_form_category') || '分类'}>
            <Select
              options={EDITABLE_CATEGORIES.map((c) => ({ value: c, label: categoryLabel(c, t) }))}
            />
          </Form.Item>
        )}

        {kind === 'expression' ? (
          <Form.Item
            name="expression"
            label={t('factor_lib_form_expr') || '表达式'}
            extra={t('factor_lib_form_expr_hint') || ''}
            rules={[{ required: true, message: t('factor_lib_form_expr_req') || '请输入表达式' }]}
          >
            <Input.TextArea
              rows={3}
              placeholder={t('factor_lib_form_expr_ph') || '如 close / Ref(close, 5) - 1'}
            />
          </Form.Item>
        ) : (
          <Spin spinning={loadingDef}>
            <Form.Item
              name="code"
              label={t('factor_form_code') || 'Python 代码'}
              extra={t('factor_form_code_hint') || ''}
              rules={[{ required: true, message: t('factor_form_code_req') || '请输入代码' }]}
            >
              <CodeEditor />
            </Form.Item>
            <Form.Item name="description" label={t('factor_form_desc') || '描述（可选）'}>
              <Input placeholder={t('factor_form_desc_ph') || '一句话说明这个因子在算什么'} />
            </Form.Item>
            <Space direction="vertical" size="small" style={{ display: 'flex' }}>
              <Button size="small" loading={validating} onClick={() => void runValidate()}>
                {validating
                  ? t('factor_form_validating') || '校验中…'
                  : t('factor_form_validate') || '校验'}
              </Button>
              {validateResult && (
                <Alert
                  type={validateResult.ok ? 'success' : 'error'}
                  showIcon
                  message={validateResult.text}
                />
              )}
            </Space>
          </Spin>
        )}
      </Form>
    </Modal>
  );
};

export default FactorFormModal;
