//! 自动升级：封装 tauri-plugin-updater。
//!
//! 双渠道：镜像 manifest（用户可选配置）优先，官方 GitHub Release 兜底。
//! 前端不直连 updater 的 JS API —— Updater/Update 在 Rust 侧创建并暂存，
//! 前端只拿可序列化 DTO，进度也只从一条事件出口推送，避免状态漂移。

use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State, Url};
use tauri_plugin_updater::{Update, UpdaterExt};

use crate::backend::PersistedState;
use crate::config;

/// 官方更新源：GitHub Release 的 latest 固定下载地址
pub const OFFICIAL_ENDPOINT: &str =
    "https://github.com/pengwow/QuantCell/releases/latest/download/latest.json";

/// 下载进度事件名（前端 updateBridge 订阅）
pub const PROGRESS_EVENT: &str = "update://progress";

/// 检查到的待安装更新。check 存入、install 取出；锁绝不跨 await。
#[derive(Default)]
pub struct SharedUpdate(pub Mutex<Option<Update>>);

/// 前端可见的更新信息（updater 的 Update 不可序列化，故单独出 DTO）
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateInfo {
    pub current_version: String,
    pub version: String,
    pub notes: Option<String>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProgressPayload {
    downloaded: u64,
    total: Option<u64>,
}

/// 组装更新源：配置了镜像则镜像在前（更快），官方始终兜底。
/// 镜像基址允许带路径前缀，统一拼 `/latest-mirror.json`。
pub fn endpoints_for(mirror_base: Option<&str>) -> Result<Vec<Url>, String> {
    let mut urls = Vec::new();
    if let Some(base) = mirror_base.map(str::trim).filter(|s| !s.is_empty()) {
        let mirror = format!("{}/latest-mirror.json", base.trim_end_matches('/'));
        urls.push(Url::parse(&mirror).map_err(|e| format!("镜像地址无效: {e}"))?);
    }
    // 常量自身合法；解析失败只可能是改坏了常量，直接 expect
    urls.push(Url::parse(OFFICIAL_ENDPOINT).expect("官方 endpoint 常量必须合法"));
    Ok(urls)
}

/// 读取当前镜像基址（未配置返回 None）
#[tauri::command]
pub fn update_get_mirror(persisted: State<'_, PersistedState>) -> Option<String> {
    persisted.0.lock().unwrap().mirror_base_url.clone()
}

/// 保存镜像基址；传 null 或空串表示恢复「仅官方源」。
#[tauri::command]
pub fn update_set_mirror(
    app: AppHandle,
    persisted: State<'_, PersistedState>,
    mirror_base_url: Option<String>,
) -> Result<(), String> {
    let normalized = mirror_base_url
        .map(|s| s.trim().trim_end_matches('/').to_string())
        .filter(|s| !s.is_empty());
    // 先校验再落盘：坏地址持久化后每次检查都失败，用户很难自查
    endpoints_for(normalized.as_deref())?;

    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let mut guard = persisted.0.lock().unwrap();
    let mut new_cfg = guard.clone();
    new_cfg.mirror_base_url = normalized;
    config::save(&data_dir, &new_cfg).map_err(|e| e.to_string())?;
    *guard = new_cfg;
    Ok(())
}

/// 检查更新：命中则暂存 Update 并返回信息，无更新返回 None。
#[tauri::command]
pub async fn update_check(
    app: AppHandle,
    slot: State<'_, SharedUpdate>,
) -> Result<Option<UpdateInfo>, String> {
    let mirror = {
        // 单独作用域：锁在 await 之前释放
        let persisted = app.state::<PersistedState>();
        let guard = persisted.0.lock().unwrap();
        guard.mirror_base_url.clone()
    };
    let endpoints = endpoints_for(mirror.as_deref())?;

    let updater = app
        .updater_builder()
        .endpoints(endpoints)
        .map_err(|e| format!("更新源配置失败: {e}"))?
        .build()
        .map_err(|e| format!("更新器初始化失败: {e}"))?;

    let found = updater
        .check()
        .await
        .map_err(|e| format!("检查更新失败: {e}"))?;

    let info = match found {
        Some(update) => {
            let info = UpdateInfo {
                current_version: update.current_version.clone(),
                version: update.version.clone(),
                notes: update.body.clone(),
            };
            *slot.0.lock().unwrap() = Some(update);
            Some(info)
        }
        None => {
            *slot.0.lock().unwrap() = None;
            None
        }
    };
    Ok(info)
}

/// 下载并静默安装已暂存的更新，完成后重启应用。
/// 进度按累计字节推送到 `update://progress`。
#[tauri::command]
pub async fn update_install(app: AppHandle, slot: State<'_, SharedUpdate>) -> Result<(), String> {
    // 锁不跨 await：先把 Update 取出来，再下载
    let update = slot
        .0
        .lock()
        .unwrap()
        .take()
        .ok_or("没有待安装的更新，请先检查更新")?;

    let emitter = app.clone();
    let mut downloaded: u64 = 0;
    update
        .download_and_install(
            move |chunk_len, total| {
                downloaded += chunk_len as u64;
                let _ = emitter.emit(PROGRESS_EVENT, ProgressPayload { downloaded, total });
            },
            || {},
        )
        .await
        .map_err(|e| format!("下载安装失败: {e}"))?;

    // 安装完成后必须重启才会加载新版本；Windows 的 passive 安装器会自行接管进程退出。
    // tauri-plugin-process 2.4 起移除了 Rust 侧 ProcessExt trait，重启直接用
    // tauri 核心的同语义 API（返回 !，主线程同步重启 / 其他线程借 Exit 事件重启，
    // lib.rs 里 RunEvent::Exit 的 signal_stop 兜底会先回收 sidecar 进程树）
    app.restart();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn endpoints_without_mirror_is_official_only() {
        let urls = endpoints_for(None).expect("官方源常量必须可解析");
        assert_eq!(urls.len(), 1);
        assert_eq!(urls[0].as_str(), OFFICIAL_ENDPOINT);
    }

    #[test]
    fn endpoints_with_mirror_puts_mirror_first() {
        let urls = endpoints_for(Some("https://mirror.example.com/qc/")).expect("镜像地址可解析");
        assert_eq!(urls.len(), 2);
        assert_eq!(
            urls[0].as_str(),
            "https://mirror.example.com/qc/latest-mirror.json"
        );
        assert_eq!(urls[1].as_str(), OFFICIAL_ENDPOINT);
    }

    #[test]
    fn endpoints_reject_invalid_mirror_and_ignore_blank() {
        assert!(endpoints_for(Some("not a url")).is_err());
        // 空白镜像基址等同「未配置」，只保留官方源
        assert_eq!(endpoints_for(Some("   ")).expect("空白按未配置处理").len(), 1);
    }
}
