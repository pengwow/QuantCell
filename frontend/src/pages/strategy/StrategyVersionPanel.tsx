/**
 * 策略版本历史面板（管理页详情块 / 编辑器抽屉共用）：
 * - inline（管理页）：一行一条「时间 · 版本号+hash · 大小·行数 · 当前 · 查看/载入编辑器」，
 *   只读审计；载入编辑器走跳转（管理页没有保存动作，不在这里改文件）。
 * - drawer（编辑器）：左时间轴 + 右快照预览（只读 Monaco，可切「对比当前文件」行内 diff），
 *   「载入编辑器」只写编辑缓冲区，不落盘；版本历史本身不写库。
 * - 列表只回元信息，点查看/选中才拉快照全文；写操作受访客限制。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App as AntApp, Button, Checkbox, Modal, Popconfirm, Spin, Tag, Tooltip } from 'antd';
import { DiffEditor, Editor } from '@monaco-editor/react';
import dayjs from 'dayjs';

import { strategyApi, type StrategyVersionItem } from '@/api';
import {
  QC_THEME_NAME,
  registerQuantcellTheme,
} from '@/monaco/quantcellTheme';
import { useGuestRestriction } from '@/hooks/useGuestRestriction';
import './StrategyManagement.css';

interface StrategyVersionPanelProps {
  strategyName: string;
  /** inline = 管理页简单列表；drawer = 编辑器抽屉双栏 */
  variant?: 'inline' | 'drawer';
  /** drawer：把快照代码交给编辑器缓冲区（调用方不改 savedCode，dirty 自然为真） */
  onLoadToEditor?: (code: string, version: StrategyVersionItem) => void;
  /** inline：跳转编辑器并从该快照载入 */
  onLoadInEditor?: (version: StrategyVersionItem) => void;
  /** drawer：编辑器有未保存改动，载入确认里额外提示会丢失 */
  dirty?: boolean;
  /** 容器附加类名 */
  className?: string;
}

const versionLabel = (v: StrategyVersionItem): string =>
  v.version ? `v${v.version}` : (v.code_hash || '').slice(0, 8) || '—';

/** 行内「版本号」列：没有声明版本时留破折号，hash 由独立列展示，避免同一串重复两遍 */
const versionTag = (v: StrategyVersionItem): string => (v.version ? `v${v.version}` : '—');

const formatSize = (n: number): string => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`);

const StrategyVersionPanel = ({
  strategyName,
  variant = 'inline',
  onLoadToEditor,
  onLoadInEditor,
  dirty,
  className,
}: StrategyVersionPanelProps) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const { getButtonDisabled, getButtonTooltip } = useGuestRestriction();
  const isDrawer = variant === 'drawer';

  const [versions, setVersions] = useState<StrategyVersionItem[]>([]);
  const [state, setState] = useState<'loading' | 'idle' | 'error'>('loading');
  const [restoring, setRestoring] = useState(false);

  // 快照全文按 id 缓存：列表只给元信息，点开/选中过一次就不再重复请求
  const codeCache = useRef<Map<number, string>>(new Map());
  // inline：查看弹窗
  const [viewing, setViewing] = useState<StrategyVersionItem | null>(null);
  // drawer：选中的快照 id
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [code, setCode] = useState('');
  const [codeState, setCodeState] = useState<'loading' | 'idle' | 'error'>('idle');
  // 对比当前文件：当前磁盘内容按需拉一次并缓存
  const [diffOn, setDiffOn] = useState(false);
  const [currentCode, setCurrentCode] = useState<string | null>(null);
  const [currentLoading, setCurrentLoading] = useState(false);

  const loadVersions = useCallback(async () => {
    setState('loading');
    try {
      const res = await strategyApi.getStrategyVersions(strategyName);
      const list = res?.versions ?? [];
      setVersions(list);
      setState('idle');
      return list;
    } catch (err) {
      console.error('Failed to load strategy versions:', err);
      setState('error');
      return [];
    }
  }, [strategyName]);

  useEffect(() => {
    void loadVersions();
  }, [loadVersions]);

  /** 取快照全文（带缓存）。返回 undefined 表示失败，调用方按 codeState 展示。 */
  const ensureCode = useCallback(
    async (v: StrategyVersionItem): Promise<string | undefined> => {
      const cached = codeCache.current.get(v.id);
      if (cached !== undefined) {
        setCode(cached);
        setCodeState('idle');
        return cached;
      }
      setCodeState('loading');
      try {
        const detail = await strategyApi.getStrategyVersion(strategyName, v.id);
        const full = detail?.code ?? '';
        codeCache.current.set(v.id, full);
        setCode(full);
        setCodeState('idle');
        return full;
      } catch (err) {
        console.error('Failed to load strategy version:', err);
        setCodeState('error');
        return undefined;
      }
    },
    [strategyName],
  );

  // 抽屉：默认选中第一条（最新快照），选中即拉全文
  useEffect(() => {
    if (!isDrawer || state !== 'idle' || versions.length === 0) return;
    if (selectedId !== null) return;
    const first = versions[0];
    setSelectedId(first.id);
    void ensureCode(first);
  }, [isDrawer, state, versions, selectedId, ensureCode]);

  const selectVersion = (v: StrategyVersionItem) => {
    setSelectedId(v.id);
    void ensureCode(v);
  };

  const openView = async (v: StrategyVersionItem) => {
    setViewing(v);
    setDiffOn(false);
    await ensureCode(v);
  };

  const closeView = () => {
    setViewing(null);
    setDiffOn(false);
  };

  const toggleDiff = async (on: boolean) => {
    setDiffOn(on);
    if (!on || currentCode !== null || currentLoading) return;
    setCurrentLoading(true);
    try {
      const detail = (await strategyApi.getStrategyDetail(strategyName)) as { code?: string };
      setCurrentCode(detail?.code ?? '');
    } catch (err) {
      console.error('Failed to load current strategy code:', err);
      message.error(t('sm_ver_current_failed'));
      setDiffOn(false);
    } finally {
      setCurrentLoading(false);
    }
  };

  /** drawer：载入到编辑缓冲区（不落盘、不新增历史） */
  const handleLoadToEditor = async (v: StrategyVersionItem) => {
    setRestoring(true);
    try {
      const full = codeCache.current.get(v.id) ?? (await ensureCode(v));
      if (full === undefined) {
        message.error(t('sm_ver_detail_failed'));
        return;
      }
      onLoadToEditor?.(full, v);
    } finally {
      setRestoring(false);
    }
  };

  const renderInlineRow = (v: StrategyVersionItem) => (
    <div className="sm-ver-row" key={v.id}>
      <span className="qc-mono sm-ver-time">
        {v.created_at && dayjs(v.created_at).isValid() ? dayjs(v.created_at).format('MM-DD HH:mm') : '—'}
      </span>
      <span className="qc-mono sm-ver-ver">
        {/* 有声明版本就「vX · hash」，没有就只给 hash（不出现「— hash」的冗余） */}
        {v.version ? <>{versionTag(v)} <i>{v.code_hash.slice(0, 8)}</i></> : v.code_hash.slice(0, 8)}
      </span>
      <span className="qc-mono sm-ver-size">
        {formatSize(v.code_size)} · {v.code_lines} 行
      </span>
      <span className="sm-ver-curcell">{v.is_current ? <Tag className="sm-ver-current">{t('sm_ver_current')}</Tag> : null}</span>
      <span className="sm-ver-actions">
        <Button type="text" size="small" className="sm-ver-btn" onClick={() => void openView(v)}>
          {t('sm_ver_view')}
        </Button>
        <Tooltip title={getButtonTooltip()}>
          {/* 禁用按钮自身不派发 hover，套一层 span 才能让访客限制提示浮出来 */}
          <span className="sm-ver-disabled-wrap">
            <Button
              type="text"
              size="small"
              className="sm-ver-btn pri"
              disabled={getButtonDisabled()}
              onClick={() => onLoadInEditor?.(v)}
            >
              {t('sm_ver_load_editor')}
            </Button>
          </span>
        </Tooltip>
      </span>
    </div>
  );

  const selected = versions.find((v) => v.id === selectedId) ?? null;
  const viewLabel = viewing ? versionLabel(viewing) : '';
  const shown = isDrawer ? versions : versions.slice(0, 20);

  return (
    <div className={className}>
      {state === 'loading' && <div className="sm-ver-note">{t('sm_ver_loading')}</div>}
      {state === 'error' && <div className="sm-ver-note sm-ver-note-error">{t('sm_ver_failed')}</div>}
      {state === 'idle' && versions.length === 0 && <div className="sm-ver-note">{t('sm_ver_empty')}</div>}

      {state === 'idle' && versions.length > 0 && !isDrawer && (
        <>
          <div className="sm-ver-list">{shown.map(renderInlineRow)}</div>
          {versions.length > shown.length && <div className="sm-ver-note">{t('sm_ver_more')}</div>}
        </>
      )}

      {state === 'idle' && versions.length > 0 && isDrawer && (
        <div className="sm-ver-split">
          <ol className="sm-ver-timeline">
            {shown.map((v) => (
              <li
                key={v.id}
                className={`sm-ver-tl-item${v.id === selectedId ? ' on' : ''}${v.is_current ? ' cur' : ''}`}
                onClick={() => selectVersion(v)}
              >
                <span className="sm-ver-tl-dot" aria-hidden="true" />
                <span className="qc-mono sm-ver-tl-t">
                  {v.created_at && dayjs(v.created_at).isValid() ? dayjs(v.created_at).format('MM-DD HH:mm') : '—'}
                </span>
                {v.version ? (
                  <span className="qc-mono sm-ver-tl-label">{versionTag(v)}</span>
                ) : null}
                <span className="qc-mono sm-ver-tl-sub">
                  {v.code_hash.slice(0, 8)} · {formatSize(v.code_size)} · {v.code_lines} 行
                  {v.is_current ? t('sm_ver_tl_current_suffix') : ''}
                </span>
              </li>
            ))}
          </ol>

          <div className="sm-ver-pane">
            <div className="sm-ver-meta">
              <span>
                {t('sm_ver_meta_version')} <b>{selected ? versionTag(selected) : '—'}</b>
              </span>
              <span>
                {t('sm_ver_meta_created')}{' '}
                <b>
                  {selected?.created_at && dayjs(selected.created_at).isValid()
                    ? dayjs(selected.created_at).format('MM-DD HH:mm')
                    : '—'}
                </b>
              </span>
              <span>
                {t('sm_ver_meta_size')} <b>{selected ? formatSize(selected.code_size) : '—'}</b> ·{' '}
                <b>{selected?.code_lines ?? 0}</b> {t('sm_ver_meta_lines')}
              </span>
              <span>
                {t('sm_ver_meta_hash')} <b className="qc-mono">{selected ? selected.code_hash.slice(0, 8) : '—'}</b>
              </span>
              {selected?.is_current && <span className="sm-ver-meta-cur">{t('sm_ver_current_file')}</span>}
            </div>

            {codeState === 'loading' || (diffOn && currentLoading) ? (
              <div className="sm-ver-code">
                <Spin style={{ display: 'block', margin: '80px auto' }} />
              </div>
            ) : codeState === 'error' ? (
              <div className="sm-ver-code">
                <div className="sm-ver-note sm-ver-note-error">{t('sm_ver_detail_failed')}</div>
              </div>
            ) : diffOn ? (
              <DiffEditor
                height="100%"
                className="sm-ver-code"
                language="python"
                theme={QC_THEME_NAME}
                beforeMount={registerQuantcellTheme}
                original={code}
                modified={currentCode ?? ''}
                options={{ renderSideBySide: false, minimap: { enabled: false }, readOnly: true }}
              />
            ) : (
              <Editor
                height="100%"
                className="sm-ver-code"
                language="python"
                theme={QC_THEME_NAME}
                beforeMount={registerQuantcellTheme}
                value={code}
                options={{ readOnly: true, minimap: { enabled: false }, scrollBeyondLastLine: false }}
              />
            )}

            <div className="sm-ver-foot">
              <Checkbox checked={diffOn} onChange={(e) => void toggleDiff(e.target.checked)}>
                {t('sm_ver_diff_toggle')}
              </Checkbox>
              <span className="sm-ver-foot-btns">
                <Popconfirm
                  title={t('sm_ver_load_confirm', { label: selected ? versionLabel(selected) : '' })}
                  description={dirty ? t('sm_ver_dirty_hint') : t('sm_ver_load_hint')}
                  okText={t('sm_ver_load_editor')}
                  cancelText={t('cancel')}
                  disabled={getButtonDisabled() || !selected || codeState !== 'idle'}
                  onConfirm={() => {
                    if (selected) void handleLoadToEditor(selected);
                  }}
                >
                  <Tooltip title={getButtonTooltip()}>
                    <span className="sm-ver-disabled-wrap">
                      <Button
                        type="primary"
                        loading={restoring}
                        disabled={getButtonDisabled() || !selected || codeState !== 'idle'}
                      >
                        {t('sm_ver_load_editor')}
                      </Button>
                    </span>
                  </Tooltip>
                </Popconfirm>
              </span>
            </div>
          </div>
        </div>
      )}

      {!isDrawer && (
        <Modal
          className="qc-modal"
          open={viewing !== null}
          title={t('sm_ver_view_title', { label: viewLabel })}
          width={960}
          onCancel={closeView}
          footer={
            viewing ? (
              <div className="sm-ver-modal-foot">
                <Checkbox checked={diffOn} onChange={(e) => void toggleDiff(e.target.checked)}>
                  {t('sm_ver_diff_toggle')}
                </Checkbox>
                <span className="sm-ver-modal-btns">
                  <Button onClick={closeView}>{t('sm_ver_close')}</Button>
                  <Tooltip title={getButtonTooltip()}>
                    <span className="sm-ver-disabled-wrap">
                      <Button
                        type="primary"
                        disabled={getButtonDisabled()}
                        onClick={() => {
                          closeView();
                          onLoadInEditor?.(viewing);
                        }}
                      >
                        {t('sm_ver_load_editor')}
                      </Button>
                    </span>
                  </Tooltip>
                </span>
              </div>
            ) : null
          }
        >
          {codeState === 'loading' || (diffOn && currentLoading) ? (
            <Spin style={{ display: 'block', margin: '80px auto' }} />
          ) : codeState === 'error' ? (
            <div className="sm-ver-note sm-ver-note-error">{t('sm_ver_detail_failed')}</div>
          ) : diffOn ? (
            <DiffEditor
              height="520px"
              language="python"
              theme={QC_THEME_NAME}
              beforeMount={registerQuantcellTheme}
              original={code}
              modified={currentCode ?? ''}
              options={{ renderSideBySide: false, minimap: { enabled: false }, readOnly: true }}
            />
          ) : (
            <Editor
              height="520px"
              language="python"
              theme={QC_THEME_NAME}
              beforeMount={registerQuantcellTheme}
              value={code}
              options={{ readOnly: true, minimap: { enabled: false }, scrollBeyondLastLine: false }}
            />
          )}
        </Modal>
      )}
    </div>
  );
};

export default StrategyVersionPanel;