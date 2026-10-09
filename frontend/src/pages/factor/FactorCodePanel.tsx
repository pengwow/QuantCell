/**
 * 因子详情「代码」Tab：挂载时懒加载因子完整定义并按形态渲染。
 * - expression：单行表达式 + 复制
 * - code：描述/hash/行数 + 只读 Monaco（Python 高亮、行号）
 * - composite：训练窗口 + 成分 Collapse，每个成分展开才挂载 Monaco（防多实例膨胀）
 */
import { Component, type ErrorInfo, type ReactNode, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Collapse,
  Descriptions,
  Flex,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import Editor from '@monaco-editor/react';
import { factorApi, type FactorCatalogItem, type FactorDefinition } from '@/api/factor';

/** Monaco 渲染失败兜底：退化为 <pre>，复制功能不受影响 */
class EditorBoundary extends Component<{ children: ReactNode; fallbackPre: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Monaco loader/worker 异常仅降级展示，不抛白屏
  }
  render() {
    return this.state.failed ? this.props.fallbackPre : this.props.children;
  }
}

const codePreStyle = (maxHeight: number): React.CSSProperties => ({
  whiteSpace: 'pre-wrap',
  margin: 0,
  fontSize: 13,
  maxHeight,
  overflow: 'auto',
  padding: 12,
  background: '#1e1e1e',
  color: '#d4d4d4',
  borderRadius: 6,
});

/** 只读 Python 代码块（Monaco；加载/渲染异常由 EditorBoundary 降级为 <pre>） */
const ReadOnlyCode: React.FC<{ code: string; height?: number }> = ({ code, height = 460 }) => (
  <EditorBoundary fallbackPre={<pre style={codePreStyle(height)}>{code}</pre>}>
    <Editor
      defaultLanguage="python"
      theme="vs-dark"
      value={code}
      height={height}
      loading={<Spin />}
      options={{
        readOnly: true,
        minimap: { enabled: false },
        fontSize: 13,
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        wordWrap: 'on',
        automaticLayout: true,
      }}
    />
  </EditorBoundary>
);

const FactorCodePanel: React.FC<{ factor: FactorCatalogItem }> = ({ factor }) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [def, setDef] = useState<FactorDefinition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDef(await factorApi.getFactorDefinition(factor.name));
    } catch (e) {
      setError((e as Error)?.message || 'error');
    } finally {
      setLoading(false);
    }
  }, [factor.name]);

  useEffect(() => {
    void load();
  }, [load]);

  const copy = (text: string) => {
    void navigator.clipboard
      .writeText(text)
      .then(() => message.success(t('factor_code_copied') || '已复制'))
      .catch(() => message.error('copy failed'));
  };

  if (loading) {
    return (
      <Flex justify="center" align="center" gap="middle" style={{ padding: 48 }}>
        <Spin />
        <span>{t('factor_code_loading') || '加载因子定义…'}</span>
      </Flex>
    );
  }
  if (error || !def) {
    return (
      <Alert
        type="error"
        showIcon
        message={t('factor_code_load_failed') || '因子定义加载失败'}
        description={error}
        action={
          <Button size="small" onClick={() => void load()}>
            {t('factor_code_retry') || '重试'}
          </Button>
        }
      />
    );
  }

  if (def.kind === 'expression') {
    return (
      <Card size="small">
        <Flex justify="space-between" align="center" gap="middle">
          <Typography.Text code style={{ fontSize: 14 }}>
            {def.expression}
          </Typography.Text>
          <Button size="small" icon={<CopyOutlined />} onClick={() => copy(def.expression)}>
            {t('factor_code_copy') || '复制代码'}
          </Button>
        </Flex>
      </Card>
    );
  }

  if (def.kind === 'code') {
    const lines = def.code.split('\n').length;
    return (
      <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
        <Card size="small">
          <Flex justify="space-between" align="center" wrap="wrap" gap="small">
            <Space size="small" wrap>
              {def.description && <span>{def.description}</span>}
              <Tag>{lines} lines</Tag>
              <Typography.Text type="secondary" style={{ fontSize: 12 }} title={def.code_hash}>
                {t('factor_code_hash') || '代码 hash'}: {def.code_hash}
              </Typography.Text>
            </Space>
            <Button size="small" icon={<CopyOutlined />} onClick={() => copy(def.code)}>
              {t('factor_code_copy') || '复制代码'}
            </Button>
          </Flex>
        </Card>
        <ReadOnlyCode code={def.code} />
      </Space>
    );
  }

  // composite
  const tw = def.train_window ?? {};
  return (
    <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
      <Card size="small">
        <Descriptions
          column={{ xs: 1, sm: 2 }}
          size="small"
          items={[
            { key: 'method', label: 'Method', children: <Tag>{def.method}</Tag> },
            {
              key: 'window',
              label: t('factor_code_train_window') || '训练窗口',
              children: `${tw.start ?? '—'} ~ ${tw.end ?? '—'} · ${tw.interval ?? '—'} · ${tw.candle_type ?? '—'}`,
            },
          ]}
        />
      </Card>
      <Typography.Text strong>
        {t('factor_code_constituents_n', { n: def.constituents.length }) ||
          `成分（${def.constituents.length}）`}
      </Typography.Text>
      <Collapse
        items={def.constituents.map((c, i) => ({
          key: i,
          label: (
            <Space size="small">
              <span>
                {t('factor_code_constituent', { i: i + 1, w: `${(c.weight * 100).toFixed(1)}%` }) ||
                  `成分 ${i + 1} · 权重 ${(c.weight * 100).toFixed(1)}%`}
              </span>
              <Tag title={c.code_hash}>{c.code_hash.slice(0, 8)}</Tag>
            </Space>
          ),
          children: (
            <Space direction="vertical" size="small" style={{ display: 'flex' }}>
              <Flex justify="flex-end">
                <Button size="small" icon={<CopyOutlined />} onClick={() => copy(c.code)}>
                  {t('factor_code_copy') || '复制代码'}
                </Button>
              </Flex>
              <ReadOnlyCode code={c.code} height={360} />
            </Space>
          ),
          // 折叠即销毁 Editor，避免 20 个成分累积 Monaco 实例
          destroyOnHidden: true,
        }))}
      />
    </Space>
  );
};

export default FactorCodePanel;
