import { type UnlistenFn } from "@tauri-apps/api/event";
import { useCallback, useEffect, useState } from "react";
import {
  type BackendConfig,
  type BackendEvent,
  type BackendMode,
  getBackendConfig,
  onBackendEvent,
  restartBackend,
  setBackendMode,
  startBackend,
  stopBackend,
} from "../lib/backend";

export type Health = "unknown" | "starting" | "ok" | "down";

async function probe(baseUrl: string): Promise<Health> {
  try {
    const res = await fetch(`${baseUrl}/health`, { method: "GET" });
    return res.ok ? "ok" : "down";
  } catch {
    return "down";
  }
}

export function useBackend() {
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [health, setHealth] = useState<Health>("unknown");
  const [busy, setBusy] = useState(false);

  const refreshConfig = useCallback(async () => {
    const cfg = await getBackendConfig();
    setConfig(cfg);
    return cfg;
  }, []);

  // 启动引导：local 且未运行 → 自动 start；remote → 仅加载配置
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setBusy(true);
      try {
        let cfg = await getBackendConfig();
        if (cfg.mode === "local" && cfg.status === "stopped") {
          cfg = await startBackend();
          setHealth("starting");
        }
        if (!cancelled) setConfig(cfg);
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 健康轮询：未就绪 1s 一次，就绪后 10s 心跳；baseUrl 为空（未配置 remote）则不轮询
  useEffect(() => {
    const baseUrl = config?.baseUrl;
    if (!baseUrl) return;
    let timer: number;
    const tick = async () => {
      const h = await probe(baseUrl);
      setHealth(h);
      timer = window.setTimeout(tick, h === "ok" ? 10000 : 1000);
    };
    void tick();
    return () => window.clearTimeout(timer);
  }, [config?.baseUrl]);

  // sidecar 退出/崩溃事件
  useEffect(() => {
    let unlisten: UnlistenFn | undefined;
    void onBackendEvent((event: BackendEvent) => {
      if (event.status === "crashed") setHealth("down");
      if (event.type === "terminated") void refreshConfig();
    }).then((fn) => {
      unlisten = fn;
    });
    return () => unlisten?.();
  }, [refreshConfig]);

  const switchMode = useCallback(async (mode: BackendMode, remoteUrl?: string) => {
    const saved = await setBackendMode(mode, remoteUrl);
    if (mode === "local") {
      // 从 remote 切回：本机 sidecar 此前已在切 remote 时被停止，需要重新拉起
      const started = await startBackend();
      setConfig(started);
      setHealth("starting");
    } else {
      // 关键：切到 remote 必须停掉本机 sidecar，否则会留下残留进程
      await stopBackend();
      setConfig(saved);
      setHealth("unknown");
    }
  }, []);

  const restart = useCallback(async () => {
    const cfg = await restartBackend();
    setConfig(cfg);
    setHealth("starting");
  }, []);

  return { config, health, busy, switchMode, restart, refreshConfig };
}
