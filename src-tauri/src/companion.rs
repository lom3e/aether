//! Native window behaviour of the Aether Companion (compact orb <-> expanded panel).
//!
//! The Companion is a *surface* of the same runtime: this module only owns the window (size, position, focus,
//! dragging, cursor-relative placement). Conversation, memory, missions and approvals stay in Aether Core and are
//! reached by the webview through the normal API.
//!
//! Cursor position: Tauri's `cursor_position()` reads the real global pointer (NSEvent.mouseLocation on macOS,
//! GetCursorPos on Windows). It needs no Accessibility permission. Reading what is *under* the cursor, drawing on
//! the screen or controlling input will need Accessibility / Screen Recording; none of that is requested here.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, LogicalSize, Manager, PhysicalPosition, State, WebviewWindow};
#[cfg(target_os = "macos")]
use tauri::utils::config::WindowEffectsConfig;
#[cfg(target_os = "macos")]
use tauri::window::{Effect, EffectState};

pub const ORB_SIZE: f64 = 88.0;
/// The "Bar" (a Spotlight-like glass chat): starts as one input row and grows with the conversation up to PANEL_MAX_H.
pub const PANEL_W: f64 = 680.0;
pub const PANEL_H: f64 = 132.0;
pub const PANEL_MAX_H: f64 = 640.0;
/// Space kept free around the window when it is clamped to a screen (logical px).
const SCREEN_MARGIN: f64 = 8.0;
/// Where the orb settles relative to the pointer when it comes to it (logical px, right/below).
const FOLLOW_OFFSET: f64 = 44.0;
/// The pointer must rest this long before a following orb moves (it never chases a moving cursor).
const FOLLOW_IDLE: Duration = Duration::from_millis(550);
/// Minimum distance (logical px) between orb and target before it bothers to move.
const FOLLOW_MIN_DISTANCE: f64 = 160.0;
/// After the user drags the orb themselves, following is suspended for this long.
const USER_MOVE_BACKOFF: Duration = Duration::from_secs(6);

#[derive(Clone, Copy, PartialEq, Eq, Serialize, Debug)]
#[serde(rename_all = "lowercase")]
pub enum Mode {
    Orb,
    Panel,
}

impl Mode {
    pub fn parse(s: &str) -> Option<Mode> {
        match s {
            "orb" => Some(Mode::Orb),
            "panel" => Some(Mode::Panel),
            _ => None,
        }
    }
    pub fn as_str(&self) -> &'static str {
        match self {
            Mode::Orb => "orb",
            Mode::Panel => "panel",
        }
    }
    fn logical_size(&self) -> (f64, f64) {
        match self {
            Mode::Orb => (ORB_SIZE, ORB_SIZE),
            Mode::Panel => (PANEL_W, PANEL_H),
        }
    }
}

/// A key held at least this long is "hold to talk"; anything shorter is a tap.
pub const HOLD_THRESHOLD: Duration = Duration::from_millis(250);
/// A summon capture nobody collected within this long is discarded (it is never kept around).
const CONTEXT_TTL: Duration = Duration::from_secs(120);

/// Pure: is this press-and-release a hold-to-talk (versus a tap)?
pub fn is_hold(held: Duration) -> bool {
    held >= HOLD_THRESHOLD
}

pub struct CompanionState {
    pub mode: Mutex<Mode>,
    /// When the summon key went down (None = not down).
    pub pressed: Mutex<Option<Instant>>,
    pub released: Mutex<Option<Instant>>,
    /// The Bar was already open when the key went down (a tap then collapses it).
    pub was_open: AtomicBool,
    /// The summon flow has shown the Bar and sent `press` to the page.
    pub shown: AtomicBool,
    /// The screen taken when summoned, in memory only, handed over once to the page.
    pub pending: Mutex<Option<(Instant, crate::screen_capture::CaptureResult)>>,
    pub follow: AtomicBool,
    pub last_user_move: Mutex<Instant>,
}

impl CompanionState {
    pub fn new() -> Self {
        CompanionState {
            mode: Mutex::new(Mode::Orb),
            pressed: Mutex::new(None),
            released: Mutex::new(None),
            was_open: AtomicBool::new(false),
            shown: AtomicBool::new(false),
            pending: Mutex::new(None),
            follow: AtomicBool::new(false),
            last_user_move: Mutex::new(Instant::now() - USER_MOVE_BACKOFF),
        }
    }
}

#[derive(Serialize)]
pub struct CompanionInfo {
    pub mode: &'static str,
    pub follow: bool,
    pub visible: bool,
    pub platform: &'static str,
}

fn window(app: &AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window("companion")
}

/// Clamps a window of `w` x `h` physical pixels with its top-left at (x, y) into the monitor under (px, py).
pub fn clamp_to_monitor(app: &AppHandle, x: i32, y: i32, w: i32, h: i32, px: f64, py: f64, scale: f64) -> (i32, i32) {
    let margin = (SCREEN_MARGIN * scale) as i32;
    if let Ok(Some(m)) = app.monitor_from_point(px, py) {
        let mp = m.position();
        let ms = m.size();
        let min_x = mp.x + margin;
        let min_y = mp.y + margin;
        let max_x = (mp.x + ms.width as i32 - w - margin).max(min_x);
        let max_y = (mp.y + ms.height as i32 - h - margin).max(min_y);
        return (x.clamp(min_x, max_x), y.clamp(min_y, max_y));
    }
    (x, y)
}

fn notify_mode(win: &WebviewWindow, mode: Mode) {
    let _ = win.eval(&format!(
        "window.dispatchEvent(new CustomEvent('aether-companion-mode',{{detail:{{mode:'{}'}}}}))",
        mode.as_str()
    ));
}

/// The orb is plain transparent glass. The Bar is a frosted-glass sheet (vibrancy) WITHOUT any native shadow: the blurred
/// halo behind a rounded window read as a smudge before, so there is none; the page draws a thin crisp edge instead.
pub fn apply_chrome(win: &WebviewWindow, mode: Mode) {
    #[cfg(target_os = "macos")]
    {
        let _ = win.set_shadow(false);
        let effects = if mode == Mode::Panel {
            Some(WindowEffectsConfig { effects: vec![Effect::Popover], state: Some(EffectState::Active), radius: Some(22.0), color: None })
        } else {
            None
        };
        let _ = win.set_effects(effects);
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (win, mode);
    }
}

/// Switches between the compact orb and the expanded panel, keeping the top-left corner where it was
/// (clamped so the window never leaves the screen).
pub fn set_mode(app: &AppHandle, mode: Mode) {
    let Some(win) = window(app) else { return };
    let scale = win.scale_factor().unwrap_or(1.0);
    let (lw, lh) = mode.logical_size();
    let _ = win.set_size(LogicalSize::new(lw, lh));
    if mode == Mode::Panel {
        place_bar(app, &win, lw, lh, scale);
    } else {
        place_near_cursor(app, &win, lw, lh, scale, FOLLOW_OFFSET, FOLLOW_OFFSET);
    }
    if let Some(state) = app.try_state::<CompanionState>() {
        *state.mode.lock().unwrap() = mode;
    }
    apply_chrome(&win, mode);
    if mode == Mode::Panel {
        let _ = win.set_focus();
    }
    notify_mode(&win, mode);
}

/// Shows the Companion as the expanded panel next to the pointer (quick-ask), or toggles it when already visible:
/// panel -> orb, orb -> panel.
pub fn toggle(app: &AppHandle) {
    let Some(win) = window(app) else { return };
    let visible = win.is_visible().unwrap_or(false);
    if !visible {
        let (lw, lh) = Mode::Panel.logical_size();
        let scale = win.scale_factor().unwrap_or(1.0);
        let _ = win.set_size(LogicalSize::new(lw, lh));
        place_bar(app, &win, lw, lh, scale);
        if let Some(state) = app.try_state::<CompanionState>() {
            *state.mode.lock().unwrap() = Mode::Panel;
        }
        apply_chrome(&win, Mode::Panel);
        let _ = win.show();
        let _ = win.unminimize();
        let _ = win.set_focus();
        notify_mode(&win, Mode::Panel);
        return;
    }
    let current = app
        .try_state::<CompanionState>()
        .map(|s| *s.mode.lock().unwrap())
        .unwrap_or(Mode::Panel);
    set_mode(app, if current == Mode::Panel { Mode::Orb } else { Mode::Panel });
}

/// Brings the Companion up as the expanded panel without ever collapsing it (used by "minimize to Companion").
pub fn summon_panel(app: &AppHandle) {
    let visible = window(app).and_then(|w| w.is_visible().ok()).unwrap_or(false);
    if visible {
        set_mode(app, Mode::Panel);
    } else {
        toggle(app);
    }
}

fn notify_summon(win: &WebviewWindow, phase: &str) {
    let _ = win.eval(&format!("window.dispatchEvent(new CustomEvent('aether-companion-summon',{{detail:{{phase:'{}'}}}}))", phase));
}

fn show_bar(app: &AppHandle, win: &WebviewWindow) {
    let (lw, lh) = Mode::Panel.logical_size();
    let scale = win.scale_factor().unwrap_or(1.0);
    let _ = win.set_size(LogicalSize::new(lw, lh));
    place_bar(app, win, lw, lh, scale);
    if let Some(state) = app.try_state::<CompanionState>() {
        *state.mode.lock().unwrap() = Mode::Panel;
    }
    apply_chrome(win, Mode::Panel);
    let _ = win.show();
    let _ = win.unminimize();
    let _ = win.set_focus();
    notify_mode(win, Mode::Panel);
}

/// The summon key went down. On macOS the screen is read FIRST (before anything shows), then the Bar appears and the page
/// starts listening; releasing it later decides between hold-to-talk and a tap. Other platforms keep the plain toggle.
pub fn summon_press(app: &AppHandle) {
    if !cfg!(target_os = "macos") {
        toggle(app);
        return;
    }
    let Some(win) = window(app) else { return };
    let Some(state) = app.try_state::<CompanionState>() else { return };
    {
        let mut p = state.pressed.lock().unwrap();
        if p.is_some() {
            return; // key auto-repeat
        }
        *p = Some(Instant::now());
    }
    *state.released.lock().unwrap() = None;
    state.shown.store(false, Ordering::SeqCst);
    let open = win.is_visible().unwrap_or(false) && *state.mode.lock().unwrap() == Mode::Panel;
    state.was_open.store(open, Ordering::SeqCst);
    let app2 = app.clone();
    thread::spawn(move || {
        if !open {
            let shot = crate::screen_capture::capture_screen_blocking();
            if shot.ok {
                if let Some(st) = app2.try_state::<CompanionState>() {
                    *st.pending.lock().unwrap() = Some((Instant::now(), shot));
                }
            }
        }
        let Some(win) = window(&app2) else { return };
        if !open {
            show_bar(&app2, &win);
        }
        notify_summon(&win, "press");
        if let Some(st) = app2.try_state::<CompanionState>() {
            st.shown.store(true, Ordering::SeqCst);
            // The key may have been released while the screen was being read.
            if st.released.lock().unwrap().is_some() {
                finish_summon(&app2, &win);
            }
        }
    });
}

pub fn summon_release(app: &AppHandle) {
    if !cfg!(target_os = "macos") {
        return;
    }
    let Some(state) = app.try_state::<CompanionState>() else { return };
    if state.pressed.lock().unwrap().is_none() {
        return;
    }
    *state.released.lock().unwrap() = Some(Instant::now());
    if state.shown.load(Ordering::SeqCst) {
        if let Some(win) = window(app) {
            finish_summon(app, &win);
        }
    }
}

/// Key is up and the page knows the key went down: tell it hold vs tap (and collapse an already-open Bar on a tap).
fn finish_summon(app: &AppHandle, win: &WebviewWindow) {
    let Some(state) = app.try_state::<CompanionState>() else { return };
    let (down, up) = (state.pressed.lock().unwrap().take(), state.released.lock().unwrap().take());
    let held = match (down, up) {
        (Some(d), Some(u)) => u.saturating_duration_since(d),
        _ => Duration::ZERO,
    };
    if is_hold(held) {
        notify_summon(win, "release");
    } else if state.was_open.load(Ordering::SeqCst) {
        notify_summon(win, "cancel");
        set_mode(app, Mode::Orb);
    } else {
        notify_summon(win, "tap");
    }
}

pub fn hide(app: &AppHandle) {
    if let Some(win) = window(app) {
        let _ = win.hide();
    }
}

/// Centres the Bar horizontally on the monitor under the pointer, a fifth of the way down (where Spotlight sits).
fn place_bar(app: &AppHandle, win: &WebviewWindow, lw: f64, lh: f64, scale: f64) {
    let (w, h) = ((lw * scale) as i32, (lh * scale) as i32);
    let cursor = app.cursor_position().ok();
    let monitor = cursor.as_ref().and_then(|c| app.monitor_from_point(c.x, c.y).ok().flatten()).or_else(|| app.primary_monitor().ok().flatten());
    match monitor {
        Some(m) => {
            let (mp, ms) = (m.position(), m.size());
            let x = mp.x + (ms.width as i32 - w) / 2;
            let y = mp.y + (ms.height as f64 * 0.2) as i32;
            let (px, py) = cursor.map(|c| (c.x, c.y)).unwrap_or((x as f64, y as f64));
            let (x, y) = clamp_to_monitor(app, x, y, w, h, px, py, scale);
            let _ = win.set_position(PhysicalPosition::new(x, y));
        }
        None => crate::center_window_on_active_monitor(win, lw as u32, lh as u32),
    }
}

/// Places a `lw` x `lh` (logical) window near the real global pointer, flipping to the other side when it would
/// overflow the screen. Falls back to the screen centre when the pointer cannot be read.
fn place_near_cursor(app: &AppHandle, win: &WebviewWindow, lw: f64, lh: f64, scale: f64, dx: f64, dy: f64) {
    match app.cursor_position() {
        Ok(c) => {
            let (w, h) = ((lw * scale) as i32, (lh * scale) as i32);
            let mut x = c.x as i32 + (dx * scale) as i32;
            let mut y = c.y as i32 + (dy * scale) as i32;
            if let Ok(Some(m)) = app.monitor_from_point(c.x, c.y) {
                let mp = m.position();
                let ms = m.size();
                if x + w > mp.x + ms.width as i32 {
                    x = c.x as i32 - w - (dx * scale) as i32;
                }
                if y + h > mp.y + ms.height as i32 {
                    y = c.y as i32 - h - (dy * scale) as i32;
                }
            }
            let (x, y) = clamp_to_monitor(app, x, y, w, h, c.x, c.y, scale);
            let _ = win.set_position(PhysicalPosition::new(x, y));
        }
        Err(_) => crate::center_window_on_active_monitor(win, lw as u32, lh as u32),
    }
}

// ----------------------------------------------------------------------------------------------------------------
// Commands (own commands: they need no capability/ACL entry, unlike the generic window plugin)
// ----------------------------------------------------------------------------------------------------------------

#[tauri::command]
pub fn companion_get_state(app: AppHandle, state: State<CompanionState>) -> CompanionInfo {
    CompanionInfo {
        mode: state.mode.lock().unwrap().as_str(),
        follow: state.follow.load(Ordering::SeqCst),
        visible: window(&app).and_then(|w| w.is_visible().ok()).unwrap_or(false),
        platform: if cfg!(target_os = "macos") { "macos" } else if cfg!(windows) { "windows" } else { "other" },
    }
}

/// The screen read when the Companion was summoned, handed over ONCE (None if there is none or it is stale).
#[tauri::command]
pub fn companion_take_context(state: State<CompanionState>) -> Option<crate::screen_capture::CaptureResult> {
    let taken = state.pending.lock().unwrap().take();
    taken.filter(|(at, _)| at.elapsed() < CONTEXT_TTL).map(|(_, c)| c)
}

#[tauri::command]
pub fn companion_set_mode(app: AppHandle, mode: String) -> Result<(), String> {
    let m = Mode::parse(&mode).ok_or_else(|| format!("unknown companion mode '{}'", mode))?;
    set_mode(&app, m);
    Ok(())
}

/// The Bar grows and shrinks with its content (the page reports the height it needs). Only meaningful in Panel mode.
#[tauri::command]
pub fn companion_resize_panel(app: AppHandle, state: State<CompanionState>, height: f64) {
    if *state.mode.lock().unwrap() != Mode::Panel || !height.is_finite() {
        return;
    }
    let Some(win) = window(&app) else { return };
    let h = height.clamp(PANEL_H.min(96.0), PANEL_MAX_H);
    let scale = win.scale_factor().unwrap_or(1.0);
    let pos = win.outer_position().unwrap_or(PhysicalPosition::new(0, 0));
    let (pw, ph) = ((PANEL_W * scale) as i32, (h * scale) as i32);
    let (x, y) = clamp_to_monitor(&app, pos.x, pos.y, pw, ph, pos.x as f64 + 10.0, pos.y as f64 + 10.0, scale);
    let _ = win.set_size(LogicalSize::new(PANEL_W, h));
    let _ = win.set_position(PhysicalPosition::new(x, y));
}

/// Starts a native window drag (called on mouse-down on a drag handle). Following pauses afterwards.
#[tauri::command]
pub fn companion_start_drag(window: WebviewWindow, state: State<CompanionState>) -> Result<(), String> {
    *state.last_user_move.lock().unwrap() = Instant::now();
    window.start_dragging().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn companion_set_follow(state: State<CompanionState>, enabled: bool) {
    state.follow.store(enabled, Ordering::SeqCst);
}

// ----------------------------------------------------------------------------------------------------------------
// Optional "come to the cursor" behaviour
// ----------------------------------------------------------------------------------------------------------------

/// Pure decision used by the follow loop (unit-tested): should the orb move to the pointer now?
pub fn should_follow(
    enabled: bool,
    mode: Mode,
    visible: bool,
    cursor_idle: Duration,
    since_user_move: Duration,
    cursor_over_orb: bool,
    distance_logical: f64,
) -> bool {
    enabled
        && mode == Mode::Orb
        && visible
        && cursor_idle >= FOLLOW_IDLE
        && since_user_move >= USER_MOVE_BACKOFF
        && !cursor_over_orb
        && distance_logical >= FOLLOW_MIN_DISTANCE
}

/// Background loop. It only ever *settles* next to a resting pointer; it never tracks a moving one, never runs while
/// the panel is open, while the pointer is over the orb, or shortly after the user dragged the orb.
pub fn start_follow_loop(app: AppHandle) {
    thread::spawn(move || {
        let mut last_cursor = (f64::MIN, f64::MIN);
        let mut idle_since = Instant::now();
        loop {
            thread::sleep(Duration::from_millis(120));
            let Some(state) = app.try_state::<CompanionState>() else { continue };
            let Some(win) = window(&app) else { continue };
            let Ok(cursor) = app.cursor_position() else { continue };
            if (cursor.x - last_cursor.0).abs() > 3.0 || (cursor.y - last_cursor.1).abs() > 3.0 {
                last_cursor = (cursor.x, cursor.y);
                idle_since = Instant::now();
            }
            if !state.follow.load(Ordering::SeqCst) {
                continue;
            }
            let (Ok(pos), Ok(size)) = (win.outer_position(), win.outer_size()) else { continue };
            let scale = win.scale_factor().unwrap_or(1.0);
            let over = cursor.x >= pos.x as f64 - 40.0 * scale
                && cursor.x <= (pos.x + size.width as i32) as f64 + 40.0 * scale
                && cursor.y >= pos.y as f64 - 40.0 * scale
                && cursor.y <= (pos.y + size.height as i32) as f64 + 40.0 * scale;
            let center = (pos.x as f64 + size.width as f64 / 2.0, pos.y as f64 + size.height as f64 / 2.0);
            let dist = ((cursor.x - center.0).powi(2) + (cursor.y - center.1).powi(2)).sqrt() / scale;
            let mode = *state.mode.lock().unwrap();
            let since_move = state.last_user_move.lock().unwrap().elapsed();
            if !should_follow(true, mode, win.is_visible().unwrap_or(false), idle_since.elapsed(), since_move, over, dist) {
                continue;
            }
            let (w, h) = (size.width as i32, size.height as i32);
            let tx = cursor.x as i32 + (FOLLOW_OFFSET * scale) as i32;
            let ty = cursor.y as i32 + (FOLLOW_OFFSET * scale) as i32;
            let (tx, ty) = clamp_to_monitor(&app, tx, ty, w, h, cursor.x, cursor.y, scale);
            // Short eased glide so the move reads as intentional, not as a jump.
            let steps = 12;
            for i in 1..=steps {
                let t = i as f64 / steps as f64;
                let e = 1.0 - (1.0 - t).powi(3);
                let nx = pos.x as f64 + (tx - pos.x) as f64 * e;
                let ny = pos.y as f64 + (ty - pos.y) as f64 * e;
                let _ = win.set_position(PhysicalPosition::new(nx as i32, ny as i32));
                thread::sleep(Duration::from_millis(14));
            }
            // Do not trigger again until the pointer rests somewhere new.
            idle_since = Instant::now();
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    const REST: Duration = Duration::from_millis(900);
    const LONG: Duration = Duration::from_secs(30);

    fn follow(enabled: bool, mode: Mode, visible: bool, idle: Duration, since: Duration, over: bool, dist: f64) -> bool {
        should_follow(enabled, mode, visible, idle, since, over, dist)
    }

    #[test]
    fn follows_only_a_resting_pointer_far_from_the_orb() {
        assert!(follow(true, Mode::Orb, true, REST, LONG, false, 400.0));
        assert!(!follow(true, Mode::Orb, true, Duration::from_millis(100), LONG, false, 400.0), "moving pointer is never chased");
        assert!(!follow(true, Mode::Orb, true, REST, LONG, false, 50.0), "already close enough");
    }

    #[test]
    fn never_interferes_with_the_user() {
        assert!(!follow(false, Mode::Orb, true, REST, LONG, false, 400.0), "opt-in");
        assert!(!follow(true, Mode::Panel, true, REST, LONG, false, 400.0), "never while the panel is open");
        assert!(!follow(true, Mode::Orb, false, REST, LONG, false, 400.0), "never while hidden");
        assert!(!follow(true, Mode::Orb, true, REST, LONG, true, 400.0), "pointer on the orb = user is interacting");
        assert!(!follow(true, Mode::Orb, true, REST, Duration::from_secs(2), false, 400.0), "backs off after a manual drag");
    }

    #[test]
    fn a_short_press_is_a_tap_and_a_long_one_is_hold_to_talk() {
        assert!(!is_hold(Duration::from_millis(0)));
        assert!(!is_hold(Duration::from_millis(249)));
        assert!(is_hold(Duration::from_millis(250)));
        assert!(is_hold(Duration::from_secs(3)));
    }

    #[test]
    fn modes_round_trip_and_have_distinct_sizes() {
        assert_eq!(Mode::parse("orb"), Some(Mode::Orb));
        assert_eq!(Mode::parse("panel"), Some(Mode::Panel));
        assert_eq!(Mode::parse("hud"), None);
        assert!(Mode::Orb.logical_size().0 < Mode::Panel.logical_size().0);
    }
}

/// Hides the Companion so it is not part of a screenshot. Returns whether it was visible (to restore it afterwards).
pub fn hide_for_capture(app: &AppHandle) -> bool {
    let Some(win) = window(app) else { return false };
    let was_visible = win.is_visible().unwrap_or(false);
    if was_visible {
        let _ = win.hide();
    }
    was_visible
}

/// Shows the Companion again exactly where it was (no re-placement), after a capture.
pub fn restore_after_capture(app: &AppHandle, was_visible: bool) {
    if !was_visible {
        return;
    }
    if let Some(win) = window(app) {
        let _ = win.show();
        let _ = win.set_focus();
    }
}
