//! Signed in-app updates (Tauri updater plugin).
//!
//! The update manifest and artifacts are verified with the minisign public key embedded in
//! `tauri.conf.json` (`plugins.updater.pubkey`); the private key never ships with the app.
//! Only the commands below are exposed to the UI. The plugin's own JS commands are not
//! reachable because no capability grants them.
//!
//! Failure policy: a check or download problem never stops the running app. The sidecar is only
//! stopped after the package has been downloaded *and* its signature verified; if the install step
//! then fails, the app relaunches itself from the (restored) bundle so the user is never left
//! with a window and no runtime.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use serde::Serialize;
use tauri::{AppHandle, State};
use tauri_plugin_updater::UpdaterExt;

use crate::{graceful_shutdown, RuntimeState};

static UPDATE_IN_PROGRESS: AtomicBool = AtomicBool::new(false);

#[derive(Serialize, Clone, Debug)]
pub struct UpdateInfo {
    pub available: bool,
    pub current_version: String,
    pub version: Option<String>,
    pub notes: Option<String>,
    pub date: Option<String>,
}

#[derive(Serialize, Clone, Debug, PartialEq, Eq)]
pub struct UpdateError {
    /// Stable machine-readable category the UI translates: not_configured | network | signature | busy | install.
    pub code: &'static str,
    pub detail: String,
}

pub fn classify(err: &tauri_plugin_updater::Error) -> UpdateError {
    use tauri_plugin_updater::Error as E;
    let code = match err {
        E::EmptyEndpoints => "not_configured",
        E::Minisign(_)
        | E::Base64(_)
        | E::SignatureUtf8(_)
        | E::SignedVersionMismatch { .. }
        | E::MissingSignedVersion => "signature",
        E::Reqwest(_) | E::Network(_) | E::ReleaseNotFound | E::TargetNotFound(_) | E::TargetsNotFound(_) | E::UrlParse(_) => "network",
        _ => "install",
    };
    UpdateError { code, detail: err.to_string() }
}

async fn check_inner(app: &AppHandle) -> Result<(Option<tauri_plugin_updater::Update>, UpdateInfo), UpdateError> {
    let current = app.package_info().version.to_string();
    let updater = app.updater().map_err(|e| classify(&e))?;
    match updater.check().await.map_err(|e| classify(&e))? {
        Some(update) => {
            let info = UpdateInfo {
                available: true,
                current_version: current,
                version: Some(update.version.clone()),
                notes: update.body.clone(),
                date: update.date.map(|d| d.to_string()),
            };
            Ok((Some(update), info))
        }
        None => Ok((
            None,
            UpdateInfo { available: false, current_version: current, version: None, notes: None, date: None },
        )),
    }
}

/// Checks the configured channel. Never changes anything on disk.
#[tauri::command]
pub async fn check_for_update(app: AppHandle) -> Result<UpdateInfo, UpdateError> {
    check_inner(&app).await.map(|(_, info)| info)
}

/// Downloads, verifies, installs and relaunches. Requires an explicit call from the user (or the e2e hook).
#[tauri::command]
pub async fn install_update(app: AppHandle, state: State<'_, RuntimeState>) -> Result<(), UpdateError> {
    apply_update(&app, state.port, &state.token, &state.child).await
}

pub async fn apply_update(
    app: &AppHandle,
    port: u16,
    token: &str,
    child: &Arc<std::sync::Mutex<Option<std::process::Child>>>,
) -> Result<(), UpdateError> {
    if UPDATE_IN_PROGRESS.swap(true, Ordering::SeqCst) {
        return Err(UpdateError { code: "busy", detail: "An update is already in progress.".into() });
    }
    let result = apply_update_inner(app, port, token, child).await;
    UPDATE_IN_PROGRESS.store(false, Ordering::SeqCst);
    result
}

async fn apply_update_inner(
    app: &AppHandle,
    port: u16,
    token: &str,
    child: &Arc<std::sync::Mutex<Option<std::process::Child>>>,
) -> Result<(), UpdateError> {
    let (update, _) = check_inner(app).await?;
    let Some(update) = update else {
        return Ok(()); // nothing newer: not an error
    };
    println!("[Aether Updater] Downloading version {}...", update.version);
    // download() verifies the minisign signature before returning the bytes.
    let bytes = update.download(|_, _| {}, || {}).await.map_err(|e| classify(&e))?;
    println!("[Aether Updater] Package downloaded and signature verified.");

    // Only now is the running runtime stopped: nothing before this point could have failed destructively.
    graceful_shutdown(port, token, child);
    match update.install(bytes) {
        Ok(()) => {
            println!("[Aether Updater] Installed version {}; relaunching.", update.version);
            app.restart();
        }
        Err(e) => {
            eprintln!("[Aether Updater] Install failed ({}); relaunching the current version.", e);
            // The updater restores the previous bundle on failure; relaunch so the user gets a working app again.
            app.restart();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tauri_plugin_updater::Error as E;

    #[test]
    fn errors_are_classified_for_the_ui() {
        assert_eq!(classify(&E::EmptyEndpoints).code, "not_configured");
        assert_eq!(classify(&E::MissingSignedVersion).code, "signature");
        assert_eq!(classify(&E::Network("down".into())).code, "network");
        assert_eq!(classify(&E::ReleaseNotFound).code, "network");
        assert_eq!(classify(&E::BinaryNotFoundInArchive).code, "install");
    }
}
