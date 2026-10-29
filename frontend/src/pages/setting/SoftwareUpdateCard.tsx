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
      message.success(t('update_mirror_saved') || '镜像源已保存');
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
            title: t('update_running_confirm_title') || '升级会中断运行中的策略',
            content:
              t('update_running_confirm_content', { count: running }) ||
              `当前有 ${running} 个策略正在运行，升级并重启后将全部中断。确定继续？`,
            okText: t('update_confirm_ok') || '继续升级',
            cancelText: t('update_confirm_cancel') || '取消',
            onOk: () => resolve(true),
            onCancel: () => resolve(false),
          });
        }),
    });
  };

  const percent = total ? Math.min(100, Math.floor((downloaded / total) * 100)) : 0;
  const busy = status === 'checking' || status === 'downloading';

  return (
    <Card title={t('update_title') || '软件更新'} style={{ maxWidth: 640 }}>
      <Space orientation="vertical" size="middle" style={{ display: 'flex', width: '100%' }}>
        <Space size="small" wrap>
          <span>
            {t('update_current_version') || '当前版本'}：{currentVersion || '-'}
          </span>
          {status === 'idle' && <Tag color="success">{t('update_latest') || '已是最新版本'}</Tag>}
          {status === 'checking' && <Tag>{t('update_checking') || '正在检查更新…'}</Tag>}
          {status === 'available' && info && (
            <Tag color="processing">
              {t('update_available', { version: info.version }) || `发现新版本 ${info.version}`}
            </Tag>
          )}
          {status === 'downloading' && (
            <Tag color="processing">{t('update_downloading') || '正在下载更新'}</Tag>
          )}
          {status === 'error' && <Tag color="error">{t('update_failed') || '更新失败'}</Tag>}
        </Space>

        {status === 'error' && error && <Typography.Text type="danger">{error}</Typography.Text>}

        {status === 'downloading' && <Progress percent={percent} status="active" />}

        {status === 'available' && info?.notes && (
          <Typography.Paragraph
            type="secondary"
            style={{ whiteSpace: 'pre-wrap', marginBottom: 0, maxHeight: 120, overflow: 'auto' }}
          >
            {t('update_notes') || '更新说明'}
            {'\n'}
            {info.notes}
          </Typography.Paragraph>
        )}

        <Space size="small">
          <Button loading={status === 'checking'} disabled={busy} onClick={() => void runCheck()}>
            {t('update_check') || '检查更新'}
          </Button>
          <Button
            type="primary"
            loading={status === 'downloading'}
            disabled={status !== 'available'}
            onClick={handleInstall}
          >
            {t('update_install') || '立即更新'}
          </Button>
        </Space>

        {status === 'available' && (
          <span style={{ color: '#94a3b8', fontSize: 12 }}>
            {t('update_restart_hint') || '安装完成后应用将自动重启'}
          </span>
        )}

        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder={t('update_mirror_placeholder') || 'https://mirror.example.com/quantcell'}
            value={mirror}
            onChange={(e) => setMirror(e.target.value)}
          />
          <Button loading={savingMirror} onClick={() => void handleSaveMirror()}>
            {t('update_mirror_save') || '保存镜像源'}
          </Button>
        </Space.Compact>
        <span style={{ color: '#94a3b8', fontSize: 12 }}>
          {t('update_mirror_label') || '更新镜像源（可选，留空仅使用官方源）'}
        </span>
      </Space>
    </Card>
  );
}
