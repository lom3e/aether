# Aether Actions and Connections Architecture (Phase C)

## 1. Overview & Core Contracts

The Action and Connection layers bridge Aether from an analytical conversational model to an **operational execution engine** capable of mutating workspace state, interacting with external tools, and triggering multi-agent delegations safely.

---

## 2. The Action Tri-Tier Hierarchy

Every action capability in Aether is classified under an explicit `ActionTier`:

| Action Tier | Scope & Behavior | Permission Level | Confirmation Required | Example Capabilities |
|---|---|---|---|---|
| **ANSWER** | Read-only lookup & analytics | `READ_ONLY` | No | `calendar.list_events`, `files.read_document`, `web.search` |
| **DO** | Safe, reversible local mutation | `LOCAL_MUTATION` | No | `files.create_document`, local note saving |
| **ACT** | External mutation & sensitive tasks | `EXTERNAL_MUTATION` | **Yes (Enforced)** | `calendar.create_event`, email send, remote repo commits |

### Safety Gate Contract
- Any action with `requires_confirmation = True` or tier `ActionTier.ACT` enters `ActionExecutionStatus.PENDING_APPROVAL`.
- The execution is saved in SQLite (`data/actions.db`) and an approval request is broadcasted to the user via the Personal Companion card and Activity feed.
- Execution only runs when the user invokes `POST /api/actions/executions/{id}/approve`.
- If the user declines (`POST /api/actions/executions/{id}/reject`), the execution is marked `REJECTED` and audited.

---

## 3. Connections & First-Party Integrations

The `Connection` layer manages tool auth states, capabilities, and persistent entities:
- **Calendar Connector**: Provides bidirectional calendar event management. Events created through `calendar.create_event` or the UI are persisted in `data/connections.db` and queryable via `/api/connections/calendar/events`.
- **Extensible Provider Model**: Supports GitHub, Email / Gmail, Slack, and Notion integrations with clean capability discovery.

---

## 4. Activity Subsystem & Human-Readable Audit Trail

All operations across Work, Actions, Workforce, and Connections are recorded in plain language via `ActivityService` (`data/activity.db`):
- Plain-language titles and summaries instead of low-level JSON dumps.
- Category partitioning (`work`, `action`, `workforce`, `connection`, `system`).
- Real-time visibility in the **Activity Feed** hub (`/activity`).
