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

// tauri://* 为 release 下 WebView origin；1420 是 M1 桌面 UI 端口（已废弃，保留无害）；
// 5173 是 M2 复用 frontend 的 Vite dev server 端口，dev 模式跨域必须放行
const CORS_ORIGINS: &str = "tauri://localhost,http://tauri.localhost,http://localhost:1420,http://127.0.0.1:1420,http://localhost:5173,http://127.0.0.1:5173";
const PORT_ATTEMPTS: usize = 3;
/// 关闭时给 sidecar 进程树的 SIGTERM 宽限，超时逐个 SIGKILL
const SHUTDOWN_SIGTERM_WAIT_MS: u64 = 1500;
const SHUTDOWN_POLL_MS: u64 = 200;
const SHUTDOWN_SIGKILL_WAIT_MS: u64 = 1000;

pub struct RuntimeState {
    pub child: Option<CommandChild>,
    pub port: Option<u16>,
    /// stopped | starting | crashed；"可服务" 由 UI 以 /health 结果为准
    pub status: String,
    /// 主动停止标记：区分正常退出与崩溃事件
    pub stopping: bool,
    /// 启停操作进行中标记：合并并发的 start/restart 请求，防止重复 spawn
    pub starting: bool,
}

impl Default for RuntimeState {
    fn default() -> Self {
        Self {
            child: None,
            port: None,
            status: "stopped".into(),
            stopping: false,
            starting: false,
        }
    }
}

impl RuntimeState {
    /// start 守卫：已有实例或启停进行中则合并调用（返回 false），
    /// 否则占位开始（返回 true）。spawn 的所有出口必须复位 starting。
    pub fn try_begin_start(&mut self) -> bool {
        if self.child.is_some() || self.starting {
            return false;
        }
        self.starting = true;
        true
    }

    /// restart 守卫：重启允许在实例运行中发起，但进行中的重启必须被合并，
    /// 防止 stop+spawn 窗口期交错产生多个 sidecar。
    pub fn try_begin_restart(&mut self) -> bool {
        if self.starting {
            return false;
        }
        self.starting = true;
        true
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
/// 约定：调用方已在锁内把 starting 置为 true；本函数负责在所有出口复位。
fn spawn_sidecar(app: &AppHandle) -> Result<(), String> {
    let dir = data_dir(app).inspect_err(|_| {
        app.state::<SharedRuntime>().lock().unwrap().starting = false;
    })?;
    if let Err(e) = std::fs::create_dir_all(&dir) {
        app.state::<SharedRuntime>().lock().unwrap().starting = false;
        return Err(e.to_string());
    }
    let dir_str = dir.to_string_lossy().to_string();

    let mut last_error = String::new();
    for _ in 0..PORT_ATTEMPTS {
        let Some(port) = pick_free_port() else {
            app.state::<SharedRuntime>().lock().unwrap().starting = false;
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
            // macOS：PyInstaller onefile bootloader 在多线程 ObjC GUI 父进程下
            // fork 子进程时会触发 __SharedStringStorage fork-safety 确定性崩溃
            // （从 shell 直接运行不触发）。此环境变量让 ObjC runtime 跳过该 abort。
            // 升级 PyInstaller 或改 onedir 后可评估移除。
            .env("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
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
                rt.starting = false;
                return Ok(());
            }
            Err(e) => last_error = e.to_string(),
        }
    }
    app.state::<SharedRuntime>().lock().unwrap().starting = false;
    Err(format!(
        "sidecar 启动失败（重试 {PORT_ATTEMPTS} 次）: {last_error}"
    ))
}

#[cfg(unix)]
fn collect_process_tree(root_pid: u32) -> Vec<u32> {
    // 用 pgrep -P 逐层 BFS 枚举后代。
    // ponytail: 关闭路径每 200ms 调一次 pgrep，macOS 自带该命令；
    // 上限是多一层外部进程依赖，升级路径是 FFI 调 libproc 替代 pgrep。
    let mut all = vec![root_pid];
    let mut frontier = vec![root_pid];
    while let Some(pid) = frontier.pop() {
        let Ok(out) = std::process::Command::new("pgrep")
            .args(["-P", &pid.to_string()])
            .output()
        else {
            continue;
        };
        for line in String::from_utf8_lossy(&out.stdout).lines() {
            if let Ok(child_pid) = line.trim().parse::<u32>() {
                all.push(child_pid);
                frontier.push(child_pid);
            }
        }
    }
    all
}

#[cfg(unix)]
fn pid_alive(pid: u32) -> bool {
    // kill(pid, 0) 返回 0 表示进程存在（僵尸态也算，但会被 tauri-plugin-shell 的回收线程收走）
    unsafe { libc::kill(pid as i32, 0) == 0 }
}

#[cfg(unix)]
fn wait_pids_gone(pids: &[u32], timeout_ms: u64) {
    let deadline = std::time::Instant::now() + std::time::Duration::from_millis(timeout_ms);
    while std::time::Instant::now() < deadline {
        if !pids.iter().copied().any(pid_alive) {
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(SHUTDOWN_POLL_MS));
    }
}

/// 同步回收 sidecar 进程树：SIGTERM 宽限 → 逐个 SIGKILL → 等待消失。
/// 必须在 app 退出前调用（detached 线程会随进程死亡，来不及兜底）。
#[cfg(unix)]
fn terminate_process_tree(root_pid: u32) {
    let pids = collect_process_tree(root_pid);
    // onefile bootloader 不保证转发信号，树内每个 PID 都显式发
    for pid in &pids {
        unsafe {
            libc::kill(*pid as i32, libc::SIGTERM);
        }
    }
    wait_pids_gone(&pids, SHUTDOWN_SIGTERM_WAIT_MS);

    let survivors: Vec<u32> = pids.iter().copied().filter(|p| pid_alive(*p)).collect();
    if survivors.is_empty() {
        return;
    }
    for pid in &survivors {
        unsafe {
            libc::kill(*pid as i32, libc::SIGKILL);
        }
    }
    wait_pids_gone(&survivors, SHUTDOWN_SIGKILL_WAIT_MS);
}

/// 发信号停止 sidecar 并同步等待进程树退出。幂等：Destroyed、ExitRequested、
/// Exit 可能先后触发，stopping 已置位或子进程已离场时直接返回。
pub fn signal_stop(app: &AppHandle) -> Result<(), String> {
    let runtime = app.state::<SharedRuntime>();
    let mut rt = runtime.lock().unwrap();
    if rt.stopping {
        return Ok(());
    }
    let Some(child) = rt.child.as_ref() else {
        rt.status = "stopped".into();
        return Ok(());
    };
    let root_pid = child.pid();
    rt.stopping = true;
    rt.status = "stopped".into();

    #[cfg(unix)]
    {
        // 持锁同步回收：最坏约 2.5s，仅发生在关闭/重启路径；
        // sidecar 的 Terminated 回调需要同一把锁，会在本函数返回后执行，无死锁。
        terminate_process_tree(root_pid);
        rt.child = None;
    }
    #[cfg(not(unix))]
    {
        // M1 首发 macOS；Windows 无 SIGTERM 与进程树信号语义，直接 kill 兜底
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
        let mut rt = runtime.lock().unwrap();
        // 已有实例，或另一个 start/restart 正在 spawn：直接合并，不重复拉起
        if !rt.try_begin_start() {
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
    {
        let runtime = app.state::<SharedRuntime>();
        let mut rt = runtime.lock().unwrap();
        // 合并并发重启：stop+spawn 窗口期内到达的请求直接返回当前状态，
        // 避免两次 restart 交错导致旧 child 句柄被覆盖、进程树失控
        if !rt.try_begin_restart() {
            let persisted_state = app.state::<PersistedState>();
            let persisted = persisted_state.0.lock().unwrap();
            return Ok(dto(&rt, &persisted));
        }
    }
    let _ = signal_stop(&app);
    // signal_stop 已同步等到进程树退出；300ms 仅给内核端口释放兜底
    std::thread::sleep(std::time::Duration::from_millis(300));
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    /// 100 个线程同时发起 restart，必须恰好 1 个获得执行权，其余全部被合并。
    #[test]
    fn restart_guard_coalesces_concurrent_callers() {
        let state = Arc::new(SharedRuntime::default());
        let mut handles = Vec::new();
        for _ in 0..100 {
            let state = Arc::clone(&state);
            handles.push(std::thread::spawn(move || {
                state.lock().unwrap().try_begin_restart()
            }));
        }
        let winners = handles
            .into_iter()
            .map(|h| h.join().expect("线程恐慌"))
            .filter(|won| *won)
            .count();
        assert_eq!(winners, 1, "并发 restart 只允许 1 个通过守卫");
        assert!(state.lock().unwrap().starting);
    }

    /// start 守卫：进行中合并；复位后允许下一次发起。
    #[test]
    fn start_guard_blocks_while_in_progress_and_resets() {
        let mut state = RuntimeState::default();
        assert!(state.try_begin_start());
        assert!(!state.try_begin_start());
        state.starting = false; // 模拟 spawn 出口复位
        assert!(state.try_begin_start());
    }
}
