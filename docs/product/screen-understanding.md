# Screen Understanding & Visual Assistance (Companion 2.0)

Status (2026-10-16): first vertical slice implemented and verified on macOS in the real Tauri window. Decision: ADR-018.

## What it does

The user presses the camera button in the Companion panel and chooses **Entire screen** (main display) or **Select an area**
(the system's own selection UI). A preview shows exactly what would be sent. The user may draw boxes, highlights and
arrows on it, write a question (default: "What am I looking at?") and optionally ask Aether to point at the relevant
elements. Only **Send** transmits anything. The answer is a normal message in the shared session (same session key as the
main Assistant, same history).

## Principles

* **Explicit, never ambient.** One capture per button press. No timer, no background or start-up capture. Nothing is sent before Send.
* **No silent substitution.** Capture is blocked (and the reason shown) when no provider is configured, the provider is unusable, no model is selected, or the *model* has no vision. Nothing is captured or sent in those cases. No other provider or model is tried.
* **Never stored.** The image lives in the webview's memory and in one request. The native side writes it to a private 0700 temp dir and deletes it right after reading. History keeps only the question, the answer and the capture's size/type. Annotated images shown in the conversation are in-memory and disappear with the window.
* **No tools on the vision call.** The model receives no tools, and its system prompt says that text inside the screenshot is content, not instructions. What is on screen therefore cannot trigger an action.
* **Permissions are respected, never bypassed.** macOS Screen Recording is checked first (`CGPreflightScreenCaptureAccess`); without it nothing is captured and the UI explains the path: System Settings → Privacy & Security → Screen & System Audio Recording → enable Aether → quit and reopen Aether. The system prompt is requested (`CGRequestScreenCaptureAccess`) only when the user clicks a capture button or "Request permission".

## Modules

| Concern | Where |
|---|---|
| Native capture, permission, temp-file lifecycle, hide/restore of the Companion | `src-tauri/src/screen_capture.rs` (+ `hide_for_capture` / `restore_after_capture` in `companion.rs`) |
| UI bridge (no-op outside Tauri) | `ui/src/companion/vision/captureBridge.ts` |
| Flow (choose → capture → review → send) | `ui/src/companion/vision/ScreenAssist.tsx` |
| Annotation geometry, drawing, flattening | `ui/src/companion/vision/annotations.ts`, `AnnotatedImage.tsx` |
| Runtime hook (status, request, shared session) | `ui/src/companion/useCompanionRuntime.ts` (`fetchVisionStatus`, `askAboutImage`) |
| Image validation (magic bytes, size, dimensions) | `src/aether/vision/image.py` |
| Per-model vision capability | `src/aether/vision/capability.py` + `ProviderCapabilities.vision` on each provider |
| Analysis through the shared runtime/session | `src/aether/vision/service.py`, routes `GET /api/personal/companion/vision/status`, `POST /api/personal/companion/vision` |
| Annotation validation and screen mapping | `src/aether/vision/annotations.py` |
| Image encoding per provider | `Message.images` (never serialized by `to_dict`); OpenAI/Groq `image_url` data URI, Anthropic `image` block, Gemini inline part, Ollama `images` |

## Which models can see

`model_supports_vision(provider, model)` is a conservative allow-list by model name (OpenAI GPT-4o/4.1/5/o-series, every current Claude model, Gemini 1.5+, Groq Llama 4 Scout/Maverick and `*vision*`, Ollama llava/llama3.2-vision/qwen-VL/gemma3 and similar). An unknown model is treated as text-only. The list is a heuristic, not a probe: a provider may still reject an image, and that error is shown as is (timeout, credentials, rate limit, connection, unknown model, empty answer, other).

## Annotations

All coordinates are normalized to the captured image (0–1, origin top-left). Two sources:

1. **Manual** (reliable): the user draws boxes/highlights/arrows on the preview; they are drawn into the pixels that are sent, so "explain this element" works by circling it. The editing surface is exactly the image (no letterboxing), so marks land where drawn.
2. **Model-suggested** (approximate): when asked, the model returns `{answer, annotations:[{kind: box|point, x, y, w, h, label}]}`. The backend validates every entry (finite numbers, inside the image, minimum size, not covering almost everything, at most 8, sanitized labels) and **drops** invalid ones instead of clamping them into plausible spots; the UI re-checks defensively, reports how many were discarded and labels the result "positions are approximate". Marks are drawn on the captured image in the conversation, not on the live screen.

`to_screen_rect` (Python and TypeScript, tested) maps a validated annotation to desktop coordinates given the capture's screen rectangle. It is the bridge for a future live overlay and is **not used for drawing on the screen yet**: the screen may have changed since the capture, so a live overlay needs its own staleness check.

## Verified

* Backend: image validation, capability table, annotation validation, provider encoding, the route through the shared runtime/session (no provider, text-only model, failures, empty answer, redaction of secrets, nothing stored): `tests/test_vision_screen_understanding.py`.
* UI (real browser, native layer stubbed at the Tauri IPC boundary): permission denied/unsupported, cancelled/failed/oversized capture, no provider (real runtime), text-only model, analysis errors, drawing, validated model marks, Esc, IT/EN: `tests/test_companion_vision_ui.py`.
* Rust: base64, PNG size parsing, result shape.
* Real `Aether.app` on macOS (isolated HOME, a local stand-in for an Ollama server speaking the real wire protocol): full-screen capture, system area selection, Esc cancellation, drawing with the real mouse, the received image really was the 1568×1018 capture with the user's mark pixels in it, the validated mark drawn and the invalid one rejected with a notice, no image left on disk. The same build launched through `open` (no Screen Recording grant) shows the permission guidance and captures nothing.

## Not done / limits

* No test with a real cloud vision model (no provider key was used); the wire formats for OpenAI, Anthropic and Gemini are unit-tested at the message-building level only (OpenAI/Anthropic SDKs and the Gemini types are not installed in the test environment). Groq/Ollama encoding is covered the same way.
* Windows and Linux: the command contract exists, the capability reports `unsupported`. The Windows capture implementation is future work.
* Region capture has no known desktop rectangle (the system selection UI does not report it), so only full-screen captures carry geometry. Only the main display is captured.
* No live on-screen overlay, no continuous watching, no OCR or accessibility-tree reading, no clicking/typing. Mouse and keyboard control is deliberately absent; it must go through `ExecutionAuthority`/approvals (M4) with its own review, and will reuse `to_screen_rect` plus a staleness check.
* "Open System Settings" and the system permission prompt were verified only at the UI/stub level; granting the permission is a manual step.
