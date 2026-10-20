//! Native screen capture for the Companion's screen understanding.
//!
//! Principles (see docs/product/screen-understanding.md):
//! * Only on an explicit command from the Companion UI. There is no timer, no background capture and no capture on
//!   start-up; every call is one user gesture.
//! * macOS needs the *Screen Recording* permission. It is never bypassed: the permission is checked first and, when it
//!   is missing, nothing is captured and the UI is told exactly that (and how to grant it). Without it macOS would
//!   hand back an image with the windows missing, which would be a silent lie, so we do not even try.
//! * The image goes through a private temp dir (0700, owned by this process) and is deleted right after it is read. It
//!   is returned to the UI in memory; it is not stored anywhere by default.
//! * The Companion hides itself for the capture so that it is not in the picture, and comes back afterwards.
//! * Region/window selection uses the system's own `screencapture -i` UI (Esc cancels, nothing is produced).
//!
//! Non-macOS targets report `unsupported` honestly (the Windows implementation is future work; the command contract
//! is the same, so the UI needs no change).

#[cfg(target_os = "macos")]
use std::time::Duration;

use serde::Serialize;
use tauri::AppHandle;

#[cfg(target_os = "macos")]
use crate::companion;

/// Longest side sent to a model: bigger screenshots are resampled down (models downscale anyway; this bounds the size).
#[cfg(target_os = "macos")]
const MAX_SIDE: u32 = 1568;
#[cfg(target_os = "macos")]
const MAX_BYTES: usize = 8 * 1024 * 1024;

#[derive(Serialize, Clone, Debug)]
pub struct CaptureStatus {
    pub platform: &'static str,
    pub supported: bool,
    /// granted | denied | unsupported
    pub permission: &'static str,
}

#[derive(Serialize, Clone, Debug)]
pub struct ScreenRect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

#[derive(Serialize, Clone, Debug, Default)]
pub struct CaptureResult {
    pub ok: bool,
    /// permission_denied | cancelled | capture_failed | unsupported | too_large (only when ok == false)
    pub error: Option<String>,
    pub detail: Option<String>,
    pub image_base64: Option<String>,
    pub media_type: Option<String>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub mode: String,
    /// Where the image sits on the desktop, in screen points. Known for full-screen captures only.
    pub screen: Option<ScreenRect>,
    /// What the bundled local OCR read: `{width,height,words:[{text,x,y,w,h}]}` with boxes normalised to the image. None when
    /// the helper is missing or failed: the capture is then offered without automatic hiding, and the UI says so.
    pub ocr: Option<serde_json::Value>,
}

impl CaptureResult {
    fn err(mode: &str, code: &str, detail: impl Into<String>) -> Self {
        CaptureResult { ok: false, error: Some(code.to_string()), detail: Some(detail.into()), mode: mode.to_string(), ..Default::default() }
    }
}

/// Parses width/height from a PNG header (IHDR). None when the bytes are not a PNG.
pub fn png_size(bytes: &[u8]) -> Option<(u32, u32)> {
    if bytes.len() < 24 || &bytes[..8] != b"\x89PNG\r\n\x1a\n" || &bytes[12..16] != b"IHDR" {
        return None;
    }
    let w = u32::from_be_bytes([bytes[16], bytes[17], bytes[18], bytes[19]]);
    let h = u32::from_be_bytes([bytes[20], bytes[21], bytes[22], bytes[23]]);
    Some((w, h))
}

pub fn base64_encode(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity((data.len() + 2) / 3 * 4);
    for chunk in data.chunks(3) {
        let b = [chunk[0], *chunk.get(1).unwrap_or(&0), *chunk.get(2).unwrap_or(&0)];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        out.push(T[(n >> 18) as usize & 63] as char);
        out.push(T[(n >> 12) as usize & 63] as char);
        out.push(if chunk.len() > 1 { T[(n >> 6) as usize & 63] as char } else { '=' });
        out.push(if chunk.len() > 2 { T[n as usize & 63] as char } else { '=' });
    }
    out
}

#[cfg(target_os = "macos")]
mod mac {
    use super::*;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::path::PathBuf;
    use std::process::Command;

    #[repr(C)]
    #[derive(Clone, Copy)]
    struct CGPoint {
        x: f64,
        y: f64,
    }
    #[repr(C)]
    #[derive(Clone, Copy)]
    struct CGSize {
        width: f64,
        height: f64,
    }
    #[repr(C)]
    #[derive(Clone, Copy)]
    struct CGRect {
        origin: CGPoint,
        size: CGSize,
    }

    #[link(name = "CoreGraphics", kind = "framework")]
    extern "C" {
        fn CGPreflightScreenCaptureAccess() -> bool;
        fn CGRequestScreenCaptureAccess() -> bool;
        fn CGMainDisplayID() -> u32;
        fn CGDisplayBounds(display: u32) -> CGRect;
    }

    pub fn permission_granted() -> bool {
        unsafe { CGPreflightScreenCaptureAccess() }
    }

    /// Shows the system's permission prompt (once per app; afterwards macOS only lists it in System Settings).
    pub fn request_permission() -> bool {
        unsafe { CGRequestScreenCaptureAccess() }
    }

    pub fn open_settings() {
        let _ = Command::new("/usr/bin/open")
            .arg("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
            .spawn();
    }

    fn main_display_rect() -> ScreenRect {
        let r = unsafe { CGDisplayBounds(CGMainDisplayID()) };
        ScreenRect { x: r.origin.x, y: r.origin.y, width: r.size.width, height: r.size.height }
    }

    /// A private, per-process scratch dir (0700). Removed by the caller.
    fn scratch_dir() -> std::io::Result<PathBuf> {
        let dir = std::env::temp_dir().join(format!("aether-capture-{}", std::process::id()));
        fs::create_dir_all(&dir)?;
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700))?;
        Ok(dir)
    }

    /// Where the bundled OCR helper lives: next to the runtime in the app bundle, or AETHER_VISION_PATH for development.
    fn vision_helper() -> Option<PathBuf> {
        if let Ok(p) = std::env::var("AETHER_VISION_PATH") {
            let p = PathBuf::from(p);
            if p.is_file() {
                return Some(p);
            }
        }
        let exe = std::env::current_exe().ok()?;
        let dir = exe.parent()?;
        [dir.join("../Resources/aether-vision"), dir.join("../Resources/resources/aether-vision"), dir.join("../../resources/aether-vision")]
            .into_iter()
            .find(|c| c.is_file())
    }

    /// Local OCR (macOS Vision, offline) of one image file. Bounded to 8 s; any failure yields None, never an error.
    pub(super) fn ocr_words(image: &std::path::Path) -> Option<serde_json::Value> {
        let helper = vision_helper()?;
        let mut child = Command::new(helper)
            .arg("ocr")
            .arg(image)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .spawn()
            .ok()?;
        let started = std::time::Instant::now();
        loop {
            match child.try_wait().ok()? {
                Some(status) if status.success() => break,
                Some(_) => return None,
                None if started.elapsed() > Duration::from_secs(8) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return None;
                }
                None => std::thread::sleep(Duration::from_millis(25)),
            }
        }
        let mut out = String::new();
        use std::io::Read;
        child.stdout.take()?.read_to_string(&mut out).ok()?;
        serde_json::from_str(&out).ok()
    }

    pub fn capture(mode: &str) -> CaptureResult {
        let region = mode == "region";
        let dir = match scratch_dir() {
            Ok(d) => d,
            Err(e) => return CaptureResult::err(mode, "capture_failed", format!("temp dir: {e}")),
        };
        let raw = dir.join("capture.png");
        let small = dir.join("capture-small.png");
        let result = (|| {
            let mut cmd = Command::new("/usr/sbin/screencapture");
            cmd.arg("-x").args(["-t", "png"]);
            if region {
                cmd.arg("-i"); // the system's own selection UI; Esc cancels and writes nothing
            } else {
                cmd.arg("-m"); // main display only
            }
            cmd.arg(&raw);
            let status = cmd.status().map_err(|e| CaptureResult::err(mode, "capture_failed", format!("screencapture: {e}")))?;
            let exists = raw.metadata().map(|m| m.len() > 0).unwrap_or(false);
            if !exists {
                return Err(if region && status.success() {
                    CaptureResult::err(mode, "cancelled", "selection cancelled")
                } else if region {
                    CaptureResult::err(mode, "cancelled", format!("screencapture exited with {status}"))
                } else {
                    CaptureResult::err(mode, "capture_failed", format!("screencapture exited with {status} and produced no image"))
                });
            }
            // Bound the size (also keeps the in-memory hand-over to the UI small). If sips fails the original is used.
            let used = if Command::new("/usr/bin/sips")
                .args(["-Z", &MAX_SIDE.to_string()])
                .arg(&raw)
                .arg("--out")
                .arg(&small)
                .output()
                .map(|o| o.status.success())
                .unwrap_or(false)
                && small.exists()
            {
                &small
            } else {
                &raw
            };
            let bytes = fs::read(used).map_err(|e| CaptureResult::err(mode, "capture_failed", format!("read: {e}")))?;
            if bytes.len() > MAX_BYTES {
                return Err(CaptureResult::err(mode, "too_large", format!("{} bytes", bytes.len())));
            }
            let (w, h) = png_size(&bytes).ok_or_else(|| CaptureResult::err(mode, "capture_failed", "not a PNG"))?;
            let ocr = ocr_words(used);
            Ok(CaptureResult {
                ok: true,
                image_base64: Some(base64_encode(&bytes)),
                media_type: Some("image/png".into()),
                width: Some(w),
                height: Some(h),
                mode: mode.to_string(),
                screen: if region { None } else { Some(main_display_rect()) },
                ocr,
                ..Default::default()
            })
        })();
        let _ = fs::remove_dir_all(&dir); // the image never stays on disk
        match result {
            Ok(r) | Err(r) => r,
        }
    }
}

#[tauri::command]
pub fn screen_capture_status() -> CaptureStatus {
    #[cfg(target_os = "macos")]
    {
        CaptureStatus { platform: "macos", supported: true, permission: if mac::permission_granted() { "granted" } else { "denied" } }
    }
    #[cfg(not(target_os = "macos"))]
    {
        CaptureStatus { platform: if cfg!(target_os = "windows") { "windows" } else { "other" }, supported: false, permission: "unsupported" }
    }
}

/// Asks macOS to show its Screen Recording prompt (only the first time) and returns the resulting status.
#[tauri::command]
pub fn screen_capture_request_permission() -> CaptureStatus {
    #[cfg(target_os = "macos")]
    {
        let _ = mac::request_permission();
    }
    screen_capture_status()
}

#[tauri::command]
pub fn screen_capture_open_settings() {
    #[cfg(target_os = "macos")]
    mac::open_settings();
}

/// A capture for the summon flow (hotkey pressed): the display under the pointer's main screen, taken BEFORE the Bar shows, so
/// nothing of the Companion is in the picture and no hide/restore dance is needed. Blocking; call from a worker thread.
pub fn capture_screen_blocking() -> CaptureResult {
    #[cfg(not(target_os = "macos"))]
    {
        CaptureResult::err("screen", "unsupported", "screen capture is not implemented on this platform yet")
    }
    #[cfg(target_os = "macos")]
    {
        if !mac::permission_granted() {
            return CaptureResult::err("screen", "permission_denied", "Screen Recording permission is not granted");
        }
        mac::capture("screen")
    }
}

/// One capture, on explicit request. `mode` is "screen" (main display) or "region" (the system selection UI).
#[tauri::command]
pub async fn screen_capture_take(app: AppHandle, mode: String) -> CaptureResult {
    let mode = if mode == "region" { "region" } else { "screen" }.to_string();
    #[cfg(not(target_os = "macos"))]
    {
        let _ = &app;
        return CaptureResult::err(&mode, "unsupported", "screen capture is not implemented on this platform yet");
    }
    #[cfg(target_os = "macos")]
    {
        if !mac::permission_granted() {
            return CaptureResult::err(&mode, "permission_denied", "Screen Recording permission is not granted");
        }
        let was_visible = companion::hide_for_capture(&app);
        if was_visible {
            // let the window actually leave the screen before the picture is taken
            tokio::time::sleep(Duration::from_millis(350)).await;
        }
        let m = mode.clone();
        let res = tauri::async_runtime::spawn_blocking(move || mac::capture(&m))
            .await
            .unwrap_or_else(|e| CaptureResult::err(&mode, "capture_failed", format!("capture task: {e}")));
        companion::restore_after_capture(&app, was_visible);
        res
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_matches_the_standard_vectors() {
        assert_eq!(base64_encode(b""), "");
        assert_eq!(base64_encode(b"f"), "Zg==");
        assert_eq!(base64_encode(b"fo"), "Zm8=");
        assert_eq!(base64_encode(b"foo"), "Zm9v");
        assert_eq!(base64_encode(b"foobar"), "Zm9vYmFy");
    }

    #[test]
    fn png_size_reads_ihdr_and_rejects_anything_else() {
        let mut png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR".to_vec();
        png.extend_from_slice(&1920u32.to_be_bytes());
        png.extend_from_slice(&1080u32.to_be_bytes());
        png.extend_from_slice(&[8, 2, 0, 0, 0]);
        assert_eq!(png_size(&png), Some((1920, 1080)));
        assert_eq!(png_size(b"GIF89a-not-a-png-at-all-really"), None);
        assert_eq!(png_size(&png[..10]), None);
    }

    #[test]
    fn unsupported_or_failed_results_never_carry_an_image() {
        let r = CaptureResult::err("screen", "permission_denied", "x");
        assert!(!r.ok && r.image_base64.is_none() && r.error.as_deref() == Some("permission_denied"));
    }
}
