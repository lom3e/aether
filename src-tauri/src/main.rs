// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::HashMap;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use rand::distributions::Alphanumeric;
use rand::Rng;
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::menu::{MenuBuilder, MenuItemBuilder};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};
use tauri_plugin_notification::NotificationExt;

#[derive(Clone, Deserialize, Serialize, Debug)]
pub struct CanonicalNotificationTarget {
    pub notification_id: Option<String>,
    pub target_type: Option<String>,
    pub target_id: Option<String>,
    pub view: String,
    pub id: Option<String>,
    pub deep_link: Option<String>,
    pub created_at: u64,
}

#[derive(Clone, Deserialize, Serialize, Debug)]
pub struct DesktopNotificationPayload {
    pub id: Option<String>,
    pub title: String,
    pub body: Option<String>,
    pub sound: Option<String>,
    pub link_view: Option<String>,
    pub link_id: Option<String>,
    pub target_type: Option<String>,
    pub target_id: Option<String>,
    pub deep_link: Option<String>,
    pub source: Option<String>,
}

fn get_target_file_path(data_dir: &Path) -> PathBuf {
    data_dir.join("pending_notification_target.json")
}

fn persist_target_to_file(data_dir: &Path, target: &CanonicalNotificationTarget) {
    let path = get_target_file_path(data_dir);
    if let Ok(json) = serde_json::to_string_pretty(target) {
        let _ = std::fs::write(path, json);
    }
}

fn clear_target_file(data_dir: &Path) {
    let path = get_target_file_path(data_dir);
    if path.exists() {
        let _ = std::fs::remove_file(path);
    }
}

fn read_persisted_target(data_dir: &Path) -> Option<CanonicalNotificationTarget> {
    let path = get_target_file_path(data_dir);
    if path.exists() {
        if let Ok(contents) = std::fs::read_to_string(&path) {
            if let Ok(target) = serde_json::from_str::<CanonicalNotificationTarget>(&contents) {
                return Some(target);
            }
        }
    }
    None
}

#[allow(dead_code)]
struct RuntimeState {
    port: u16,
    token: String,
    child: Arc<Mutex<Option<Child>>>,
    notifications_muted: Arc<AtomicBool>,
    recent_notifications: Arc<Mutex<HashMap<String, Instant>>>,
    pending_targets: Arc<Mutex<Vec<CanonicalNotificationTarget>>>,
    data_dir: PathBuf,
}

#[derive(Serialize)]
struct RuntimeInfo {
    api_url: String,
    session_token: String,
    port: u16,
    version: String,
    notifications_muted: bool,
}

#[tauri::command]
fn get_runtime_info(state: State<RuntimeState>) -> Result<RuntimeInfo, String> {
    Ok(RuntimeInfo {
        api_url: format!("http://127.0.0.1:{}", state.port),
        session_token: state.token.clone(),
        port: state.port,
        version: "1.6.0".to_string(),
        notifications_muted: state.notifications_muted.load(Ordering::Relaxed),
    })
}

#[tauri::command]
fn get_surface_type(window: WebviewWindow) -> String {
    if window.label() == "companion" {
        "companion".to_string()
    } else {
        "workspace".to_string()
    }
}

#[tauri::command]
fn toggle_companion(app: AppHandle) {
    toggle_companion_window(&app);
}

#[tauri::command]
fn hide_companion(app: AppHandle) {
    if let Some(companion) = app.get_webview_window("companion") {
        let _ = companion.hide();
    }
}

#[tauri::command]
fn show_main_window(app: AppHandle) {
    show_main_window_action(&app);
}

#[tauri::command]
fn minimize_to_companion(app: AppHandle) {
    if let Some(main) = app.get_webview_window("main") {
        let _ = main.hide();
    }
    toggle_companion_window(&app);
}

#[tauri::command]
fn is_notifications_muted(state: State<RuntimeState>) -> bool {
    state.notifications_muted.load(Ordering::Relaxed)
}

#[tauri::command]
fn set_notifications_muted(muted: bool, state: State<RuntimeState>) {
    state.notifications_muted.store(muted, Ordering::Relaxed);
}

#[tauri::command]
fn send_desktop_notification(
    app: AppHandle,
    state: State<RuntimeState>,
    payload: DesktopNotificationPayload,
) -> Result<bool, String> {
    // 1. Check if notifications are muted
    if state.notifications_muted.load(Ordering::Relaxed) {
        println!("[Aether Desktop] Notification suppressed (muted): {}", payload.title);
        return Ok(false);
    }

    // 2. Deduplication check (30-second window based on ID or canonical content)
    let dedup_key = payload
        .id
        .clone()
        .unwrap_or_else(|| {
            format!(
                "{}:{}:{}:{}",
                payload.title,
                payload.body.as_deref().unwrap_or(""),
                payload.target_type.as_deref().unwrap_or(""),
                payload.target_id.as_deref().unwrap_or("")
            )
        });

    {
        let mut recent = state
            .recent_notifications
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;
        let now = Instant::now();
        // Prune entries older than 60 seconds
        recent.retain(|_, time| now.duration_since(*time) < Duration::from_secs(60));

        if let Some(last_time) = recent.get(&dedup_key) {
            if now.duration_since(*last_time) < Duration::from_secs(30) {
                println!("[Aether Desktop] Duplicate notification suppressed: {}", dedup_key);
                return Ok(false);
            }
        }
        recent.insert(dedup_key, now);
    }

    // 3. Resolve and record canonical target
    let (canonical_view, canonical_id) = match payload.target_type.as_deref() {
        Some("mission") => ("missions".to_string(), payload.target_id.clone().or_else(|| payload.link_id.clone())),
        Some("approval") => ("missions".to_string(), payload.target_id.clone().or_else(|| payload.link_id.clone())),
        Some("action_execution") => ("connections".to_string(), payload.target_id.clone().or_else(|| payload.link_id.clone())),
        Some("automation") => ("automations".to_string(), payload.target_id.clone().or_else(|| payload.link_id.clone())),
        Some("deliverable") => ("missions".to_string(), payload.target_id.clone().or_else(|| payload.link_id.clone())),
        Some("task") => ("home".to_string(), payload.target_id.clone().or_else(|| payload.link_id.clone())),
        Some("connection") => ("connections".to_string(), payload.target_id.clone().or_else(|| payload.link_id.clone())),
        Some("chat") => ("chat".to_string(), payload.target_id.clone().or_else(|| payload.link_id.clone())),
        Some("settings") => ("settings".to_string(), None),
        Some("view") => (
            payload.target_id.clone().unwrap_or_else(|| payload.link_view.clone().unwrap_or_else(|| "home".to_string())),
            payload.link_id.clone()
        ),
        _ => (
            payload.link_view.clone().unwrap_or_else(|| "home".to_string()),
            payload.link_id.clone().or_else(|| payload.target_id.clone())
        )
    };

    let canonical_target = CanonicalNotificationTarget {
        notification_id: payload.id.clone(),
        target_type: payload.target_type.clone(),
        target_id: payload.target_id.clone().or_else(|| payload.link_id.clone()),
        view: canonical_view,
        id: canonical_id,
        deep_link: payload.deep_link.clone(),
        created_at: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs(),
    };

    if let Ok(mut pending) = state.pending_targets.lock() {
        pending.push(canonical_target.clone());
    }
    persist_target_to_file(&state.data_dir, &canonical_target);

    // 4. Send native OS notification via tauri-plugin-notification
    let mut builder = app.notification().builder();
    builder = builder.title(&payload.title);

    if let Some(ref body) = payload.body {
        builder = builder.body(body);
    }

    let sound = payload.sound.unwrap_or_else(|| "Glass".to_string());
    if !sound.is_empty() && sound != "none" {
        builder = builder.sound(sound);
    }

    match builder.show() {
        Ok(_) => {
            println!("[Aether Desktop] Native notification dispatched: {}", payload.title);
            Ok(true)
        }
        Err(err) => {
            eprintln!("[Aether Desktop] Failed to show native notification: {:?}", err);
            Err(err.to_string())
        }
    }
}

#[tauri::command]
fn consume_notification_target(state: State<RuntimeState>) -> Option<CanonicalNotificationTarget> {
    let mut target = None;
    if let Ok(mut pending) = state.pending_targets.lock() {
        target = pending.pop();
    }
    if target.is_none() {
        target = read_persisted_target(&state.data_dir);
    }
    clear_target_file(&state.data_dir);

    if let Some(ref t) = target {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        if now.saturating_sub(t.created_at) > 900 {
            return None;
        }
    }
    target
}

#[tauri::command]
fn quit_aether(app: AppHandle, state: State<RuntimeState>) {
    graceful_shutdown(state.port, &state.token, &state.child);
    app.exit(0);
}

enum RuntimeTarget {
    Standalone(PathBuf),
    PythonDev {
        workspace_root: PathBuf,
        python_path: PathBuf,
    },
}

fn get_data_directory(is_app_bundle: bool) -> PathBuf {
    // 1. Explicit environment variable override
    if let Ok(dir) = std::env::var("AETHER_DATA_DIR") {
        let trimmed = dir.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }

    // 2. Windows: %APPDATA%\Aether or %USERPROFILE%\.aether
    #[cfg(target_os = "windows")]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            return PathBuf::from(appdata).join("Aether");
        }
        if let Ok(userprofile) = std::env::var("USERPROFILE") {
            return PathBuf::from(userprofile).join(".aether");
        }
    }

    // 3. macOS / Unix
    if let Ok(home) = std::env::var("HOME") {
        if is_app_bundle {
            #[cfg(target_os = "macos")]
            return PathBuf::from(home)
                .join("Library")
                .join("Application Support")
                .join("Aether");
            #[cfg(not(target_os = "macos"))]
            return PathBuf::from(home).join(".aether");
        } else {
            return PathBuf::from(home).join(".aether");
        }
    }

    PathBuf::from(".aether")
}

fn resolve_runtime_target(is_app_bundle: bool) -> Result<RuntimeTarget, String> {
    // 1. Explicit override for test/debugging
    if let Ok(override_path) = std::env::var("AETHER_RUNTIME_PATH") {
        let p = PathBuf::from(override_path);
        if p.exists() {
            println!("[Aether Desktop] Using runtime from AETHER_RUNTIME_PATH: {:?}", p);
            return Ok(RuntimeTarget::Standalone(p));
        }
    }

    let exe_path = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("."));
    let exe_dir = exe_path.parent().unwrap_or_else(|| Path::new("."));
    let current_dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));

    // 2. Bundled production paths (inside Aether.app/Contents/Resources/, NSIS resources, or adjacent)
    let bundled_candidate_paths = [
        exe_dir.join("../Resources/aether-runtime/aether-runtime.exe"),
        exe_dir.join("../Resources/aether-runtime/aether-runtime"),
        exe_dir.join("../Resources/resources/aether-runtime/aether-runtime.exe"),
        exe_dir.join("../Resources/resources/aether-runtime/aether-runtime"),
        exe_dir.join("../Resources/binaries/aether-runtime-x86_64-pc-windows-msvc.exe"),
        exe_dir.join("../Resources/binaries/aether-runtime-aarch64-apple-darwin"),
        exe_dir.join("../Resources/aether-runtime.exe"),
        exe_dir.join("../Resources/aether-runtime"),
        exe_dir.join("resources/aether-runtime/aether-runtime.exe"),
        exe_dir.join("resources/aether-runtime/aether-runtime"),
        exe_dir.join("aether-runtime/aether-runtime.exe"),
        exe_dir.join("aether-runtime/aether-runtime"),
        exe_dir.join("aether-runtime.exe"),
        exe_dir.join("aether-runtime"),
        exe_dir.join("aether-runtime-x86_64-pc-windows-msvc.exe"),
        exe_dir.join("aether-runtime-aarch64-apple-darwin"),
    ];

    for candidate in &bundled_candidate_paths {
        if candidate.exists() && candidate.is_file() {
            println!("[Aether Desktop] Found bundled standalone sidecar runtime: {:?}", candidate);
            return Ok(RuntimeTarget::Standalone(candidate.clone()));
        }
    }

    // 3. Strict production bundle guard: In .app bundle, do NOT fallback to dev python/repo!
    if is_app_bundle {
        return Err(format!(
            "CRITICAL: Standalone Aether Python sidecar runtime not found in Application bundle Resources. \
            Looked in: {:?}. Production app cannot run without bundled sidecar.",
            bundled_candidate_paths
        ));
    }

    // 4. Local build paths in repository/development mode
    let dev_standalone_paths = [
        current_dir.join("build").join("aether-runtime").join("aether-runtime.exe"),
        current_dir.join("build").join("aether-runtime").join("aether-runtime"),
        current_dir.join("..").join("build").join("aether-runtime").join("aether-runtime.exe"),
        current_dir.join("..").join("build").join("aether-runtime").join("aether-runtime"),
        current_dir.join("src-tauri").join("resources").join("aether-runtime").join("aether-runtime.exe"),
        current_dir.join("src-tauri").join("resources").join("aether-runtime").join("aether-runtime"),
        current_dir.join("src-tauri").join("binaries").join("aether-runtime-x86_64-pc-windows-msvc.exe"),
        current_dir.join("src-tauri").join("binaries").join("aether-runtime-aarch64-apple-darwin"),
        current_dir.join("binaries").join("aether-runtime-x86_64-pc-windows-msvc.exe"),
        current_dir.join("binaries").join("aether-runtime-aarch64-apple-darwin"),
    ];

    for candidate in &dev_standalone_paths {
        if candidate.exists() && candidate.is_file() {
            println!("[Aether Desktop] Found local build sidecar runtime: {:?}", candidate);
            return Ok(RuntimeTarget::Standalone(candidate.clone()));
        }
    }

    // 5. Fallback to Python Virtualenv in development mode only
    let mut check_dir = current_dir.clone();
    for _ in 0..5 {
        let venv_python_unix = check_dir.join(".venv").join("bin").join("python");
        let venv_python_win = check_dir.join(".venv").join("Scripts").join("python.exe");
        let venv_python = if venv_python_win.exists() {
            venv_python_win
        } else {
            venv_python_unix
        };
        if venv_python.exists() {
            println!("[Aether Desktop] Found development Python virtualenv: {:?}", venv_python);
            return Ok(RuntimeTarget::PythonDev {
                workspace_root: check_dir,
                python_path: venv_python,
            });
        }
        if let Some(parent) = check_dir.parent() {
            check_dir = parent.to_path_buf();
        } else {
            break;
        }
    }

    Err("Neither bundled standalone Aether runtime nor development Python virtualenv was found.".to_string())
}

fn generate_session_token() -> String {
    rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(32)
        .map(char::from)
        .collect()
}

fn spawn_backend_and_handshake() -> Result<(Child, u16, String, PathBuf), String> {
    let exe_path = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("."));
    let is_app_bundle = exe_path.to_string_lossy().contains(".app/Contents/MacOS");
    let data_dir = get_data_directory(is_app_bundle);

    // Ensure data directory exists
    let _ = std::fs::create_dir_all(&data_dir);

    let runtime_target = resolve_runtime_target(is_app_bundle)?;
    let token = generate_session_token();

    println!("[Aether Desktop] Application bundle mode: {}", is_app_bundle);
    println!("[Aether Desktop] User data directory: {:?}", data_dir);

    let mut cmd = match runtime_target {
        RuntimeTarget::Standalone(bin_path) => {
            println!("[Aether Desktop] Spawning standalone frozen sidecar: {:?}", bin_path);
            let mut c = Command::new(&bin_path);
            c.args([
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--data-dir",
                &data_dir.to_string_lossy(),
                "--token",
                &token,
                "--no-browser",
            ]);

            // Clean environment variables to ensure zero dependency on host python
            c.env_remove("PYTHONHOME");
            c.env_remove("PYTHONPATH");
            c.env_remove("VIRTUAL_ENV");
            c
        }
        RuntimeTarget::PythonDev { workspace_root, python_path } => {
            println!("[Aether Desktop] Spawning dev Python interpreter: {:?}", python_path);
            let mut c = Command::new(&python_path);
            c.current_dir(&workspace_root);
            c.args([
                "-m",
                "aether.cli.main",
                "ui",
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--data-dir",
                &data_dir.to_string_lossy(),
                "--token",
                &token,
                "--no-browser",
            ]);

            let src_dir = workspace_root.join("src");
            let mut python_path_env = src_dir.to_string_lossy().to_string();
            if let Ok(existing) = std::env::var("PYTHONPATH") {
                python_path_env = format!("{}:{}", python_path_env, existing);
            }
            c.env("PYTHONPATH", python_path_env);
            c
        }
    };

    cmd.env("PYTHONUNBUFFERED", "1");
    cmd.env("AETHER_SESSION_TOKEN", &token);
    cmd.env("AETHER_DESKTOP_RUNTIME", "1");
    if is_app_bundle {
        cmd.env("AETHER_APP_BUNDLE", "1");
    }
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Failed to spawn Aether backend process: {}", e))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "Failed to capture backend stdout pipe".to_string())?;

    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "Failed to capture backend stderr pipe".to_string())?;

    // Background thread to log stderr for diagnostics
    thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines().flatten() {
            eprintln!("[Aether Backend STDERR] {}", line);
        }
    });

    let (tx, rx) = std::sync::mpsc::channel::<u16>();
    let token_clone = token.clone();

    // Read stdout to parse ephemeral port
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        let mut port_found = false;

        for line in reader.lines().flatten() {
            println!("[Aether Backend] {}", line);

            if !port_found && line.contains("Aether runtime ready at: http://127.0.0.1:") {
                if let Some(port_str) = line.split("http://127.0.0.1:").nth(1) {
                    let clean_port = port_str.trim().trim_matches('/');
                    if let Ok(port) = clean_port.parse::<u16>() {
                        port_found = true;
                        let _ = tx.send(port);
                    }
                }
            }
        }
    });

    // Wait for port detection with 10s timeout
    let port = rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for backend to output bound port".to_string())?;

    println!("[Aether Desktop] Detected assigned backend port: {}", port);

    // Readiness health check probe
    let health_url = format!("http://127.0.0.1:{}/api/health", port);
    let start_probe = Instant::now();
    let mut ready = false;

    while start_probe.elapsed() < Duration::from_secs(15) {
        if let Ok(resp) = ureq::get(&health_url).timeout(Duration::from_millis(500)).call() {
            if resp.status() == 200 {
                ready = true;
                break;
            }
        }
        thread::sleep(Duration::from_millis(100));
    }

    if !ready {
        let _ = child.kill();
        return Err("Aether backend failed health check readiness probe within 15 seconds.".to_string());
    }

    println!("[Aether Desktop] Backend successfully passed readiness probe.");
    Ok((child, port, token_clone, data_dir))
}

fn graceful_shutdown(port: u16, token: &str, child_lock: &Arc<Mutex<Option<Child>>>) {
    println!("[Aether Desktop] Initiating graceful backend shutdown...");
    let shutdown_url = format!("http://127.0.0.1:{}/api/system/shutdown", port);

    let _ = ureq::post(&shutdown_url)
        .set("X-Aether-Session-Token", token)
        .timeout(Duration::from_secs(2))
        .send_json(serde_json::json!({}));

    // Allow child up to 2 seconds to terminate cleanly
    let start = Instant::now();
    loop {
        let mut guard = child_lock.lock().unwrap();
        if let Some(ref mut child) = *guard {
            match child.try_wait() {
                Ok(Some(status)) => {
                    println!("[Aether Desktop] Backend process exited cleanly with status: {:?}", status);
                    *guard = None;
                    break;
                }
                Ok(None) => {
                    if start.elapsed() > Duration::from_secs(2) {
                        println!("[Aether Desktop] Backend shutdown timed out; terminating process.");
                        let _ = child.kill();
                        *guard = None;
                        break;
                    }
                    drop(guard);
                    thread::sleep(Duration::from_millis(100));
                }
                Err(e) => {
                    eprintln!("[Aether Desktop] Error waiting for backend process: {}", e);
                    break;
                }
            }
        } else {
            break;
        }
    }
}

pub fn center_window_on_active_monitor(window: &WebviewWindow, width: u32, height: u32) {
    if let Ok(Some(monitor)) = window.current_monitor() {
        let m_pos = monitor.position();
        let m_size = monitor.size();
        let scale = monitor.scale_factor();

        let win_w = (width as f64 * scale) as i32;
        let win_h = (height as f64 * scale) as i32;

        let center_x = m_pos.x + (m_size.width as i32 - win_w) / 2;
        // Position at top 28% of display (classic Spotlight / ambient HUD position)
        let center_y = m_pos.y + (m_size.height as i32 - win_h) / 3;

        let _ = window.set_position(tauri::PhysicalPosition::new(center_x, center_y));
    }
}

pub fn position_companion_near_cursor(window: &WebviewWindow, width: u32, height: u32) {
    let app = window.app_handle();
    if let Ok(cursor_pos) = app.cursor_position() {
        if let Ok(Some(monitor)) = window.current_monitor() {
            let m_pos = monitor.position();
            let m_size = monitor.size();
            let scale = monitor.scale_factor();

            let win_w = (width as f64 * scale) as i32;
            let win_h = (height as f64 * scale) as i32;
            let margin = (16.0 * scale) as i32;

            // Offset slightly from cursor (e.g. 12px right and 16px down)
            let mut target_x = cursor_pos.x as i32 + (12.0 * scale) as i32;
            let mut target_y = cursor_pos.y as i32 + (16.0 * scale) as i32;

            let max_x = m_pos.x + m_size.width as i32 - win_w - margin;
            let min_x = m_pos.x + margin;
            let max_y = m_pos.y + m_size.height as i32 - win_h - margin;
            let min_y = m_pos.y + margin;

            // Flip to left/above if overflowing screen bounds
            if target_x > max_x {
                target_x = (cursor_pos.x as i32 - win_w - (12.0 * scale) as i32).max(min_x);
            }
            if target_y > max_y {
                target_y = (cursor_pos.y as i32 - win_h - (16.0 * scale) as i32).max(min_y);
            }

            let final_x = target_x.clamp(min_x, max_x.max(min_x));
            let final_y = target_y.clamp(min_y, max_y.max(min_y));

            let _ = window.set_position(tauri::PhysicalPosition::new(final_x, final_y));
            return;
        }
    }
    // Fallback to center if cursor position cannot be determined
    center_window_on_active_monitor(window, width, height);
}

pub fn toggle_companion_window(app: &AppHandle) {
    if let Some(companion) = app.get_webview_window("companion") {
        if let Ok(is_visible) = companion.is_visible() {
            if is_visible {
                let _ = companion.hide();
            } else {
                position_companion_near_cursor(&companion, 420, 580);
                let _ = companion.show();
                let _ = companion.unminimize();
                let _ = companion.set_focus();
            }
        }
    }
}

pub fn show_main_window_action(app: &AppHandle) {
    if let Some(companion) = app.get_webview_window("companion") {
        let _ = companion.hide();
    }
    if let Some(main) = app.get_webview_window("main") {
        let _ = main.show();
        let _ = main.unminimize();
        let _ = main.set_focus();
    }
}

fn main() {
    let (child, port, token, data_dir) = match spawn_backend_and_handshake() {
        Ok(res) => res,
        Err(err) => {
            eprintln!("[Aether Desktop ERROR] {}", err);
            std::process::exit(1);
        }
    };

    let child_arc = Arc::new(Mutex::new(Some(child)));
    let child_arc_clone = Arc::clone(&child_arc);
    let token_clone = token.clone();
    let notifications_muted = Arc::new(AtomicBool::new(false));

    let init_script = format!(
        r#"
        window.__AETHER_API_URL__ = 'http://127.0.0.1:{}';
        window.__AETHER_SESSION_TOKEN__ = '{}';
        window.__AETHER_SURFACE__ = 'workspace';
        "#,
        port, token
    );

    let companion_script = format!(
        r#"
        window.__AETHER_API_URL__ = 'http://127.0.0.1:{}';
        window.__AETHER_SESSION_TOKEN__ = '{}';
        window.__AETHER_SURFACE__ = 'companion';
        "#,
        port, token
    );

    let notifications_muted_for_state = Arc::clone(&notifications_muted);
    let notifications_muted_for_tray = Arc::clone(&notifications_muted);
    let recent_notifications = Arc::new(Mutex::new(HashMap::new()));
    let pending_targets = Arc::new(Mutex::new(Vec::new()));

    if let Some(saved) = read_persisted_target(&data_dir) {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        if now.saturating_sub(saved.created_at) <= 900 {
            pending_targets.lock().unwrap().push(saved);
        } else {
            clear_target_file(&data_dir);
        }
    }

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .manage(RuntimeState {
            port,
            token: token.clone(),
            child: Arc::clone(&child_arc),
            notifications_muted: notifications_muted_for_state,
            recent_notifications,
            pending_targets,
            data_dir,
        })
        .invoke_handler(tauri::generate_handler![
            get_runtime_info,
            get_surface_type,
            toggle_companion,
            hide_companion,
            show_main_window,
            minimize_to_companion,
            is_notifications_muted,
            set_notifications_muted,
            send_desktop_notification,
            consume_notification_target,
            quit_aether,
        ])
        .setup(move |app| {
            // 1. Build Main Workspace Window
            let main_window = WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .initialization_script(&init_script)
                .title("Aether")
                .inner_size(1200.0, 800.0)
                .min_inner_size(900.0, 600.0)
                .resizable(true)
                .build()?;

            let main_win_clone = main_window.clone();
            main_window.on_window_event(move |event| {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = main_win_clone.hide();
                    println!("[Aether Desktop] Main window hidden to system tray.");
                }
            });

            // 2. Build Ambient Companion Window
            let companion_window = WebviewWindowBuilder::new(
                app,
                "companion",
                WebviewUrl::App("index.html?surface=companion".into()),
            )
            .initialization_script(&companion_script)
            .title("Aether Companion")
            .inner_size(420.0, 580.0)
            .resizable(false)
            .decorations(false)
            .always_on_top(true)
            .skip_taskbar(true)
            .visible(false)
            .shadow(true)
            .build()?;

            let companion_win_clone = companion_window.clone();
            companion_window.on_window_event(move |event| {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = companion_win_clone.hide();
                }
            });

            // 3. System Tray & Menu Setup
            let tray_menu = MenuBuilder::new(app)
                .item(&MenuItemBuilder::with_id("open_companion", "Open Companion").build(app)?)
                .item(&MenuItemBuilder::with_id("open_workspace", "Open Full Workspace").build(app)?)
                .separator()
                .item(&MenuItemBuilder::with_id("status", "Status: Ready (idle)").enabled(false).build(app)?)
                .item(&MenuItemBuilder::with_id("mute_notifications", "Mute Notifications").build(app)?)
                .separator()
                .item(&MenuItemBuilder::with_id("quit", "Quit Aether").build(app)?)
                .build()?;

            let tray_child_arc = Arc::clone(&child_arc);
            let tray_token = token.clone();
            let tray_port = port;

            let mut tray_builder = TrayIconBuilder::new()
                .menu(&tray_menu)
                .show_menu_on_left_click(false)
                .tooltip("Aether - Personal AI Assistant")
                .on_menu_event(move |app, event| {
                    match event.id().as_ref() {
                        "open_companion" => {
                            toggle_companion_window(app);
                        }
                        "open_workspace" => {
                            show_main_window_action(app);
                        }
                        "mute_notifications" => {
                            let current = notifications_muted_for_tray.load(Ordering::Relaxed);
                            notifications_muted_for_tray.store(!current, Ordering::Relaxed);
                            println!("[Aether Desktop] Notifications muted: {}", !current);
                        }
                        "quit" => {
                            graceful_shutdown(tray_port, &tray_token, &tray_child_arc);
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        toggle_companion_window(app);
                    }
                });

            if let Some(default_icon) = app.default_window_icon() {
                tray_builder = tray_builder.icon(default_icon.clone());
            }

            let _tray = tray_builder.build(app)?;
            println!("[Aether Desktop] System tray initialized successfully.");

            // 4. Global Hotkey Registration
            app.handle().plugin(
                tauri_plugin_global_shortcut::Builder::new()
                    .with_handler(|app, _shortcut, event| {
                        if event.state() == ShortcutState::Pressed {
                            toggle_companion_window(app);
                        }
                    })
                    .build(),
            )?;

            let primary_shortcut_str = if cfg!(target_os = "macos") {
                "Option+Space"
            } else {
                "Alt+Space"
            };

            let shortcut: Result<Shortcut, _> = primary_shortcut_str.parse();
            if let Ok(s) = shortcut {
                if let Err(e) = app.global_shortcut().register(s) {
                    eprintln!(
                        "[Aether Desktop] Could not register '{}': {}. Trying fallback 'CommandOrControl+Shift+Space'...",
                        primary_shortcut_str, e
                    );
                    if let Ok(fallback) = "CommandOrControl+Shift+Space".parse::<Shortcut>() {
                        let _ = app.global_shortcut().register(fallback);
                        println!("[Aether Desktop] Registered fallback global Companion shortcut: CommandOrControl+Shift+Space");
                    }
                } else {
                    println!("[Aether Desktop] Registered global Companion shortcut: {}", primary_shortcut_str);
                }
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Error building Tauri application");

    app.run(move |app_handle, event| match event {
        RunEvent::Reopen { has_visible_windows, .. } => {
            println!("[Aether Desktop] macOS Reopen event (has_visible_windows={}). Focusing main window...", has_visible_windows);
            show_main_window_action(&app_handle);
            if let Some(state) = app_handle.try_state::<RuntimeState>() {
                let mut target = None;
                if let Ok(mut pending) = state.pending_targets.lock() {
                    target = pending.pop();
                }
                if target.is_none() {
                    target = read_persisted_target(&state.data_dir);
                }
                clear_target_file(&state.data_dir);

                if let Some(t) = target {
                    let now = SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .unwrap_or_default()
                        .as_secs();
                    if now.saturating_sub(t.created_at) <= 900 {
                        println!("[Aether Desktop] Dispatched notification target navigation on reopen: view={}, id={:?}", t.view, t.id);
                        let _ = app_handle.emit("navigate_view", serde_json::json!({
                            "notification_id": t.notification_id,
                            "target_type": t.target_type,
                            "target_id": t.target_id,
                            "view": t.view,
                            "id": t.id,
                            "deep_link": t.deep_link,
                        }));
                    }
                }
            }
        }
        RunEvent::Exit | RunEvent::ExitRequested { .. } => {
            graceful_shutdown(port, &token_clone, &child_arc_clone);
        }
        _ => {}
    });
}
