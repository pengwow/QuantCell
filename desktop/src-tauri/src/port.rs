//! 空闲端口选择。
//!
//! ponytail: 绑定探测与 sidecar 实际绑定之间存在 TOCTOU 竞态；
//! 上限是启动瞬间的小概率抢占，升级路径是 backend_start 整体重试（已在 backend.rs 做 3 次）。

use std::net::TcpListener;

/// 绑定 127.0.0.1:0 让 OS 分配临时端口，drop 后立即返回。
pub fn pick_free_port() -> Option<u16> {
    let listener = TcpListener::bind("127.0.0.1:0").ok()?;
    Some(listener.local_addr().ok()?.port())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn returns_reusable_ephemeral_port() {
        let port = pick_free_port().expect("应能分配到空闲端口");
        assert!(port > 1024);
        // listener 已 drop，该端口应可被再次绑定
        TcpListener::bind(("127.0.0.1", port)).expect("释放后端口应可再次绑定");
    }
}
