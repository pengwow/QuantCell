mod backend;
mod config;
mod port;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?;
            let persisted = config::load(&data_dir);
            app.manage(backend::PersistedState(std::sync::Mutex::new(persisted)));
            app.manage(backend::SharedRuntime::default());
            Ok(())
        })
        .on_window_event(|window, event| {
            // 关窗即回收 sidecar，防止残留进程
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
        .run(tauri::generate_context!())
        .expect("启动 QuantCell 桌面端失败");
}
