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

Replaced: `AmbientCompanion.tsx` (2,180 lines, cyan HUD, fixed 420×580 window whose "orb" mode was only a CSS state; recoverable from Git history). Functional parity with it is tracked in §6.

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

## 6. Functional parity with the previous Companion (audit 2026-10-15)

Every feature of the old `AmbientCompanion.tsx` was checked against the backend routes (all still exist) and the new module.

| Previous feature | Now | How |
| :--- | :--- | :--- |
| Context capture (frontmost app, window title, clipboard) | **Recovered**, explicit | Eye button → `POST /personal/companion/context`; shown as a card; "Add to message" inserts it into the (editable) input; an unreadable result is reported, never invented. Limit: asked from the panel, the frontmost app is Aether itself (the card says so); the clipboard is real |
| Drag & drop of files into the workspace inbox | **Recovered** (+ attach button) | HTML5 drop on the panel and a file picker → `POST /personal/companion/drop`; chip with the real stored path; 10 MB cap checked before upload; the native drag-drop handler is disabled on the Companion window so the page receives the drop. Native Finder drop was **not** exercised by hand |
| Quick actions: notifications | **Recovered** | Bell / chip → quick-action `check_notifications` (real unread count and latest items) |
| Quick actions: refresh deliverables | **Recovered** as the Results list | from the overview (refreshed by polling, events and focus) |
| Missions, progress | **Recovered** (and fixed) | `active_works` listed with status, stage and progress (the old UI read a non-existent `current_step`); only running/in-progress missions make the status "Working on it"; pending ones are listed but are not work in progress |
| Results / deliverables | **Recovered** | collapsible list (title, source, size) with copy-path and open-in-Aether |
| Approvals | Kept and improved | uses the runtime's `human_summary`; decisions go through the canonical approval router |
| Shared session with the main Assistant | Kept, tested both directions | same `aether_active_session_id`; a conversation started in the main app continues in the Companion |
| Proposals awaiting confirmation | **New**, truthful | a reply carrying a proposal shows "A plan is waiting for your confirmation" + *Review in Aether*; accepting is **not** done here (the accept/clarify flow lives in the main app; a third copy would duplicate it) |
| Keyboard | Recovered | `Esc` collapse, `Cmd/Ctrl+O` open Aether, `Cmd/Ctrl+K` new conversation |
| Errors and Orb states | Kept | see §3 |

**Deliberately not recovered**
* The hard-coded success toast of the old "Take care of it" quick action ("autonomous loop completed, deliverable ready"): the runtime actually returns `blocked_pending_acceptance`, so the message was false.
* Text-to-speech read-aloud (voice phase M3a). Dictation is kept.

**Deferred (need more than a small change)**
* Inline proposal acceptance / clarification: extract one shared accept-and-run module used by the main Assistant, Home and the Companion.
* "Take care of it" and "Mesh audit" quick actions: the first depends on inline proposals, the second is a niche telemetry view.
* Capturing the *previous* frontmost app: needs a native capture at summon time, before the Companion takes focus (belongs with the screen-context phase).
* Unread-notification badge on the orb; file preview/download from the Results list (routes exist).
