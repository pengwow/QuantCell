//! 后端模式持久化：<app_data_dir>/desktop-config.json。
//! 纯 JSON 读写；文件缺失或损坏时回退默认（local），不阻断启动。

use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::{Path, PathBuf},
};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum BackendMode {
    Local,
    Remote,
}

impl Default for BackendMode {
    fn default() -> Self {
        Self::Local
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PersistedConfig {
    #[serde(default)]
    pub mode: BackendMode,
    #[serde(default, rename = "remoteUrl")]
    pub remote_url: Option<String>,
    /// 自定义更新镜像基址（如 https://mirror.example.com/quantcell）；None 表示只用官方源
    #[serde(default, rename = "mirrorBaseUrl")]
    pub mirror_base_url: Option<String>,
}

impl Default for PersistedConfig {
    fn default() -> Self {
        Self {
            mode: BackendMode::Local,
            remote_url: None,
            mirror_base_url: None,
        }
    }
}

pub fn config_path(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("desktop-config.json")
}

pub fn load(app_data_dir: &Path) -> PersistedConfig {
    match fs::read_to_string(config_path(app_data_dir)) {
        Ok(raw) => serde_json::from_str(&raw).unwrap_or_default(),
        Err(_) => PersistedConfig::default(),
    }
}

pub fn save(app_data_dir: &Path, cfg: &PersistedConfig) -> std::io::Result<()> {
    fs::create_dir_all(app_data_dir)?;
    let raw = serde_json::to_string_pretty(cfg).expect("PersistedConfig 序列化不会失败");
    fs::write(config_path(app_data_dir), raw)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    /// 进程内单调计数：并行测试可能落在同一纳秒上
    static TMP_DIR_SEQ: AtomicU64 = AtomicU64::new(0);

    /// 不用 tempfile 第三方 crate，用 pid+纳秒+进程内计数构造唯一临时目录
    fn unique_tmp_dir() -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        // 计数器保证同进程内即使两次调用落在同一纳秒也不会撞名（否则并行测试会互删/覆盖对方目录）
        let seq = TMP_DIR_SEQ.fetch_add(1, Ordering::Relaxed);
        let dir = std::env::temp_dir().join(format!(
            "qc-desktop-cfg-test-{}-{nanos}-{seq}",
            std::process::id()
        ));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn missing_file_returns_default() {
        let dir = unique_tmp_dir();
        assert_eq!(load(&dir), PersistedConfig::default());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn corrupt_file_returns_default() {
        let dir = unique_tmp_dir();
        fs::write(config_path(&dir), "{not json").unwrap();
        assert_eq!(load(&dir), PersistedConfig::default());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn remote_mode_round_trip() {
        let dir = unique_tmp_dir();
        let cfg = PersistedConfig {
            mode: BackendMode::Remote,
            remote_url: Some("https://api.example.com".into()),
            mirror_base_url: None,
        };
        save(&dir, &cfg).unwrap();
        assert_eq!(load(&dir), cfg);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn mirror_base_url_round_trip() {
        let dir = unique_tmp_dir();
        let cfg = PersistedConfig {
            mode: BackendMode::Local,
            remote_url: None,
            mirror_base_url: Some("https://mirror.example.com/quantcell".into()),
        };
        save(&dir, &cfg).unwrap();
        assert_eq!(load(&dir), cfg);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn legacy_config_without_mirror_loads() {
        // 老版本 desktop-config.json 没有 mirrorBaseUrl 字段，必须回退 None
        let dir = unique_tmp_dir();
        fs::write(config_path(&dir), r#"{"mode":"local","remoteUrl":null}"#).unwrap();
        assert_eq!(load(&dir).mirror_base_url, None);
        let _ = fs::remove_dir_all(&dir);
    }
}
