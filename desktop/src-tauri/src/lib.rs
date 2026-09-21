mod backend;
mod config;
mod port;

use tauri::{Manager, RunEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?;
            let persisted = config::load(&data_dir);
            app.manage(backend::PersistedState(std::sync::Mutex::new(persisted)));
            app.manage(backend::SharedRuntime::default());
            Ok(())
        })
        .on_window_event(|window, event| {
            // 关窗即回收 sidecar（Cmd+Q 路径由 RunEvent::Exit 兜底，两处都幂等）
            if let tauri::WindowEvent::Destroyed = event {
                let _ = backend::signal_stop(window.app_handle());
            }
        })
        .invoke_handler(tauri::generate_handler![
            backend::backend_start,
            backend::backend_stop,
            backend::backend_restart,
            backend::backend_status,
            backend::get_backend_config,
            backend::set_backend_mode,
        ])
        .build(tauri::generate_context!())
        .expect("启动 QuantCell 桌面端失败");

    app.run(|app_handle, event| {
        // 必须在进程退出前同步灭杀整棵 sidecar 进程树；
        // 仅靠 Destroyed + detached 线程会导致 onefile 父子进程被 launchd 收养。
        // 实测 macOS Cmd+Q 不触发 ExitRequested、也不发 WindowEvent::Destroyed，
        // 事件循环直接走到 Exit；两处都挂，靠 signal_stop 的 stopping 标记幂等。
        if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
            let _ = backend::signal_stop(app_handle);
        }
    });
}
