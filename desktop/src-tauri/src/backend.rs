//! Sidecar 生命周期管理：
//! local 模式 spawn/停止 quantcell-backend，转发退出事件给 UI；
//! remote 模式不起进程，只持久化远程地址。健康探活由 UI 直接 fetch，
//! Rust 侧不引入 HTTP 客户端依赖。

use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

use crate::config::{self, BackendMode, PersistedConfig};
use crate::port::pick_free_port;

const CORS_ORIGINS: &str =
    "tauri://localhost,http://tauri.localhost,http://localhost:1420,http://127.0.0.1:1420";
const PORT_ATTEMPTS: usize = 3;
const SIGTERM_GRACE_SECS: u64 = 5;

pub struct RuntimeState {
    pub child: Option<CommandChild>,
    pub port: Option<u16>,
    /// stopped | starting | crashed；"可服务" 由 UI 以 /health 结果为准
    pub status: String,
    /// 主动停止标记：区分正常退出与崩溃事件
    pub stopping: bool,
}

impl Default for RuntimeState {
    fn default() -> Self {
        Self {
            child: None,
            port: None,
            status: "stopped".into(),
            stopping: false,
        }
    }
}

pub type SharedRuntime = Mutex<RuntimeState>;

pub struct PersistedState(pub Mutex<PersistedConfig>);

#[derive(Serialize, Clone)]
pub struct BackendConfigDto {
    mode: String,
    #[serde(rename = "baseUrl")]
    base_url: Option<String>,
    port: Option<u16>,
    #[serde(rename = "remoteUrl")]
    remote_url: Option<String>,
    status: String,
}

fn data_dir(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    app.path().app_data_dir().map_err(|e| e.to_string())
}

fn dto(runtime: &RuntimeState, persisted: &PersistedConfig) -> BackendConfigDto {
    match persisted.mode {
        BackendMode::Local => BackendConfigDto {
            mode: "local".into(),
            base_url: runtime.port.map(|p| format!("http://127.0.0.1:{p}")),
            port: runtime.port,
            remote_url: None,
            status: runtime.status.clone(),
        },
        BackendMode::Remote => BackendConfigDto {
            mode: "remote".into(),
            base_url: persisted.remote_url.clone(),
            port: None,
            remote_url: persisted.remote_url.clone(),
            status: "stopped".into(),
        },
    }
}

/// spawn sidecar；端口探测与实际绑定间存在竞态，最多换端口重试 PORT_ATTEMPTS 次。
fn spawn_sidecar(app: &AppHandle) -> Result<(), String> {
    let dir = data_dir(app)?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let dir_str = dir.to_string_lossy().to_string();

    let mut last_error = String::new();
    for _ in 0..PORT_ATTEMPTS {
        let Some(port) = pick_free_port() else {
            return Err("无法分配空闲端口".into());
        };

        let result = app
            .shell()
            .sidecar("quantcell-backend")
            .map_err(|e| e.to_string())?
            .args([
                "--host",
                "127.0.0.1",
                "--port",
                &port.to_string(),
                "--data-dir",
                &dir_str,
            ])
            .env("CORS_ORIGINS", CORS_ORIGINS)
            .spawn();

        match result {
            Ok((mut rx, child)) => {
                let app_handle = app.clone();
                tauri::async_runtime::spawn(async move {
                    let mut code: Option<i32> = None;
                    while let Some(event) = rx.recv().await {
                        if let CommandEvent::Terminated(payload) = event {
                            code = payload.code;
                            break;
                        }
                    }
                    let runtime = app_handle.state::<SharedRuntime>();
                    let mut rt = runtime.lock().unwrap();
                    rt.child = None;
                    // 主动停止或退出码 0 视为 stopped，其余为 crashed
                    let status = if rt.stopping || code == Some(0) {
                        "stopped"
                    } else {
                        "crashed"
                    };
                    rt.status = status.to_string();
                    rt.stopping = false;
                    let port = rt.port;
                    drop(rt);
                    let _ = app_handle.emit(
                        "backend:event",
                        serde_json::json!({
                            "type": "terminated",
                            "code": code,
                            "port": port,
                            "status": status,
                        }),
                    );
                });

                let runtime = app.state::<SharedRuntime>();
                let mut rt = runtime.lock().unwrap();
                rt.child = Some(child);
                rt.port = Some(port);
                rt.status = "starting".into();
                rt.stopping = false;
                return Ok(());
            }
            Err(e) => last_error = e.to_string(),
        }
    }
    Err(format!(
        "sidecar 启动失败（重试 {PORT_ATTEMPTS} 次）: {last_error}"
    ))
}

/// 发信号停止 sidecar。unix 先 SIGTERM 走 FastAPI lifespan，超时再 SIGKILL。
pub fn signal_stop(app: &AppHandle) -> Result<(), String> {
    let runtime = app.state::<SharedRuntime>();
    let mut rt = runtime.lock().unwrap();
    let Some(child) = rt.child.as_ref() else {
        rt.status = "stopped".into();
        return Ok(());
    };
    // 注意：tauri-plugin-shell 2.x 的 CommandChild::pid 是方法不是字段
    let pid = child.pid();
    rt.stopping = true;
    rt.status = "stopped".into();

    #[cfg(unix)]
    {
        unsafe {
            libc::kill(pid as i32, libc::SIGTERM);
        }
        let app_handle = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_secs(SIGTERM_GRACE_SECS));
            // kill(pid, 0) 返回 0 表示进程仍存在
            if unsafe { libc::kill(pid as i32, 0) } == 0 {
                let runtime = app_handle.state::<SharedRuntime>();
                let mut rt = runtime.lock().unwrap();
                if let Some(child) = rt.child.take() {
                    let _ = child.kill();
                }
                let _ = app_handle.emit(
                    "backend:event",
                    serde_json::json!({"type": "force-killed", "port": rt.port}),
                );
            }
        });
    }
    #[cfg(not(unix))]
    {
        // M1 首发 macOS；Windows 无 SIGTERM 语义，直接 kill 兜底
        if let Some(child) = rt.child.take() {
            let _ = child.kill();
        }
    }
    Ok(())
}

#[tauri::command]
pub fn backend_start(app: AppHandle) -> Result<BackendConfigDto, String> {
    let is_local = {
        let persisted_state = app.state::<PersistedState>();
        let persisted = persisted_state.0.lock().unwrap();
        persisted.mode == BackendMode::Local
    };
    if !is_local {
        return Err("当前为 remote 模式，无需启动本机后端".into());
    }
    {
        let runtime = app.state::<SharedRuntime>();
        let rt = runtime.lock().unwrap();
        if rt.child.is_some() {
            let persisted_state = app.state::<PersistedState>();
            let persisted = persisted_state.0.lock().unwrap();
            return Ok(dto(&rt, &persisted));
        }
    }
    spawn_sidecar(&app)?;
    let runtime = app.state::<SharedRuntime>();
    let rt = runtime.lock().unwrap();
    let persisted_state = app.state::<PersistedState>();
    let persisted = persisted_state.0.lock().unwrap();
    Ok(dto(&rt, &persisted))
}

#[tauri::command]
pub fn backend_stop(app: AppHandle) -> Result<(), String> {
    signal_stop(&app)
}

#[tauri::command]
pub fn backend_restart(app: AppHandle) -> Result<BackendConfigDto, String> {
    let _ = signal_stop(&app);
    // ponytail: 固定等 800ms 让端口释放；崩溃恢复场景进程已退出，等待无害。
    // 上限是极端慢关闭时的偶发端口占用，升级路径是 wait 旧进程退出事件后再 spawn。
    std::thread::sleep(std::time::Duration::from_millis(800));
    spawn_sidecar(&app)?;
    let runtime = app.state::<SharedRuntime>();
    let rt = runtime.lock().unwrap();
    let persisted_state = app.state::<PersistedState>();
    let persisted = persisted_state.0.lock().unwrap();
    Ok(dto(&rt, &persisted))
}

#[tauri::command]
pub fn backend_status(app: AppHandle) -> BackendConfigDto {
    let runtime = app.state::<SharedRuntime>();
    let rt = runtime.lock().unwrap();
    let persisted_state = app.state::<PersistedState>();
    let persisted = persisted_state.0.lock().unwrap();
    dto(&rt, &persisted)
}

#[tauri::command]
pub fn get_backend_config(app: AppHandle) -> BackendConfigDto {
    let runtime = app.state::<SharedRuntime>();
    let rt = runtime.lock().unwrap();
    let persisted_state = app.state::<PersistedState>();
    let persisted = persisted_state.0.lock().unwrap();
    dto(&rt, &persisted)
}

#[tauri::command]
pub fn set_backend_mode(
    app: AppHandle,
    state: State<'_, PersistedState>,
    mode: String,
    remote_url: Option<String>,
) -> Result<BackendConfigDto, String> {
    let parsed = match mode.as_str() {
        "local" => BackendMode::Local,
        "remote" => BackendMode::Remote,
        other => return Err(format!("未知后端模式: {other}")),
    };

    let new_cfg = match parsed {
        BackendMode::Remote => {
            let url = remote_url.unwrap_or_default().trim().to_string();
            if !url.starts_with("http://") && !url.starts_with("https://") {
                return Err("远程地址必须以 http:// 或 https:// 开头".into());
            }
            PersistedConfig {
                mode: BackendMode::Remote,
                remote_url: Some(url),
            }
        }
        BackendMode::Local => PersistedConfig::default(),
    };

    config::save(&data_dir(&app)?, &new_cfg).map_err(|e| e.to_string())?;
    *state.0.lock().unwrap() = new_cfg.clone();

    // 注意：不在此处停/启 sidecar，由 UI 编排（保存后按模式决定 start/stop），
    // remote 地址的 /health 校验也在 UI 做（避免 Rust 引 HTTP 客户端依赖）。
    let runtime = app.state::<SharedRuntime>();
    let rt = runtime.lock().unwrap();
    Ok(dto(&rt, &new_cfg))
}
