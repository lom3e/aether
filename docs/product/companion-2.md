# Aether Companion 2.0 — first vertical slice

**Status (2026-10-15):** first usable slice implemented and verified on macOS. It is a *surface* of Aether Core: conversation, memory, missions, tools and approvals all come from the existing runtime. Nothing here controls the mouse or keyboard, reads the screen or speaks.

## 1. What exists

| Area | Implementation |
| :--- | :--- |
| Compact companion | A dedicated native, transparent, frameless, always-on-top window (88×88) showing the real Aether particle orb, in a **compact** layout of the orb engine (`orb/OrbEngine.ts` option `compact`). Draggable; click or Enter opens the panel |
| Expanded panel | 408×604 conversation panel: messages (Markdown), loading indicator, approvals, running missions with progress, errors with a way out, optional dictation |
| Summon / dismiss | Existing global shortcut (`Option+Space`, `Alt+Space` on Windows, fallback `Cmd/Ctrl+Shift+Space`; no conflicts found at registration): hidden → panel next to the pointer; panel ↔ orb afterwards. `Esc` collapses to the orb; header buttons: follow toggle, new conversation, open Aether, collapse, hide |
| Real statuses | Ready · Listening · Working on it · Needs your approval · Something went wrong · Done. Each is derived from facts the runtime/browser reported (`companion/status.ts`); see §3 |
| Conversation | `POST /api/personal/chat` with the UI language, same workspace and **same session as the main Assistant** (`aether_active_session_id`, restored from `/api/personal/sessions/{id}`) |
| Approvals / missions | From `/api/personal/overview` (+ SSE events + polling); decisions go through the canonical approval router (`submitApprovalDecision`). Shown only when the runtime reports them |
| Pointer behaviour | Summon next to the **real global pointer**; optional *come to the cursor* mode (off by default, §4) |

Replaced: `AmbientCompanion.tsx` (2,180 lines, cyan HUD, fixed 420×580 window whose "orb" mode was only a CSS state). Not carried over in this slice: context capture, file drop and quick actions (their backend routes remain), text-to-speech. They return in later slices on top of the structure below.

## 2. Code layout (extension points)

```
src-tauri/src/companion.rs        native window: modes, anchoring, clamping, drag, pointer placement, follow loop
ui/src/companion/
  status.ts                       CompanionStatus + deriveCompanionStatus(facts)   <- add statuses here
  windowControl.ts                the only bridge to native window commands (no-op outside Tauri)
  useCompanionRuntime.ts          the only place that talks to Aether Core (chat, overview, approvals, session)
  CompanionApp.tsx                surface shell: mode (orb|panel), follow preference
  CompanionOrb.tsx / CompanionPanel.tsx / useDictation.ts / companion.css
```

Next slices plug in without touching the runtime contract:
* **Visual indicators / annotations:** a second, separate transparent, click-through window (`set_ignore_cursor_events(true)`) owned by `companion.rs`; the panel only sends it shapes. The orb/panel window is never made click-through.
* **Context understanding:** a `useCompanionContext` hook beside `useCompanionRuntime` calling the existing `/api/personal/companion/context` route; screen content needs Screen Recording permission, to be requested explicitly with a settings shortcut and a graceful "not granted" state.
* **Authorized actions:** unchanged path — the runtime proposes, `ExecutionAuthority` and the approval router decide, the Companion only presents and reports the real outcome.
* **Voice output:** a separate module reading already generated replies (roadmap M3a); the `listening` status already exists for input.

## 3. Truthfulness rules implemented

* *Listening* is shown only after the speech engine fires `onstart`, and cleared on `onend`/`onerror`. If no engine exists, no microphone is offered.
* *Working on it* means a request is in flight or the runtime lists running tasks. *Needs your approval* means the runtime lists pending approvals. *Done* is a 4-second pulse after a successful reply or after a task disappears from the running list.
* A reply flagged by the runtime with an error code (e.g. `NO_PROVIDER`) is an **error**, not a success; the panel offers "Open Aether".
* If the workspace or runtime is unreachable the Companion says so, and **recovers by itself** when it comes back (found and fixed during native verification).

## 4. Pointer interaction: what is available and what was chosen

* Tauri's `cursor_position()` reads the **real global pointer** (macOS `NSEvent.mouseLocation`, Windows `GetCursorPos`). It needs **no Accessibility permission**. Page-level `mousemove` events are never used for this.
* Implemented: (1) *summon near the pointer*, clamped to the monitor under it; (2) optional *come to the cursor*: only when the pointer has rested ≥ 550 ms, is ≥ 160 px away and is not over the orb, only while the orb (not the panel) is visible, and not within 6 s of the user dragging the orb; it glides 44 px right/below the pointer. It **never chases a moving pointer**. Pure decision logic is unit-tested (`companion::tests`).
* Not implemented, by design: continuous tracking (distracting and click-interfering), click-through orb, reading what is under the pointer, controlling input. Those need Accessibility / Screen Recording and a separate risk review (roadmap M7).

## 5. Platform notes and limits

* A transparent window on macOS needs Tauri's `macos-private-api` feature (`app.macOSPrivateApi: true`): acceptable for direct distribution and notarization, **not** for the Mac App Store. Decision recorded as ADR-017.
* `accept_first_mouse(true)` keeps the first click on the floating orb from being swallowed when another app is active.
* Verified on macOS only (real Tauri window). Windows: compile and installed-app smoke run on the CI runner; the Companion's window behaviour on Windows (transparency, global shortcut, follow) has not been exercised by hand.
* Follow-cursor with multiple monitors / mixed DPI is implemented via `monitor_from_point` but was only verified on a single display.
* The first expanded panel is fixed-size (no user resizing) and dark regardless of the app theme.
