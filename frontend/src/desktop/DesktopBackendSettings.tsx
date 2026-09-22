import { useEffect, useState } from 'react';
import { Button, Card, Input, Radio, Space, Tag, message } from 'antd';
import {
  getBackendConfig,
  setBackendMode,
  startBackend,
  stopBackend,
} from './bridge';
import { type BackendMode } from './env';
import { showSplash } from './splash';

type Health = 'unknown' | 'ok' | 'down';

async function probe(baseUrl: string): Promise<Health> {
  try {
    const res = await fetch(`${baseUrl}/health`);
    return res.ok ? 'ok' : 'down';
  } catch {
    return 'down';
  }
}

/** 仅 Tauri 环境由设置页挂载：local/remote 切换，保存后整页重载重走引导 */
export default function DesktopBackendSettings() {
  const [mode, setMode] = useState<BackendMode>('local');
  const [remoteUrl, setRemoteUrl] = useState('');
  const [endpoint, setEndpoint] = useState<string | null>(null);
  const [health, setHealth] = useState<Health>('unknown');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getBackendConfig().then((cfg) => {
      setMode(cfg.mode);
      setRemoteUrl(cfg.remoteUrl ?? '');
      setEndpoint(cfg.baseUrl);
    });
  }, []);

  useEffect(() => {
    if (!endpoint) {
      setHealth('unknown');
      return;
    }
    let alive = true;
    void probe(endpoint).then((h) => alive && setHealth(h));
    return () => {
      alive = false;
    };
  }, [endpoint]);

  const handleSave = async () => {
    const url = remoteUrl.trim().replace(/\/+$/, '');
    if (mode === 'remote') {
      if (!/^https?:\/\/.+/.test(url)) {
        message.error('远程地址须以 http:// 或 https:// 开头');
        return;
      }
      const h = await probe(url);
      if (h !== 'ok') {
        message.error('无法连接该远程后端（/health 不通）');
        return;
      }
    }
    setBusy(true);
    try {
      await setBackendMode(mode, mode === 'remote' ? url : undefined);
      if (mode === 'local') {
        showSplash('正在启动本机后端…');
        await startBackend();
      } else {
        // 切 remote 必须停掉本机 sidecar，避免残留进程
        await stopBackend();
      }
      // 整页重载：网络重写基址、鉴权、各 WS/SSE 全部按新模式重新初始化
      window.location.reload();
    } catch (e) {
      setBusy(false);
      message.error(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Card title="桌面后端" style={{ maxWidth: 640 }}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Radio.Group
          value={mode}
          onChange={(e) => setMode(e.target.value as BackendMode)}
          options={[
            { label: '本机后端（应用自启 sidecar，免登录）', value: 'local' },
            { label: '远程后端（走登录鉴权）', value: 'remote' },
          ]}
        />
        <Input
          placeholder="https://your-quantcell-host"
          value={remoteUrl}
          disabled={mode !== 'remote'}
          onChange={(e) => setRemoteUrl(e.target.value)}
        />
        <Space>
          {endpoint && <span>当前地址：{endpoint}</span>}
          {health === 'ok' && <Tag color="success">在线</Tag>}
          {health === 'down' && <Tag color="error">不可用</Tag>}
          {health === 'unknown' && <Tag>未知</Tag>}
        </Space>
        <Button type="primary" loading={busy} onClick={handleSave}>
          保存并切换
        </Button>
        <span style={{ color: '#94a3b8', fontSize: 12 }}>
          切换将重启界面。本机模式数据保存在应用私有数据目录。
        </span>
      </Space>
    </Card>
  );
}
