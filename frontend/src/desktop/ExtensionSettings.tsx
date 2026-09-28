import { useEffect, useRef, useState } from 'react';
import { Button, Card, Popconfirm, Progress, Space, Tag, message } from 'antd';
import {
  extensionsApi,
  type ExtensionInfo,
  type InstallProgress,
} from '../api/extensions';
import { restartBackend } from './bridge';
import { showSplash } from './splash';

const POLL_MS = 1500;
const ACTIVE_STATUSES = ['resolving', 'downloading', 'installing'];

/** 从 axios 风格异常里取后端 detail 文案 */
function errText(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: string } } }).response?.data
      ?.detail;
    if (detail) return detail;
  }
  return e instanceof Error ? e.message : String(e);
}

/** 桌面设置页「扩展能力」：展示/安装/卸载可选重依赖（当前为 RL 训练链） */
export default function ExtensionSettings() {
  const [items, setItems] = useState<ExtensionInfo[]>([]);
  const [progress, setProgress] = useState<InstallProgress | null>(null);
  const [activeExt, setActiveExt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // 终态提示只弹一次：轮询可能多次拿到 done/error
  const terminalNotified = useRef(false);

  const refresh = async () => {
    try {
      setItems(await extensionsApi.list());
    } catch {
      // 非桌面/后端未起时静默：该组件只在桌面设置页挂载，失败不打扰主流程
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  // 安装中轮询；进入终态后停轮询、弹一次提示、刷新安装状态
  useEffect(() => {
    if (!activeExt) return;
    const timer = window.setInterval(async () => {
      const p = await extensionsApi.progress(activeExt);
      setProgress(p);
      if (ACTIVE_STATUSES.includes(p.status)) return;
      window.clearInterval(timer);
      setActiveExt(null);
      if (terminalNotified.current) return;
      terminalNotified.current = true;
      if (p.status === 'done') {
        message.success('扩展安装完成，重启后端后生效');
      } else if (p.status === 'error') {
        message.error(`安装失败：${p.detail || '未知错误'}`);
      }
      void refresh();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [activeExt]);

  const handleInstall = async (id: string) => {
    setBusy(true);
    try {
      const { task_id } = await extensionsApi.install(id);
      terminalNotified.current = false;
      setProgress({ task_id, status: 'resolving', pct: 0, detail: '' });
      setActiveExt(id);
    } catch (e) {
      message.error(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const handleUninstall = async (id: string) => {
    setBusy(true);
    try {
      await extensionsApi.uninstall(id);
      message.success('已卸载，重启后端后生效');
      void refresh();
    } catch (e) {
      message.error(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const handleRestart = async () => {
    showSplash('正在重启本机后端…');
    await restartBackend();
    window.location.reload();
  };

  return (
    <Card title="扩展能力" style={{ maxWidth: 640 }}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {items.map((ext) => {
          const active = activeExt === ext.id;
          const sizeMb = ext.live_size_mb ?? ext.approx_size_mb;
          const versionText = Object.entries(ext.versions)
            .map(([name, version]) => `${name} ${version}`)
            .join('，');
          return (
            <div key={ext.id}>
              <Space wrap>
                <strong>{ext.name}</strong>
                {ext.installed ? <Tag color="success">已安装</Tag> : <Tag>未安装</Tag>}
              </Space>
              <div style={{ color: '#94a3b8', fontSize: 12, margin: '4px 0' }}>
                {ext.description}
              </div>
              <div style={{ fontSize: 12 }}>用途：{ext.purpose}</div>
              <div style={{ fontSize: 12 }}>
                包含：{ext.deps.join(' / ')} · 安装后约 {sizeMb} MB
                {versionText && ` · ${versionText}`}
              </div>
              {active && progress && (
                <Progress percent={progress.pct} status="active" size="small" />
              )}
              {active && progress?.detail && (
                <div style={{ fontSize: 12, color: '#94a3b8' }}>{progress.detail}</div>
              )}
              {!active && (
                <Space style={{ marginTop: 8 }}>
                  {!ext.installed && (
                    <Button
                      type="primary"
                      loading={busy}
                      onClick={() => void handleInstall(ext.id)}
                    >
                      安装
                    </Button>
                  )}
                  {ext.installed && (
                    <Popconfirm
                      title="卸载该扩展？"
                      description="卸载并重启后端后，RL 训练回到降级提示"
                      onConfirm={() => void handleUninstall(ext.id)}
                    >
                      <Button danger loading={busy}>
                        卸载
                      </Button>
                    </Popconfirm>
                  )}
                  {ext.installed && (
                    <Button onClick={() => void handleRestart()}>重启后端</Button>
                  )}
                </Space>
              )}
            </div>
          );
        })}
        <span style={{ color: '#94a3b8', fontSize: 12 }}>
          扩展安装到应用私有数据目录，不影响主程序；安装或卸载后需重启后端生效。
        </span>
      </Space>
    </Card>
  );
}
