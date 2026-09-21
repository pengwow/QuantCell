import { useEffect, useState } from "react";
import "./App.css";
import { useBackend } from "./hooks/useBackend";

const HEALTH_LABEL: Record<string, string> = {
  unknown: "检测中…",
  starting: "后端启动中…",
  ok: "后端在线",
  down: "后端不可用",
};

export default function App() {
  const { config, health, busy, switchMode, restart } = useBackend();
  const [modeDraft, setModeDraft] = useState<"local" | "remote">(
    config?.mode ?? "local",
  );
  const [urlDraft, setUrlDraft] = useState(config?.remoteUrl ?? "");
  const [formError, setFormError] = useState<string | null>(null);

  // 配置加载/外部切换后，把表单初值同步为当前已生效配置
  useEffect(() => {
    if (config) {
      setModeDraft(config.mode);
      setUrlDraft(config.remoteUrl ?? "");
    }
  }, [config]);

  // local 模式 sidecar 非正常退出时展示重启条
  const crashed = health === "down" && config?.mode === "local";

  const handleSave = async () => {
    setFormError(null);
    try {
      await switchMode(modeDraft, modeDraft === "remote" ? urlDraft : undefined);
    } catch (e) {
      setFormError(String(e));
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">QuantCell</div>
        <nav className="nav">
          <span className="nav-item active">工作台（M1 占位）</span>
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <span className={`badge badge-${health}`}>
            {HEALTH_LABEL[health] ?? health}
          </span>
          <span className="endpoint">{config?.baseUrl ?? "（无后端地址）"}</span>
        </header>

        {crashed && (
          <div className="crash-banner">
            本机后端已退出（非正常停止）。
            <button type="button" onClick={() => void restart()} disabled={busy}>
              重启后端
            </button>
          </div>
        )}

        <section className="card">
          <h2>后端模式（M1 设置页占位）</h2>
          <div className="form-row">
            <label>
              <input
                type="radio"
                value="local"
                checked={modeDraft === "local"}
                onChange={() => setModeDraft("local")}
              />
              本机后端（应用自启 sidecar）
            </label>
          </div>
          <div className="form-row">
            <label>
              <input
                type="radio"
                value="remote"
                checked={modeDraft === "remote"}
                onChange={() => setModeDraft("remote")}
              />
              远程后端
            </label>
            <input
              className="url-input"
              type="text"
              placeholder="https://api.example.com"
              value={urlDraft}
              disabled={modeDraft !== "remote"}
              onChange={(e) => setUrlDraft(e.target.value)}
            />
          </div>
          {formError && <div className="form-error">{formError}</div>}
          <button
            type="button"
            className="save-btn"
            onClick={() => void handleSave()}
            disabled={busy}
          >
            {busy ? "处理中…" : "保存并切换"}
          </button>
          <p className="hint">
            M1 仅交付启动/探活/模式切换；工作台、回测、策略等页面在 M2 实现。
          </p>
        </section>
      </main>
    </div>
  );
}
