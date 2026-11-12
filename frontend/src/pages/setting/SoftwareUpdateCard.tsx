import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Input, Modal, Progress, Space, Tag, Typography, message } from 'antd';
import { getVersion } from '@tauri-apps/api/app';
import { getUpdateMirror, setUpdateMirror } from '../../desktop/updateBridge';
import { useUpdateStore } from '../../desktop/updateStore';
import { runCheck, runInstall } from '../../desktop/useUpdater';

/** 通用设置页的「软件更新」卡（仅桌面端渲染，调用方负责 isTauri 守卫） */
export default function SoftwareUpdateCard() {
  const { t } = useTranslation();
  const status = useUpdateStore((s) => s.status);
  const info = useUpdateStore((s) => s.info);
  const downloaded = useUpdateStore((s) => s.downloaded);
  const total = useUpdateStore((s) => s.total);
  const error = useUpdateStore((s) => s.error);

  const [currentVersion, setCurrentVersion] = useState('');
  const [mirror, setMirror] = useState('');
  const [savingMirror, setSavingMirror] = useState(false);

  useEffect(() => {
    void getVersion().then(setCurrentVersion);
    void getUpdateMirror().then((value) => setMirror(value ?? ''));
  }, []);

  const handleSaveMirror = async () => {
    setSavingMirror(true);
    try {
      await setUpdateMirror(mirror.trim() || null);
      message.success(t('update_mirror_saved'));
    } catch (e) {
      message.error(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingMirror(false);
    }
  };

  // 有运行中策略时二次确认：安装后应用会重启，策略会被中断
  const handleInstall = () => {
    void runInstall({
      confirm: (running) =>
        new Promise<boolean>((resolve) => {
          Modal.confirm({
            title: t('update_running_confirm_title'),
            content: t('update_running_confirm_content', { count: running }),
            okText: t('update_confirm_ok'),
            cancelText: t('update_confirm_cancel'),
            onOk: () => resolve(true),
            onCancel: () => resolve(false),
          });
        }),
    });
  };

  const percent = total ? Math.min(100, Math.floor((downloaded / total) * 100)) : 0;
  const busy = status === 'checking' || status === 'downloading';

  return (
    <Card title={t('update_title')} style={{ maxWidth: 640 }}>
      <Space orientation="vertical" size="middle" style={{ display: 'flex', width: '100%' }}>
        <Space size="small" wrap>
          <span>
            {t('update_current_version')}: {currentVersion || '-'}
          </span>
          {status === 'idle' && <Tag color="success">{t('update_latest')}</Tag>}
          {status === 'checking' && <Tag>{t('update_checking')}</Tag>}
          {status === 'available' && info && (
            <Tag color="processing">
              {t('update_available', { version: info.version })}
            </Tag>
          )}
          {status === 'downloading' && (
            <Tag color="processing">{t('update_downloading')}</Tag>
          )}
          {status === 'error' && <Tag color="error">{t('update_failed')}</Tag>}
        </Space>

        {status === 'error' && error && <Typography.Text type="danger">{error}</Typography.Text>}

        {status === 'downloading' && <Progress percent={percent} status="active" />}

        {status === 'available' && info?.notes && (
          <Typography.Paragraph
            type="secondary"
            style={{ whiteSpace: 'pre-wrap', marginBottom: 0, maxHeight: 120, overflow: 'auto' }}
          >
            {t('update_notes')}
            {'\n'}
            {info.notes}
          </Typography.Paragraph>
        )}

        <Space size="small">
          <Button loading={status === 'checking'} disabled={busy} onClick={() => void runCheck()}>
            {t('update_check')}
          </Button>
          <Button
            type="primary"
            loading={status === 'downloading'}
            disabled={status !== 'available'}
            onClick={handleInstall}
          >
            {t('update_install')}
          </Button>
        </Space>

        {status === 'available' && (
          <span style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)', fontSize: 12 }}>
            {t('update_restart_hint')}
          </span>
        )}

        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder={t('update_mirror_placeholder')}
            value={mirror}
            onChange={(e) => setMirror(e.target.value)}
          />
          <Button loading={savingMirror} onClick={() => void handleSaveMirror()}>
            {t('update_mirror_save')}
          </Button>
        </Space.Compact>
        <span style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)', fontSize: 12 }}>
          {t('update_mirror_label')}
        </span>
      </Space>
    </Card>
  );
}
