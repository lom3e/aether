// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use rand::distributions::Alphanumeric;
use rand::Rng;
use serde::Serialize;
use tauri::{Manager, RunEvent, State};

#[allow(dead_code)]
struct RuntimeState {
    port: u16,
    token: String,
    child: Arc<Mutex<Option<Child>>>,
}

#[derive(Serialize)]
struct RuntimeInfo {
    api_url: String,
    session_token: String,
    port: u16,
    version: String,
}

#[tauri::command]
fn get_runtime_info(state: State<RuntimeState>) -> Result<RuntimeInfo, String> {
    Ok(RuntimeInfo {
        api_url: format!("http://127.0.0.1:{}", state.port),
        session_token: state.token.clone(),
        port: state.port,
        version: "1.4.0".to_string(),
    })
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

    // 2. Production app bundle on macOS: ~/Library/Application Support/Aether
    if let Ok(home) = std::env::var("HOME") {
        if is_app_bundle {
            return PathBuf::from(home)
                .join("Library")
                .join("Application Support")
                .join("Aether");
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

    // 2. Bundled production paths (inside Aether.app/Contents/Resources/ or adjacent)
    let bundled_candidate_paths = [
        exe_dir.join("../Resources/aether-runtime/aether-runtime"),
        exe_dir.join("../Resources/resources/aether-runtime/aether-runtime"),
        exe_dir.join("../Resources/binaries/aether-runtime-aarch64-apple-darwin"),
        exe_dir.join("../Resources/aether-runtime"),
        exe_dir.join("aether-runtime/aether-runtime"),
        exe_dir.join("aether-runtime"),
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
        current_dir.join("build").join("aether-runtime").join("aether-runtime"),
        current_dir.join("..").join("build").join("aether-runtime").join("aether-runtime"),
        current_dir.join("src-tauri").join("resources").join("aether-runtime").join("aether-runtime"),
        current_dir.join("src-tauri").join("binaries").join("aether-runtime-aarch64-apple-darwin"),
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
        let venv_python = check_dir.join(".venv").join("bin").join("python");
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

fn spawn_backend_and_handshake() -> Result<(Child, u16, String), String> {
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
    Ok((child, port, token_clone))
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

fn main() {
    let (child, port, token) = match spawn_backend_and_handshake() {
        Ok(res) => res,
        Err(err) => {
            eprintln!("[Aether Desktop ERROR] {}", err);
            std::process::exit(1);
        }
    };

    let child_arc = Arc::new(Mutex::new(Some(child)));
    let child_arc_clone = Arc::clone(&child_arc);
    let token_clone = token.clone();

    let init_script = format!(
        r#"
        window.__AETHER_API_URL__ = 'http://127.0.0.1:{}';
        window.__AETHER_SESSION_TOKEN__ = '{}';
        "#,
        port, token
    );

    let app = tauri::Builder::default()
        .manage(RuntimeState {
            port,
            token: token.clone(),
            child: Arc::clone(&child_arc),
        })
        .invoke_handler(tauri::generate_handler![get_runtime_info])
        .setup(move |app| {
            tauri::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::default())
                .initialization_script(&init_script)
                .title("Aether")
                .inner_size(1200.0, 800.0)
                .min_inner_size(900.0, 600.0)
                .resizable(true)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Error building Tauri application");

    app.run(move |_app_handle, event| match event {
        RunEvent::Exit | RunEvent::ExitRequested { .. } => {
            graceful_shutdown(port, &token_clone, &child_arc_clone);
        }
        _ => {}
    });
}
