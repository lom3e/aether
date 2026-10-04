# Aether Production Stabilization Plan — Canonical Source of Truth

**Audience:** Aether Core Engineers & Autonomous Implementation Agents  
**Baseline Commit:** `f181080960d3fa7e40f1241d9757a8d335cf1bfd`  
**Status:** Active Execution Plan  
**Branch:** `development`  

---

## 1. Baseline & Mandate

### Baseline
- **HEAD:** `f181080960d3fa7e40f1241d9757a8d335cf1bfd`
- The latest change restored `ActionExecutionStatus` to standard Python `StrEnum` semantics.
- **Rule:** Under no circumstances reintroduce custom `__eq__`, custom `__hash__`, string-comparison hacks, or wrapper/subclass compatibility tricks.

### Production-Readiness Mandate
Treat Aether as if it were being released to real users tomorrow.
> **Absolute Standard:** If a user installs Aether, configures real providers/connectors, and starts using the exposed product normally, the exposed functionality must actually work.

- No demo behavior.
- No simulated behavior presented as real.
- No fake success states (`COMPLETED`, `CONNECTED`, `SYNCED`, `PUBLISHED`, `VERIFIED`).
- No fake integrations.
- No placeholder deliverables.
- No fake telemetry.
- No invented agent or specialist results.
- If a capability cannot genuinely work yet, it must be marked `UNSUPPORTED` or `UNAVAILABLE`. Pretending it works is strictly forbidden.

### No Test Hacking Mandate
- Forbidden: `xfail`, skipping to hide failures, weakening assertions, deleting failing tests, fake authority in positive-path tests, `test_mode`, `force_execute`, `skip_validation`, bypass flags, mocks that bypass the real final execution sink, compatibility hacks that change production semantics.
- Positive mutation flow:
  `Intent → Proposal → Acceptance → Authority → Persistent validation → Scope validation → Real execution`

---

## 2. Confirmed Production Problems (Source Audit)

Severity Scale:
- **P0:** Fabricated results or states, or a security vulnerability reachable in default configuration.
- **P1:** Broken or unsafe flow in normal use.
- **P2:** Truthfulness or code hygiene issue.

### A1 — "Autonomous goal" ("take care of it") is mostly scripted theatre — P0
- **File:** `src/aether/autonomy/engine.py` L191–L310 (stages 2, 4, 6), L312–L330 (stage 7, `_create_deliverable` at L466), L349+ (stage 9).
- **Path:** User triggers "Aether, take care of it" / "Prenditene cura tu". `personal/service.py::classify_intent` returns `autonomy.take_care_of_it`, and `AutonomousGoalOrchestrator` runs.
- **Problem:**
  - Stage 2 (PLAN) stores a hardcoded `plan_nodes` list and marks itself completed.
  - Stage 4 (WORKFORCE_DISPATCH) hardcodes `assigned_agents = ["Systems Lead","Domain Specialist","Reviewer"]` and dispatches nothing.
  - Stage 6 (SAFETY_VERIFICATION) hardcodes `policy_check: "passed"` and `quality_score: 100` without evaluating anything.
  - The only real work is stage 5, which defaults to the read-only `fabric.get_telemetry`.
  - Stage 7 then creates a "deliverable", stage 8 sends "Autonomous Goal Complete", and stage 9 writes a memory with `verification_status="verified"`. All based on hardcoded stages.
- **Fix:** Replace stages 2, 4, and 6 with real work:
  - PLAN: call real planner (`planning/generator.py`).
  - DISPATCH: run a mission or team through `missions/runtime.py` or `workspace.runtime`.
  - VERIFY: use real reviewer (`missions/reviewer.py`) and policy service.
  - Mark a stage `completed` only when its real result exists. Failure must mark the goal `FAILED`.
  - If the real pipeline cannot be wired without inventing behavior, disable that capability rather than simulating it.

### A2 — Fake offline AI specialists when no provider is configured — P0
- **File:** `src/aether/core/runtime.py` L478–L546. Classes `GenericOfflineSpecialist` and `GenericOfflineCoordinator`, fake models `aether-specialist` and `aether-lead`.
- **Path:** First launch with no provider, then the user asks for a delegated or workforce task.
- **Problem:** The runtime fabricates "Specialist findings … Completed structured investigation" and an "Executive Strategic Synthesis", returning them as a successful result.
- **Fix:** Delete the classes. When `resolve_provider()` returns `None`, return `ExecutionResult(success=False, status=ActionExecutionStatus.FAILED, error="No AI provider configured. Open Settings → Provider.", metadata={"code":"NO_PROVIDER"})`.

### A3 — Provider failure converted into a COMPLETED answer — P0
- **File:** `src/aether/core/runtime.py` L189–L216, with `_synthesize_contextual_response` at L776.
- **Problem:** A provider exception is only logged at WARNING, then the result is `success=True, status=COMPLETED` carrying canned "contextual synthesis" text. The same happens when no provider is configured. The status says COMPLETED despite failure.
- **Fix:**
  - On exception, return FAILED with a sanitized provider error.
  - On no provider, return FAILED `NO_PROVIDER`.
  - Keep `_synthesize_contextual_response` only as an explicitly labeled memory lookup (`metadata.source="memory_only"`, with a visible banner in the UI) or remove it.

### A4 — `web.search` action returns invented results — P0
- **File:** `src/aether/actions/executor.py` L619–L630.
- **Problem:** Returns `title: "Workspace query: {query}"` and `snippet: "Real search result query executed…"` without any network call. The status is SUCCEEDED. The real backend exists in `tools/web_search.py` (`DuckDuckGoSearchBackend`) and is not used here.
- **Fix:** Call the real backend, return its results, and raise on failure or empty backend response.

### A5 — Automation actions return success when workspace cannot be resolved — P0
- **File:** `src/aether/actions/executor.py` L632–L667 (`automations.create_draft`, `automations.activate`). The same `Workspace.get(...)` followed by `except Exception: pass` pattern appears at L560+, L669+, L704+, and L740+.
- **Problem:** If `ws` is `None`, `create_draft` returns `{"status":"draft", automation_id: …}` and `activate` returns `{"status":"active","enabled":True}`. Nothing is persisted, but execution is recorded SUCCEEDED.
- **Fix:** Use `self.workspace` (injected at `workspace/workspace.py` L363). Remove the `Workspace.get` fallbacks. Raise `RuntimeError("Workspace unavailable")` when missing.

### A6 — Slack / Email / HTTP "sync" reports synced items with no I/O — P0
- **File:** `src/aether/connections/sync.py` L499–L562. Dispatch at L74–L100. UI toast at `ui/src/Connections.tsx` L738/L758.
- **Path:** Connections → Sync, `connections.sync` action, `/api/connections/{id}/sync`.
- **Problem:** If stored connection status is CONNECTED, they return `status="synced", items_synced=1` after only bumping `last_synced_at`. The UI toast says "Synced N items into workspace memory and knowledge!".
- **Related capability gaps:**
  - Slack connector only has `send_message` and `verify`.
  - Email connector only does SMTP.
  - Notion and Telegram have no sync branch (fall through to "skipped").
  - `Connections.tsx` L189–L194 advertises "read and synchronize workspace pages" for Notion.
- **Fix:**
  - Delete the three stubs.
  - Return `status="unsupported"` (`items_synced=0`) for providers without a real read path.
  - Implement real reads where feasible, or hide Sync for those providers in the UI.
  - UI toast must reflect `data.status`.
  - Correct capability text.

### A7 — Document creation falls back to placeholder content — P0
- **File:** `src/aether/core/runtime.py` L233–L262, with failure swallowed at L260 (`logger.debug`).
- **Problem:** If the provider is missing or draft fails, the action runs with empty or `# Document created by Aether…` content. The file is written and reported "created".
- **Fix:** If content is empty or placeholder and generation fails, return `ExecutionResult(FAILED, error="Could not draft content: …")`. Never write placeholder deliverables.

### A8 — "Publish" content only flips a DB flag; engagement scores are constants — P0
- **File:** `src/aether/server/routes.py` L5427–L5441 (`publish_variant_route`). `src/aether/content/repurposer.py` L318/L373/L418 (fixed 85/88/82). `src/aether/content/models.py` L53 (default 75.0). `ui/src/ContentRepurposing.tsx` L287–L297. `content.schedule_variant` at `actions/executor.py` L1401.
- **Problem:** Route sets `ContentStatus.PUBLISHED` and `published_at` with no platform call. There is no publishing connector, yet UI shows variant as published. `analytics.get_campaign_bi` is built on these heuristic scores.
- **Fix:**
  - Remove "Publish" (route, UI button, status transition) or rename state to `approved_for_manual_publish`.
  - Only mark `published` after a real connector call returns a post ID.
  - Label scores "heuristic estimate" in API and UI.

### A9 — Provider API keys stored in plaintext `.env`; process-global env mutation — P0
- **File:** `src/aether/server/routes.py` L745–L761 (workspace create), L928–L941 (`/settings/provider`), L982–L1004 (`/settings/provider/test` mutates `os.environ`). Resolution reads env vars only at `providers/resolution.py` L72–L83 and `providers/openai_provider.py` L57.
- **Problem:**
  - Keys written to `<workspace>/.env` with default permissions and no encryption. `core/secrets.py` (AES-GCM + Keychain) exists but is unused for provider keys.
  - Keys apply process-wide via `os.environ`, crossing workspaces.
  - Test endpoint temporarily overwrites global env. Concurrent requests race, and crashes leave wrong keys.
- **Fix:**
  - Store provider keys via `core/secrets.get_secret_store()` and keep only a `secret_ref` in workspace config.
  - Resolve key per workspace in `providers/resolution.py` and pass via `ProviderConfig(api_key=…)`.
  - Test endpoint must pass key via `ProviderConfig`, never touching `os.environ`.
  - Add migration that moves existing `.env` keys into SecretStore and deletes them from `.env`.
  - If a `.env` is written, enforce `chmod 0600`.

### A10 — Local file actions are unsandboxed (path traversal / arbitrary read) — P0
- **File:** `src/aether/actions/executor.py` L588–L617. `files.read_document` is READ_ONLY (no authority needed) and exposed through personal agent ANSWER path (`personal/service.py` ~L1868) and `/api/actions/execute`. Sandbox exists at `core/security.py` L81 (`PathSandbox`) and is used by `tools/filesystem.py`.
- **Problem:** `base_dir / filename` with absolute or `../` filename escapes project. Example: `filename="/Users/x/.ssh/id_rsa"` is read and returned. `create_document` can overwrite arbitrary files.
- **Fix:** Route both through `PathSandbox.validate_path(...)` with operation types READ/WRITE. Reject sensitive paths (`sandbox.is_sensitive`). Reject absolute paths and `..`. Return error on denial.

### A11 — External-agent `command` execution is auto-approved at default autopilot tier — P0
- **File:**
  - `src/aether/actions/registry.py` L567–L570: `agents.delegate_external` has `EXTERNAL_MUTATION` and `requires_confirmation=False`.
  - `src/aether/policy/service.py` L99–L108: Tier 2 (default) auto-approves `EXTERNAL_MUTATION` unless `requires_confirmation` is true.
  - `src/aether/actions/executor.py` L740–L809: `command`, `endpoint_url`, `auth_token` come straight from `input_data`.
  - `src/aether/agents/external.py` L372–L380: `shell=isinstance(cmd, str)`, running strings through shell.
  - `src/aether/tools/mcp.py` L76 and `src/aether/server/routes.py` L7857–L7900: `command` comes from request payload.
  - `src/aether/actions/registry.py` L607: `telegram.send_message` also has `requires_confirmation=False`.
- **Problem:** An accepted proposal + LLM-chosen `command` runs arbitrary local processes with no human prompt.
- **Fix:**
  - Set `requires_confirmation=True` for `agents.delegate_external` and `telegram.send_message`.
  - Never accept `command`, `endpoint_url`, or `auth_token` from action input. Resolve only pre-registered external agents from team config (`ws.team._agents` of type `ExternalAgentAdapter`).
  - Remove `shell=True`. Require list commands (`shlex.split` at registration time).
  - For `/api/tools/mcp/call`, accept only server IDs registered in workspace config.

### A12 — Authority checks bind to action name only; empty scope is unrestricted — P1
- **File:** `src/aether/core/execution.py` L326–L450 (`ExecutionBoundary.validate_authority`).
- **Problem:**
  - An accepted proposal with no `allow:`/`scope:` constraint authorizes any action.
  - Arguments are not bound: proposal approved for `email.send` authorizes any recipient and body.
  - Authority is reusable: repeated executions possible without use counter.
  - Malformed `expires_at` is silently ignored (L442–L450). `ExecutionAuthority.expires_at` is not checked here.
- **Fix:**
  - Derive allowed actions from proposal's own steps when no explicit scope exists.
  - Store an `args_digest` per authorized step and compare at execute time.
  - Record executed step IDs on proposal and reject duplicates (idempotency key).
  - Fail closed on unparseable `expires_at`, and honor `authority.expires_at`.

### A13 — Proactive "accept" marks APPLIED even when action failed — P1
- **File:** `src/aether/server/routes.py` L5733–L5760.
- **Problem:** Calls `ws.actions.execute(..., auto_approve=True)` with no authority. Mutating actions raise `UnauthorizedExecutionError`, caught into `executed_action={"error":…}`. Suggestion is marked `SuggestionStatus.APPLIED` regardless.
- **Fix:**
  - For mutating actions, create proposal or approval record instead of direct execution.
  - Only set APPLIED when `execution.status == SUCCEEDED`.
  - Otherwise return 4xx/5xx or set `failed` / `pending_approval`.

### A14 — Failures rendered as success to user — P1
- **File:**
  - `src/aether/personal/service.py` L1851–L1895: `calendar.list_events` and `files.read_document` execute without checking `execution.status`.
  - `src/aether/connections/telegram_bridge.py` L50–L57: After approval, edits message to "✅ Azione Approvata ed Eseguita con Successo" even on FAILED.
  - `src/aether/missions/runtime.py` ~L1033: `out_text = result.output or "Stage … completed successfully."`.
  - `src/aether/agents/agent.py` L316: `"Plan completed successfully."`.
- **Fix:** Check `execution.status`. On FAILED, set step to `failed` and show `execution.error_message`. In Telegram bridge, branch on `res.status`. Replace invented completion text with `"(no output produced)"` or warn/empty state.

### A15 — Authentication / OAuth / Webhook paths — P0/P1
- **File:** `src/aether/server/app.py` L57–L90, `server/sockets.py` L47–L58, `cli/main.py` L270–L330, `connections/google_calendar.py` L96–L145, `server/routes.py` L7085–L7150, `src-tauri/tauri.conf.json`.
- **Problems:**
  1. Optional auth: `aether serve` without `--token` leaves `/api/*` wide open.
  2. OAuth and webhook breakage: middleware exempts only `/api/health`. Google OAuth callback and Telegram webhook get 401 when token is set.
  3. Telegram webhook lacks `X-Telegram-Bot-Api-Secret-Token` verification.
  4. Non-constant-time token compares; query tokens logged.
  5. Hardcoded redirect URI port 8000; wildcard `window.opener.postMessage('*')`.
- **Fix:**
  - `serve` generates random token by default and prints it; `--insecure-no-auth` required for opt-out.
  - Exemption set: OAuth callback (PKCE state protected) and Telegram webhook (secret verified).
  - Use `hmac.compare_digest` everywhere.
  - Tighten CORS and CSP.
  - Pin redirect URI from bound port and use app origin for `postMessage`.

### A16 — HTTP connector credential exfiltration; no SSRF protection — P1
- **File:** `src/aether/connections/http.py` L236–L282, `connections/openapi.py`, `server/routes.py` L542+, `tools/web_search.py`.
- **Problem:**
  - Absolute `url` overrides `base_url` while stored auth header is still attached.
  - No blocking on loopback, link-local (169.254.169.254), or RFC1918 private IPs.
- **Fix:** Require same host when `base_url` is set. Add `core/security.py::assert_public_http_url(url)` with DNS resolution checking private/loopback/link-local ranges.

### A17 — `mock` provider reachable as production provider — P1
- **File:** `src/aether/server/routes.py` L79, `providers/manager.py` L95–L97, `providers/health.py` L136–L143, `ui/src/Teams.tsx`, `ui/src/AutoArchitectModal.tsx`, `team/team.py`.
- **Problem:** UI offers "Mock", API accepts it, health reports ready.
- **Fix:** Gate on `AETHER_ENABLE_TEST_PROVIDERS=1`. Remove `mock` from `_VALID_PROVIDERS` unless set.

### A18 — Test-only code in production runtime — P2
- **File:** `src/aether/missions/runtime.py` L55–L66 (`_has_usable_runtime` imports `unittest.mock`).
- **Fix:** `return workspace.runtime is not None`. Update tests to inject real stub runtime.

### A19 — Fabric remote nodes: invented hardware, no dispatch — P1
- **File:** `src/aether/fabric/engine.py` L181–L228, `server/routes.py` L7948–L8040, `ui/src/ExecutionFabricView.tsx`.
- **Problem:** Default specs ("Remote Compute Unit", 32 GB RAM, 16 GB VRAM) are fabricated. No remote HTTP call exists; assignments are purely recorded.
- **Fix:** Require real capabilities probe or set `capabilities=None` and `status="unverified"`. Label assignments advisory until remote dispatch exists.

### A20 — Workspace registry collisions — P1
- **File:** `src/aether/workspace/workspace.py` L65, L91–L94, L823–L826 (`_active_workspaces` keyed by root, name, and id).
- **Problem:** Two workspaces with same name in different roots overwrite each other's name key.
- **Fix:** Key registry by unique `id` and root path only. Executors use injected `self.workspace`.

### A21 — Provider/connector health & misc truthfulness — P2
- `actions/executor.py` L452–L463: HTTP connector doesn't check `res.success`.
- Frontend silent `catch {}` hides backend failures (`Missions.tsx`, `Knowledge.tsx`, `AgentBuilder.tsx`, `AutoArchitectModal.tsx`, `ContentRepurposing.tsx`).
- Stray artifacts in repo root (`patch_generate.py`, `patch_tests.py`, `test_ollama_*.py`, `scratch/`, `sqlite:/`).

### A22 — Scale / readiness blockers (current architecture) — P1
- Single workspace per process documented and enforced.
- Blocking I/O in async routes offloaded via `asyncio.to_thread`.
- Provider failure isolation with timeouts/resilience.
- In-memory OAuth state documented for desktop usage.
- SQLite hygiene: unify through `core/sqlite.py` with WAL and `busy_timeout`.

---

## 3. Unverified / Environment-Dependent Status

| Item | Status & Verification Path |
|---|---|
| Native streamed delegation test (`tests/test_agent_delegation_execution.py`) | **Ollama is now ONLINE** on local machine (`http://localhost:11434/api/tags` confirmed active). Verified during MP6. |
| TestClient dependencies | `.venv` has `fastapi`, `pytest`, `httpx` installed and available. |
| Google OAuth callback under token middleware | Unit + integration test in MP2 with PKCE exemption. |
| Real GitHub, Notion, Slack, SMTP, Telegram I/O | Live smoke tests run when environment credentials provided; otherwise mocked at network boundary. |
| Token refresh concurrency | Lock added in `refresh_access_token` and verified under threaded stress. |
| Automation retry backoff | Event loop non-blocking behavior verified. |
| Mission crash recovery | Crash-injection tests in MP5. |

---

## 4. Macro-Pass Implementation Plan

### MP1 — Remove Fabricated Behavior (A1–A8, A18, A19, A21-http)
1. `core/runtime.py`: Remove `GenericOfflineSpecialist` and `GenericOfflineCoordinator`. When no provider, return FAILED `NO_PROVIDER`. Provider exceptions return FAILED with sanitized error. Fail DO path if draft fails.
2. `autonomy/engine.py`: Wire real planner, mission dispatch, reviewer, and policy. If real execution fails, goal fails. No fake score of 100 or fabricated verified memory.
3. `actions/executor.py`: Call real `DuckDuckGoSearchBackend` for `web.search`. Use `self.workspace` directly. Check `res.success` for HTTP connector.
4. `connections/sync.py`: Remove fake synced stubs for Slack/Email/HTTP; return `status="unsupported"`.
5. `server/routes.py` & `content/*`: Remove fake publish; label engagement scores as heuristic estimates.
6. `fabric/engine.py`: Remove fabricated hardware specs; mark unprobed nodes `unverified`.
7. `missions/runtime.py` & `agents/agent.py`: Remove `unittest.mock` production import; replace invented completion text.
8. UI updates: Connection toasts reflect actual status; publish button hidden or labeled manual.

### MP2 — Security & Authentication (A9, A10, A15, A16, A17)
1. Default API auth: Generate random token on launch; require `--insecure-no-auth` to disable. Exempt OAuth callback and verified Telegram webhook.
2. Constant-time token comparisons (`hmac.compare_digest`). Redact token in logs.
3. Provider secrets: Store in `core/secrets.SecretStore`; inject per-workspace into `ProviderConfig`. Never mutate `os.environ`. Migrate legacy `.env` keys.
4. Filesystem sandbox: Route `files.read_document` and `files.create_document` through `PathSandbox.validate_path`. Reject path traversal and sensitive files.
5. SSRF protection: Add `core/security.py::assert_public_http_url` and enforce across HTTP connector, web search, and URL ingestion.
6. Mock provider: Gate on `AETHER_ENABLE_TEST_PROVIDERS=1`.

### MP3 — Execution Authorization (A11, A12, A13)
1. Confirmation gating: `agents.delegate_external` and `telegram.send_message` require confirmation.
2. Command safety: Remove `shell=True`. Never accept raw `command` strings from LLM input data; resolve only registered adapters.
3. MCP gating: Route calls by registered server ID only.
4. Authority binding: Bind authority to step action and arguments digest (`args_digest`). Enforce expiration and idempotent step execution.
5. Proactive accept: Proactive suggestions create proposals for mutations; never set APPLIED on execution failure.

### MP4 — Real Connectors & Integrations
1. Capability matrix on `BaseConnector`: `can_read`, `can_write`, `can_sync`.
2. Connectors verify against real endpoints; return truthful status.
3. Notion, Slack, Google Calendar: Genuine API calls or explicit `unsupported` status.
4. Concurrency lock on token refresh.
5. Disconnect revokes tokens and purges credentials.

### MP5 — Runtime, Persistence & Recovery
1. Workspace registry: Disambiguate by ID and root path.
2. SQLite unification: Route all store connections through `core/sqlite.py` with WAL and timeout.
3. Idempotency ledger for actions (`proposal_id` + step + digest).
4. Non-blocking async retry in automation engine.
5. Crash recovery: Mark interrupted executions as `FAILED/interrupted`.

### MP6 — Agents, Workforce & Planning
1. Truthful mission lifecycle: Mission fails if milestone fails or reviewer rejects.
2. Real planner and team delegation pipeline.
3. Intent classification: Use LLM tier classification when available; prompt for provider if absent.
4. Ollama delegation verification: Run live native streamed delegation against active local Ollama instance.

### MP7 — UI / Backend Truthfulness
1. Eliminate silent `catch {}` in UI pages (`Missions`, `Knowledge`, `AgentBuilder`, `AutoArchitect`, `Content`).
2. Display authentic execution and connection states.
3. Surface clear onboarding error when no provider is configured.
4. Build UI assets and verify frontend compile.

### MP8 — Scale & Readiness Blockers (A21, A22)
1. Offload sync blocking operations in routes via `asyncio.to_thread`.
2. Circuit breaker and timeouts for provider calls.
3. Remove dev server auto-spawn from production CLI.
4. Clean up root directory stray files (`patch_*.py`, `test_ollama_*.py`, `scratch/`, `sqlite:/`).
5. Document architectural constraints in documentation.

### MP9 — Final Verification
1. Focused test batches across all subsystems.
2. Live Ollama delegation verification.
3. End-to-end user journey validation (install → configure → prompt → proposal → accept → execute → restart).
4. Full test suite execution and final status reporting.

---

## 5. Definition of Done
The stabilization is complete only when:
1. No confirmed fake production behavior remains.
2. No execution authorization bypass remains.
3. Authorization is persistent, scoped, and argument-bound.
4. Real connectors work or are explicitly marked unsupported.
5. Provider failures are truthful (no fake COMPLETED or canned synthesis).
6. Filesystem and network security boundaries are enforced.
7. Missions, workforce, and autonomy execute genuine pipelines.
8. Async execution, retry, and recovery are truthful and crash-safe.
9. UI states strictly match backend reality.
10. Focused verification batches and full repository verification pass.
