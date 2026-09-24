# Aether Actions and Connections Architecture

## 1. Executive Summary & Vision

Aether unites autonomous AI workforces, a Personal Companion agent, and mission-driven cognitive loops into an **operational AI system**.
To ensure AI agents have real-world utility without unconstrained risk, the **Actions & Connections Architecture** bridges conversational intelligence to real external systems with:
1. **Zero Simulation Guarantee**: Absolute elimination of fake IDs, mocked responses, or simulated fallback completions when performing external tasks. If an external service is not configured or unavailable, execution fails truthfully.
2. **Unified Execution Engine**: All user surfaces (Companion chat, UI action controls, mission milestones, CLI) route through the canonical `Runtime` and `ActionExecutor`.
3. **Deterministic Safety Gating**: Strict permission classification enforcing human-in-the-loop approvals for external and sensitive mutations.
4. **Secret Hygiene**: Comprehensive credential masking preventing leakage into UI, SQLite databases, logs, activities, and serialized payloads.

---

## 2. BaseConnector Lifecycle & Provider Contract

All external integrations inherit from [`BaseConnector`](file:///Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/connections/base.py), located in `src/aether/connections/base.py`.

```
                    ┌────────────────────────┐
                    │      BaseConnector     │
                    │  (Abstract Lifecycle)  │
                    └───────────┬────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────▼────────┐      ┌───────▼────────┐      ┌───────▼────────┐
│ GitHubConnector│      │ EmailConnector │      │ SlackConnector │
│  (REST API v3) │      │ (SMTP/TLS/SSL) │      │ (Chat Web API) │
└────────────────┘      └────────────────┘      └────────────────┘
                                │
                        ┌───────▼────────┐
                        │ HttpConnector  │
                        │ (Generic REST) │
                        └────────────────┘
```

### 2.1 Connector Contract Elements
- **`ConnectorResult`**: Standardized execution outcome containing `success`, `operation`, `provider`, `data`, `error`, `status_code`, and execution `latency_ms`.
- **`ConnectorHealth`**: Health status probe reporting connectivity, latency, status (`healthy`, `degraded`, `unhealthy`), and diagnostic messages.
- **`CredentialRequirement`**: Declarative credential specification (`key`, `display_name`, `secret`, `required`, `description`) used by the UI to render dynamic configuration modals.
- **`ConnectorError` Taxonomy**: Structured exceptions including `AuthenticationError`, `RateLimitError`, `ResourceNotFoundError`, `ConnectionTimeoutError`, and `ConfigurationError`.

---

## 3. Implemented Real Connectors

### 3.1 GitHub Connector (`GitHubConnector`)
- **Transport**: Real HTTP requests against `https://api.github.com` via `urllib.request`.
- **Authentication**: `Bearer <token>` / `token <pat>` personal access tokens.
- **Operations Supported**:
  - `github.inspect_repo`: Fetches repository metadata, visibility, default branch, stars, and open issues.
  - `github.list_branches`: Lists active branches in the repository.
  - `github.get_branch` & `github.create_branch`: Verifies SHA commitments and creates lightweight branch refs.
  - `github.list_pull_requests` & `github.get_pull_request`: Queries open/closed pull requests with labels and assignees.
  - `github.create_pull_request`: Opens real PRs with target base and head branches.
  - `github.list_issues` & `github.get_issue`: Retrieves issues filtered by state (`open`, `closed`, `all`).
  - `github.create_issue`: Creates GitHub issues with titles, markdown descriptions, labels, and assignees.
  - `github.update_issue`: Updates issue state, title, and body.
  - `github.add_comment`: Appends comments to existing issues or pull requests.
  - `github.get_file`: Reads repository files via raw contents API.
- **Truthful Error Handling**: 401 Unauthorized, 404 Not Found, and 403 Rate Limit errors are surfaced truthfully with actionable descriptions; no simulated issue numbers or fake PR links are ever generated.

### 3.2 Email Connector (`EmailConnector`)
- **Transport**: Standard SMTP client using Python's `smtplib` (`SMTP` with `starttls()` or `SMTP_SSL`).
- **Authentication**: SMTP username and password / app-specific password.
- **Operations Supported**:
  - `email.send`: Formats MIME text and HTML messages, validates recipient email syntax, establishes secure connection, and delivers message to target mail transfer agents.
  - `email.verify`: Validates SMTP handshake and credential validity without sending message.
- **Truthful Error Handling**: Network drops, SMTP auth errors (`SMTPAuthenticationError`), and recipient syntax errors fail explicitly.

### 3.3 Slack Connector (`SlackConnector`)
- **Transport**: Real Slack Web API calls (`https://slack.com/api/chat.postMessage`, `auth.test`).
- **Authentication**: Bot User OAuth Token (`xoxb-...`) with Bearer authorization.
- **Operations Supported**:
  - `slack.send_message`: Posts messages to public channels, private channels, or user IDs.
  - `slack.verify`: Validates bot credentials via `auth.test`.
- **Truthful Error Handling**: Invalid tokens or `channel_not_found` errors are reported verbatim from Slack's response payload.

### 3.4 Generic HTTP Connector (`HttpConnector`)
- **Transport**: Dynamic HTTP client supporting arbitrary REST endpoints.
- **Authentication Types**:
  - `none`: Unauthenticated public APIs.
  - `bearer`: Header `Authorization: Bearer <token>`.
  - `api_key`: Custom header (e.g. `X-API-Key: <key>`) or query parameter (`?api_key=<key>`).
  - `basic`: HTTP Basic authentication (`Authorization: Basic <base64>`).
- **Operations Supported**:
  - `http.request`: Universal request dispatcher (`method`, `path`, `query`, `headers`, `body`, `timeout`).
  - `http.get`, `http.post`, `http.put`, `http.patch`, `http.delete`: Convenience verbs.

---

## 4. Dynamic OpenAPI 3.x Tool & Action Generation

The [`OpenAPIToolGenerator`](file:///Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/connections/openapi.py) (`src/aether/connections/openapi.py`) converts arbitrary OpenAPI 3.0/3.1 specifications into first-class Aether tools and registered actions:

1. **Spec Ingestion**: Accepts raw JSON/YAML strings, Python dictionaries, or file paths.
2. **Operation Parsing**: Iterates over all OpenAPI `paths` and HTTP methods, resolving `operationId`, summary, tags, parameters, and request bodies.
3. **Permission Classification**:
   - `GET` / `HEAD` / `OPTIONS` $\rightarrow$ `ActionPermissionLevel.READ_ONLY` (`requires_confirmation=False`).
   - `POST` / `PUT` / `PATCH` / `DELETE` $\rightarrow$ `ActionPermissionLevel.EXTERNAL_MUTATION` (`requires_confirmation=True`).
4. **Tool Registration**: Registers executable callable tools into `ToolRegistry`, validating path parameters, query parameters, header parameters, and JSON payloads at invocation time.
5. **Action Registry Ingestion**: Exposes operations under the `openapi.<operation_id>` action namespace so they appear in UI action management, approval queues, and activity feeds.

---

## 5. Permission Hierarchy & Safety Policy

Every action defined in the system has an explicit [`ActionPermissionLevel`](file:///Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/actions/models.py):

| Permission Level | Description | Confirmation Required | Auto-Approvable by Policy |
|---|---|---|---|
| `READ_ONLY` | Pure information retrieval with zero side-effects. | No | Yes |
| `LOCAL_MUTATION` | Modifies workspace-local resources (e.g., creating documents). | No (configurable) | Yes |
| `EXTERNAL_MUTATION` | Changes state on remote services (e.g., GitHub issues, Slack messages, emails, HTTP POST). | **Yes (Default)** | **No (Blocked by Safety Policy)** |
| `SENSITIVE_MUTATION` | Critical operations (deletions, credential updates, financial transactions). | **Yes (Strict)** | **No (Blocked by Safety Policy)** |

### Safety Policy Invariants
The [`ActionSafetyPolicy`](file:///Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/actions/executor.py) prevents accidental or malicious bypass:
- If an action requires confirmation or has permission level `EXTERNAL_MUTATION` or `SENSITIVE_MUTATION`, the policy **refuses auto-approval** even if the caller passes `auto_approve=True`.
- The execution transitions to `PENDING_APPROVAL`, is persisted to `data/actions.db`, and an approval notification card is posted to the user's Home cockpit and Activity log.
- Only an explicit user approval (`POST /api/actions/executions/{id}/approve`) transitions the action to `APPROVED` and triggers execution.
- If rejected (`POST /api/actions/executions/{id}/reject`), the execution is marked `REJECTED` and no network calls are dispatched.

---

## 6. Secret Hygiene & Masking Invariants

All authentication credentials (passwords, tokens, API keys, secrets) are protected across the entire data lifecycle:

1. **Storage Isolation**: Stored securely in `ConnectionStore` (`data/connections.db`).
2. **Display Masking**: The `mask_secret_value()` utility masks tokens using prefix/suffix hints (e.g., `ghp_1234567890abcdef1234567890` becomes `ghp...890`). Short secrets are completely masked as `••••••••`.
3. **Recursive Sanitization**: When executions, activities, or connections are serialized for API responses or UI display, `sanitize_payload()` recursively scrubs dictionaries and lists, masking any key matching `token`, `key`, `secret`, `password`, `authorization`, `cred`, or `auth`.
4. **Error Message Scrubbing**: Any exception message caught during connector dispatch is scrubbed before being recorded in `ActionExecution.error_message`.

---

## 7. Companion & Workforce Integration

The Personal Companion chat and multi-agent workforce platforms share the **identical execution engine**:
- When the user asks the Companion: *"Send an email to team@company.com with the sprint summary"*, intent classification parses the request into `ActionTier.ACT`.
- An `ActionExecution` record is created for `email.send` in `PENDING_APPROVAL` status.
- The Companion presents a structured pending approval card displaying the recipient, subject, preview body, and provider.
- Upon clicking **Approve**, the canonical `ActionExecutor` dispatches the real `EmailConnector`, executes the SMTP transaction, and logs the human-readable result to the Activity feed.
- Upon clicking **Reject**, execution is halted without side effects.
