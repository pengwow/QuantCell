/**
 * 策略版本历史面板（管理页详情块 / 编辑器抽屉共用）：
 * - 列表只回元信息，展开才拉；点「查看」才请求快照全文；
 * - 「查看」弹窗内可只读预览，或切「对比当前文件」（Monaco DiffEditor，左快照右当前磁盘内容）；
 * - 「恢复」写回策略文件并留新快照，历史不删除；恢复成功后把返回的 code 交给 onRestored。
 * - 写操作受访客限制（与页面删除按钮同口径）。
 */
import { useCallback, useEffect, useState } from 'react';
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
  /** 恢复成功：把写回的文件内容交给调用方（编辑器同步 buffer；管理页刷新 overview） */
  onRestored?: (code: string) => void;
  /** 编辑器场景：本地有未保存改动时，恢复确认里额外提示会丢失 */
  dirty?: boolean;
  /** 容器附加类名（管理页展开面板 / 编辑器抽屉共用同一份列表样式） */
  className?: string;
}

const versionLabel = (v: StrategyVersionItem): string =>
  v.version ? `v${v.version}` : (v.code_hash || '').slice(0, 8) || '—';

const StrategyVersionPanel = ({ strategyName, onRestored, dirty, className }: StrategyVersionPanelProps) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const { getButtonDisabled, getButtonTooltip } = useGuestRestriction();

  const [versions, setVersions] = useState<StrategyVersionItem[]>([]);
  const [state, setState] = useState<'loading' | 'idle' | 'error'>('loading');

  // 查看弹窗：只点开才拉全文，避免展开列表就把整份代码搬一遍
  const [viewing, setViewing] = useState<StrategyVersionItem | null>(null);
  const [code, setCode] = useState<string>('');
  const [codeState, setCodeState] = useState<'loading' | 'idle' | 'error'>('loading');
  // 对比当前文件：当前磁盘内容按需拉一次并缓存
  const [diffOn, setDiffOn] = useState(false);
  const [currentCode, setCurrentCode] = useState<string | null>(null);
  const [currentLoading, setCurrentLoading] = useState(false);
  const [restoring, setRestoring] = useState(false);

  const loadVersions = useCallback(async () => {
    setState('loading');
    try {
      const res = await strategyApi.getStrategyVersions(strategyName);
      setVersions(res?.versions ?? []);
      setState('idle');
    } catch (err) {
      console.error('Failed to load strategy versions:', err);
      setState('error');
    }
  }, [strategyName]);

  useEffect(() => {
    void loadVersions();
  }, [loadVersions]);

  const openView = async (v: StrategyVersionItem) => {
    setViewing(v);
    setDiffOn(false);
    setCode('');
    setCodeState('loading');
    try {
      const detail = await strategyApi.getStrategyVersion(strategyName, v.id);
      setCode(detail?.code ?? '');
      setCodeState('idle');
    } catch (err) {
      console.error('Failed to load strategy version:', err);
      setCodeState('error');
    }
  };

  const closeView = () => {
    setViewing(null);
    setDiffOn(false);
    setCode('');
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

  const handleRestore = async (v: StrategyVersionItem) => {
    setRestoring(true);
    try {
      const res = await strategyApi.restoreStrategyVersion(strategyName, v.id);
      message.success(
        res.new_snapshot
          ? t('sm_ver_restore_ok', { label: versionLabel(v) })
          : t('sm_ver_restore_dedup', { label: versionLabel(v) }),
      );
      await loadVersions();
      setCurrentCode(null); // 文件已变，下次对比重新取
      closeView();
      onRestored?.(res.code ?? '');
    } catch (err) {
      message.error(t('sm_ver_restore_failed', { msg: String(err) }));
    } finally {
      setRestoring(false);
    }
  };

  const renderRow = (v: StrategyVersionItem, i: number) => {
    const d = v.created_at ? dayjs(v.created_at) : null;
    const time = d?.isValid() ? d.format('MM-DD HH:mm') : '—';
    const label = versionLabel(v);
    return (
      <div className="sm-ver-row" key={v.id ?? `${v.code_hash}-${i}`}>
        <span className="qc-mono sm-ver-time">{time}</span>
        <span className="qc-mono sm-ver-label">{label}</span>
        {v.is_current && <Tag className="sm-ver-current">{t('sm_ver_current')}</Tag>}
        <span className="sm-ver-actions">
          <Button type="link" size="small" onClick={() => void openView(v)}>
            {t('sm_ver_view')}
          </Button>
          <Popconfirm
            title={t('sm_ver_restore_confirm', { label })}
            description={dirty ? t('sm_ver_dirty_hint') : undefined}
            okText={t('sm_ver_restore')}
            cancelText={t('cancel')}
            disabled={getButtonDisabled()}
            onConfirm={() => void handleRestore(v)}
          >
            <Tooltip title={getButtonTooltip()}>
              {/* 禁用按钮自身不派发 hover，套一层 span 才能让访客限制提示浮出来 */}
              <span className="sm-ver-restore-wrap">
                <Button
                  type="link"
                  size="small"
                  danger
                  loading={restoring}
                  disabled={getButtonDisabled()}
                >
                  {t('sm_ver_restore')}
                </Button>
              </span>
            </Tooltip>
          </Popconfirm>
        </span>
      </div>
    );
  };

  const shown = versions.slice(0, 20);
  const label = viewing ? versionLabel(viewing) : '';

  return (
    <div className={className}>
      {state === 'loading' && <div className="sm-ver-note">{t('sm_ver_loading')}</div>}
      {state === 'error' && <div className="sm-ver-note sm-ver-note-error">{t('sm_ver_failed')}</div>}
      {state === 'idle' && versions.length === 0 && <div className="sm-ver-note">{t('sm_ver_empty')}</div>}
      {state === 'idle' && versions.length > 0 && (
        <div className="sm-ver-list">
          {shown.map(renderRow)}
          {versions.length > shown.length && <div className="sm-ver-note">{t('sm_ver_more')}</div>}
        </div>
      )}

      <Modal
        className="qc-modal"
        open={viewing !== null}
        title={t('sm_ver_view_title', { label })}
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
                <Popconfirm
                  title={t('sm_ver_restore_confirm', { label })}
                  description={dirty ? t('sm_ver_dirty_hint') : undefined}
                  okText={t('sm_ver_restore')}
                  cancelText={t('cancel')}
                  disabled={getButtonDisabled()}
                  onConfirm={() => void handleRestore(viewing)}
                >
                  <Tooltip title={getButtonTooltip()}>
                    <span className="sm-ver-restore-wrap">
                      <Button type="primary" loading={restoring} disabled={getButtonDisabled()}>
                        {t('sm_ver_restore')}
                      </Button>
                    </span>
                  </Tooltip>
                </Popconfirm>
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
    </div>
  );
};

export default StrategyVersionPanel;